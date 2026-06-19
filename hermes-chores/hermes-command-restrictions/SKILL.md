---
name: hermes-command-restrictions
description: "Restrict what commands Hermes can run and where — approval system, server-side SSH restrictions, wrapper scripts, and container isolation. Covers the gap where Hermes has no built-in per-host command blocklist."
version: 1.0.0
author: agent
tags: [hermes, security, ssh, terminal, approval, command-restriction]
---

# Hermes Command Restrictions

Hermes has a defense-in-depth security model, but **does not have a built-in per-host or per-command blocklist** that you can configure via `config.yaml`. When you need to block a specific command (e.g. `docker`) on a specific remote host, the practical solution is **server-side enforcement**.

## What Hermes Has Built-In

| Layer | Scope | Configurable? |
|-------|-------|---------------|
| **Dangerous command approval** (`tools/approval.py`) | Patterns like `rm -rf`, `mkfs`, `systemctl`, `DROP TABLE` — global only | Pattern list is hardcoded; `approvals.mode` (manual/smart/off) is configurable |
| **Hardline blocklist** (`UNRECOVERABLE_BLOCKLIST`) | `rm -rf /`, fork bombs, `dd if=/dev/zero of=/dev/sd*` — always on, no override | Not configurable |
| **Tirith pre-exec scanning** | Homograph URLs, pipe-to-interpreter, terminal injection | `security.tirith_enabled` toggle only |
| **Website blocklist** | Domains blocked for web/browser tools | `security.website_blocklist.domains` |
| **Command allowlist** (`command_allowlist`) | Permanently approve specific dangerous patterns (whitelist, not blocklist) | `command_allowlist` list in config.yaml |

## The Gap: Per-Host Command Blocking

There is **no** `security.command_blocklist` or per-host restriction in Hermes config. `docker`, `kubectl`, `helm`, etc. are NOT on the dangerous command list — they pass through without approval prompts.

For the common pattern `ssh serverhome docker <...>`, Hermes sees `ssh` with arguments and does not inspect the remote command content.

## Solutions

### A. SSH Authorized Keys `command=` (Recommended)

On the **target host** (`serverhome`), restrict the SSH key used by Hermes via `~/.ssh/authorized_keys`:

```
command="~/.ssh/hermes-ssh-wrapper.sh",no-agent-forwarding,no-port-forwarding ssh-ed25519 AAAA... hermes-agent
```

The wrapper script (`~/.ssh/hermes-ssh-wrapper.sh` on the target host):

```bash
#!/bin/bash
# Block docker commands via Hermes, allow everything else
if [[ "$SSH_ORIGINAL_COMMAND" == *"docker"* ]]; then
  echo "ERROR: docker commands are not allowed via Hermes agent" >&2
  exit 1
fi
exec bash -c "$SSH_ORIGINAL_COMMAND"
```

**Pros**: Only affects the specific SSH key — you can still use docker when logged in directly. No Hermes config changes needed.

### B. Wrapper Script on Target Host

Replace `docker` on the target host's PATH with a wrapper for the Hermes user:

```bash
# On serverhome
sudo mv /usr/bin/docker /usr/bin/docker.real
sudo tee /usr/local/bin/docker << 'WRAPPER'
#!/bin/bash
echo "ERROR: docker is blocked via Hermes agent" >&2
exit 1
WRAPPER
sudo chmod +x /usr/local/bin/docker
# Ensure /usr/local/bin is before /usr/bin in PATH
```

**Pros**: Dead simple, impossible to bypass. **Cons**: Affects ALL sessions for that user, not just Hermes.

### C. Container Isolation

Set `terminal.backend: docker` or `modal` on the Hermes side. Dangerous command checks are **skipped** for container backends (the container IS the security boundary). The target host never sees the commands because they run inside a sandbox.

**Not a solution** if you need Hermes to reach `serverhome` specifically — container backends replace the execution environment entirely.

### D. Extend Approval Patterns (Code Change)

Add `docker` to the dangerous command patterns in `tools/approval.py` in the Hermes source. Every command matching `docker` would then prompt for user approval.

**Pros**: Works for all targets. **Cons**: Requires modifying Hermes source, global (not per-host).

## Where to Look

| What | Where |
|------|-------|
| Danger command patterns | `hermes-agent/tools/approval.py` |
| Hardline blocklist | `hermes-agent/tools/approval.py::UNRECOVERABLE_BLOCKLIST` |
| Tirith integration | `hermes-agent/tools/tirith_security.py` |
| Approval config docs | `security.md` in Hermes docs |
| SSH backend config | `terminal.backend: ssh`, env `TERMINAL_SSH_HOST/USER/KEY` |

## Pitfalls

- **SSH key `command=` strips the original command** into `$SSH_ORIGINAL_COMMAND` env var — your wrapper MUST check that var and `exec` the command. Without `exec bash -c "$SSH_ORIGINAL_COMMAND"` you silently drop all commands.
- **PATH matters for wrapper scripts.** Put the wrapper in a directory that comes before `/usr/bin` in the PATH (e.g. `/usr/local/bin` for root, `~/bin` for user).
- **SSH non-interactive commands bypass `~/.local/bin` PATH.** `ssh serverhome docker ...` runs as a non-interactive, non-login shell — bash does NOT read `~/.bashrc`, `~/.profile`, or `~/.bash_profile`. If your wrapper is in `~/.local/bin`, SSH won't find it. Fix: add PATH before the interactive guard in `~/.bashrc` and set `export BASH_ENV="$HOME/.bashrc"` in `~/.profile`. This makes `bash -c` source `.bashrc`, setting the custom PATH before the command executes.
- **Approvals.mode: off** / `--yolo` bypass ALL pattern-based approval but do NOT bypass the hardline blocklist.
- **Tirith fail_open: true** (default) means commands proceed if tirith is missing or crashes — set to `false` in high-security environments.
