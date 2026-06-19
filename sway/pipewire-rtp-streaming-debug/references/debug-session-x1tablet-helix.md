# Debug Session: x1tablet → helix PipeWire RTP Audio

## Environment

- x1tablet: Debian 13, PipeWire 1.4.2, Wi-Fi `192.168.1.249/24`, Tailscale `100.66.66.249`, Docker
- helix: Debian 13, PipeWire 1.4.2, Wi-Fi `192.168.1.102/24`, Tailscale `100.66.66.102`, Docker + 2 more bridge networks
- Same Wi-Fi AP (192.168.1.0/24), also connected via Tailscale (100.66.66.0)

## Problem

Original audio streaming (via raw PulseAudio compat RTP) had stuttering.

## Variable Isolation Results

| # | Config Change | Stuttering | Noise | Conclusion |
|---|--------------|-----------|-------|------------|
| 1 | Baseline: multicast `destination=100.66.66.102`, L16, no jitter | ✅ Stutters | ? | Confirmed problem exists |
| 2 | + enable_opus=true, still multicast | ✅ Stutters | — | OPUS alone ≠ fix |
| 3 | + unicast (`destination_ip`/`source_ip`/`port`), OPUS, `sap_address=0.0.0.0` | ❌ No stutter | — | **Unicast fixed stuttering** |
| 4 | + destination=192.168.1.102 (multicast on local subnet), OPUS | ✅ Stutters | — | **Multicast is the root cause**, not 100.x vs 192.x |
| 5 | + unicast, L16 (no OPUS) | ❌ No stutter | ✅ Has noise | **Unicast alone fixes stutter**, OPUS fixes noise |

## Root Cause

**Multicast packet duplication due to multiple network interfaces.** Both machines have Wi-Fi, Tailscale, and Docker bridges. When sender sends RTP to `224.0.0.56`, the receiver may receive duplicate packets via different interfaces (Wi-Fi + Tailscale + Docker bridges). Duplicate audio frames → stuttering.

## Final Working Config

- **Network**: Unicast `192.168.1.249 → 192.168.1.102:5004`
- **Codec**: OPUS (`enable_opus=true`) — fixes L16 16-bit quantization noise
- **Receiver**: `sap_address=0.0.0.0` + `latency_msec=500` (jitter buffer)
- **MTU**: 1400 (avoids IP fragmentation)
- **Auto-suspend**: `inhibit_auto_suspend=always`
- **Receiver auto-connect**: WirePlumber may not auto-connect → `pw-link x1tablet:receive_AUX1` → HDMI playback_FL

## Key Commands Used

- Module reload: `pactl unload-module <ID>; pactl load-module ...`
- Check session format: `NODE=$(pw-cli list-objects | grep "rtp_session.x1tablet"...); pw-cli i $NODE`
- Connect to sink: `pw-link "x1tablet:receive_FL" "alsa_output...hdmi-stereo:playback_FL"`
- Restart all: `systemctl --user restart pipewire pipewire-pulse wireplumber`
