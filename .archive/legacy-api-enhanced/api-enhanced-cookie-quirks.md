# api-enhanced Cookie / Response Quirks

NetEase Cloud Music's third-party API backends (NeteaseCloudMusicApiEnhanced,
yesPlayMusic, etc.) follow a non-standard pattern for cookie placement and
status codes. Other backends (Spotify, librespot, etc.) likely have similar
quirks — these notes document the api-enhanced specifics verified by reading
the source code at <https://github.com/NeteaseCloudMusicApiEnhanced/api-enhanced>.

## Login cookie lives in `body.cookie`, not `Set-Cookie`

After a successful QR scan (`code: 803`), the response is:

```json
{
  "code": 803,
  "message": "...",
  "cookie": "MUSIC_U=xxx; MUSIC_A=yyy; __csrf=zzz; NMTID=...",
  ...
}
```

The actual login cookies (`MUSIC_U`, `MUSIC_A`, `__csrf`) are in `body.cookie`.
The Set-Cookie header may also be present, but typically only carries the
anonymous `NMTID` tracking cookie.

**Source** — `module/login_qr_check.js`:

```js
let result = await request(`/api/login/qrcode/client/login`, data, createOption(query))
result = {
  status: 200,
  body: {
    ...result.body,                              // upstream NetEase body (code 800/801/802/803)
    cookie: result.cookie.join(';'),            // <-- login cookie here
  },
  cookie: result.cookie,
}
```

The `result.cookie` array comes from the upstream NetEase response Set-Cookie
header, which IS where MUSIC_U lives. api-enhanced flattens that into the body
for easier access by API consumers.

**Implication for ncm-login**: read the body field first, fall back to header
only if body.cookie is absent.

```python
# Good
if code == 803:
    cookie_str = r.get("cookie", "")
    if not cookie_str:
        # Set-Cookie fallback (some api-enhanced versions / forks)
        cookies = r.get("_cookies") or []
        cookie_str = "; ".join(c.split(";", 1)[0] for c in cookies)
    COOKIE_FILE.write_text(cookie_str + "\n", encoding="utf-8")
```

A ncm-login that only reads `Set-Cookie` will save NMTID only — every
subsequent `/like`, `/user/playlist`, `/personal_fm` (logged-in variants) will
return `{"code":301,"msg":"需要登录"}`.

## `Set-Cookie` on anonymous endpoints = NMTID trap

The FIRST unauthenticated request to any api-enhanced endpoint (e.g.
`/login/qr/key`) returns `Set-Cookie: NMTID=...`. This is an anonymous
tracking cookie, NOT an auth signal. A ncm-login that checks
`if "Set-Cookie" in response.headers: return auth-success-dict` will
return early on the first request and never reach the QR generation step.

**Fix**: parse JSON first, only treat `Set-Cookie` specially on
`/login/qr/check` (the one endpoint where it might carry MUSIC_U).

## Status codes for `/login/qr/check`

| Code | Meaning | Has MUSIC_U? |
|---|---|---|
| 800 | QR expired or doesn't exist | no (just NMTID in `cookie` field) |
| 801 | Waiting for user to scan | no |
| 802 | User scanned, awaiting confirmation in app | no |
| 803 | **Login success** | **yes — read `body.cookie`** |

The `cookie` field is present in ALL responses (always NMTID), but MUSIC_U
only appears in 803. Don't pattern-match on the presence of the `cookie`
field; pattern-match on `code == 803` AND length of cookie string containing
`MUSIC_U=`.

## `/personal_fm` returns PUBLIC data when unauthenticated

The personal FM endpoint works for unauthenticated requests — it returns
public recommendations, not user-personalized ones. This is useful for the
"try before you log in" flow: even without a cookie, `ncm fm` plays a song
and the IPC `script-message` flow works end-to-end. Login only matters for
`/like`, `/user/playlist`, `/likelist` — anything that touches user state.

This is also why `ncm fm` (and the waybar FM button) works even when the user
hasn't scanned the QR — the API happily returns public recommendations.

## `/song/url/v1` works without cookie too

`/song/url/v1?id=<id>&level=standard` returns a signed MP3 URL even for
unauthenticated requests. The signed URL is bound to the requester IP and
short-lived (~30 min), but enough to start playback. So mpv can stream
songs and play them via mpris without ever logging in.

The user only NEEDS to log in for: like/unlike, accessing user playlists,
showing liked-songs, sync state to cloud.

## Verifying response shape changes

When the api-enhanced backend changes a response shape, the symptom is
"endpoint returns 200 but ncm.lua sees nil/empty data". To debug, curl the
endpoint directly and inspect the actual JSON:

```bash
curl -s http://ncm.z-core.cn/login/qr/check?key=TEST | python3 -m json.tool
```

If the body shape changed (field renamed, status code added/removed), the
fallback is to read the api-enhanced source for that module:

```bash
# Login
curl -s https://raw.githubusercontent.com/NeteaseCloudMusicApiEnhanced/api-enhanced/main/module/login_qr_check.js
curl -s https://raw.githubusercontent.com/NeteaseCloudMusicApiEnhanced/api-enhanced/main/module/login_qr_key.js
curl -s https://raw.githubusercontent.com/NeteaseCloudMusicApiEnhanced/api-enhanced/main/module/login_qr_create.js

# Music
curl -s https://raw.githubusercontent.com/NeteaseCloudMusicApiEnhanced/api-enhanced/main/module/personal_fm.js
curl -s https://raw.githubusercontent.com/NeteaseCloudMusicApiEnhanced/api-enhanced/main/module/song_url_v1.js
```

Each module is small (50-100 lines) and shows the upstream API call + the
response shape api-enhanced exposes. Compare the actual response against
what your Lua code expects.

## Verifying cookie validity

If the user reports "login was successful but `/like` still returns 301",
the cookie file may have been written with only NMTID (the previous bug).
Check the file size and content:

```bash
ls -la ~/.local/share/ncmctl/cookie
cat ~/.local/share/ncmctl/cookie | tr ';' '\n' | head
# Should show MUSIC_U, MUSIC_A, __csrf, NMTID
# If only NMTID, login was incomplete — re-scan QR
```
