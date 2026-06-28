# Event-Driven Cache Architecture (v3, 2026-06-24)

## The problem with v2 (daemon busy loop)

```bash
daemon)
    while ...; do
        state=$(ncm_status)         # 2s × 30/min = 30 calls/min
        check_login                  # 60s × 1/min (with cache)
        # ... write state.json
        sleep 2
    done
```

Total: **1860 ncm-cli calls/hour**, all just to keep one icon (📻/⏹) up to date.

## The v3 redesign (event-driven + slow fallback)

**Truth source**: `ncm-cli state` is the only place that knows the real playback state. ncm-player and daemon are both caches; they must always read from ncm-cli, never guess.

**Triggering**:
- **Active triggers** (0-latency): `toggle` / `next` / `prev` / `heartbeat_play` / `ncm-playlist` → all call `sync_state` at the end
- **Passive trigger** (slow fallback): daemon calls `sync_state` every 10s

**Cache TTL**:
- login cache: 1h (user doesn't log out in a waybar session)
- ncm-cli state: no cache (always re-read; mpv state changes fast)

## sync_state function (canonical)

```bash
sync_state() {
  # 1. Truth: playback state (no cache)
  local ncm_state=$(ncm_status)

  # 2. Truth: login state (1h cache via check_login)
  local logged="false"
  check_login && logged="true"

  # 3. Compute icons from truth
  local play_icon like_icon pl_icon status_icon status_class
  if [ "$logged" = "true" ]; then
    case "$ncm_state" in
      playing|paused) play_icon="⏹" ;;
      *)              play_icon="📻" ;;
    esac
    like_icon="♡"; pl_icon="📋"
    status_icon=""; status_class="logged-in"
  else
    play_icon=""; like_icon=""; pl_icon=""
    status_icon="🔑"; status_class="logged-out"
  fi

  # 4. Write cache (merge /tmp/ncm-current.json's current_*)
  NCM_STATE="$ncm_state" NCM_LOGGED="$logged" \
  NCM_PLAY="$play_icon" NCM_LIKE="$like_icon" NCM_PL="$pl_icon" \
  NCM_STATUS_ICON="$status_icon" NCM_STATUS_CLASS="$status_class" python3 -c "
import os, json
s = {
  'status': os.environ['NCM_STATE'],
  'logged_in': os.environ['NCM_LOGGED'],
  'play': os.environ['NCM_PLAY'],
  'like': os.environ['NCM_LIKE'],
  'pl': os.environ['NCM_PL'],
  'status_icon': os.environ['NCM_STATUS_ICON'],
  'status_class': os.environ['NCM_STATUS_CLASS'],
}
try:\n    cur = json.load(open('/tmp/ncm-current.json'))\n    s.update({k: cur.get(k, '') for k in ('current_encrypted_id','current_title','current_artist')})\nexcept: pass\n# 保留 fav_playlist_id 和 liked_song_id（其他模块维护的字段，sync_state 不能覆盖）\ntry:\n    old = json.load(open('/tmp/ncm-state.json'))\n    if 'fav_playlist_id' in old:\n        s['fav_playlist_id'] = old['fav_playlist_id']\n    if 'liked_song_id' in old:\n        s['liked_song_id'] = old['liked_song_id']\nexcept: pass\ntry: json.dump(s, open('/tmp/ncm-state.json','w'))\nexcept: pass
" 2>/dev/null || true

  # 5. Notify waybar
  pkill -RTMIN+$STATUS_SIGNAL waybar 2>/dev/null || true
}
```

## User's architectural rule (verbatim)

> "不是 ncm-player 直接写 stats，而是播放控制动作后，读 ncm-cli stats，再写 ncm-cli stats 到缓存，统一 stats 源为 ncm-cli stats"

This is the single-most important architectural rule. ncm-player never:
- Records "I just called ncm-cli stop, so now state = stopped" (guessing)
- Hardcodes the play icon based on what command was invoked

ncm-player only:
- Invokes ncm-cli to do work
- Reads ncm-cli state to see actual result
- Writes the actual result to cache

## Call sites for sync_state

| Command | Caller | Why |
|---------|--------|-----|
| `toggle` | ncm-player | After stop/heartbeat_play |
| `next` | ncm-player | After ncm-cli next |
| `prev` | ncm-player | After ncm-cli prev |
| `heartbeat_play` | ncm-player (called by toggle) | After ncm-cli play |
| `ncm sync-state` | ncm-playlist (Python) | After ncm-cli play |
| `login` success | ncm-player | After check_login returns true |

## Performance comparison

| Metric | v2 (busy loop) | v3 (event-driven) |
|--------|----------------|-------------------|
| ncm-cli calls/hour | 1860 | **6** (1 login + 6 state) |
| toggle → icon delay | 0-2s | **0s** |
| next/prev → icon delay | 0-2s | **0s** |
| login check interval | 60s | 3600s |
| mpv-natural-end → icon | 0-2s | 0-10s (acceptable) |

## Why daemon still exists (just slow)

The daemon's primary job is now: **stay alive to handle SWAYSOCK exit detection**. The 10s sync_state is purely fallback for cases the active commands don't catch:
- mpv natural playback end
- External stop (e.g. user kills mpv via another tool)
- ncm-go-style state changes (legacy paths)

If we trusted all ncm-cli state changes to come from ncm-cli commands we issued, we could eliminate the daemon entirely. But mpv itself can transition (song ends, user pauses via playerctl), and ncm-cli reflects that. The 10s slow loop catches those.

## Edge case: like race

Before v3, `ncm like` read `/tmp/ncm-state.json`, which daemon updated every 2s. User would click toggle, see icon, immediately click like — but like failed because state.json didn't have current_encrypted_id yet.

v3 fix: `ncm like` reads `/tmp/ncm-current.json` (the freshest source, written synchronously by toggle/heartbeat_play/ncm-playlist) first, then falls back to state.json. Zero delay.

```bash
enc_id=$(NCM_CUR=/tmp/ncm-current.json NCM_STATE=/tmp/ncm-state.json python3 -c "
import os, json
for p in (os.environ.get('NCM_CUR',''), os.environ.get('NCM_STATE','')):
    try:
        d=json.load(open(p))
        v=d.get('current_encrypted_id','')
        if v: print(v); break
    except: pass
" 2>/dev/null)
```

## Audit checklist

After any ncm-player change, verify:

```bash
# 1. Bash syntax
bash -n ~/.local/bin/ncm-player

# 2. Every playback control command calls sync_state
grep -nE 'sync_state' ~/.local/bin/ncm-player
# Should appear in: toggle, next, prev, heartbeat_play, login (success), sync-state case, daemon

# 3. No command writes state.json directly (bypasses sync_state)
grep -nE 'state\.json' ~/.local/bin/ncm-player | grep -vE 'state-get|/tmp/ncm-state.json'
# Only state-get reads; sync_state is the only writer

# 4. End-to-end: toggle → 0.2s → state.json shows new play icon
ncm toggle
sleep 0.2
cat /tmp/ncm-state.json | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'status={d[\"status\"]} play={d[\"play\"]}')"
# Expect: status=playing play=⏹ (or status=stopped play=📻)
```
