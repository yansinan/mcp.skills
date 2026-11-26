# V8 SIGTRAP: MemoryDenyWriteExecute on Node.js systemd services

## Symptom

```
code-server.service: Main process exited, code=killed, status=5/TRAP
# Fatal error in , line 0
# Check failed: 12 == (*__errno_location ()).
```

V8's JIT compiler needs to write to executable memory pages. When `MemoryDenyWriteExecute=true` is set in the systemd unit, `mprotect()` and `mmap()` calls that set `PROT_WRITE | PROT_EXEC` fail with `ENOMEM (12)`, crashing Node at isolate initialization.

## Affected services

Any service using bundled Node.js:
- code-server (VS Code in browser) — bundles its own Node binary
- VS Code Server / OpenVSCode Server
- Theia, Eclipse OpenVSX
- Any Electron-based app (via systemd --user)
- Any `node` process under a systemd unit with JIT enabled

## Fix

**Option A — remove MemoryDenyWriteExecute (recommended for Node.js services):**

```ini
[Service]
# NO: MemoryDenyWriteExecute=true
NoNewPrivileges=true
ProtectSystem=full
PrivateTmp=true
```

This keeps the most important safety features (no privilege escalation, read-only `/usr`/`/etc` after boot, private `/tmp`) while allowing V8 JIT.

**Option B — fully hardened but disable V8 JIT (--jitless):**

```ini
[Service]
MemoryDenyWriteExecute=true
ExecStart=/usr/bin/node --jitless /path/to/app.js
```

Warning: `--jitless` disables V8 JIT entirely, which can be 2–10× slower for some workloads. Only works when you control how Node is invoked (not for bundled-Node apps like code-server that start their own runtime).

## Verified working config (code-server 4.123.0 on Debian 13)

```ini
[Unit]
Description=code-server (VS Code in browser)
After=network.target network-online.target
Wants=network-online.target

[Service]
Type=exec
ExecStart=%h/.local/bin/code-server --config %h/.config/code-server/config.yaml
Restart=on-failure
RestartSec=5
WorkingDirectory=%h
NoNewPrivileges=true
ProtectSystem=full
PrivateTmp=true

[Install]
WantedBy=default.target
```

Binds to `100.66.66.249:5000` (Tailscale IP). Access via http://100.66.66.249:5000 with password auth.
