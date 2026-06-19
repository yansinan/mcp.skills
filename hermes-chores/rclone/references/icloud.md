# iCloud Drive + iCloud Photos (rclone backend)

Source: https://rclone.org/iclouddrive/ (verified 2026-06 against rclone v1.74.3)

## Critical: do NOT use app-specific passwords

The official rclone docs explicitly state:

> "IMPORTANT: App-specific passwords are not accepted. Only use your regular Apple ID password and 2FA."

Many blog posts and old forum threads (including on rclone's own forum) recommend app-specific passwords — these are **outdated**. The current backend (since v1.65) uses SRP (Secure Remote Password protocol), not the older auth flow that accepted app-specific passwords.

If a user says "rclone iCloud auth keeps failing", check whether they're pasting an app-specific password first.

## Auth flow (rclone v1.65+)

1. rclone initiates SRP key exchange — password is used locally to derive a key, never sent to Apple
2. Apple sends a 2FA prompt to trusted device(s), or allows `sms` to request a text
3. User enters the 6-digit 2FA code → rclone receives a **trust token** valid for ~30 days
4. Trust token stored in `rclone.conf` for silent re-auth during the window

## Two services

- `drive` (default) — iCloud Drive
- `photos` — iCloud Photos (full photo library)

Switch with `--iclouddrive-service photos` on the command line, or `service = photos` in the config block.

## Advanced Data Protection (ADP)

If ADP (end-to-end encryption) is enabled on the Apple ID:

- After 2FA, rclone requests **PCS cookies** (Private Computing Service)
- Apple may require an **extra approval prompt on a trusted device**
- If approval fails: `Missing PCS cookies from the request` or `requestPCS:` error
- Fix: `rclone reconnect <name>` and complete the device-side approval
- A stale `cookies` entry in the config can also cause this — clear it during reconnect

## When the trust token expires

`rclone reconnect <name>` — re-runs 2FA, refreshes trust token. Use this for cron jobs / systemd timers that fail after ~30 days.

## Common errors

| Error | Cause | Fix |
|-------|-------|-----|
| `Missing PCS cookies` | ADP approval incomplete | `rclone reconnect` + approve on trusted device |
| `requestPCS:` error | Same as above | `rclone reconnect` + approve on trusted device |
| `HTTP 400` on config | Stale rclone / missing user-agent | Update rclone; some setups need an explicit user-agent |
| Auth keeps failing | Probably using app-specific password | Switch to main Apple ID password |
| 2FA code never arrives | Trusted device not set up, or push notifications disabled | Use the `sms` option to request a text code |

## Verification

```bash
rclone lsd icloud:                                    # iCloud Drive root
rclone tree icloud: --max-depth 2                     # Browse structure
rclone lsd icloud: --iclouddrive-service photos       # iCloud Photos
rclone copy icloud:Documents/small.pdf /tmp/          # Test download
```

## What to ask the user up front

1. Apple ID email + **main** password (not app-specific)
2. A trusted device for 2FA — or willingness to receive `sms`
3. Whether they have ADP enabled — if yes, warn about the extra trusted-device approval
4. Recommend `s) Set configuration password` so credentials aren't plaintext in `~/.config/rclone/rclone.conf`

## Region notes

Mainland China Apple IDs (21cn / 163 / qq registered) sometimes behave differently. Not documented officially; if auth fails for non-obvious reasons after the basics are correct, this is a likely suspect.

## Config file layout

`~/.config/rclone/rclone.conf` for an iCloud remote:

```ini
[icloud]
type = iclouddrive
apple_id = user@example.com
password = Wx5erg96...         # SRP-encrypted blob, NOT the actual password
_auth_session = eyJz...        # trust token (~30-day validity, hidden in config view)
cookies = dslang=US-EN; ...    # session cookies (incl. ADP PCS cookies if enabled)
```

- `password` is an SRP-derived blob, not the literal password. rclone displays it as `*** ENCRYPTED ***` in `rclone config`. This is normal.
- `_auth_session` and `cookies` are only present after a successful 2FA round-trip. If they're missing or stale, the next `rclone lsd` fails with an auth error → fix with `rclone reconnect <name>`.
- If you set a config password via `s) Set configuration password`, the **whole file** is encrypted at rest, and all fields render as `*** ENCRYPTED ***` regardless of underlying type.

## If `rclone config` asks for 2FA mid-edit

When you run `rclone config` → `e` (edit) → select a remote, the wizard steps through every option. If the saved trust token is invalid/expired, the wizard stops at:

```
Option config_2fa.
Two-factor authentication: enter your 2FA code or type 'sms' for a text message
config_2fa>
```

**Gotcha:** sending `q\n` to abort at this prompt makes rclone submit `q` to Apple as the 2FA code → `Incorrect Verification Code` → process exits with code 2. The original config is left as-is (no partial write), but you've burned a 2FA attempt against your Apple account for nothing.

**Right move:**

- **Ctrl+C** to abort cleanly. Then `rclone reconnect <name>` — that's the dedicated re-auth command, asks for 2FA at the end, and is the path you want.
- If 2FA is required and you don't have a trusted device ready, just abort — nothing was saved by the failed edit.

## iCloud Photos directory structure

When `service = photos`:

```
<remote>:
├── PrimarySync/
│   ├── All Photos/
│   ├── Favorites/
│   ├── <album-name>/         ← User-created albums
│   └── Recently Deleted/
└── Shared/                    ← Shared photo albums (收到的共享相簿)
    └── <shared-album-name>/
```

- `ZONE_NOT_FOUND` on any sub-path = iCloud Photos never initialized for this Apple ID. Enable on a device or via icloud.com.
- `Shared/` root returns empty list if no shared albums exist, or `directory not found` if the zone was just created and indexes haven't synced yet.

## 2FA codes are session-bound (critical timing chain)

This is the #1 gotcha when an agent drives rclone iCloud config:

1. Agent starts `rclone config reconnect <remote>:`  → triggers SRP handshake + Apple push to iPhone
2. User, seeing the push, taps Allow, gets a 6-digit code
3. User types the code in chat → agent submits it
4. **But**: between step 1 and step 3, rclone may have exited (e.g. from a prior failed attempt) → the code is orphaned
5. Apple rejects with `HTTP 400: Incorrect Verification Code` (error -21669)

Each `rclone config reconnect` generates a distinct SRP session + distinct push. Old codes are never valid for new sessions. If rclone exits between the push and the code submission, the code is dead.

**Fix for agent-driven auth**: 
- Use SMS (`sms` at the 2FA prompt) — SMS codes are NOT session-bound and tolerate timing gaps.
- Or: start reconnect, then tell user to **wait for the new push from THIS reconnect** before tapping Allow and sending the code. The agent must NOT have started a reconnect before receiving the code.

**Fix for user-driven auth** (recommended):
- Let the user run `rclone config reconnect <remote>:` in their own terminal. They see the push, approve it, enter the code directly. No timing race.

## Common errors

| Error | Cause | Fix |
|-------|-------|-----|
| `Incorrect Verification Code` (HTTP 400, code -21669) | Sent a bad 2FA code to Apple — usually the `q`-as-abort mistake, or a stale code from a previous session | Ctrl+C out, then `rclone reconnect <name>` and provide a real code tied to the current session |
| HTTP 302: `"domainToUse":"iCloud.com.cn"` | Apple ID registered in mainland China → route to iCloud.com.cn | Use a non-China Apple ID, or build rclone from PR #9399 (see SKILL.md) |
| `ZONE_NOT_FOUND` | Never-before-used iCloud Photos library on this Apple ID | Enable iCloud Photos on a device or icloud.com, wait 5–30 minutes |
| `directory not found` for PrimarySync/ or Shared/ | Photos zone created but indexes not populated yet | Wait 5–10 minutes; try again |
