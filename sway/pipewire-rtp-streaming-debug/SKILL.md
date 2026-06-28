---
name: pipewire-rtp-streaming-debug
description: Systematic isolation debugging of PipeWire RTP audio streaming between machines — isolate one variable at a time (network path, codec, buffer settings) to find root cause
---

# PipeWire RTP Audio Streaming Debugging

Systematic approach to debugging PipeWire RTP (`module-rtp-send` / `module-rtp-recv`) audio streaming between Linux machines.

## Golden Rule: One Variable at a Time

Never change multiple parameters between tests. Per user preference:
> "一个一个排除，你改了太多根本搞不清根因"

**Workflow:**

1. Identify the problem (no sound / stuttering / noise)
2. Revert to a KNOWN WORKING baseline first (not a bare default)
3. Change exactly ONE parameter
4. Test with actual audio playback
5. Report the finding to the user before changing the next variable

## Test Sequence (prioritized order)

### Phase 1: Network Path
- **Multicast (default)**: `destination=<IP>` → RTP to `224.0.0.56`. **Suspect when** the machine has multiple network interfaces (Wi-Fi + Tailscale + Docker bridges) — multicast packets can arrive via multiple paths causing stuttering.
- **Unicast**: `destination_ip=<IP> source_ip=<local IP> port=<port>` → direct UDP to target. Single deterministic path.
- **Receiver delta for unicast**: Receiver needs `sap_address=0.0.0.0` to listen on all interfaces (not just multicast SAP).

### Phase 2: Codec
- **L16 (default)**: 16-bit PCM. Quantization noise is audible on quiet passages. Equivalent to CD quality but limited dynamic range.
- **OPUS**: `enable_opus=true`. 32-bit float internal processing, transparent quality. Fixes quantization noise. OPUS codec built into PipeWire RTP module (no external codec package needed).
- **`format=` parameter** on `module-rtp-send` only accepts `s16le`/`s16be` despite being listed in usage. `S24_32LE`, `S32LE`, `float32le` all return "Invalid argument".

### Phase 3: Buffer / Jitter
- **`latency_msec=<N>`** on receiver (`module-rtp-recv`): jitter buffer in ms. Default = none. Larger values (250-500ms) smooth clock drift between two independent machines.
- **`inhibit_auto_suspend=always`** on sender: prevents null-sink from pausing during idle silences.

### Phase 4: Network Tuning
- **`mtu=1400`**: Avoid IP fragmentation for RTP packets. L16 at 48kHz stereo is ~1268 bytes/packet (header + payload). 1400 is safe.

## PipeWire RTP Module Architecture

```
PipeWire kernel ─┬── libpipewire-module-rtp-sink/source  (native, pipewire.conf.d/)
                 └── pipewire-pulse ─── module-rtp-send/recv  (PulseAudio compat, pipewire-pulse.conf.d/)
```

- **Native modules** (`libpipewire-module-rtp-sink/source`): More format control (`audio.format` supports `S16BE`, `S24BE`, `S32BE`), but may not work on PipeWire 1.4.x — packets may not reach network.
- **PulseAudio compat modules** (`module-rtp-send/recv`): Limited to L16, but more reliable on PipeWire 1.4.x. OPUS support works (`enable_opus=true`).

## Common Pitfalls

- **Multicast + multiple network interfaces**: Docker bridges, Tailscale, and Wi-Fi all join the same multicast group → packets arrive duplicated → stuttering. Verify with `ip maddr show | grep 224.0.0.56` on both machines.
- **SAP discovery after module reload**: When using multicast, the receiver discovers the RTP stream via SAP (Session Announcement Protocol) on `224.0.0.56:9875`. After unloading/reloading both modules, receiver may miss the announcement. Restart pipewire fully or reload receiver after sender has started sending.
- **WirePlumber missing auto-connect**: After reloading `module-rtp-recv` on the receiver, the x1tablet receive node may not auto-connect to the HDMI sink. Fix with `pw-link "x1tablet:receive_FL" "hdmi-sink:playback_FL"` (and FR).
- **Module reload "Connection failure"**: Normal disruption at the PulseAudio compat layer — the command still executed.
- **No `enable_opus` before**: OPUS only works when explicitly set. Without it, sender uses L16 even if null-sink outputs float32le.

## Verification Commands

```bash
# Check sender RTP session format
pw-cli list-objects | grep -B6 'node.name = "rtp_session.x1tablet"' | grep "id "
pw-cli i <NODE_ID> | grep -E "mime|media|opus|destination"

# Check all network interfaces
ip addr show | grep "inet "

# Check multicast group membership
ip maddr show | grep 224.0.0.56

# Check UDP packet flow
cat /proc/net/udp | grep "<port_hex>"

# Check PipeWire processing status
pw-top

# Check module status
pactl list modules short | grep -E "rtp|null"

# Connect receiver to sink
pw-link "x1tablet:receive_AUX1" "alsa_output.pci-...hdmi-stereo:playback_FL"
```

## Config Files

### Sender (x1tablet) — `~/.config/pipewire/pipewire-pulse.conf.d/99-rtp-send.conf`
```conf
context.exec = [
    { path = "pactl" args = "load-module module-null-sink sink_name=rtp_to_helix" }
    { path = "pactl" args = "load-module module-rtp-send
        source=rtp_to_helix.monitor
        destination_ip=<target-IP>
        source_ip=<local-IP>
        port=5004
        enable_opus=true
        inhibit_auto_suspend=always" }
    { path = "pactl" args = "set-default-sink rtp_to_helix" }
]
```

### Receiver (helix) — `~/.config/pipewire/pipewire-pulse.conf.d/99-rtp-recv.conf`
```conf
context.exec = [
    { path = "pactl" args = "load-module module-rtp-recv
        sap_address=0.0.0.0
        latency_msec=500" }
]
```

## References

- `references/debug-session-x1tablet-helix.md` — per-session debug log, may be empty or contain test results from a particular debugging session
