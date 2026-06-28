# mpv 0.40 Pitfalls — Transcripts and Fixes

This file documents the exact error transcripts and reproductions for each gotcha
listed in the parent SKILL.md "Pitfalls" section. Read this when something is
silently failing and you suspect mpv.

---

## Pitfall #1 — `utils.format_url` does NOT exist

**Reproduction**:
```lua
local qs = url .. "?" .. utils.format_url(k) .. "=" .. utils.format_url(v)
--                                ^^^^^^^^^^^^^^^^^^                     ^
--                                nil                                    nil
```

**Error from mpv**:
```
[f][ncm] Lua error: /home/dr/.config/mpv/scripts/ncm.lua:80: attempt to call
field 'format_url' (a nil value)
```

**Root cause**: `mp.utils.format_url` was added in mpv 0.38 BUT removed/renamed in
0.40. The bundled `utils` table in 0.40 only exposes:
- `parse_json(str [, trail])`
- `format_json(v)`
- `subprocess(t)` (legacy wrapper)
- `get_env_list()`, `split_path()`, `join_path()`, `file_info()`, `readdir()`, `getcwd()`

**Fix**: Self-implement URL encoding.
```lua
local function url_encode(s)
    s = tostring(s or "")
    return (s:gsub("[^%w%-_~.]", function(c)
        return string.format("%%%02X", string.byte(c))
    end))
end
```

---

## Pitfall #2 — `utils.subprocess` ignores `playback_only=false`

**Reproduction**:
```lua
local r = mp.utils.subprocess({
    args = {"curl", url},
    capture_stdout = true,
    playback_only = false,  -- ignored
})
```

**Symptom from mpv log**:
```
[v][cplayer] Run command: subprocess, flags=64,
    args=[args="curl,-sSL,http://...",
          playback_only="yes",                  -- <-- still "yes"!
          capture_size=..., ...]
[v][ncm] Starting subprocess: [curl, ...]
[v][ncm] Subprocess failed: killed              -- <-- 5-10ms after start
```

**Root cause**: `mp.utils.subprocess` is documented as a "legacy wrapper" that:
1. Copies the input table
2. Renames `cancellable` → `playback_only`
3. Calls `mp.command_native(copied_t)`

If the input table doesn't have a `cancellable` key, the wrapper does NOT explicitly
set `playback_only=false` — it lets mpv use the default, which is `true` (see
`man input.rst` "subprocess" section).

**Fix**: Bypass the wrapper entirely.
```lua
local r = mp.command_native({
    name = "subprocess",       -- note: NOT "_name"
    args = {"curl", "-sSL", url},
    capture_stdout = true,
    capture_stderr = true,
    playback_only = "no",      -- FLAG = string "yes"/"no", not boolean
})
```

---

## Pitfall #3 — `mp.command("set force-media-title <text>")` does NOT work

**Reproduction**:
```lua
mp.command("set force-media-title 陈奕迅 - 最佳损友")
-- expected: media-title = "陈奕迅 - 最佳损友"
-- actual: media-title = "<last URL fragment like SkBnGSVd9FH1UqgHdsHNvsLkt6CjzXeElaMeDv+3Hknc=>"
```

**Symptom in `playerctl`**:
```
$ playerctl -p mpv metadata --format '{{ artist }} - {{ title }}'
 - oTyo3Jx6h+Uy4WmU+XnVfjrS1VBzdljfDEfS6pNifTe4=
```

**Root cause**: The `set` input command parser is strict about argument shapes.
The string-command form `mp.command("set force-media-title X")` is parsed as
`set <one arg>"force-media-title X"` and silently fails. The property remains
unset, so mpv falls back to deriving `media-title` from the URL path.

**Fix**: Use the 3-element array form.
```lua
mp.commandv("set", "force-media-title", "陈奕迅 - 最佳损友")
-- or via IPC:
-- {"command": ["set", "force-media-title", "陈奕迅 - 最佳损友"]}
```

**Verification**:
```
$ playerctl -p mpv metadata --format '{{ artist }} - {{ title }}'
 - 陈奕迅 - 最佳损友
```

---

## Pitfall #4 — Debian `mpv-mpris` is a separate package

**Reproduction**:
```bash
$ apt install mpv
$ ls /usr/lib/x86_64-linux-gnu/mpv/mpris.so 2>&1 || echo missing
missing
$ ls /usr/share/mpv/scripts/ | head
(empty)
```

**Symptom**: mpv starts, plays audio, registers on D-Bus, but `playerctl -l` does
not list `mpv` as a media player. The D-Bus interface name is `org.mpris.MediaPlayer2.mpv`
but there's no service providing it.

**Root cause**: Debian splits the `mpris.lua` upstream script into a separate
package `mpv-mpris`. The base `mpv` package only ships core scripts (ytdl_hook,
stats, console, etc.) but NOT mpris.

**Fix**:
```bash
sudo apt install mpv-mpris
```

After install, `/etc/mpv/scripts/mpris.so` (a compiled Lua C plugin, not a .lua
file) is auto-loaded by every mpv invocation.

**Verification**:
```
$ playerctl -l | grep mpv
mpv
$ busctl --user list | grep mpris
org.mpris.MediaPlayer2.mpv    ...    mpv
```

---

## Pitfall #5 — script-message handler needs correct argument count

**Reproduction** (in `ncm.lua`):
```lua
mp.register_script_message("ncm-fm", function(arg)
    -- ncm.lua receives the message but doesn't actually do anything
end)
```

**Symptom in mpv log when IPC client sends wrong shape**:
```
[d][cplayer] Run command: script-message, args=[args="ncm-fm", args=""]
[e][ipc_0] Write error (Broken pipe)        -- client timed out
```

**Root cause**: The IPC command format for `script-message` is:
```json
{"command": ["script-message", "<handler-name>", "<arg1>", "<arg2>", ...]}
```

Each `<argN>` is a SEPARATE array element, not a single space-separated string.

**Fix** (in the bash dispatcher, sending to /tmp/ncm-mpv.sock):
```bash
python3 - "$msg" "$arg" <<'PYEOF'
import socket, json, sys
msg, arg = sys.argv[1], sys.argv[2]
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); s.settimeout(5)
s.connect("/tmp/ncm-mpv.sock")
s.sendall((json.dumps({"command": ["script-message", "ncm-" + msg, arg]}) + "\n").encode())
s.close()
PYEOF
```

Note the three-element array `["script-message", "ncm-fm", ""]`. If you send
`["script-message", "ncm-fm extra args as one string"]`, the handler receives
"ncm-fm extra args as one string" as the single argument.

---

## Pitfall #6 — mpv IPC socket cleanup

**Reproduction**:
```bash
$ mpv --idle --input-ipc-server=/tmp/ncm-mpv.sock
# crashes or is killed
$ ls /tmp/ncm-mpv.sock
/tmp/ncm-mpv.sock       # <-- stale socket file
$ mpv --idle --input-ipc-server=/tmp/ncm-mpv.sock
Failed to create IPC socket
```

**Root cause**: mpv creates the Unix socket file at startup but doesn't always
clean it up on crash/SIGKILL.

**Fix**: Always `pkill -x mpv` then `rm -f /tmp/ncm-mpv.sock` before starting.
The `exec_always` pattern in sway handles this:
```bash
exec_always bash -c 'pkill -x mpv 2>/dev/null; sleep 0.3; exec mpv --idle=yes ...'
```

If mpv crashes mid-session, manually:
```bash
pkill -9 mpv; rm -f /tmp/ncm-mpv.sock
```

---

## Verification cheatsheet

```bash
# Check mpv is registered with MPRIS
playerctl -l | grep mpv

# Check current metadata
playerctl -p mpv metadata --format '{{ artist }} - {{ title }}'

# Check IPC socket is alive
ls -la /tmp/ncm-mpv.sock

# Direct test via python
python3 -c "
import socket, json
s = socket.socket(socket.AF_UNIX); s.settimeout(2)
s.connect('/tmp/ncm-mpv.sock')
s.sendall(json.dumps({'command':['get_property','media-title']}).encode() + b'\n')
print(s.recv(2048).decode()[:200])
"
```