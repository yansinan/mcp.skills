# Player Module Audit — 2026-06-23

## Scope
Audit of all waybar modules-right player-related modules: data flow, polling intervals,
CSS styling, and cross-module consistency.

## Architecture (as found)

```
ncm (Go v0.2.1)            ncm-cli (npm v0.1.6)       mpv-mpris.so
─── 数据操作层               ─── 播放控制层              ─── D-Bus 桥接层
• search / playlist        • play / pause / next       • org.mpris.MediaPlayer2.mpv
• recommend songs          • state / login --check     • waybar mpris 模块消费
• playlist list/show       • volume                    • event-driven (非轮询)
       │                           │
       ▼                           ▼
  ncm-playlist (Python)    ncm-player (bash dispatcher)
  fuzzel 双层选歌                     │
                                    ▼
                               mpv (headless, idle)
```

## modules-right layout (player section, modules 1–8)

| # | 模块 | 方式 | 间隔 | exec | 输出 | on-click | 耗时/次 |
|---|------|------|------|------|------|----------|---------|
| 1 | `mpris` | event | 0 | — | 歌曲标题 (D-Bus) | ncm-player toggle | 0ms |
| 2 | `custom/ncm-status` | poll | 3s | ncm-player status-button | 🔌/🔋 (登录状态) | foot -a ncm-login ... | ~365ms |
| 3 | `custom/ncm-fm` | poll | 30s | ncm-player logged_only FM | "FM" / 空(未登录) | ncm-player fm | ~365ms |
| 4 | `custom/ncm-pl` | poll | 30s | ncm-player playlist-button | 🎵 / 空(未登录) | ncm-player pl | ~365ms |
| 5 | `custom/ncm-prev` | static | — | — | ⏈ (固定) | ncm-player prev | 0ms |
| 6 | `custom/ncm-like` | poll | 3s | ncm-player like-button | ♡ (固定，无登录检查) | ncm-player like | ~365ms |
| 7 | `custom/ncm-play` | poll | 1s | ncm-player play-button | ▶/⏸ | ncm-player toggle | ~365ms |
| 8 | `custom/ncm-next` | static | — | — | ⏑ (固定) | ncm-player next | 0ms |

## Key findings

### P1: ncm-cli login --check called 34,560×/day

`ncm-cli` is a Node.js binary. Each invocation has ~365ms startup overhead.
Three modules call `check_login()` → `ncm-cli login --check` on every poll:
- ncm-status (3s) = 28,800 calls/day
- ncm-fm (30s) = 2,880 calls/day
- ncm-pl (30s) = 2,880 calls/day

**Daily CPU waste**: 34,560 × 0.365s ≈ 3.5 CPU-hours.

**Fix**: Create a local login cache file `~/.local/share/ncmctl/.logged_in`.
- On login success: `touch .logged_in`
- On login check: stat mtime → if < 60s old, return cached result without calling ncm-cli
- On logout/clear: `rm -f .logged_in`

### P2: ncm-play polls at 1s regardless of playback state

`interval: 1` calls `ncm-cli state` every second, even when mpv is stopped.
The 1s interval only makes sense during active playback (to show ▶↔⏸ toggle).

**Fix**: Increase to 3s for all states, or add a dead-man check (stop polling if mpv has been idle for >30s).

### P3: like-button always outputs ♡, no login check

```bash
like-button)   printf '\U00002661' ;;
```
Unlike `playlist-button` and `logged_only`, `like-button` does NOT call `check_login()` before outputting the heart. And `ncm-cli` has no `like` command — clicking the button shows "红心暂不支持" notification.

**Fix**: Add login check to like-button, output empty string when not logged in.

### P4: Dual state source (MPRIS vs ncm-cli)

Waybar has TWO independent state sources for music:
1. `mpris` module — event-driven via D-Bus (fast, accurate)
2. `ncm-*` modules — polling via ncm-cli (slow, can diverge)

They can disagree when:
- ncm-cli reports "stopped" but mpv D-Bus still shows the previous track
- mpv is idle but ncm-cli just initiated a play

### P5: Missing CSS for ncm modules

Only 3 of 6 ncm modules have CSS rules:
```css
#custom-ncm-fm, #custom-ncm-pl, #custom-ncm-like { min-width: 0; }
```

No styles for: `ncm-status`, `ncm-prev`, `ncm-play`, `ncm-next`
No play-vs-paused visual differentiation despite different icon output.

### P6: waybar-pwa-gen.py sort_keys=True

`waybar-pwa-gen.py` writes the entire config-back with `sort_keys=True`:
```python
tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n")
```
This silently alphabetizes all JSON keys, losing any intentional ordering.
It only touches modules-left and PWA custom/* blocks, but the full-file rewrite
with `sort_keys=True` means non-PWA sections may also get reordered.

## State.json gap

`ncm-playlist` writes current track info to `~/.local/share/ncmctl/state.json`:
```json
{
  "current_id": 3394747492,
  "current_artist": "贊詩",
  "current_title": "上蔡无量寺",
  "current_url": "http://m801.music.126.net/..."
}
```
But NO waybar module reads this file — all state comes through ncm-cli.
This is a missed opportunity for a fast state cache.

## mpv-mpris plugin loading

The plugin `.so` at `/usr/lib/mpv-mpris/mpris.so` is installed by the Debian package
`mpv-mpris` (v0.7.1-1). The sway config launches mpv WITHOUT an explicit
`--script=` flag:
```bash
exec mpv --idle=yes --no-video --no-terminal --input-ipc-server=/tmp/ncm-mpv.sock --quiet
```
Yet `playerctl -l` shows `mpv` and `busctl` confirms `org.mpris.MediaPlayer2.mpv`.
The plugin loads via the Debian package's auto-registration mechanism.
For resilience, add `--script=/usr/lib/mpv-mpris/mpris.so` explicitly.
