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
- **Always test bi-directional ping on BOTH interfaces** (LAN + Tailscale). If LAN ping fails both ways but Tailscale ping succeeds → **AP isolation** (see `references/ap-isolation-diagnosis.md`). Don't trust a single-direction test.

### Phase 2: Codec
- **L16 (default)**: 16-bit PCM. Quantization noise is audible on quiet passages. Equivalent to CD quality but limited dynamic range.
- **OPUS**: `enable_opus=true`. 32-bit float internal processing, transparent quality. Fixes quantization noise. OPUS codec built into PipeWire RTP module (no external codec package needed).
- **`format=` parameter** on `module-rtp-send` only accepts `s16le`/`s16be` despite being listed in usage. `S24_32LE`, `S32LE`, `float32le` all return "Invalid argument".

### Phase 3: Buffer / Jitter
- **`latency_msec=<N>`** on receiver (`module-rtp-recv`): jitter buffer in ms. Default = none. Larger values (250-500ms) smooth clock drift between two independent machines.
- **`inhibit_auto_suspend=always`** on sender: prevents null-sink from pausing during idle silences.

### Phase 4: Network Tuning
- **`mtu=1400`**: Avoid IP fragmentation for RTP packets. L16 at 48kHz stereo is ~1268 bytes/packet (header + payload). 1400 is safe.

## Common Pitfalls

### "/proc/net/udp IP byte-order trap"
- `/proc/net/udp` stores addresses as 8 hex chars in **network byte order** (big-endian). To decode `6601A8C0`:
  - Split into 2-char pairs: `66 01 A8 C0`
  - **Reverse the pair order**: `C0 A8 01 66` (NOT reverse the whole string char-by-char)
  - Decimal: `192.168.1.102`
- Common misread: treating the hex string as a single big number or reversing it char-by-char would give `100.66.66.102` instead of `192.168.1.102` — this can hide a real LAN bug by making you think traffic is going to Tailscale when it's actually going to LAN (or vice versa).
- **Tip**: when in doubt, write a 5-line decoder script (or use `socket.inet_ntoa(struct.pack('<I', int(hex, 16)))`) instead of doing it in your head. Use `scripts/decode-udp-addresses.py` to batch-decode all entries from `/proc/net/udp`.

### "Sender's /proc/net/udp shows SAP port, not data port"
- After loading `module-rtp-send`, sender's `/proc/net/udp` may show entries like `<sender-ip>:RANDOM → <receiver-ip>:9875`. This is the **SAP control socket**, NOT the RTP data path. Don't conclude "wrong port" from this — the real data socket uses the configured `port=` argument (often invisible via /proc/net/udp because PA uses sendmmsg/recvmmsg).
- **Better proof of data flow**: on receiver, check `pactl list sink-inputs` for a row with `media-name = "RTP Stream (<sender-hostname>)"` (e.g. `RTP Stream (x1tablet)`). If that sink-input exists with s16be/opus codec, the stream is alive.

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

## Common Pitfalls

### 1. `/proc/net/udp` hex IP 是 little-endian（字节倒序）
看 hex 末两字节判定段：
- `A8C0` 结尾 → 192.168.x.x
- `0A00` 结尾 → 10.x.x.x
- `AC10` 结尾 → 172.16.x.x

`6601A8C0` ≠ `66.01.A8.C0`（直觉上是 100.66.66.102?），而是 `C0.A8.01.66` = **192.168.1.102**。

端口是 big-endian 16-bit（直接十进制转 hex）：9875 → `0x2693`。

辅助脚本：`scripts/decode-udp-addresses.py`（直接读 /proc/net/udp 输出 IP:port）。

### 2. 不要用 `bash /dev/tcp` 测 UDP 端口
RTP 是 UDP。`/dev/tcp` 只测 TCP，Connection refused ≠ UDP refused。
正确：python socket (`SOCK_DGRAM` + `sendto`) 或 `nc -u`。无 ICMP unreachable = 端口可能开放。

### 3. `module-rtp-recv sap_address=0.0.0.0` 实际端口不一定是 4010
PulseAudio 可能 fallback 到其他可用端口（实测 9875）。**必须从 `ss -ulpn` 读真实端口**，不能假设。

### 4. AP 隔离 / client isolation 让 LAN "看起来通但实际丢包"
同 SSID 不同客户端之间单播被 AP 丢弃（100% packet loss），但 `ip route` / default gateway 显示正常。
诊断组合：**双向 ping**（单向 ping 通不代表双向通，helix → 本机更准）+ Tailscale 对比。

### 5. 修改 `~/.config/pipewire/pipewire-pulse.conf.d/99-rtp-send.conf` 后必须重启
`systemctl --user restart pipewire pipewire-pulse wireplumber` 会断当前播放 1-2 秒，
ncm-player 守护会自动重启 mpv。避免在播放关键节点操作。

## References

- `references/debug-session-x1tablet-helix.md` — 历史 session 详细排查记录
- `references/ap-isolation-diagnosis.md` — **AP 隔离场景的诊断路径**（含字节序速查表 / UDP 探针方法）
- `scripts/decode-udp-addresses.py` — 解码 `/proc/net/{udp,tcp}` hex 地址的小工具
