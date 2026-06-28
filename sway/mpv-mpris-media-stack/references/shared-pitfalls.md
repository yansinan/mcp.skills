# Shared Pitfalls for Sway Music Stack

> **Canonical source.** This file lives under `mpv-mpris-media-stack/references/` and is the single source of truth for pitfalls that apply across all three sway music skills. If a pitfall needs updating, edit here — do not add another copy to `mpv-waybar-control` or `sway-music-client`.

All pitfall IDs map to the same numbering used in `mpv-mpris-media-stack`'s inline Pitfalls section.

---

## mpv 0.40 specifics

### P01: `utils.format_url` does NOT exist (mpv 0.40)

Only `parse_json` and `format_json` are exposed. Hand-roll URL encoding:

```lua
local function url_encode(s)
    return (s:gsub("[^%w%-_~.]", function(c)
        return string.format("%%%02X", string.byte(c))
    end))
end
```

### P02: `utils.subprocess` ignores `playback_only=false`

The mpv `subprocess` command defaults to `playback_only=true`, which kills the subprocess immediately when mpv is in `idle`. Bypass the wrapper:

```lua
local r = mp.command_native({
    name = "subprocess",
    args = {"curl", "-sSL", url},
    capture_stdout = true,
    playback_only = "no",     -- string "no", NOT boolean false
})
```

### P03: `set force-media-title` requires 3-element array form

```lua
mp.commandv("set", "force-media-title", media_title)  -- ✓
mp.command("set force-media-title " .. title)          -- ✗ fails silently
```

### P04: Debian mpv package does not include `mpris.so`

Install `mpv-mpris` separately: `apt install mpv-mpris`. It drops `/etc/mpv/scripts/mpris.so`.

### P05: `loadfile` mode `replace-play` is NOT valid

mpv accepts `replace` (replace and play) and `append-play` (append and queue). `replace-play` silently no-ops:

```lua
mp.commandv("loadfile", url, "replace")       -- ✓
mp.commandv("loadfile", url, "append-play")    -- ✓
-- mp.commandv("loadfile", url, "replace-play") -- ✗
```

---

## mpv-mpris / MPRIS specifics

### P06: mpv-mpris 0.7 stays "Stopped" after `loadfile`

Root cause: when mpv is `--idle=yes`, `pause=false` is the default. `loadfile` into idle mpv fires `MPV_EVENT_IDLE` → `set_stopped_status()`. But `pause` stays `false`, so `handle_property_change("pause")` never fires, `ud->status` stays `STATUS_STOPPED`.

Fix: explicitly toggle `pause` after loadfile with separate timeouts:

```lua
mp.commandv("loadfile", url, "replace")
mp.add_timeout(0.5, function()
    mp.commandv("set", "pause", "yes")    -- triggers PROPERTY_CHANGE
end)
mp.add_timeout(0.6, function()
    mp.commandv("set", "pause", "no")     -- triggers PROPERTY_CHANGE → Playing
end)
```

### P07: mpv-mpris 0.7 does NOT split "Artist - Title" from media-title

The `mpris.so` 0.7.1 reads `xesam:artist` ONLY from `metadata/by-key/Artist` (ID3 tag) or `metadata/by-key/uploader` (YouTube). For streaming URLs (no ID3), artist is always empty.

Fix: pack full "Artist - Title" into `force-media-title` and use waybar format `" {title}"` (single field), not `" {title} - {artist}"`.

### P08: waybar mpris `interval` default (5s) blocks "Playing" after "Stopped"

Root cause in waybar-mpris.cpp lines 688-701: `update()` sets `last_update_` BEFORE the Stopped check and early returns. The Playing signal arrives ~200ms later but hits the rate-limit check `now - last_update_ < interval_` (= true) and silently skips.

Fix in waybar config:

```json
"mpris": {
    "interval": 0,
    "format-stopped": " {}",
    "player": "mpv",
    ...
}
```

`interval=0` disables the rate-limit entirely so every signal triggers a widget update.

---

## Sway / Wayland specifics

### P09: SWAYSOCK inheritance — waybar inherits stale socket after sway reload

Waybar inherits `SWAYSOCK` from its parent shell. If sway reloaded (new PID), the old socket path is stale. Waybar silently drops `sway/window` + `sway/workspaces` modules.

Diagnose: `cat /proc/<waybar_pid>/environ | tr '\0' '\n' | grep SWAYSOCK`.

Fix: discover current sway PID from `/proc` before launching waybar:

```bash
for pid in /proc/[0-9]*; do
    [ -r "$pid/comm" ] || continue
    if [ "$(cat "$pid/comm" 2>/dev/null)" = "sway" ]; then
        SWAY_PID="${pid##*/}"; break
    fi
done
if [ -n "$SWAY_PID" ] && [ -S "/run/user/$(id -u)/sway-ipc.$(id -u).${SWAY_PID}.sock" ]; then
    export SWAYSOCK="/run/user/$(id -u)/sway-ipc.$(id -u).${SWAY_PID}.sock"
fi
```

Put this in an external script (not inline `bash -c '...'`) — see P11.

### P10: sway `exec_always` parses the command LINE BY LINE

Multi-line `bash -c '...\n...\n...'` blocks break — sway processes each non-first line as a separate sway command.

Fix: put multi-line logic in a separate script file and call directly:

```bash
exec_always /path/to/script.sh    # ✓
exec_always bash -c '...'         # ✗ if multi-line
```

### P11: foot has no `--float` flag

The correct way to launch a floating terminal from waybar:

```bash
foot -a <app-id> -W 80x24 <command>
```

Then declare float in sway config:

```
for_window [app_id="<app-id>"] floating enable
for_window [app_id="<app-id>"] resize set 700 400
for_window [app_id="<app-id>"] move position center
```

### P12: i3 IPC requires protocol header, not raw JSON

Sway's IPC server uses the i3-ipc protocol: magic header `b"i3-ipc\0"` + 4-byte LE length + 4-byte LE type + payload. Don't `sendall(b'{"command":[...]}\n')` — use `python3-i3ipc` / `python3-swayipc` or hand-roll the header.

---

## Font / terminal specifics

### P13: Nerd Font PUA codepoints require 8 hex digits (`\U`)

`\xf00c` in bash/Python only consumes 1-2 hex digits. For PUA range (U+E000..U+F8FF):

```bash
printf '\U0000F00C'          # ✓ bash
python3 -c "print('\U0000F00C', end='')"  # ✓ Python
```

Working set for music-control buttons:

| Glyph | Codepoint | Escape |
|-------|-----------|--------|
| ✓ | U+F00C | `\U0000F00C` |
| 🔑 | U+F09C | `\U0000F09C` |
| ♥ | U+F004 | `\U0000F004` |
| ▶ | U+F04B | `\U0000F04B` |
| ⏸ | U+F04C | `\U0000F04C` |
| ⏮ | U+F048 | `\U0000F048` |
| ⏭ | U+F051 | `\U0000F051` |

### P14: `qrencode -t UTF8` for scannable QR, not `chafa`

`chafa --size=40x20 --colors=256 /tmp/qr.png` produces blurry ASCII blocks that fail to scan. Use `qrencode -t UTF8 -s 1 -m 2` which outputs dense half-character (▀▄█) QR codes.

---

## Login / cookie specifics

### P15: NMTID cookie false positive in `/login/qr/key`

NetEase returns `Set-Cookie: NMTID=...` (tracking cookie, NOT auth) on the *first* unauthenticated request. If login code checks `if "Set-Cookie" in response.headers: return ...`, it treats NMTID as auth success.

Fix: only treat `Set-Cookie` as auth signal on `/login/qr/check` specifically. Parse JSON first.

### P16: api-enhanced puts MUSIC_U in JSON body, not Set-Cookie header

After successful QR scan, the cookie string is in `r.json()["cookie"]` (JSON body field). The Set-Cookie header may carry only NMTID.

```python
cookie_str = r.get("cookie", "")           # api-enhanced: MUSIC_U here
if not cookie_str:
    cookies = r.get("_cookies") or []      # Set-Cookie fallback
    cookie_str = "; ".join(c.split(";", 1)[0] for c in cookies)
```

---

## Waybar exec specifics

### P17: waybar `exec` absolute path requirement

waybar exec calls `execve()` directly — no shell PATH resolution. Always use absolute paths:

```json
"exec": "/home/dr/.local/bin/ncm play-button"   // ✓
"exec": "ncm play-button"                        // ✗
```

### P18: waybar custom modules with empty `exec` still occupy horizontal space

Even when exec returns empty string, the GTK label occupies space. For true auto-hide, combine CSS:

```css
#custom-ncm-like, #custom-ncm-pl, #custom-ncm-fm { min-width: 0; }
```

With exec returning empty → module collapses to 0 width. For complete invisibility, use `return-type: json`:

```json
{"text": "", "class": "hidden"}
```

```css
.hidden { display: none !important; }
```
