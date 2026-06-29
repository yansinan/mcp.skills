# NeteaseCloudMusicApiEnhanced / api-enhanced — endpoint map

**Verified**: 2026-06-22 against the public Vercel instance `https://ncm-api-wine.vercel.app/`.

The Vercel deployment is the same Node.js backend that ships from
`https://github.com/NeteaseCloudMusicApiEnhanced/api-enhanced` — it's an
unofficial mirror of the community-maintained `api-enhanced` (a revival of the
archived `Binaryify/NeteaseCloudMusicApi`).

Full online docs: <https://neteasecloudmusicapienhanced.js.org/>
Docker image: <https://hub.docker.com/r/moefurina/ncm-api>

---

## Endpoints actually needed for a minimal client

| Need | Method | Path | Auth | Notes |
|---|---|---|---|---|
| Search songs | GET | `/search?keywords=...&limit=30` | — | Returns `{songs:[{id,name,artists,...}], songCount, hasMore}` |
| Song mp3 URL | GET | `/song/url/v1?id=...&level=standard` | **cookie** | `level=standard\|higher\|exhigh\|lossless\|hires`; **returns null URL if no cookie**, even for free songs |
| Lyrics | GET | `/lyric?id=...` | — | Returns `{lrc:{lyric}, tlyric:{lyric}}` for translated |
| Personal FM (私人雷达) | GET | `/personal_fm` | cookie | Returns 1-3 songs; **call repeatedly** to advance |
| Like / unlike | GET | `/like?id=...&like=true\|false` | cookie | Returns `{code:200}` on success |
| My playlists | GET | `/user/playlist?uid={userId}` | cookie | Get uid from `/user/account` first |
| Playlist detail | GET | `/playlist/detail?id=...` | cookie (for full) | Returns `{playlist:{tracks:[...]}}` |
| QR login key | GET | `/login/qr/key` | — | Returns `{data:{unikey}}` |
| QR image | GET | `/login/qr/create?key={unikey}&qrimg=true` | — | Returns `{data:{qrurl, qrimg:base64PNG}}` |
| QR poll | GET | `/login/qr/check?key={unikey}&timestamp={ms}` | — | Poll every 2s; `code=801` waiting, `code=802` scanning, `code=803` authorized (response Set-Cookie has MUSIC_U) |
| Current user | GET | `/user/account` | cookie | Returns `{profile:{userId,nickname}, account:{...}}` — needed to get `uid` for `/user/playlist` |
| Banner (homepage) | GET | `/banner` | — | Returns `{banners:[{targetId,picUrl,...}]}` — useful for "daily recommended" cards |

**End-to-end verified working on Vercel**: search, banner, fm, qr-key, lyric. Endpoints marked **cookie** confirmed: `/like`, `/user/playlist`, `/user/account` return `{code:301, msg:"需要登录"}` without cookie.

---

## Cookie format & persistence

After QR `code=803`, the response `Set-Cookie` header contains multiple `Set-Cookie:` lines. The two you need are:
- `MUSIC_U=` — main user token
- `MUSIC_A=` — anonymous user fallback

Both are HttpOnly cookies. Persist them as a single `Cookie:` header value:

```
MUSIC_U=xxx; MUSIC_A=yyy; __csrf=zzz; ...
```

Concatenate all cookie values; reorder not required. Store at:
`~/.local/share/ncmctl/cookie` (chmod 600).

Send on every authenticated call:
```
curl -H "Cookie: $(cat ~/.local/share/ncmctl/cookie)" \
     "https://ncm-api-wine.vercel.app/personal_fm"
```

---

## Public API quirks

- **Cold start ~6s**: Vercel spins down between requests. First song fetch after idle may take 6s. Mitigation: run a `--keep-alive` ping script in background, or accept the latency. Self-hosted Docker doesn't have this.
- **No rate limit headers** exposed — service is "fair use". Heavy playlist loads (>50 songs) may 429; back off and retry.
- **Cookie persistence on public API**: the Vercel deployment is operated by a third party. They can in principle read your MUSIC_U token. Risk level: same as using any unofficial Netease client. Mitigation: rotate password if you see 异地登录 alerts; or deploy your own.
- **HTTP 200 with `code:301`** is the auth-failure pattern (not 401/403). Always check the JSON `code` field, not just HTTP status.
- **NMTID cookie false positive in QR login**: `/login/qr/key` (and any first request) returns `Set-Cookie: NMTID=...` — NMTID is a *tracking* cookie, not an auth cookie. If your `api_get()` short-circuits on `Set-Cookie` to extract the auth token, you'll treat NMTID as login success, the response will be `{"_raw": b"...", "_cookies": [...]}`, `r.get("code") != 200` will be true, `die()` fires, and the floating foot window flash-closes. **Fix**: parse JSON first, then attach `_cookies` only when path is `/login/qr/check`. Example:

  ```python
  def api_get(path, params=None, cookie=""):
      # ... build req ...
      with urllib.request.urlopen(req, timeout=10) as resp:
          data = resp.read()
          try:
              parsed = json.loads(data)        # parse first, always
          except Exception:
              return {"code": -1, "msg": "JSON parse error"}
          if path.endswith("/login/qr/check") and "Set-Cookie" in resp.headers:
              parsed["_cookies"] = resp.headers.get_all("Set-Cookie")
          return parsed
  ```

---

## When to self-host instead

Self-host `api-enhanced` in Docker (or on your always-on server) when:
1. You want cookie privacy (serverhome is ideal — tailscale, already running)
2. Vercel cold-start latency is annoying
3. You need endpoints the public instance might not enable

Minimum Docker run:
```bash
docker run -d --name ncm-api \
  -p 3000:3000 \
  --restart unless-stopped \
  moefurina/ncm-api:latest
```
Then point your client at `http://localhost:3000` (or `http://serverhome:3000` on tailscale).

For serverhome: same command, but use `tailscale0` IP and ensure ncm-api is in the right Docker network. Document alongside your other servicehome services (LiteLLM, nginx, etc.).

---

## Self-host vs public: script config snippet

In your control script, support both via env var:
```python
import os
API_BASE = os.environ.get("NCM_API_BASE", "https://ncm-api-wine.vercel.app")
# override: NCM_API_BASE=http://serverhome:3000 ncmctl search foo
```