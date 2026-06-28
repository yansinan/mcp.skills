# Swayidle wrapper scripts must NOT enter daemon mode by default

## Symptom

`systemctl --user status swayidle` repeatedly shows:
```
State 'stop-sigterm' timed out. Killing.
Killing process XXXXXX (swayidle) with signal SIGKILL.
Killing process XXXXXX (sh) with signal SIGKILL.
Killing process XXXXXX (python3) with signal SIGKILL.
Main process exited, code=killed, status=9/KILL
Failed with result 'timeout'.
Started swayidle.service ...
```

`ps` shows swayidle with a `sh -c <wrapper>` + `python3 <wrapper>` child chain that's been running for hours/days. Wrapper child PID's elapsed time matches swayidle's start time → child forked at swayidle startup, never exited.

## Root cause

`~/.config/swayidle/config` lines like:
```
timeout 60 ~/Scripts/sway-session --mark-idle resume ~/Scripts/sway-session --mark-active
```
spawn `sh -c "sway-session --mark-idle"`. If the wrapper script accepts `--mark-idle` as a one-shot subcommand, it exits cleanly. **But if the wrapper's default (no-arg) mode is to enter a long-running daemon loop**, then any path that invokes the wrapper without proper args leaves a stuck long-running python child.

Common mistake: wrapper script's argparse sets `daemon` as default when no subcommand is given (e.g. `if len(sys.argv) == 1: run_daemon()`), instead of failing with "missing subcommand".

This is distinct from the `swayidle-parse-command-argv0-bug.md` issue (which is about swayidle only taking the first token of a command line). The fix below is for the wrapper-side: ensure wrapper exits unless a real subcommand is passed.

## Detection

```bash
# Find swayidle and its stuck children
pstree -aps $(pidof swayidle)
# Look for sh + python3 children with elapsed time ≈ swayidle start time
ps -o pid,ppid,etime,stat,command -C python3 | grep sway-session
```

If any python3 child has ELAPSED > 5 minutes and PPID chain leads back to swayidle (not sway-session.service), it's stuck.

## Fix

Wrapper script must explicitly require a subcommand. Pattern in `~/Scripts/sway-session`:

```python
def main():
    if len(sys.argv) < 2:
        # Was: sys.exit(run_daemon())   ← WRONG: silently enters daemon
        sys.exit("usage: sway-session {--daemon|--mark-idle|--mark-active|...}")
    sub = sys.argv[1]
    if sub == "--daemon":
        run_daemon()
    elif sub == "--mark-idle":
        mark_idle()
    # ... other one-shots
    else:
        sys.exit(f"unknown subcommand: {sub}")
```

## Cleanup of orphans

When the bug has been running for a while, orphan `sh -c sway-session` + `python3 sway-session` pairs accumulate (PPID=1, parent died). They are not zombies — they are running normally but unbound. Kill them:

```bash
# List orphans
ps -eo pid,ppid,stat,etime,command | awk '$2==1 && /sway-session/ {print}'
# Kill (safe — these are running redundant daemon loops, PPID=1 means no one will restart them)
pkill -f "sh -c /home/dr/Scripts/sway-session"
```

## Prevention

After editing any wrapper called from `~/.config/swayidle/config`, run a 10-second dry test:

```bash
timeout 10 sh -c "$HOME/Scripts/sway-session --mark-idle"
# Must exit within 1 second with status 0
```

If it runs to the timeout (10s), the wrapper has the default-daemon bug.