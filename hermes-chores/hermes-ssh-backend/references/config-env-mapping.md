# SSH Backend Config-to-Env Mapping

Derived from `hermes_cli/config.py::TERMINAL_CONFIG_ENV_MAP` (line 5484) and `tools/terminal_tool.py`.

## Config → Env Var

```
terminal.backend              → TERMINAL_ENV
terminal.ssh_host             → TERMINAL_SSH_HOST
terminal.ssh_user             → TERMINAL_SSH_USER
terminal.ssh_port             → TERMINAL_SSH_PORT
terminal.ssh_key              → TERMINAL_SSH_KEY
terminal.cwd                  → TERMINAL_CWD
terminal.timeout              → TERMINAL_TIMEOUT
terminal.lifetime_seconds     → TERMINAL_LIFETIME_SECONDS
terminal.persistent_shell     → TERMINAL_PERSISTENT_SHELL
terminal.modal_mode           → TERMINAL_MODAL_MODE
terminal.sandbox_dir          → TERMINAL_SANDBOX_DIR
terminal.docker_image         → TERMINAL_DOCKER_IMAGE
terminal.docker_forward_env   → TERMINAL_DOCKER_FORWARD_ENV
terminal.singularity_image    → TERMINAL_SINGULARITY_IMAGE
terminal.modal_image          → TERMINAL_MODAL_IMAGE
terminal.daytona_image        → TERMINAL_DAYTONA_IMAGE
terminal.container_cpu        → TERMINAL_CONTAINER_CPU
terminal.container_memory     → TERMINAL_CONTAINER_MEMORY
terminal.container_disk       → TERMINAL_CONTAINER_DISK
terminal.container_persistent → TERMINAL_CONTAINER_PERSISTENT
```

## SSHEnvironment Constructor

Source: `tools/environments/ssh.py` line 45-46

```python
def __init__(self, host: str, user: str, cwd: str = "~",
             timeout: int = 60, port: int = 22, key_path: str = ""):
```

## SSH Command Builder

Source: `tools/environments/ssh.py` line 83-98

```python
def _build_ssh_command(self, extra_args: list | None = None) -> list:
    cmd = ["ssh"]
    cmd.extend(["-o", f"ControlPath={self.control_socket}"])
    cmd.extend(["-o", "ControlMaster=auto"])
    cmd.extend(["-o", "ControlPersist=300"])
    cmd.extend(["-o", "BatchMode=yes"])
    cmd.extend(["-o", "StrictHostKeyChecking=accept-new"])
    cmd.extend(["-o", "ConnectTimeout=10"])
    if self.port != 22:
        cmd.extend(["-p", str(self.port)])
    if self.key_path:
        cmd.extend(["-i", self.key_path])
    if extra_args:
        cmd.extend(extra_args)
    cmd.append(f"{self.user}@{self.host}")
    return cmd
```

## FileSyncManager Behavior

Source: `tools/environments/ssh.py` line 71-78

On startup, syncs from local `~/.hermes/` to `{remote_home}/.hermes/`:
- Skills (`skills/`)
- Credentials (`credentials/`)
- Cache (`cache/`)

On cleanup (line 355-358), syncs back: downloads remote changes to local.

The `_ensure_remote_dirs()` method (line 143-155) creates these dirs if absent:
- `{remote_home}/.hermes/`
- `{remote_home}/.hermes/skills/`
- `{remote_home}/.hermes/credentials/`
- `{remote_home}/.hermes/cache/`
