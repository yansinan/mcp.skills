---
name: pipewire-rtp-audio-streaming
description: "Configure PipeWire/PulseAudio RTP network audio streaming between Linux machines."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [pipewire, pulseaudio, rtp, audio, streaming, network]
    related_skills: [systematic-debugging]
---

# PipeWire RTP Audio Streaming

## Overview

Stream audio from one Linux machine to another over the network using PipeWire's PulseAudio-compatible RTP modules (`module-rtp-send` / `module-rtp-recv`).

## When to Use

- Play audio from machine A on machine B's speakers
- Wireless audio streaming over local LAN or Tailscale
- Multi-room audio distribution

## Quick Start

### Sender (machine A)

```bash
pactl load-module module-null-sink sink_name=rtp_sink
pactl load-module module-rtp-send source=rtp_sink.monitor \
    destination_ip=192.168.1.102 source_ip=192.168.1.249 port=47024
pactl set-default-sink rtp_sink
### module-rtp-recv

Loads `module-rtp-recv` to listen for incoming RTP streams.

**Port discovery gotcha**: `sap_address=0.0.0.0` does **not** always bind to the default 4010.
PulseAudio may pick any free port as fallback (commonly 9875, sometimes 5004).
Always run `ss -ulpn | grep pipewire` on the receiver after setup to read the actual port,
and configure the sender's `port=` to match. Mismatched port = silent loss (UDP has no
handshake to surface the error).

```bash
pactl load-module module-rtp-recv sap_address=0.0.0.0
ss -ulpn | grep pipewire    # read actual port
```

If you need a deterministic port (firewall rules, port forwarding), pass `port=4010` explicitly:
```bash
pactl load-module module-rtp-recv sap_address=0.0.0.0 port=4010
```

WirePlumber auto-connects the RTP source to the default audio output.

## Key Parameters

### module-rtp-send

| Parameter | Default | Notes |
|-----------|---------|-------|
| `destination=<ip>` | — | SAP discovery target; triggers **multicast** mode |
| `destination_ip=<ip>` | — | Unicast target IP (preferred — avoids multicast issues) |
| `source_ip=<ip>` | — | Bind sender socket to specific interface IP |
| `port=<n>` | random (46000–47024) | UDP port for RTP data |
| `mtu=<n>` | 1280 | Max packet size; avoid IP fragmentation |
| `enable_opus=true` | false | Use OPUS codec instead of L16 (no quantization noise) |
| `inhibit_auto_suspend=always` | — | Prevent null-sink from idling on silence |
| `format=<fmt>` | s16le | Only `s16le`/`s16be` accepted (16-bit only) |

### module-rtp-recv

| Parameter | Default | Notes |
|-----------|---------|-------|
| `sap_address=<ip>` | multicast | Use `0.0.0.0` for unicast receiver (listen all interfaces) |
| `latency_msec=<n>` | — | Jitter buffer in ms; helps with network jitter and clock drift |
| `sink=<name>` | auto | Name for the created sink on receiver |

## Critical: Multicast vs Unicast

### ❌ Multicast (`destination=<ip>`)

- RTP data sent to multicast `224.0.0.56`, SAP to `224.0.0.56:9875`
- **Problem**: On machines with multiple network interfaces (Wi-Fi + Docker bridges + Tailscale), the same packet may be delivered multiple times via different interfaces → duplicated audio frames → **stuttering**
- Linux kernel delivers multicast packets to all interfaces that joined the group; Docker bridges can forward multicast even without containers

### ✅ Unicast (`destination_ip=<ip>` + `source_ip=<ip>`)

- RTP data sent directly to receiver's local IP:port
- Single deterministic path → no duplication → **no stuttering**
- Requires `sap_address=0.0.0.0` on receiver (listen on all interfaces for SAP)
- Works on any network topology

### Interface Binding

- PulseAudio compat `module-rtp-recv` has **no** interface binding parameter
- Native PipeWire `libpipewire-module-rtp-source` has `local.ifname = "wlp3s0"` but may not work on all PipeWire versions (tested broken on 1.4.2)

### Root Cause: Why Multicast Duplicates

When sender uses `destination=IP` (multicast mode):
1. RTP data sent to `224.0.0.56` (multicast); SAP to `224.0.0.56:9875`
2. Receiver's `module-rtp-recv` joins the multicast group on **all** interfaces
3. On a machine with WiFi + Tailscale + Docker bridges, each interface that joined delivers a copy
4. Kernel delivers the same RTP packet to the receiver's socket **multiple times** → duplicate frames with same SSRC → `module-rtp-recv` reads corrupted timeline → **stuttering**

**Firewall does not help**: tested with `nft add rule ip filter INPUT udp dport 46000-47024 ip saddr != 192.168.1.0/24 drop`. The packet duplication happens at the kernel's IP multicast routing layer, before the INPUT chain. Even with the rule, the kernel has already delivered copies from other interfaces to the socket.

### Manual Link Reconnection

On the receiver, after a full `pipewire-pulse` restart, WirePlumber should auto-connect the RTP source to the default audio sink. Verify with:
```bash
pw-link -l | grep -E "x1tablet|hdmi"
```

If auto-connect fails, link manually:
```bash
# PulseAudio compat module uses "receive_AUX1/AUX2"
pw-link "x1tablet:receive_AUX1" "alsa_output.pci...hdmi-stereo:playback_FL"
pw-link "x1tablet:receive_AUX2" "alsa_output.pci...hdmi-stereo:playback_FR"
```

## Audio Formats

| Format | Bit depth | Notes |
|--------|-----------|-------|
| L16 (default) | 16-bit | PulseAudio `module-rtp-send` is hardcoded to L16; quantization noise may be audible |
| OPUS | 32-bit float internal | `enable_opus=true`; no quantization noise, lower bandwidth, built-in PLC |

**The format parameter only accepts `s16le`/`s16be`.** Higher bit depths (24-bit, 32-bit float) are not supported by the PulseAudio RTP module.

## Persistence

Make configs auto-load on restart:

### Sender (`~/.config/pipewire/pipewire-pulse.conf.d/99-rtp-send.conf`)

```ini
context.exec = [
    { path = "pactl" args = "load-module module-null-sink sink_name=rtp_to_helix" }
    { path = "pactl" args = "load-module module-rtp-send source=rtp_to_helix.monitor destination_ip=<receiver_ip> source_ip=<sender_ip> port=47024" }
    { path = "pactl" args = "set-default-sink rtp_to_helix" }
]
```

### Receiver (`~/.config/pipewire/pipewire-pulse.conf.d/99-rtp-recv.conf`)

```ini
context.exec = [
    { path = "pactl" args = "load-module module-rtp-recv sap_address=0.0.0.0" }
]
```

## Debugging Methodology

### Isolate One Variable at a Time

This session proved the importance of changing ONE parameter between tests. When multicast → unicast, OPUS, MTU, jitter buffer, and `sap_address` were all changed simultaneously in early attempts, it was impossible to tell what actually fixed the stuttering.

**Correct sequence from this session:**
1. Start at baseline (original config)
2. Change ONLY: `destination=100.66.66.102` → `destination=192.168.1.102` → still stutters
3. Change ONLY: `destination=192.168.1.102` → `destination_ip=192.168.1.102` (unicast) → stutter gone
4. Confirm by reverting to multicast → stutter comes back
5. Test firewall rule → doesn't fix it
6. Return to unicast → confirmed root cause

Establish a clean baseline first, then change one parameter, test, report, and iterate.

## Troubleshooting

### "No sound after restart"
- Check `pactl list modules short | grep rtp` on both sides
- Check `pactl info | grep "Default Sink"` — should be the null sink
- On receiver: `pw-link -l | grep x1tablet` — should show connections to HDMI/audio output

### "Receiver port is not 4010"
- `module-rtp-recv sap_address=0.0.0.0` does NOT always bind to 4010 (the "default SAP port"). On helix (2026-06-28 session) it bound to **9875** because PulseAudio chose a different fallback. The data port may also be auto-created from SDP at sender's `port=` value (e.g. 47024).
- **Always discover the actual port** on the receiver: `ss -ulpn | grep pipewire-pulse` — look for both the SAP listener (9875 in our case) AND any additional `0.0.0.0:<sender-port>` data listener. If sender is told to send to 47024, receiver will listen on 47024 too (auto-created from SDP), even though its SAP socket is on 9875.

### "/proc/net/udp trap on sender"
- After loading `module-rtp-send`, sender's `/proc/net/udp` may show entries like `<sender-ip>:RANDOM → <receiver-ip>:9875`. This is the **SAP control socket**, NOT the RTP data path. Don't conclude "wrong port" from this — the real data socket uses the configured `port=` argument (often invisible via /proc/net/udp because PA uses sendmmsg/recvmmsg).
- **Better proof of data flow**: on receiver, check `pactl list sink-inputs` for a row with `media-name = "RTP Stream (<sender-hostname>)"` (e.g. `RTP Stream (x1tablet)`). If that sink-input exists with s16be/opus codec, the stream is alive.

### "Stuttering audio"
- **Likely cause**: Multicast mode (`destination=xxx`). Switch to unicast (`destination_ip=` + `source_ip=`)
- Check for duplicate packet reception: compare multicast vs unicast

### "Noise / crackling"
- 16-bit L16 quantization. Switch to OPUS: add `enable_opus=true`
- Or: clock drift between two machines. Add `latency_msec=200` on receiver

### "RTP module load fails"
- `format=float32le` → `Invalid argument`; use `format=s16le` or omit
- `format=S24_32LE` → not supported by PulseAudio compat module

### "Native PipeWire modules don't send data"
- `libpipewire-module-rtp-sink` / `libpipewire-module-rtp-source` may not work on PipeWire < 1.6
- Fall back to PulseAudio compat `module-rtp-send` / `module-rtp-recv`

### "Sender destination_ip became unreachable (no audio from receiver)"
Symptom: sender side looks healthy (module loaded, sink-inputs streaming into rtp_to_helix), but receiver produces silence. UDP socket exists but no actual packets arrive.

Root cause: the wireplumber-persistent config baked a LAN IP (e.g. `192.168.1.102`) that has since become unreachable — typically because the peer migrated to a different AP / VLAN, AP isolation kicked in, or the LAN segment changed. UDP silently swallows the lost packets.

Diagnostic ladder:
1. **Confirm LAN is dead, not the receiver**: `ping <configured_destination_ip>` from sender. If 100% loss with a real receiver on the same subnet, it's AP isolation. Bidirectional ping the receiver too — AP isolation is usually symmetric.
2. **Find an alternative path**: check if both peers run Tailscale (`tailscale status`, `tailscale ping <peer-ip>`). Tailscale UDP works through AP isolation because it's a userspace tunnel.
3. **Discover the receiver's actual listening port** — do NOT trust 4010 / 47024 defaults blindly:
   ```bash
   ssh receiver 'ss -ulpn | grep pipewire'
   # typical output: 0.0.0.0:9875 pipewire-pulse,...
   ```
   PulseAudio falls back to a random port when 4010 is taken. If you set `port=` on the sender but it doesn't match the receiver's actual port, RTP packets are silently dropped.
4. **Patch the persistent config** (`~/.config/pipewire/pipewire-pulse.conf.d/99-rtp-send.conf`): swap `destination_ip` and `source_ip` to Tailscale IPs, update `port=` to match receiver's actual port.
5. `systemctl --user restart pipewire pipewire-pulse wireplumber` to reload — sender modules auto-rebuild on Pulse restart.
6. Verify end-to-end with the "Confirming RTP is actually flowing" check below.

### "Confirming RTP is actually flowing end-to-end"
Strongest signal on the **receiver** that RTP is being received and decoded:
```bash
pactl list sink-inputs | grep -E "module-stream-restore|RTP Stream"
# Expected when x1tablet sends to helix:
# module-stream-restore.id = "sink-input-by-media-name:RTP Stream (x1tablet)"
```
`module-stream-restore.id` is set by PulseAudio's stream-restore module from the SDP `media-name` field emitted by the sender's `module-rtp-send`. If this string shows the sender's hostname, the SDP arrived AND was decoded — far more reliable than `/proc/net/udp` queue counts (which UDP's `sendmmsg` doesn't increment visibly).

Cross-check on the **sender** that the UDP socket points where you think it does:
```bash
grep ':<hex_port>' /proc/net/udp
# Decode IP bytes: each 2-char pair is one octet, BUT the 4 octets are stored LITTLE-ENDIAN.
# e.g. "F9424264" → octets in order: F9 42 42 64 → swap to network order: 64.42.42.F9 → 100.66.66.249
#      "66424264"                                                       64.42.42.66 → 100.66.66.102
#      "0101A8C0"                                                       C0.A8.01.01 → 192.168.1.1
```
Easy mistake to make: reading `6601A8C0` left-to-right as `66.01.A8.C0 = 102.1.168.192` (wrong). It's `192.168.1.102` — the octets are reversed.

## References

See `references/` for session-specific examples and detailed troubleshooting logs.

See `references/` for session-specific examples and detailed troubleshooting logs.
