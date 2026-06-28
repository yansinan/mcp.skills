# mpv-mpris 0.7 Source Notes

The `mpv-mpris` package on Debian ships a compiled C plugin at
`/usr/lib/mpv-mpris/mpris.so` (NOT a Lua script). The Debian source package
at <https://salsa.debian.org/multimedia-team/mpv-mpris> contains the C source.
The upstream MPV project doesn't ship mpris; mpv-mpris is a separate project
maintained by Hans-Kristian Arntzen / debian-multimedia team.

This file documents the relevant parts of `mpris.c` for the music-streaming
use case, so future debugging doesn't require re-reading the C source.

## `create_metadata()` — what gets exposed to MPRIS

The single most relevant function. Lines 357-366 of mpris.c (mpv-mpris 0.7.1):

```c
static GVariant *create_metadata(UserData *ud) {
    GVariantDict dict;
    g_variant_dict_init(&dict, NULL);

    // initial value. Replaced with metadata value if available
    add_metadata_item_string(ud->mpv, &dict, "media-title", "xesam:title");
    add_metadata_item_string(ud->mpv, &dict, "metadata/by-key/Title", "xesam:title");
    add_metadata_item_string(ud->mpv, &dict, "metadata/by-key/Album", "xesam:album");
    add_metadata_item_string(ud->mpv, &dict, "metadata/by-key/Genre", "xesam:genre");

    add_metadata_item_string(ud->mpv, &dict, "metadata/by-key/uploader", "xesam:artist");
    add_metadata_item_string_list(ud->mpv, &dict, "metadata/by-key/Artist", "xesam:artist");
    add_metadata_item_string_list(ud->mpv, &dict, "metadata/by-key/Album_Artist", "xesam:albumArtist");
    add_metadata_item_string_list(ud->mpv, &dict, "metadata/by-key/Composer", "xesam:composer");

    add_metadata_item_int(ud->mpv, &dict, "metadata/by-key/Track", "xesam:trackNumber");
    add_metadata_item_int(ud->mpv, &dict, "metadata/by-key/Disc", "xesam:discNumber");

    add_metadata_item_string(ud->mpv, &dict, "metadata/by-key/Date", "xesam:contentCreated");
    add_metadata_uri(ud->mpv, &dict);
    add_metadata_art(ud->mpv, &dict);
    add_metadata_content_created(ud->mpv, &dict);
    return g_variant_dict_end(&dict);
}
```

Each call reads an mpv OBSERVED PROPERTY (the first arg) and emits it as
the second arg into the MPRIS D-Bus dict. Order matters: later calls
OVERRIDE earlier ones if the property is set.

**Key insight**: `xesam:title` and `xesam:artist` are read from DIFFERENT
sources. `xesam:title` defaults to `media-title` (which `force-media-title`
overrides). `xesam:artist` has NO `media-title` fallback — it only comes
from the ID3-tag-derived `metadata/by-key/Artist` property.

## The missing split logic

There is NO code path in mpris.c that splits `media-title` on `" - "` to
extract an artist. So when you set `force-media-title` to a string like
"陈奕迅 - 最佳损友", the WHOLE string goes to `xesam:title`, and
`xesam:artist` stays empty (no ID3 tag on a streaming URL).

This is intentional in the upstream design: mpv-mpris assumes that any
content with a meaningful artist has ID3 tags. Streamed content breaks
this assumption.

## Workarounds

**Option A — single-field template** (recommended, least invasive):

Pack "Artist - Title" into `force-media-title`, use waybar template
`" {title}"` only. The full "Artist - Title" string shows in the bar.

**Option B — set `metadata/by-key/Artist` from mpv Lua**:

```lua
-- In ncm.lua play_song, after setting force-media-title:
mp.command_native({
    name = "set_property",
    data = "metadata",
    value = {
        -- mpv allows you to override the metadata dict directly
        ["Artist"] = artists,
    },
})
```

This sets the `metadata` property to include an `Artist` key, which mpv-mpris
will pick up via `metadata/by-key/Artist`. Less clean than Option A because
you also have to keep `force-media-title` in sync.

**Option C — replace mpv-mpris with a custom script**:

If the waybar mpris module is critical and you need the cleanest
`{title} - {artist}` rendering, write your own Lua script that exposes a
custom MPRIS interface via mpris-proxy, or override `mpv-mpris` via
`--scripts=` with your own. This is the most invasive option — only
warranted if you need album art, complex playlists, or other MPRIS
features mpv-mpris doesn't expose.

## PlaybackStatus state machine (the "Stopped" bug root cause)

The PlaybackStatus is tracked by `ud->status`, initialized to `STATUS_STOPPED`
at init (line 986 of `mpris.c`). It changes ONLY via:

1. **`MPV_EVENT_IDLE`** → `set_stopped_status()` (line 933) — immediately
   sets `ud->status = STATUS_STOPPED` and calls `emit_property_changes()` to
   send D-Bus "Stopped" right now (not via the 100ms timer).
2. **`MPV_EVENT_PROPERTY_CHANGE("pause")`** → `handle_property_change()`
   (line 935-937, handler at 841-849) — sets `ud->status` to
   `STATUS_PAUSED` or `STATUS_PLAYING`, but does NOT call
   `emit_property_changes()` — the change is queued in `changed_properties`
   and sent by the 100ms timer at line 1018.

**Critical gap**: When mpv is `--idle=yes`, `pause` is already `false` (the
default). When `loadfile` is called on an idle mpv:
1. `MPV_EVENT_IDLE` fires → `set_stopped_status()` → "Stopped" sent immediately.
2. mpv starts playing the URL.
3. `pause` is still `false` — it NEVER CHANGED from the default.
4. No `MPV_EVENT_PROPERTY_CHANGE("pause")` fires.
5. `handle_property_change` never runs with `pause` argument.
6. `ud->status` stays at `STATUS_STOPPED` permanently.
7. The 100ms timer keeps emitting PropertiesChanged with "Stopped".
8. waybar's `onPlayerStop` fires → `dp.emit()` → `update()` → sees Stopped → skips.

The `MPV_EVENT_PLAYBACK_RESTART` event (line 942) also fires, but its only
effect is emitting a `Seeked` signal — it does NOT touch PlaybackStatus at all.

**Fix (in the mpv script, not in mpv-mpris)**: After `loadfile`, toggle
`pause=yes` then `pause=no` with separate timeouts. Each toggle fires a
`PROPERTY_CHANGE` for the `pause` property, which runs
`handle_property_change("pause")` and transitions status:
`false→true→false` → `STATUS_STOPPED→STATUS_PAUSED→STATUS_PLAYING`.
The second change (back to `false`) correctly sets Playing.

```lua
mp.commandv("loadfile", url, "replace")
mp.add_timeout(0.5, function() mp.commandv("set", "pause", "yes") end)
mp.add_timeout(0.6, function() mp.commandv("set", "pause", "no") end)
```

### Key functions in mpris.c

| Function | Line | Role |
|---|---|---|
| `set_stopped_status()` | 779 | Immediate Stopped D-Bus signal (calls emit_property_changes directly) |
| `handle_property_change()` | 837 | Sets ud->status based on pause flag; queues PropertiesChanged in changed hash |
| `emit_property_changes()` | 720 | Sends all queued D-Bus property changes, then clears the hash |
| `event_handler()` | 913 | Dispatches mpv events (IDLE → set_stopped_status, PROPERTY_CHANGE → handle) |
| `create_metadata()` | 329 | Builds Metadata dict — no Artist-from-title split logic

For the simple case of "show current song in waybar", Option A is the
right answer. It keeps the dependency surface small (one plugin, one
config field) and the rendering is unambiguous (one string, one slot).

## `media-title` vs `force-media-title`

`media-title` is the OBSERVED property (changes when the file changes).
`force-media-title` is a user-set property that overrides `media-title`
in the observer. Setting `force-media-title` works for the current
`media-title` exposed via the OBSERVER hook, which mpv-mpris reads.

**Trap**: if you set `force-media-title` then load a new file, the new
file's URL-derived title may REPLACE your `force-media-title` value
(because `force-media-title` is "the override of media-title", not
"always show this regardless"). The way to make it stick is:

```lua
-- After loadfile, re-set force-media-title:
mp.commandv("loadfile", url, "replace")
mp.commandv("set", "force-media-title", media_title)  -- set AFTER loadfile
```

Order matters: loadfile first (triggers the new file's metadata), then
force-media-title (overrides it). Doing it the other way around lets
loadfile's metadata-event overwrite your force.

## Reading the source

To inspect the actual mpris.c on your system without re-downloading:

```bash
# Get the source package
apt source mpv-mpris
cd mpv-mpris-*/

# Or read the .so binary's strings for clues (no symbols, but string table)
strings /usr/lib/mpv-mpris/mpris.so | grep -E "xesam|metadata|artist" | head -20
```

The full C source is ~600 lines, mostly D-Bus boilerplate. The two
functions that matter for our use case are `create_metadata()` (above)
and `mpv_observe_property()` calls in the `on_property_change` handler.
