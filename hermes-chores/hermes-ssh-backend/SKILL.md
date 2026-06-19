---
name: hermes-ssh-backend
description: "Configure and troubleshoot Hermes Agent with SSH terminal backend — config format, FileSyncManager behavior, remote Hermes coexistence, ControlMaster connection management."
version: 1.0.0
author: agent
platforms: [linux, macos]
metadata:
  hermes:
    tags: [hermes, ssh, terminal-backend, remote-execution, profiles]
    related_skills: [hermes-command-restrictions, hermes-model-config]
---

# Hermes SSH Backend

Configure Hermes to execute terminal commands on a remote machine via SSH, using `terminal.backend: ssh`. The LLM runs locally (or wherever the profile's provider points), but all `terminal()`, `read_file`, `write_file`, `patch`, and `search_files` operations execute on the remote host.

## Quick Reference

```yaml
# In the profile's config.yaml or default config.yaml:
terminal:
  backend: ssh
  ssh_host: serverhostname         # hostname or IP (resolved via SSH config)
  ssh_user: remote-user
  ssh_port: 22
  ssh_key: /path/to/key            # optional; empty string = default key search
  cwd: ~                           # remote working directory (default: ~)
  timeout: 180
  persistent_shell: true           # preserves env vars across commands
```

## Config-to-Env-Var Mapping

The terminal tool reads env vars, not config.yaml directly. The config system bridges automatically:

| config.yaml key          | Sets env var              |
|--------------------------|---------------------------|
| `terminal.backend`       | `TERMINAL_ENV`            |
| `terminal.ssh_host`      | `TERMINAL_SSH_HOST`       |
| `terminal.ssh_user`      | `TERMINAL_SSH_USER`       |
| `terminal.ssh_port`      | `TERMINAL_SSH_PORT`       |
| `terminal.ssh_key`       | `TERMINAL_SSH_KEY`        |
| `terminal.cwd`           | `TERMINAL_CWD`            |
| `terminal.timeout`       | `TERMINAL_TIMEOUT`        |
| `terminal.persistent_shell` | `TERMINAL_PERSISTENT_SHELL` |

Full mapping in `hermes_cli/config.py::TERMINAL_CONFIG_ENV_MAP`.

## Creating a Profile with SSH Backend

```bash
# 1. Ensure SSH key-based auth works first
ssh-copy-id user@remote-host

# 2. Create the profile (clone config from default)
hermes profile create my-remote-agent --clone-all

# 3. Edit the profile's config
my-remote-agent config edit
# Set terminal.backend: ssh, terminal.ssh_host, terminal.ssh_user

# 4. Verify
my-remote-agent chat -q "hostname && whoami && pwd"
```

## CRITICAL: FileSyncManager Behavior

**This is the most important pitfall to understand.** The `SSHEnvironment` (`tools/environments/ssh.py`) syncs the **entire local `~/.hermes/` directory structure** to the remote host at startup and back at shutdown:

- **On connect**: Uploads `skills/`, `credentials/`, `cache/` to `{remote_home}/.hermes/`
- **On cleanup**: Downloads changes from `{remote_home}/.hermes/` back to local
- Creates `~/.hermes/skills/`, `~/.hermes/credentials/`, `~/.hermes/cache/` if they don't exist

### If the Remote Already Has Hermes Installed

This will **overwrite the remote's existing skills and credentials**. The sync is one-way writing into the same paths. This causes:

- **Skills conflict**: Remote Hermes's skills get overwritten by the profile's skills
- **Credentials conflict**: Remote Hermes's credentials may be corrupted or replaced
- **Bidirectional confusion**: On cleanup, changes made on the remote by its own Hermes instance may get synced back to the local profile

### Mitigation Strategies

**Strategy A — Separate remote HERMES_HOME (recommended):**
On the remote, create an isolated directory for the profile:
```bash
# On remote:
mkdir -p ~/.hermes-ssh-agent/{skills,credentials,cache}
```
Then set `HERMES_HOME` in the SSH environment's shell init so FileSyncManager targets the isolated directory instead of the main `~/.hermes/`.

**Strategy B — Accept sync, then restore:**
On first connection, the profile populates the remote's `~/.hermes/skills/` with its own skills. If the remote Hermes doesn't use agent-created skills (only bundled), this may be acceptable — but `credentials/` and `cache/` are still at risk.

**Strategy C — Don't use persistent filesync:**
Not currently configurable via config.yaml. The FileSyncManager is hard-coded in `SSHEnvironment.__init__`. Consider this a feature request if it's a blocker.

## SSH Connection Details

- **ControlMaster auto**: Uses SSH ControlMaster for connection reuse (socket at `/tmp/hermes-ssh/<hash>.sock`)
- **ControlPersist 300s**: Socket stays alive 5 minutes after last use
- **BatchMode yes**: No interactive password prompts
- **StrictHostKeyChecking accept-new**: Auto-accepts new host keys
- **ConnectTimeout 10s**: Fast failure on unreachable hosts

The SSH socket path is deterministically hashed from `user@host:port` — multiple sessions to the same host share the socket.

## Execution Model

- **Spawn-per-call**: Every `terminal()` spawns a fresh `ssh ... bash -c 'command'` process
- **Persistent shell**: Env vars (from `~/.bashrc`, shell init) persist via session snapshot mechanism
- **CWD**: Tracks remote working directory between calls via in-band stdout markers
- **Login shell**: Use `--login` flag in commands when you need a login shell (`bash -l -c '...'`)

## File Ownership When Using a Different SSH System User

If the SSH user on the remote (`ssh_user`) is **different** from the user who owns the files you need to modify, newly created files get wrong ownership:

| Operation | Creates file as | Problem? |
|-----------|----------------|----------|
| `terminal("touch /home/dr/test")` via SSH as `hermes` user | `hermes:hermes` | 🔴 **Mixed ownership in `dr`'s home** |
| `terminal("echo >> /home/dr/existing-file")` via SSH as `hermes` | Doesn't change ownership (file stays `dr:dr`) | 🟢 OK — but needs ACL or `o+w` on directory |
| `write_file()` via scp | `hermes:hermes` | 🔴 **Same problem** |
| `patch()` via sed | Doesn't change ownership | 🟢 OK |
| `sudo -u dr touch /home/dr/test` via SSH as `hermes` | `dr:dr` | ✅ Correct, but needs sudoers config |

### When This Bites You

If you create a dedicated system user (e.g. `hermes`) specifically for the SSH backend to use, every `write_file()` or `terminal()` that creates a file under `/home/dr/` will leave `hermes:hermes` ownership. Over time, `dr`'s home directory accumulates mixed-ownership files — confusing `ls -la` output, broken service restarts, permission-denied errors.

### Best Practice

**Do not create a separate system user on the remote for Hermes SSH access.** Instead:

- **Reuse the existing user** (`dr` in this setup) — SSH as `dr`, all files stay `dr:dr`.
- Or use SSH key restriction with `command=` to force `sudo -u dr` (but this breaks `scp`-based write_file, which is used by FileSyncManager).
- Or accept the ownership mix and schedule a cleanup: `find /home/dr/ -user hermes -exec chown dr:dr {} +`.

The cleanest approach for multi-machine coordination is **not SSH at all** — see `hermes-multi-instance-coordination` for cross-machine patterns using MCP.

## Verification Checklist

```bash
# 1. Basic connectivity
ssh dr@serverhost 'hostname'

# 2. Hermes profile connectivity
my-remote-agent chat -q "hostname && echo '=== ENV ===' && env | grep -i hermes"

# 3. File operations work remotely
my-remote-agent chat -q "cat /etc/hostname && ls ~/"

# 4. No Hermes config collision
# Check that remote's ~/.hermes/ still has its own state
ssh dr@serverhost 'ls -la ~/.hermes/config.yaml'
```

## Related

- `hermes-command-restrictions` — SSH server-side restrictions (Hermes has no built-in per-host blocklist)
- Profile docs: `hermes profile --help` or https://hermes-agent.nousresearch.com/docs/user-guide/profiles
