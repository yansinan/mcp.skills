# MPRIS / mpv-mpris Debugging Reference

## Waybar mpris module architecture

Waybar mpris module (`src/modules/mpris/mpris.cpp`) uses **playerctl** library to:
1. Subscribe to D-Bus PropertiesChanged signals from MPRIS-compatible players
2. On signal: `update()` → `getPlayerInfo()` → queries `playback-status` via playerctl
3. `update()` has an **interval rate-limiter** (line 688-689):
   ```cpp
   if (now - last_update_ < interval_) return;
   ```
4. When status is `PLAYERCTL_PLAYBACK_STATUS_STOPPED` (line 697-699):
   ```cpp
   if (info.status == PLAYERCTL_PLAYBACK_STATUS_STOPPED) {
       spdlog::debug("mpris[{}]: player stopped, skipping update", info.name);
       return;  // Does NOT update widget — keeps showing previous content
   }
   ```
5. **BUG**: `last_update_` is set at line 690 (BEFORE the stopped check). So subsequent "Playing" signal within `interval_` seconds gets blocked by the rate-limiter. Widget never updates.

### Fix: `interval: 0` in waybar mpris config
```json
"mpris": {
    "format": " {}",
    "interval": 0,
    ...
}
```
This disables the rate-limiter so every D-Bus signal triggers `update()`.

## mpv-mpris 0.7 architecture (`mpris.c`, 1033 lines)

### How PlaybackStatus is determined

- **Initial state** (line 986): `ud.status = STATUS_STOPPED`
- **Property observations** (lines 1000-1006): observes `pause`, `media-title`, `speed`, `volume`, `loop-file`, `loop-playlist`, `duration`
- **MPV_EVENT_IDLE** (line 932-933): calls `set_stopped_status()` immediately
- **pause property change** (lines 841-849):
  - `pause=1` → STATUS_PAUSED
  - `pause=0` → STATUS_PLAYING
- **Property changes are queued** (line 908-909) and sent every 100ms by `emit_property_changes()` timer (line 1018).

### THE ROOT CAUSE BUG

When mpv starts with `--idle=yes`:
- `idle-active=true`, but `pause=false` (these are independent states)
- mpv-mpris observes `MPV_EVENT_IDLE` and forces `set_stopped_status()` — **immediately** sends "Stopped" via D-Bus
- When ncm.lua does `loadfile url replace`:
  - `pause` was already `false` — it does NOT change → **no PROPERTY_CHANGE fires**
  - mpv-mpris never receives a `pause=0` event → `handle_property_change("pause")` never called
  - `ud->status` stays `STATUS_STOPPED` forever
  - D-Bus still returns "Stopped" even though mpv is playing!

### Fix: Force a pause toggle in ncm.lua after loadfile

```lua
-- idle → pause is already false, no property change fires when loadfile starts playing
-- Force the transition: pause=yes → pause=no triggers PROPERTY_CHANGE for "pause"
mp.add_timeout(0.5, function()
    mp.commandv("set", "pause", "yes")   -- triggers PROPERTY_CHANGE(pause=1) → STATUS_PAUSED
end)
mp.add_timeout(0.6, function()
    mp.commandv("set", "pause", "no")    -- triggers PROPERTY_CHANGE(pause=0) → STATUS_PLAYING
end)
```

### Waybar module sources

- Waybar mpris module: https://github.com/Alexays/Waybar/blob/master/src/modules/mpris/mpris.cpp
- mpv-mpris 0.7 (Debian stable): `apt-get source mpv-mpris` → `mpris.c`
- MPRIS spec: https://specifications.freedesktop.org/mpris-spec/latest/
