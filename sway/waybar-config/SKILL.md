---
name: waybar-config
description: "Manage Waybar configuration — launcher buttons, custom modules, module ordering, and PWA sync. Class-level umbrella for Waybar config maintenance tasks."
---

# Waybar Configuration Management

Workflow for maintaining Waybar config files (`~/.config/waybar/config-top`, `config-bottom`, `style.css`).

## Sync Chrome PWAs to Waybar launcher buttons

### Step 1: Discover installed PWAs
```bash
for f in ~/.local/share/applications/chrome-*.desktop; do
  echo "=== $(basename $f) ==="
  grep -E '^Name=' "$f" 2>/dev/null
  grep -E '^Exec=' "$f" 2>/dev/null | head -1
  echo
done
```

Key fields to extract from each `.desktop` file:
- **`Name=`**: display name (the PWA title)
- **`Exec=`**: contains `--app-id=<id>` — this is the Chrome app ID used in waybar `on-click`
- **`--app-launch-url-for-shortcuts-menu-item=`**: the actual URL the PWA connects to (HTTP vs HTTPS). Only present if the PWA has a "New conversation" or similar action.

### Step 2: Identify connection protocol
The `--app-launch-url-for-shortcuts-menu-item` reveals the destination URL:
- `http://localhost:8787/` → local HTTP
- `https://hermes-x1tablet.tail2e6efb.ts.net/` → Tailscale HTTPS
- Absent → no explicit URL (bare app-id launch)

When the user says "重复的只保留 https 连接的", keep the PWA whose shortcut URL starts with `https://` and remove the HTTP/unknown ones.

### Step 3: Cross-reference against waybar config
Compare the installed app-ids from `.desktop` files against the `--app-id=` values in `modules-left` entries of `config-top`.

**Stale app-id detection**: if an `.desktop` file exists for `app-id=A` but the waybar config references `app-id=B` for the same named app (e.g. code-server), B is stale. Update B → A.

**Missing detection**: if a PWA is installed but has no corresponding `custom/<name>` entry in waybar, it needs a new module.

**Orphan detection**: if a waybar `custom/<name>` entry references an app-id with no matching `.desktop` file, it's stale and should be removed.

### Step 4: Update waybar config
When updating `config-top`:
1. Fix stale app-ids in existing module definitions
2. Remove duplicate entries (keep HTTPS, remove HTTP/localhost)
3. Add new modules for newly discovered PWAs
4. Update the `modules-left` array to match — remove deleted module names, append new ones

### Step 5: Reload waybar
```bash
killall -SIGUSR2 waybar
```

### Naming convention for PWA launcher modules
| Module name | PWA | app-id (example) |
|---|---|---|
| `custom/term` | Terminal (foot) | n/a (native app) |
| `custom/chrome` | Chrome browser | n/a |
| `custom/fuzzel` | App launcher | n/a |
| `custom/code-server` | code-server | `anlhgcnfglodaccjojnfbabpjidhenop` |
| `custom/hermes` | Hermes (HTTPS) | `hbieppijmjjnadmpdpddnobiafcncocm` |
| `custom/rclone-webui` | Rclone WebUI | `hkmbpfkfjpljkndchoakjhmcpefichen` |
| `custom/rclone-webui-ip` | Rclone WebUI IP | `jaemjmjciacjhaekaofmdbfnibifddph` |

### Pitfalls
- `.desktop` file names don't reliably match app-id — always grep the **content**, not the filename.
- A PWA re-install (e.g. after clearing browser data) gets a **new random app-id**. Always verify `.desktop` app-ids match waybar entries.
- `chrome-<name>.desktop` (named shortcut) and `chrome-<appid>-Default.desktop` (auto-generated) can coexist for the same PWA. Use the one with the actual `Exec` line.
- `Name=` in `.desktop` may conflict between different PWA instances (e.g. three Hermes PWAs all named "Hermes"). Disambiguate via the shortcut URL.

