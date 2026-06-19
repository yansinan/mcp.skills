# Session Reference: x1tablet → helix RTP Audio Streaming

## Environment

| Machine | Hostname | OS | Wi-Fi IP | Tailscale IP | Docker networks |
|---------|----------|-----|----------|--------------|-----------------|
| Sender | x1tablet | Debian 13, PipeWire 1.4.2 | 192.168.1.249/24 | 100.66.66.249/32 | docker0 (172.17.0.1) |
| Receiver | helix | Debian (same), PipeWire 1.4.2 | 192.168.1.102/24 | 100.66.66.102/32 | docker0, br-468..., br-031... |

## Root Cause Discovered

**Multicast stuttering** was caused by the receiver having multiple network interfaces (Wi-Fi + Docker bridges + Tailscale) all joining the same multicast group (224.0.0.56). The same RTP packet arrived via multiple interfaces → duplicated audio frames → audio timestamp confusion → stuttering.

**Switching to unicast** eliminated all stuttering because the RTP data has only one deterministic path.

## Testing Sequence

1. **Original**: multicast + L16 + destination=100.66.66.102 → **stutter + noise**
2. OPUS + multicast + destination=100.66.66.102 → **stutter** (OPUS didn't fix it — multicast was the issue)
3. OPUS + unicast + destination_ip=192.168.1.102 → **no stutter** (first win)
4. OPUS + multicast + destination=192.168.1.102 → **stutter** (confirmed multicast = root cause)
5. L16 + unicast + destination_ip=192.168.1.102 → **no stutter, no noise** (L16 was fine, multicast = only problem)

## Working Config

### Sender (`~/.config/pipewire/pipewire-pulse.conf.d/99-rtp-send.conf`)

```ini
context.exec = [
    { path = "pactl" args = "load-module module-null-sink sink_name=rtp_to_helix" }
    { path = "pactl" args = "load-module module-rtp-send source=rtp_to_helix.monitor destination_ip=192.168.1.102 source_ip=192.168.1.249 port=47024" }
    { path = "pactl" args = "set-default-sink rtp_to_helix" }
]
```

### Receiver (`~/.config/pipewire/pipewire-pulse.conf.d/99-rtp-recv.conf`)

```ini
context.exec = [
    { path = "pactl" args = "load-module module-rtp-recv sap_address=0.0.0.0" }
]
```

## Verification Commands

```bash
# Sender side
pactl list modules short | grep -E "rtp|null"
pactl info | grep "Default Sink"
pw-cli list-objects | grep -B6 "node.name = \"rtp_session.x1tablet\""
pw-cli i <node_id> | grep -E "destination|port|mime"

# Receiver side
pactl list modules short | grep rtp
ss -ulpn | grep pipewire
pw-link -l | grep -E "x1tablet|hdmi"
```

## Port Choice

Changed from default random (46000–47024 range) to fixed 47024 for clarity and firewall rules. Port 5004 was originally used but renumbered to fit within the module's standard range.
