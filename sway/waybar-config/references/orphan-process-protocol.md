# Waybar Orphan-Process Protocol

> **The single most common waybar operational pitfall on this system.**
> Generated 2026-06-24 after user got visibly frustrated: "又是孤儿线程问题，能不能不再犯这个错了？！！！！"

## TL;DR

**Never** SIGKILL waybar in production. **Never** spawn `timeout N waybar -l trace` as a diagnostic. Both create orphan `ncm-player waybar play` processes that reparent to init (PPID=1) and keep running forever, holding pipes and consuming CPU while the module shows blank.

The fix is mechanical: TERM → wait → KILL stragglers → verify zero orphans → restart with fresh SWAYSOCK.

## Why orphans happen

| Action | What happens to ncm-player child |
|---|---|
| `pkill -TERM waybar` | waybar exits cleanly, closes child stdin pipe. ncm-player's `while true; do echo; done` gets SIGPIPE on next write, exits with code 141. **Clean.** |
| `pkill -9 waybar` / `killall -9 waybar` | waybar dies abruptly. ncm-player's pipe stays open, script keeps running. Kernel reparents to init (PPID=1). **Orphan.** |
| `timeout 2 waybar -l trace` | timeout sends SIGTERM after 2s. Usually clean — but if timeout has `--kill-after`, OR if waybar is stuck and doesn't propagate, the child stays alive. **Orphan risk.** |
| `kill -9 $WAYBAR_PID` | Same as `pkill -9`. **Orphan.** |

The OS process tree:
```
init (PPID=1)
└── bash (ncm-player runner, PPID=1 — orphan)   ← after waybar KILL
    └── (no children)
```

vs healthy:
```
waybar (PPID=user-shell)
└── sh -c /home/dr/.local/bin/ncm-player waybar play
    └── bash /home/dr/.local/bin/ncm-player waybar play (while loop)
```

## Verification command (run after every restart)

```bash
# Must be 0 — any non-zero count means cleanup is incomplete
ps -eo pid,ppid,cmd | grep "ncm-player" | grep -v grep | awk '$2==1' | wc -l
```

## The orphan-safe restart procedure

See `SKILL.md` § "Safely restarting waybar (dual-instance) — ORPHAN-SAFE PROTOCOL" for the full 5-step procedure. The short version:

```bash
pkill -TERM -f "waybar -c" 2>/dev/null; sleep 1.5
pkill -9 -f "ncm-player" 2>/dev/null
pkill -9 -f "waybar -c" 2>/dev/null; sleep 0.5
# verify zero orphans before restarting
SWAYSOCK=$(ls -t /run/user/1000/sway-ipc.*.sock | head -1)
SWAYSOCK="$SWAYSOCK" waybar -c ~/.config/waybar/config-top >/tmp/wb-top.log 2>&1 &
SWAYSOCK="$SWAYSOCK" waybar -c ~/.config/waybar/config-bottom >/tmp/wb-bottom.log 2>&1 &
```

## `killall ncm-player` doesn't work — use `pkill -f`

`ncm-player` is a bash script. The OS process name is `bash` (the interpreter), not `ncm-player`. Tools that match by **process name** (not cmdline) silently miss it:

```bash
# ❌ matches process name = "bash" — no-op
killall ncm-player
killall ncm-playlist
killall ncm-state-daemon
pkill ncm-player            # pkill defaults to -x (exact name)

# ✅ matches cmdline — works
pkill -f "ncm-player"
pkill -f "/home/dr/.local/bin/ncm-player"
pkill -9 -f "ncm-state-daemon"   # systemd unit, but invocation pattern is also bash
```

This trap catches any script-orchestrated process. `killall waybar` happens to work because waybar's binary is named `waybar` (not a script). But for **any** `bash /path/to/script` invocation, use `pkill -f`.

## SWAYSOCK stale env (related issue)

When restarting waybar from a long-lived terminal (hermes, ssh) that survived a sway restart, the inherited `SWAYSOCK` env var points to the **old** sway's socket. Waybar fails:

```
[warning] module sway/workspaces: Disabling module "sway/workspaces", Unable to connect to Sway
[warning] module sway/window: Disabling module "sway/window", Unable to connect to Sway
```

Fix: re-resolve SWAYSOCK before each waybar start.

```bash
# Sort by mtime (newest first), pick the most recent
SWAYSOCK=$(ls -t /run/user/1000/sway-ipc.*.sock 2>/dev/null | head -1)
[ -S "$SWAYSOCK" ] || { echo "no valid sway socket — is sway running?"; exit 1; }
SWAYSOCK="$SWAYSOCK" waybar -c ~/.config/waybar/config-top >/tmp/wb-top.log 2>&1 &
```

**Why `ls -t` not `ls`**: `ls` sorts alphabetically. The socket filename is `sway-ipc.<UID>.<PID>.sock` — alphabetical sort gives you the lowest PID, not the latest. `ls -t` sorts by mtime → head -1 = newest = current sway.

## Debugging ncm-* modules WITHOUT spawning a debug waybar

**Don't** spawn a second `timeout 2 waybar -l trace` instance for diagnostic. The new instance's ncm-player children become orphans when timeout kills it.

Instead, query the state file directly + trigger a refresh:

```bash
# See what state the cache is at:
cat /tmp/ncm-state.json | python3 -m json.tool

# Trigger a refresh without restarting waybar (sync_state re-reads ncm-cli → state.json → pkill -RTMIN+6 waybar)
/home/dr/.local/bin/ncm-player sync-state

# Or run a single sync_state call from CLI (sync_state is also a subcommand):
/home/dr/.local/bin/ncm-player sync-state

# Check stderr of the ncm-player children (they're spawned by waybar with stderr captured by waybar log)
tail -f /tmp/wb-top.log
```

For deeper debug, use the `WAYBAR_LOG_LEVEL=trace` env var on the production instance — **not** a separate debug waybar.

## Repro recipe (so the next agent can recognize the symptom)

```bash
# 1. Start waybar in foreground
SWAYSOCK=$(ls -t /run/user/1000/sway-ipc.*.sock | head -1) \
  waybar -c ~/.config/waybar/config-top 2>&1 | head -50 &
WAYBAR_PID=$!
sleep 3

# 2. Verify ncm-player children have PPID=waybar
ps -eo pid,ppid,cmd | grep "ncm-player" | grep -v grep
# Should show:
#   <ncm pid>  $WAYBAR_PID  bash /home/dr/.local/bin/ncm-player waybar play

# 3. SIGKILL waybar (the WRONG way)
kill -9 $WAYBAR_PID
sleep 1

# 4. Observe the orphans
ps -eo pid,ppid,cmd | grep "ncm-player" | grep -v grep
# Now shows:
#   <ncm pid>       1  bash /home/dr/.local/bin/ncm-player waybar play
#                                                              ^^^^^^ PPID=1 = orphan

# 5. Verify the bug (orphan still running, waybar dead)
ps -p $WAYBAR_PID 2>&1   # no such process
ps -p <ncm pid>           # still running — that's the bug
```

## Why this matters beyond just "ugly pgrep output"

Orphaned `ncm-player` processes:
- **Consume CPU** — the `while true; do echo; done` loop runs forever, writing to a pipe nobody reads
- **Hold mpv IPC sockets** — if you have other tools trying to talk to mpv via the same socket, they may fail
- **Mask real bugs** — "why is the play button blank?" → because there's an orphan, not the waybar you just spawned, driving the ncm-* module
- **Confuse signal-based refresh** — the daemon's `pkill -RTMIN+6 waybar` may signal a *new* waybar while the orphan keeps writing to its dead pipe, leading to confusing GTK widget state

The cost of clean restart (1.5s sleep + 4 commands) is much less than the cost of debugging "why does the play button still show the wrong icon after I fixed everything".
