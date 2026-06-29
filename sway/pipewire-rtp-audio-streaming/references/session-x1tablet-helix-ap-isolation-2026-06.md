# x1tablet → helix RTP: AP-isolation incident (2026-06-28)

## Symptom
User reported "怎么不出声音了". ncm-cli mpv was playing, PipeWire sender config
intact, but helix produced silence. Nothing in any log flagged an error — UDP
silently swallows lost packets.

## Diagnosis timeline (what worked)

1. `wpctl get-default` → `rtp_to_helix` (id 42). At first glance looked right,
   but `wpctl inspect 42` showed `factory.name = "support.null-audio-sink"` —
   the sink itself was null, not a real RTP sink. **Red herring**: the sink
   being null is correct (it's a virtual staging sink), the actual RTP egress
   is `module-rtp-send` reading from `rtp_to_helix.monitor`. So this wasn't
   the bug.

2. `pactl list modules short | grep rtp` →
   ```
   module-null-sink        sink_name=rtp_to_helix
   module-rtp-send         source=rtp_to_helix.monitor
                            destination_ip=192.168.1.102
                            source_ip=192.168.1.249
                            port=47024
   ```
   Sender config baked: **LAN IP, port 47024**.

3. `ping 192.168.1.102` from sender → **100% packet loss**.
   `ssh helix 'ping 192.168.1.249'` from receiver → **100% packet loss**.
   Both peers are in 192.168.1.0/24 (verified via `ip route show default`
   hex `0101A8C0` = 192.168.1.1) but can't reach each other → **AP isolation**.

4. `tailscale status` showed both peers online as Tailscale nodes:
   - x1tablet: 100.66.66.249
   - helix:    100.66.66.102
   `tailscale ping 100.66.66.102` → 5.7ms, 0% loss. Tailscale path works.

5. `ssh helix 'ss -ulpn | grep pipewire'` →
   ```
   UNCONN 0 0 0.0.0.0:9875 ... users:(("pipewire-pulse",pid=2946523,fd=26))
   ```
   Receiver listens on **9875**, not 4010 (default) and not 47024 (sender config).

6. `/proc/net/udp` on sender (grep `:2693` where `9875=0x2693`):
   ```
   F9424264:A2E3 66424264:2693 01 ...
   ```
   Decoded (octets stored little-endian in /proc/net/udp):
   - `F9424264` → `64.42.42.F9` → **100.66.66.249** ✓ (sender src, Tailscale)
   - `66424264` → `64.42.42.66` → **100.66.66.102** (helix dst, Tailscale)

   **Easy mistake**: reading `66424264` left-to-right as `66.42.42.64` = 102.66.66.100
   (wrong). The byte order is reversed. See SKILL.md troubleshooting section.

7. **End-to-end confirmation** on helix (after the fix below):
   ```
   pactl list sink-inputs | grep module-stream-restore
   → module-stream-restore.id = "sink-input-by-media-name:RTP Stream (x1tablet)"
   ```
   This string only appears when PulseAudio's stream-restore has parsed the SDP
   `media-name` from the sender — strongest proof RTP is decoded.

## Fix
Patched `~/.config/pipewire/pipewire-pulse.conf.d/99-rtp-send.conf`:
```diff
- destination_ip=192.168.1.102 source_ip=192.168.1.249 port=47024
+ destination_ip=100.66.66.102  source_ip=100.66.66.249  port=9875
```

Then `systemctl --user restart pipewire pipewire-pulse wireplumber`.

Result: helix hdmi-stereo sink-input "RTP Stream (x1tablet)" s16be 2ch 48000Hz,
audio restored. mpv continued playing through ncm-player auto-restart.

## Lessons (see SKILL.md troubleshooting)

1. Sender's `destination_ip` in the persistent `.conf.d` config is **brittle**:
   it bakes a specific network assumption that breaks when APs/VLANs change.
   Document the assumption in the config comment so future debuggers don't
   repeat this hunt.

2. `port=4010` is a PulseAudio **default fallback** — actual port depends on
   what's free at module load. Always check `ss -ulpn | grep pipewire` on the
   receiver, don't trust the docs default.

3. `/proc/net/udp` IP bytes are little-endian per octet. Decode by reversing
   the 4 pairs, not reading left-to-right.

4. The strongest "RTP is flowing" signal is receiver's
   `module-stream-restore.id = "sink-input-by-media-name:RTP Stream (<hostname>)"`,
   not `/proc/net/udp` queue counters (which `sendmmsg` doesn't visibly increment).

5. Pre-fix: the LAN pair had been working before — helix was apparently reachable
   on 192.168.1.102 from x1tablet at config-write time (2025-06-19). The break
   happened later (helix migrated APs / AP isolation policy changed). Date in
   the config comment ("2025-06-19") gave us the clue that something external
   had changed since.

## Backups created
- `99-rtp-send.conf.bak-20260628-211719` — snapshot of broken LAN config
- `99-rtp-send.conf.bak` — pre-existing backup from prior session