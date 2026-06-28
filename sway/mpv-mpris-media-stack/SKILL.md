---
name: mpv-mpris-media-stack
description: mpv 0.40 + mpv-mpris 0.7 + bash dispatcher 的架构蓝图与 pitfall 清单（mpv+mpris 级，不含 NCM 应用细节和 sway/waybar 通用配置）
version: 1.1.0
metadata:
  hermes:
    tags: [sway, waybar, mpv, mpris, streaming, wayland]
    related_skills: ["mpv-waybar-control", "sway-music-client", "sway-daemon-persistence", "waybar-config", "ncm-state-daemon"]
---

# Lightweight Streaming Media on Sway + Waybar

## When to invoke

Use this when the user wants to:

- Listen to streaming music (or podcasts / radio) inside their existing Sway + Waybar stack.
- Reach the **lowest possible system footprint** — only `mpv` runs in the background.
- Control playback with the **mouse** via Waybar buttons (no keybinds).
- Offload encryption / login / URL signing to a remote API service (api-enhanced, similar), keeping the local stack thin.

Do NOT use when:
- The user wants a full GUI client (Electron / GTK / Qt) — recommend `gmg137/netease-cloud-music-gtk` or similar instead.
- The user is on macOS / Windows — this skill is Linux + Wayland specific.
- The user wants offline playback of local files — just use plain `mpv` without any of this machinery.

## Architecture (the canonical pattern)

```text
┌──────────────────┐
│  waybar          │  reads every 3s
│  mpris module    │ ←── mpv-mpris D-Bus ←── mpv (ncm-cli manages)
│  custom modules  │  click → ncm-player dispatcher → ncm-cli
└──────────────────┘
         │
         ▼ (on-click)
┌──────────────────────────────────────────────────────┐
│  ncm-player (bash dispatcher + daemon)               │
│  ├── status-button / play-button / like-button       │  ← waybar exec
│  ├── toggle / next / prev → ncm-cli                  │  ← playback control
│  ├── fm (心动模式) → ncm-cli recommend heartbeat     │
│  ├── pl (歌单) → ncm-cli playlist → fuzzel picker    │
│  └── daemon → systemd service → writes state file    │
└──────────────────────────────────────────────────────┘
```

> **后端选型**:
> - **Old (removed)**: `ncm.lua` inside mpv → HTTP calls to `api-enhanced` (serverhome:3000). Maintenance burden: two codebases, sync state between lua + bash, login cookies in file.
> - **Current**: `ncm-cli` (npm v0.1.6) unifies playback + search + recommend + playlist + like/login in one CLI. Zero Lua, zero Python HTTP helpers, one codebase.
> - **Login**: ncm-cli QR code (`ncm-cli login --background`), no Playwright, no external browser.
> - **Architecture note**: `ncm-go` (Go binary) was tried and abandoned — requires Playwright Chromium install (user rejected). All its commands (search, playlist, song metadata) are already in ncm-cli after login.

**Current layer responsibilities (after 2026-06-23 rewrite):**

| Layer | Tool | Lives in |
|-------|------|----------|
| Playback control | `ncm-cli play / pause / resume / next / prev / volume` | systemd-managed mpv |
| Data API (search, playlist, recommend, like) | `ncm-cli search / playlist / recommend / song` | spawned per-command |
| Waybar dispatcher + state daemon | `ncm-player` (bash) | `~/.local/bin/ncm` (symlink) |
| D-Bus MPRIS for waybar display | mpv-mpris (`mpris.so`) | loaded globally via `/etc/mpv/scripts/` |
| Daemon lifecycle | `ncm-state-daemon.service` | `~/.config/systemd/user/` |

**Why this shape:**
- **mpv is the only always-on process** (~15-30 MB). No extra daemon.
- **All HTTP lives inside Lua** (mpv's context). The bash dispatcher is a thin IPC shim, so clicks feel instant.
- **waybar-mpris** auto-discovers mpv and shows title/artist. waybar can't do dropdowns, so each action (like, fm, login) is its own `custom/*` module button.

## Steps

1. **Install deps**: `apt install mpv playerctl mpv-mpris`（mpv-mpris 是 Debian 单独包，不在 mpv 里）。
2. **Write `~/.config/mpv/mpv.conf`** — `--idle=yes --no-video --no-terminal --quiet --input-ipc-server=/tmp/<svc>-mpv.sock`。Add `--script-opts=osc-visibility=never` if you want no OSD.
3. **Write `~/.config/mpv/scripts/<svc>.lua`** — register IPC handlers for each command. Use `mp.command_native({name="subprocess", playback_only="no", ...})` for HTTP. Use `mp.commandv("set", "force-media-title", title)` for labels. 完整骨架见 `ncm-state-daemon/templates/ncm-lua-script.lua`。
4. **Write `~/.local/bin/<svc>`** — thin bash dispatcher: each subcommand sends an IPC `script-message` via Python's `socket` module (no `socat` needed). 完整骨架见 `ncm-state-daemon/templates/ncm-dispatcher.sh`。Plus waybar helpers (`<svc> status-button`, `<svc> like-button`, `<svc> play-button`)。
5. **Sway** — sway config 加 `exec_always` 启动 mpv（pkill 陷阱、SWAYSOCK、foot 浮窗规则都在 sway-daemon-persistence 已有完整模板，本 skill 不重复）。
6. **Waybar** — add N `custom/<svc>-*` modules (one per clickable action) plus the `mpris` module bound to `mpv`. Wire each module's `on-click` to the dispatcher. Wire `<svc> play/like/status-button` outputs to dynamic `exec` fields with `interval` polling.

## Pitfalls (READ THESE FIRST — they cost turns if missed)

### mpv 0.40 specifics

1. **`utils.format_url` does NOT exist** in mpv 0.40. Only `parse_json` and `format_json` are exposed. Hand-roll URL encoding:
   ```lua
   local function url_encode(s)
       return (s:gsub("[^%w%-_~.]", function(c)
           return string.format("%%%02X", string.byte(c))
       end))
   end
   ```

2. **`utils.subprocess` ignores `playback_only=false`**. The mpv `subprocess` command defaults to `playback_only=true`, which kills the subprocess immediately when mpv is in `idle`. To run a subprocess during idle (e.g. fetching a streaming URL before play), bypass the wrapper and call `mp.command_native` directly:
   ```lua
   local r = mp.command_native({
       name = "subprocess",
       args = {"curl", "-sSL", url},
       capture_stdout = true,
       playback_only = "no",     -- string "no", NOT boolean false
   })
   ```

3. **`mp.command("set force-media-title <text>")` does NOT work** — the string-command form fails silently and mpv falls back to deriving title from the URL. Use the 3-element array form:
   ```lua
   mp.commandv("set", "force-media-title", media_title)
   ```

4. **Debian mpv package does not include `mpris.lua`**. Install `apt install mpv-mpris` separately. It drops `/etc/mpv/scripts/mpris.so` which mpv auto-loads.

5. **mpv 0.40 hot-loads new script files** when you save changes — but only for files in `~/.config/mpv/scripts/`. The standard `Lua 5.2` is bundled; no extra packages needed.

### waybar / MPRIS specifics

> 通用 waybar 模块行为 pitfalls（#6 waybar-mpris 只读 / #7 format-icons 占位 / #8 config-top 拆分 / #9 ignored-players / #10 tooltip JSON 转义 / #28 空 exec 占位）已全部在 `waybar-config` 技能"Pitfalls"节。本 skill 不重复。

### Sway specifics

12. **mpv logs go to stderr by default.** Add `--log-file=/tmp/<svc>-mpv.log` when debugging; without it you see nothing.

### Architecture pitfall

13. **Do NOT put HTTP in the bash dispatcher.** The dispatcher should be a ~3KB IPC shim. HTTP belongs in Lua (inside mpv). Reason: HTTP is blocking; if it lives in the bash dispatcher the click feels laggy and IPC ordering becomes flaky.

14. **Do NOT iterate trial variants of an unknown API.** When `playback_only=false` doesn't work, your first move should be `curl https://raw.githubusercontent.com/mpv-player/mpv/master/DOCS/man/input.rst | grep -A30 'subprocess'` — NOT `playback_only="no"`. See `systematic-debugging` skill: "Search Before You Iterate".

> Pitfalls #15 (SWAYSOCK inheritance) 和 #17 (foot --float flag) 已在 `sway-daemon-persistence` 技能"外部组件启动模式"节有完整诊断 + 修复模板。本 skill 不重复。

> PUA codepoint escape（#16）和 modules overflow（#19）已在 `waybar-config` 技能"Pitfalls"节。本 skill 不重复。

> NetEase 登录流程的 3 个 pitfall（#18 NMTID cookie 误判 / #23 api-enhanced body cookie / #24 qrencode vs chafa）已在 `ncm-state-daemon` 技能"登录流程坑点"节。本 skill 不重复。

### Sway / Wayland edge cases

> waybar modules overflow（#19）已在 `waybar-config` 技能"Pitfalls"节。本 skill 不重复。

> Pitfall #20 (sway i3 IPC 协议) 已在 `sway-daemon-persistence` 技能"sway IPC 编程"节有完整说明 + Python 示例代码。本 skill 不重复。

21. **mpv-mpris 0.7 does NOT auto-split "Artist - Title" from `media-title`.** The mpv-mpris 0.7.1 source (`/usr/lib/mpv-mpris/mpris.so`) reads `xesam:title` from `media-title` directly, and reads `xesam:artist` ONLY from `metadata/by-key/uploader` (YouTube) or `metadata/by-key/Artist` (ID3 tag on local files). When playing a **streaming URL** (api-enhanced signed URL, no ID3), `xesam:artist` is empty. A waybar mpris template like `"{title} - {artist}"` then renders the fallback `"mpv-playing"`. **Fix**: pack the full "Artist - Title" into the `force-media-title` string, and use template `" {title}"` (single field). Verified by reading the mpv-mpris 0.7.1 C source — `mpris.c` `create_metadata()` lines 357-366, where the artist key only reads from `metadata/by-key/Artist` and there's no split logic on the media-title.

**Corollary**: `mp.set_property("artist", ...)` and `mp.commandv("set", "artist", ...)` do NOT exist in mpv — there is no `artist` property. These calls silently no-op. The only way to populate `xesam:artist` in mpv-mpris for streaming content (no ID3 tags) is via `metadata/by-key/Artist` from an mp3 container, which stream URLs never have. Therefore the force-media-title + `{title}` waybar template approach is the only viable path. Do NOT waste turns trying to set an `artist` property — it does not exist.

For reference: the mpv-mpris 0.7.1 package source is at `https://salsa.debian.org/multimedia-team/mpv-mpris`.

> Pitfall #22 (`sway exec_always` 多行 break) 已在 `sway-daemon-persistence` 技能"外部组件启动模式 → SWAYSOCK stale env"末段有完整解法。本 skill 不重复。

> Pitfall #23 (api-enhanced body cookie) 已在 `ncm-state-daemon` 技能"登录流程坑点"节标注为已归档 API 历史参考。本 skill 不重复。

> Pitfall #24 (qrencode vs chafa) 已在 `ncm-state-daemon` 技能"登录流程坑点"节。本 skill 不重复。

25. **`loadfile` with mode `replace-play` silently fails — must be `replace` or `append-play`.** mpv does NOT accept `replace-play` as a `loadfile` mode. The command appears to succeed (no error) but mpv stays in idle — `playerctl status` returns `Stopped`. **Fix**: use `replace` for single-song replace, `append-play` for queue-and-play:
    ```lua
    mp.commandv("loadfile", url, "replace")           -- correct: replace and play
    mp.commandv("loadfile", url, "append-play")        -- correct: append and play
    -- WRONG: mp.commandv("loadfile", url, "replace-play")  -- silently no-ops
    ```

26. **mpv idle → playing transition does NOT trigger `pause` PROPERTY_CHANGE, so mpv-mpris 0.7 stays "Stopped".** This is the #1 reason waybar shows "mpv-playing" even when mpv is audibly playing. Root cause: when mpv is `--idle=yes`, `pause=false` is the default — it never changes. `loadfile` into idle mpv fires `MPV_EVENT_IDLE` → `set_stopped_status()` → D-Bus "Stopped". But `pause` stays `false`, so no `MPV_EVENT_PROPERTY_CHANGE("pause")` fires, `handle_property_change()` is never called, `ud->status` stays `STATUS_STOPPED`. The `playback-restart` event fires but it only emits Seeked, not PlaybackStatus. **Fix**: explicitly toggle `pause=yes→no` after loadfile with separate timeouts to force the double event:
    ```lua
    mp.commandv("loadfile", url, "replace")
    mp.add_timeout(0.5, function()
        mp.commandv("set", "pause", "yes")    -- triggers PROPERTY_CHANGE
    end)
    mp.add_timeout(0.6, function()
        mp.commandv("set", "pause", "no")     -- triggers PROPERTY_CHANGE → Playing
    end)
    ```
    The 0.5s delay ensures `file-loaded` already fired. Two separate timeouts ensure the `0→1→0` transition is visible.

27. **Waybar mpris `update()` interval rate-limit blocks "Playing" status after "Stopped" callback.** Even after fixing the mpv-mpris "Stopped" bug (#26), waybar may still show "mpv-playing". Root cause in waybar-mpris.cpp lines 688-701:
    ```cpp
    auto Mpris::update() -> void {
      const auto now = std::chrono::system_clock::now();
      if (now - last_update_ < interval_) return;  // rate-limit
      last_update_ = now;                           // SET BEFORE the Stopped check
      auto info = getPlayerInfo();
      if (info.status == PLAYERCTL_PLAYBACK_STATUS_STOPPED) {
        spdlog::debug("mpris[{}]: player stopped, skipping update", info.name);
        return;  // early return BUT last_update_ already ticked
      }
    ```
    The Stopped callback sets `last_update_` and returns early. The Playing callback fires 100ms later (mpv-mpris timer) → now `now - last_update_ < interval_` ← true with default 5s interval → returns immediately → widget never updates. **Fix**: set `"interval": 0` + `"format-stopped": " {}"` in waybar mpris config:
    ```json
    "mpris": { "player": "mpv", "interval": 0, "format-stopped": " {}", "format": " {}" }
    ```
    The interval=0 disables the rate-limit entirely so every signal triggers a widget update. The format-stopped makes the title visible even during the brief "Stopped" window between loadfile and actual playback.

29. **2026-06-24 实证：`format-stopped` workaround 无效，必须用 `custom/ncm-nowplaying` 替换 mpris**。上一条 pitfall #27 中建议的 `format-stopped` workaround 经调试证实不起作用：waybar 在收到 `PLAYERCTL_PLAYBACK_STATUS_STOPPED` 状态时直接 `skip update`（return 不调用 widget 更新），`format-stopped` 只影响渲染，但 `skip update` 不进入渲染流程。实测证据：waybar debug log 显示 `mpris[mpv]: player stopped, skipping update`，即使 `format-stopped` 已设为与 `format` 相同的模板。**唯一可靠方案**：用 `custom/ncm-nowplaying` 自定义模块替换 waybar 内置 mpris 模块，直接从 state.json 读当前歌曲信息，完全绕过 mpv-mpris D-Bus。配置示例见 `waybar-config` 技能"mpv-mpris 0.7.x PlaybackStatus always Stopped bug — 终极修复"节。这也意味着**本 skill 中的 mpris 集成部分当前被 workaround 取代**——除非 mpv-mpris 源码修复了 PlaybackStatus 的更新逻辑。

> waybar custom modules with `exec` returning empty text（#28）已在 `waybar-config` 技能"Pitfalls → custom 模块空 exec 仍占位"节。本 skill 不重复。

## Verification

After setup, run this smoke test (replace `<svc>` with the actual command name):

```bash
<svc> fm                                    # should trigger mpv playback
playerctl -l | grep mpv                     # mpv should appear in MPRIS list
playerctl -p mpv metadata --format '{{ artist }} - {{ title }}'   # should print "歌手 - 歌名"
<svc> toggle                                # should toggle play/pause
playerctl -p mpv status                     # should alternate Playing/Paused
```

If metadata shows URL fragments instead of the song name, `set force-media-title` is not being honored — re-check pitfall #3.

If mpv disappears from `playerctl -l` immediately after `fm`, the subprocess was killed — re-check pitfall #2.

## Reference

- `references/mpv-0.40-pitfalls.md` — exact error transcripts and reproductions for each mpv 0.40 gotcha.
- `references/mpv-mpris-0.7-source-notes.md` — what mpv-mpris 0.7 actually exposes from the C source (so you don't re-read the C code to debug "mpv-playing" / empty artist).
|- `references/waybar-integration-pitfalls.md` — ~~已合并到 `sway/waybar-config` 技能"Pitfalls"节。本文件已删除。~~
- `references/shared-pitfalls.md` — pitfalls shared across `mpv-waybar-control` and `sway-music-client` (consolidated here). Edit when a pitfall applies to >1 sway music skill.
- ~~`references/api-enhanced-cookie-quirks.md` — 已归档到 `local_share/.archive/legacy-api-enhanced/`（已废弃外部 HTTP 后端）~~
- `templates/mpv.conf` — sample mpv startup config.
- `ncm-state-daemon/templates/ncm-lua-script.lua` — skeleton Lua script (HTTP + IPC + state).
- `ncm-state-daemon/templates/ncm-dispatcher.sh` — sample bash dispatcher.
- `waybar-config/templates/waybar-modules-snippet.jsonc` — waybar custom-module pattern.