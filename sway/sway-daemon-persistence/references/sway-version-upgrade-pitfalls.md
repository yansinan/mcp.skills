# Sway / Swayidle Version Upgrade Pitfalls (trixie ↔ sid, 2026-06)

Lessons from upgrading sway 1.10.1 → 1.12 and swayidle 1.8.0 → 1.9.0 on Debian 13 via temporary sid sources. These pitfalls are *not* in the upstream skill — they emerged only when actually performing the upgrade.

## 1. Couple sway and swayidle versions — never upgrade one in isolation

swayidle is built against the wlroots / sway IPC of its companion sway release. Specifically:

| sway    | swayidle (sid)  | Pair status                                |
|---------|-----------------|--------------------------------------------|
| 1.10.1 (trixie) | 1.8.0 (trixie) | OK — ext-idle-notify-v1 stable             |
| 1.10.1 (trixie) | 1.9.0 (sid)    | **BROKEN** — swayidle 1.9 reads `BlockInhibited` IPC property that doesn't exist in sway 1.10.1 |
| 1.12 (sid)      | 1.9.0 (sid)    | OK — full feature set                      |

Detection of broken pair: `journalctl --user -u swayidle | grep "Failed to parse"`
Symptom:
```
[Line 277] Failed to parse get BlockInhibited property: Invalid argument
```
swayidle logs this once on startup. Idle detection then partially works (ext-idle-notify-v1 is stable) but the state machine is incomplete — only the first-firing timeout (e.g. screensaver 30s) fires; later timeouts (mark-idle 60s, screen-off 3600s) may never trigger.

**Rule:** when upgrading sway to sid via temporary `apt install -t sid sway`, always also `apt install -t sid swayidle` (or use a pinning/apt-hold setup that couples them). Don't upgrade one without the other, especially when the running sway binary is *not* being restarted in the same session.

## 2. dpkg conffile conflict on major-version upgrades (apt returns RC=100)

When trixie's sway 1.10.1 (`/etc/sway/config` May 25, 7651B) upgrades to sid's 1.12 (`config.dpkg-new` Jun 13, 8026B), dpkg cannot decide which to keep and prompts interactively. Noninteractive apt hangs, returns RC=100, but the binary **is** already in place.

Verify state with `dpkg -s <pkg> | grep Status`:
- Bad: `Status: install ok unpacked` ← dpkg did not finish configuring
- Good: `Status: install ok installed`

Fix recipe (replace `<pkg>` with sway or swayidle):
```bash
# If the user has NOT customised the conffile, the new (sid) version is correct:
sudo cp /etc/<pkg>.config.dpkg-new /etc/<pkg>.config     # adjust path
sudo rm /etc/<pkg>.config.dpkg-new
sudo dpkg --configure -a
# Should print: Setting up sway (1.12-1) ... RC=0
```

If the user *did* customise, save the diff first:
```bash
diff /etc/<pkg>.config /etc/<pkg>.config.dpkg-new > /tmp/<pkg>-config.diff
# Review diff before overwriting
```

## 3. Verify version priority before declaring victory

After `apt install -t sid <pkg>`, always run:
```bash
apt-cache policy <pkg>
```
Expect to see:
```
  Installed: <new-version>
  Candidate: <new-version>
  Version table:
 *** <new-version> 500
        500 http://...sid/main amd64 Packages
        100 /var/lib/dpkg/status
     <old-version> 500
        500 http://...trixie/main amd64 Packages
```
The `***` should mark the sid version. Without this check, the apt transaction can look successful but `dpkg -s` may show the old version if conffile resolution failed.

## 4. Running process still holds the OLD binary in memory (until restart)

Even after the upgrade is complete on disk, the **running sway / swayidle process** still uses the old binary until you restart it. Detect with:
```bash
ls -la /proc/<PID>/exe
```
If the path shows `(deleted)`, e.g.:
```
lrwxrwxrwx 1 dr dr 0 Jun 23 10:34 /proc/294966/exe -> /usr/bin/sway (deleted)
```
the binary on disk has been replaced but the process is still using the old mmap'd copy. New IPC behaviour won't take effect until the process exits.

For swayidle.service this is a clean restart:
```bash
systemctl --user restart swayidle.service
```
For sway itself, restart requires the user to log out / log in or `swaymsg exit` from a TTY.

## 5. Orphan processes from SIGKILL'd child trees (swayidle pre-1.9 pattern)

swayidle 1.8.0 pre-forks `sh -c <wrapper>` + `<wrapper binary>` for every timeout+resume command at startup. When systemd stops the service (e.g. on `systemctl --user restart`), it sends SIGTERM to the main swayidle PID. The sh+python children don't always propagate SIGTERM cleanly → systemd hits `TimeoutStopSec` → SIGKILL the whole cgroup. If a grandchild was already running (e.g. python3 spawned its own thread / subprocess), it can survive as an **orphan with PPID=1** (adopted by init).

Detection:
```bash
ps -o pid,ppid,etime,command -u $USER | awk '$2=="1" && $3 != "ELAPSED"'
```
Symptom in this session: 4-day-old orphan `sh -c /home/dr/Scripts/sway-session` (PID 2203190) and its `python3 sway-session` child (PID 2203191), both PPID=1.

Fix (safe — no parent cares about PPID=1 processes):
```bash
kill <orphan_pid>
```

**swayidle 1.9.0 fix:** this version does NOT pre-fork — it only fork+exec when a timeout fires. So `pidof swayidle` shows just the one process, no children. This sidesteps the orphan pattern entirely. Confirmed in `pstree -aps <swayidle_pid>` after restart.

## 6. IDLE_MARKER path is NOT /tmp — it's XDG_RUNTIME_DIR

sway-session.py defines:
```python
IDLE_MARKER = Path(XDG_RUNTIME_DIR) / "sway-user-idle"
```
So the marker file lives at `/run/user/1000/sway-user-idle`, not `/tmp/sway-idle`. Easy mistake when grep'ing for it.

To verify idle really fired:
```bash
ls -la /run/user/1000/sway-user-idle
# or in sway-session.py
IDLE_MARKER.exists()
```

## 7. Full upgrade recipe (worked example)

```bash
# 1. Add sid source temporarily
echo 'deb http://mirrors.tuna.tsinghua.edu.cn/debian sid main' | \
  sudo tee /etc/apt/sources.list.d/sid.list
sudo apt update

# 2. Upgrade BOTH sway and swayidle together
sudo apt install -t sid sway swayidle -y
#    ↑ may return RC=100 if conffile conflict — see pitfall 2

# 3. If RC=100, resolve conffile (pitfall 2):
#    Inspect config.dpkg-new, decide whether to keep new or old.
#    Then `sudo dpkg --configure -a`

# 4. Verify version and priority
apt-cache policy sway swayidle
#    Expected: *** on the sid version

# 5. Remove sid source
sudo rm /etc/apt/sources.list.d/sid.list
sudo apt update
sudo apt autoremove -y

# 6. Restart daemons to pick up new binaries (pitfall 4)
systemctl --user restart swayidle.service
#    sway itself: user must log out / log in (or `swaymsg exit` from TTY)
```

## 8. Post-upgrade verification

After restarting swayidle.service, check that idle actually fires:
```bash
# Wait 60+ seconds without keyboard/mouse input
journalctl --user -u swayidle -n 20 --no-pager
#    Should see entries from sway-session sub-commands firing
ls /run/user/1000/sway-user-idle
#    Should exist after 60s of idle
```

If `[Line 277] Failed to parse get BlockInhibited` appears AND only some timeouts fire → pitfall 1 (mismatched pair). Either upgrade sway too, or downgrade swayidle back to trixie's 1.8.0.