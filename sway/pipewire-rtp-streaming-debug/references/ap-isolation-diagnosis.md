# AP 隔离导致的 RTP 链路断裂 — 诊断路径

## 场景
x1tablet → helix 局域网 RTP 推流突然没声音，所有 PipeWire / wireplumber 配置未改动。

## 根因
helix 物理接入点换了 WiFi AP，新 AP 启用了 **client isolation（AP 隔离）**：
- 同 SSID 不同客户端之间的单播包被 AP 丢弃（100% packet loss）
- 但 `ip route` / default gateway / `ping localhost` 仍显示"正常"
- LAN IP 路由表项完整存在，但实际单播不通

## 诊断步骤（按序）

### 1. 双向 ping：LAN vs Tailscale
```bash
# 从 helix 反向 ping 本机 LAN IP（关键！单向测不出 AP 隔离）
ssh dr@100.66.66.102 'ping -c 2 -W 2 192.168.1.249'
# 100% loss → 确认 AP 隔离

# Tailscale 应该通
ssh dr@100.66.66.102 'ping -c 2 -W 2 100.66.66.249'
# latency 5-10ms = 通
```

### 2. 查 sender 实际 destination IP
```bash
pactl list modules | grep -A4 'rtp-send'
# 或直接看进程打开的 UDP socket：
grep ':2693' /proc/net/udp   # 2693 = 9875 端口的 hex
```

⚠️ `/proc/net/udp` 里的 IP 是 **little-endian 32-bit hex**（字节倒序）：
- `6601A8C0` ≠ `66.01.A8.C0`，而是 `C0.A8.01.66` = **192.168.1.102**
- 判定技巧：看末两字节是否是 `A8C0`（192.168）/`AC10`（172.16）/`0A00`（10.x）

### 3. 查 helix receiver 实际监听端口
```bash
ssh dr@100.66.66.102 'ss -ulpn | grep pipewire'
```

⚠️ `module-rtp-recv sap_address=0.0.0.0` **不一定监听 4010**：
- PulseAudio 可能 fallback 到其他可用端口（实测 9875）
- 必须从 `ss -ulpn` 读真实端口，不能假设

### 4. 不要用 TCP `/dev/tcp` 测 UDP 端口！
```bash
# 错误：bash /dev/tcp 只测 TCP
bash -c 'echo > /dev/tcp/100.66.66.102/9875'
# Connection refused ≠ UDP refused（RTP 是 UDP）

# 正确：python socket 或 nc -u
python3 -c "import socket; s=socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.settimeout(2); s.sendto(b'x',('100.66.66.102',9875)); s.recvfrom(64)" 2>&1 || echo "no-unreach=端口开放但无响应"
```

UDP "no-unreach"（无 ICMP unreachable）= 端口可能开放。

### 5. 修复
修改持久化配置 `~/.config/pipewire/pipewire-pulse.conf.d/99-rtp-send.conf`：
```diff
- destination_ip=192.168.1.102 source_ip=192.168.1.249 port=47024
+ destination_ip=100.66.66.102  source_ip=100.66.66.249  port=9875
```

触发重载（**会断当前播放 1-2 秒**，ncm-player 自动重启 mpv）：
```bash
systemctl --user restart pipewire pipewire-pulse wireplumber
```

## 字节顺序速查表

| Hex      | Little-endian 解读 | IP             |
|----------|--------------------|----------------|
| `C0A80166` | C0.A8.01.66       | 192.168.1.102  |
| `F901A8C0` | C0.A8.01.F9       | 192.168.1.249  |
| `66014242` | 42.42.01.66       | 66.1.66.66     |
| `42660166` | 66.01.66.42       | 66.102.66.66   |

**实战技巧**：看到一个 hex IP，先看末两字节。
- `A8C0` 结尾 → 192.168.x.x（LAN 段，最常见）
- `0A00` 结尾 → 10.x.x.x
- `AC10` 结尾 → 172.16-31.x.x

端口 hex 是 big-endian 16-bit，直接十进制转。
9875 → `0x2693`

## 给 sender/receiver 的设计建议
1. **优先走 Tailscale 而不是 LAN** — 减少 AP 隔离/换网段带来的反复断链
2. sender 配置用 `destination_ip=<tailscale_ip>` + `source_ip=<tailscale_ip>`
3. receiver 模块 `module-rtp-recv sap_address=0.0.0.0` 启动后**实际端口需要从 `ss -ulpn` 读取**，不能假设 4010
4. 诊断组合：**双向 ping + 实际 UDP 探针**（不要只看 TCP）