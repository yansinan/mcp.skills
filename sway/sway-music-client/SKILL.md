---
name: sway-music-client
description: "Minimal-resource music playback on Sway/Wayland — thin CLI + mpv + waybar-mpris + playerctl. Architecture pattern for streaming-service backends."
tags: [sway, waybar, mpv, mpris, music, wayland]
---

# Minimal Music Client on Sway

## When to use this skill

Trigger when ANY of:
- User is on Sway/Wayland, wants to play music with **minimal RAM/CPU**
- Mentions mpv, playerctl, waybar-mpris, MPRIS, IPC socket
- Evaluating or reviving an **abandoned TUI music player** (e.g. betta-cyber/netease-music-tui, MEMLTS/MuseTUI) — this skill tells you NOT to fork it, and what to build instead
- Wants Netease Cloud Music / similar streaming on Linux without the official Electron client

## The decision: thin CLI + mpv (NOT a TUI fork)

A TUI music player looks lightweight but is the wrong tool for "minimal Sway music" because:

| | TUI fork (betta-cyber, MuseTUI) | Thin CLI + mpv (this pattern) |
|---|---|---|
| Players | Bundled (gstreamer/songbird) | System mpv ~30MB |
| Backend API | Self-implements weapi encryption | Calls public/hosted API endpoint |
| Maintenance | You maintain it forever when encryption changes | API server (api-enhanced) is maintained by community |
| Waybar integration | Need custom module | Native `mpris` module auto-discovers mpv |
| Sway keybind | Replace existing binds | Free to bind shell commands |
| Memory at idle | TUI runtime + embedded player | Just mpv ~30MB |

**The TUI only adds value when you need a selection UI**. For everything else (play/pause/skip/like), `playerctl` does it. So: **CLI for selection (fzf + curl), mpv for playback, waybar-mpris for display, playerctl for control**.

## Architecture (verified working pattern)

```
┌─────────────────────────────────────────────────────────────┐
│  Thin CLI control script (Python/Bash, ~200 lines)          │
│  - ncm search → fzf pick → API call → mpv IPC command       │
│  - ncm login → QR code → cookie file                        │
│  - ncm like / playlist / fm → API call                      │
└──────────────┬──────────────────────────────────────────────┘
               │ HTTPS
               ▼
┌─────────────────────────────────────────────────────────────┐
│  Backend API (one of)                                       │
│  - Public hosted: Vercel api-enhanced (Netease only)        │
│  - Self-host: Node.js api-enhanced in Docker (~80MB)        │
│  - Self-host on serverhome: 0 bytes on x1tablet             │
└─────────────────────────────────────────────────────────────┘

  ┌─────────┐   IPC socket    ┌────────────────────┐
  │  mpv    │ ◄─────────────► │  systemd --user    │
  │ ~30MB   │  /tmp/ncm-mpv   │  mpv-music.service │
  └────┬────┘     .sock       │  (--idle)          │
       │ MPRIS D-Bus          └────────────────────┘
       ▼
  ┌──────────┐
  │ waybar   │  native "mpris" module auto-displays
  │ playerctl│  sway keybinds control
  └──────────┘
```

## mpv setup (the foundation)

**Critical**: mpv must be launched with both `--idle` AND `--input-ipc-server` for this to work:

```bash
mpv --idle=yes \
    --no-video \
    --save-position-on-quit=no \
    --input-ipc-server=/tmp/ncm-mpv.sock
```

- `--idle=yes` keeps mpv alive after queue empties (essential for playerctl/waybar to keep showing the player)
- `--input-ipc-server=/tmp/ncm-mpv.sock` exposes a JSON-RPC socket for the CLI script
- `--no-video` because music-only
- Run via systemd `--user` so it survives Sway reload (see `sway-daemon-persistence` skill)

**Why these matter**: Without `--idle`, mpv exits between songs and `playerctl -l` returns nothing — waybar-mpris goes blank, keybinds do nothing.

## Thin CLI control script skeleton

One Python file, stdlib only (`urllib.request`, `json`, `os`, `subprocess`). Subcommand dispatch:

- `ncm search <kw>` → `GET /search?keywords=...` → pipe to `fzf --prompt="🎵 "` → output selected song id → `play <id>`
- `ncm play <id>` → `GET /song/url/v1?id=...&level=standard` → extract mp3 URL → `mpv --replace <mp3url>` (via IPC)
- `ncm fm` → `GET /personal_fm` (requires login) → loop calling `play` with each result
- `ncm like <id>` → `GET /like?id=...&like=true` (requires login)
- `ncm playlist` → `GET /user/playlist` (requires login) → fzf → `GET /playlist/detail?id=...` → fzf → `play`
- `ncm status` → read `mpv` IPC socket for current track
- `ncm login` → QR flow (see below)
- `ncm toggle / next / prev` → `playerctl play-pause / next / previous`

Cookie stored at `~/.local/share/ncmctl/cookie` after QR login. All API calls pass `Cookie: MUSIC_U=...; MUSIC_A=...` header when cookie exists.

## Sway / waybar integration (verified pattern, mouse-only)

The user has explicitly rejected sway keybinds for media control ("太多快捷键根本记不住"). All playback control goes through waybar on-click buttons. The waybar layout follows a macOS-style grouping:

```text
modules-left:   [PWA shortcuts + 登录/FM/歌单]    (or sway/window + sway/workspaces + ncm 入口 on narrow screens)
modules-center: [sway/window + sway/workspaces]
modules-right:  [mpris 歌名 | ncm-prev | ncm-like | ncm-play | ncm-next | 系统状态… | tray | clock]
```

Core mpv/mpris/sway issues maintained in `mpv-mpris-media-stack/references/shared-pitfalls.md`;
waybar-specific pitfalls in `sway/waybar-config` 技能的"Pitfalls"节。
verified waybar button-group pattern (Pitfall W1: absolute paths; Pitfall
W2: don't use single-space format; Pitfall W6: SWAYSOCK inheritance).

There IS a global quick-toggle that the user keeps regardless of keybind
aversion: `$mod+space → playerctl play-pause` (set in their sway config).
This is the only sway keybind in the music flow; everything else is mouse.

## Waybar player module performance optimization

When the streaming backend is **ncm-cli (npm)**, each call has ~365ms Node.js startup overhead. Multiple waybar modules polling independently can waste significant CPU (~150k ncm-cli calls/day before optimization). Apply these patterns:

### Login caching (eliminate repeated `login --check` calls)

```bash
# In the bash dispatcher script:
LOGIN_CACHE="$STATE_DIR/.login_cache"

cached_login() {
  [ -f "$LOGIN_CACHE" ] && [ $(( $(date +%s) - $(stat -c %Y "$LOGIN_CACHE") )) -lt 60 ]
}

check_login() {
  if cached_login; then
    return 0
  fi
  # Only call ncm-cli when cache is stale or missing
  if $NCM_CLI login --check 2>&1 | grep -q '"success": true'; then
    touch "$LOGIN_CACHE"
    return 0
  else
    rm -f "$LOGIN_CACHE"
    return 1
  fi
}
```

On successful login (after `login` case completes), also `touch "$LOGIN_CACHE"`.

**Effect**: ~99% of login checks resolve locally (zero API call, zero Node.js startup). ~34,000 calls/day → virtual zero.

### Waybar module interval tuning

| Module type | Concern | Recommended interval |
|---|---|---|
| Play/pause toggle | Must be responsive to user clicks. D-Bus event-driven is ideal but if polling is required | 3s (not 1s) |
| Login status | Changes only when QR scan completes | 10s + login cache |
| Like / playlist "hidden when not logged in" | Only needs to reflect login state changes | 30s + login cache |
| Static buttons (prev/next) | No state to poll | Use `format` only, no `exec` |
| FM / recommend | Shows/hides with login | 30s + login cache |

**Before/After example (ncm-cli daily calls):**

| Module | Before | After | Saving |
|---|---|---|---|
| ncm-status | 28,800 | ~0 (cache) | ~28,800 |
| ncm-fm/ncm-pl | 5,760 | ~0 (cache) | ~5,760 |
| ncm-play | 86,400 | 28,800 | 57,600 |
| ncm-like | 28,800 | 2,880 | 25,920 |
| **Total** | **~150k** | **~32k** | **~118k (79%)** |

### CSS state classes for play/pause

Waybar custom modules can emit `class` for CSS state routing. For a play-button module:

```bash
# In bash dispatcher:
play-button)
    state=$(ncm_state_status)
    if [ "$state" = "playing" ]; then
        printf '{"text":"▶","class":"playing"}'
    else
        printf '{"text":"⏸","class":"paused"}'
    fi
    ;;
```

Then in `style.css`:
```css
#custom-ncm-play.playing { color: #2d8a4e; font-weight: bold; }
#custom-ncm-play.paused { color: #000000; }
```

Note: this requires `"return-type": "json"` in the waybar module config.

### Login-gated module hiding (without CSS)

Waybar custom modules hide when their `exec` returns empty string. Use this idiom for login-gated controls:

```bash
# In bash dispatcher:
playlist-button)
    if check_login; then printf '🎵'; fi
    # Returns empty when not logged in → waybar auto-hides the module
    ;;
```

Paired with CSS `min-width: 0` on the target modules:
```css
#custom-ncm-fm, #custom-ncm-pl, #custom-ncm-like { min-width: 0; }
```

## Hybrid backend: ncm-cli + ncm (Go) pattern

An alternative to api-enhanced (the default backend described above) is the two-binary approach:

- **ncm-cli (npm, ~365ms call overhead)**: Playback control — play/pause/next/prev/state/login
- **ncm (Go binary, ~2.8MB, near-instant)**: Data operations — search, playlist list/show, recommend songs

The division mirrors api-enhanced's architecture but is fully local (no network dependency for login/auth state, only for actual song playback URLs).

## Backend deployment decision matrix

| Option | x1tablet RAM cost | Cookie privacy | Reliability | Effort |
|---|---|---|---|---|
| Public Vercel api-enhanced | +0 | ⚠️ Cookie sent to 3rd party | ⚠️ Cold start ~6s | 0 |
| Self-host in local docker | +80MB Node | ✅ Yours | ✅ Yours | 30min |
| Self-host on serverhome | +0 | ✅ Yours | ✅ Yours | 30min + tailscale |

**Recommendation**: Start with public Vercel to verify the whole flow in 30min. If cookie trust is uncomfortable or service flakes, deploy to serverhome (Docker, tailscale, ≤5ms latency — already proven pattern for LiteLLM).

## Daemon singleton pattern (beyond polling)

When the streaming backend is an expensive command (e.g. ncm-cli at ~365ms per Node.js startup) and waybar needs multiple modules to reflect state, even the best caching won't eliminate the core problem: **each waybar custom/module runs its own independent exec timer**.

### Architecture

```
                   ┌─ Single daemon process ────────────────┐
                   │  ncm-player daemon (while loop,         │
                   │  sleeps 3s between iterations)          │
                   │  ─────────────────────                  │
                   │  1. mpv IPC socket (idle+pause) → state │
                   │  2. check_login (cached) → Boolean      │
                   │  3. Build icons for all waybar modules  │
                   │  4. Write /tmp/ncm-state.json           │
                   └────────────────────┬────────────────────┘
                                        │ file write
                                        ▼
                              /tmp/ncm-state.json
                              (7 fields, ~200 bytes)
                                        │
               ┌────────────┬───────────┼───────────┬────────────┐
               ▼            ▼           ▼           ▼            ▼
         ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
         │ncm-play  │ │ncm-status│ │ncm-like  │ │ncm-pl    │ │ncm-fm    │
         │python3 . │ │python3 . │ │python3 . │ │python3 . │ │python3 . │
         │get(play) │ │get(icon) │ │get(like) │ │get(pl)   │ │get(fm)   │
         │1μs       │ │1μs       │ │1μs       │ │1μs       │ │1μs       │
         └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘
```

> 完整 daemon bash 实现（含 mpv IPC socket 直接读状态、登录缓存、状态文件写入）已在 `ncm-state-daemon` 技能的"完整 daemon 循环实现"节。waybar 模块 JSON 配置 + CSS 详见 `ncm-cli-setup` 技能的"waybar 集成"节。

**Why this beats ncm-cli state**: the Python socket call reads mpv's Unix socket directly — no subprocess, no Node.js startup, no network. Total latency: **<5ms** vs **~365ms** for `ncm-cli state`.

**mpv property derivation**:

| `idle` | `pause` | Derived state |
|--------|---------|---------------|
| true | false | stopped (no file loaded) |
| false | true | paused (file loaded, paused) |
| false | false | playing |

**Note**: `playback-status` is NOT a valid property in mpv ≤0.40. Always use `idle` + `pause`.

### Waybar modules: read from state file

> 所有 7 个字段的 JSON 配置 + CSS 样式已在 `ncm-cli-setup` 技能的"waybar 集成 → 7 个模块字段来源表"节。

### Sway exec_always

> 完整启动模式决策（nohup vs exec / pkill 陷阱 / 何时用 systemd 守护）见 `sway-daemon-persistence` 技能"外部组件启动模式"节。

两条推荐的 ncm-player daemon 启动模式（Pattern A 调试 / Pattern B 生产）已在那里的"启动方式选择"表中。

## Pitfalls

> ⚠️ **Shared pitfalls.** Core mpv/mpris/login issues (NMTID, `force-media-title`, `playback_only`, `loadfile replace-play`, SWAYSOCK, etc.) maintained in `mpv-mpris-media-stack/references/shared-pitfalls.md`. This section only lists items specific to the thin-CLI architecture.

- **`/song/url/v1` returns `url: null` without login cookie** — this is the #1 trip-up. Even "free old songs" (陈奕迅《最佳损友》id=65800) return null. Login via QR is mandatory for any actual playback.
- **mpv without `--idle=yes` exits after queue drains** → waybar goes blank → keybinds stop working. Always verify with `playerctl -l` after first launch.
- **API public instance cold start** is ~6s on first request (Vercel). Add `--keep-alive` ping or accept the latency for the first song.
- **网易云 copyright `fee: 1` songs** play fine for VIP account holders but return null URL for free users. Don't blame your code if a specific song won't play — check `fee` field in the API response first.
- **Cookie security on public API**: treat `MUSIC_U` token like a password. If you ever see "异地登录" alerts from NetEase after using a public API, rotate password and re-login from a trusted client.
- **`playerctl` may need `--player=mpv` flag** if multiple MPRIS players exist (e.g. mpv + Firefox video). Default `playerctld` handles this, but if you launch raw `playerctl` from a keybind, be explicit.
- **NMTID cookie false positive** in `/login/qr/key`: NetEase returns `Set-Cookie: NMTID=...` (a tracking cookie, NOT auth) on the very first request to any api-enhanced endpoint. If your ncm-login's `api_get()` short-circuits on `Set-Cookie` to extract the auth cookie, it will treat NMTID as auth success, the response will be `{"_raw": ..., "_cookies": [...]}`, `r.get("code") != 200` will be true, the script will `die()`, and the floating foot window flash-closes. **Fix**: parse JSON first, only treat `Set-Cookie` as auth signal on `/login/qr/check` specifically.
- **Don't trust the bash `$\xf00c` escape for PUA codepoints** — see `mpv-mpris-media-stack/references/waybar-integration-pitfalls.md` W7. Use `\U0000F00C` (8 hex digits) in bash AND Python, and emit via `python3 -c "import sys; sys.stdout.write('...')"` to dodge the bash trap entirely.
- **`exec_always bash -c '... &'` kills background children when the bash subshell exits**. Use `exec` (pattern A) or `nohup ... >/dev/null 2>&1 &` to keep long-lived daemon processes alive. Applies to any sway-launched background daemon.
- **mpris `format-stopped: " {}"` shows player name "mpv" when idle**. The `{}` placeholder in format-stopped renders the player name when no track metadata is available. Set to `"format-stopped": ""` to hide the module entirely when mpv is idle.
- **JSON trailing commas in waybar config**. Waybar's C++ parser tolerates them, but Python `json.load()` rejects them — breaks programmatic validation/editing. Common offender: last item in `modules-left` or `modules-right` ending with `,` before `]`.

## Evaluating abandoned TUI music forks (decision tree)

When user says "I want to revive `X/netease-music-tui` (or similar)":

1. Check **last commit date** via `git log -1` or GitHub API. If >2 years stale → reject.
2. Check **dependency health**: scan Cargo.toml/package.json for archived crates (e.g. `failure`, `tui-rs`) or unmaintained deps.
3. Check **encryption strategy**: any direct 163 weapi calls? If yes, expect login failures after 163 changes encryption.
4. Check **fork network**: are active forks (last push within 6 months) continuing the work? If not, the codebase is in a dead-end.
5. Check **issue tracker**: any "login failed" / "401 unauthorized" issues that are stale (no response)? That's the codebase's obituary.

For Netease specifically, the **modern alternative pattern** is `shaoyuanyu/ncm-tui-player` (architecturally clean — ncm-api/ncm-play/ncm-tui crates, spawns api-enhanced as child process), but even that is stalled (2024-12). The CLI+mpv pattern in this skill supersedes all TUI forks for the "minimal Sway" use case.

## Related skills

- `sway-daemon-persistence` — systemd --user pattern for keeping mpv alive across Sway reload
- `mpv-waybar-control` — ncm-player bash dispatcher 部署指南（含 daemon 模式）
- `mpv-mpris-media-stack` — 完整 mpv+MPRIS+waybar 架构参考
- `waybar-config` — waybar 配置管理

## Files in this skill

- ~~`references/api-enhanced-endpoints.md` — 已归档到 `local_share/.archive/legacy-api-enhanced/`（已废弃外部 HTTP 后端）~~
- `ncm-state-daemon/references/ncm-daemon-patterns.md` — login-gated module visibility, mpris format-stopped fix, sway exec vs nohup, pulseaudio icon fix
- `ncm-state-daemon/templates/ncmctl.py` — stdlib-only Python scaffold (~150 LOC) for the thin CLI control script
- `templates/mpv-music.service` — systemd --user unit to keep mpv alive across Sway reload