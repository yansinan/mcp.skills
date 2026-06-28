# ncm-cli as Alternative Backend

## Why

api-enhanced (`ncm.z-core.cn`) has unreliable QR login (returns code 800 instead of 803 after phone authorization). ncm-cli uses a different login mechanism (Playwright + Chrome browser automation) and is stable.

## Installation

```bash
# Install prebuilt binary + Playwright driver (no Go needed)
PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright \
npx --yes github:Davied-H/ncm-cli install --dir ~/.local/bin --with-playwright-driver
```

Binary installed to `~/.local/bin/ncm` (~7.7MB).

**Name conflict**: the bash `ncm` dispatcher is at the same path. Rename it first:
```bash
mv ~/.local/bin/ncm ~/.local/bin/ncm-player
```

## Login

```bash
ncm login
```
Opens Chrome via Playwright → navigates to music.163.com → user completes login → session saved to `~/.config/ncm-cli/session/` as Playwright storage state.

For headless mode (QR in terminal):
```bash
ncm login --headless
```

## Key Commands

```bash
ncm me --json              # check login status
ncm url <song-id> --json   # get playback URL
ncm playlist list --json   # list playlists
ncm playlist show <id> --json  # get songs in a playlist
ncm login                  # login (browser)
ncm recommend songs --json # daily recommendations
```

## Integrating with ncm.lua

Replace `api_get()` calls with `ncm <cmd> --json` subprocess calls. Example:

```lua
-- Before (api-enhanced):
local data, err = http_get("/song/url/v1", {id = sid, level = song_level}, cookie)

-- After (ncm-cli):
local r = mp.command_native({
    name = "subprocess",
    args = {"ncm", "url", tostring(sid), "--json"},
    capture_stdout = true,
    playback_only = "no",
})
if r.status == 0 then
    local data = utils.parse_json(r.stdout)
    local url = data and data[1] and data[1].url
end
```

Note: unlike api-enhanced which returns `{code:200, data:[{url:...}]}`, ncm-cli returns the raw array directly.

## Verifying Installation

```bash
ncm version --json
# {"version": "0.2.1", "commit": "7cd31ae24f76"}

ncm me --json
# -> "未找到登录态，请先执行 ncm login" (before login)
# -> {"code": 200, "profile": {"userId": 123, "nickname": "..."}} (after login)
```

## Pitfalls

- ncm-cli `ncm login` opens a visible Chrome window. On a headless server it may hang. Use `--headless` for QR mode.
- The `ncm` binary overwrites the bash dispatcher at the same path. Always rename the dispatcher first.
- ncm-cli uses its own cookie/session storage (`~/.config/ncm-cli/session/`), NOT the `~/.local/share/ncmctl/cookie` file used by api-enhanced.
