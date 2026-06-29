---
name: pipewire-audio-routing
description: PipeWire / PulseAudio 音频路由诊断 —— Sink/Source 路由、跨机 RTP 网络音频流、麦克风输入白噪音/无声诊断。覆盖本地默认设备切换、模块加载、RTP 拓扑、HDA codec 麦克风故障。
---

# PipeWire / PulseAudio 音频路由诊断

系统化追踪"音频到底去了哪里"的方法论。涵盖本地音频链路和跨机 RTP 网络音频流，**以及麦克风输入的诊断（白噪音、无声、声音过小）**。

> 📁 **麦克风诊断专用资料**：`references/x1tablet-ALC295-mic-bug.md`（x1tablet ALC295 17aa:2263 已知 bug + 修复路径），**辅助脚本**：`scripts/mic-spectrum-probe.py`（录完 WAV 一键分析频谱，自动识别"悬空 pin"模式）。

## 四阶段排查流程

### 阶段 1：快速定位默认 Sink

```bash
pactl info | grep "Default Sink"
# → 默认输出设备
```

### 阶段 2：查看 Sink 详情

```bash
pactl list sinks short                  # 列出所有 sink
pactl list sinks | grep -A 30 "rtp"    # 查看特定 sink（如 RTP 的）
```

关键字段：
- **`factory.name`** — `support.null-audio-sink`（虚拟→网络流）、`api.alsa.pcm.sink`（物理硬件）
- **`media.class`** — `Audio/Sink`（正常）、`Audio/Sink/Virtual`（虚拟/网络）
- **`node.name`** / **`device.description`** — 名称

### 阶段 3：检查音频模块

```bash
pactl list modules short | grep -E "rtp|null|tunnel|loopback"
pactl list modules | grep -A 20 'module-rtp'
```

| 模块 | 作用 | 关键参数 |
|---|---|---|
| `module-null-sink` | 虚拟静音 sink，作为 RTP 的采集点 | `sink_name=...` |
| `module-rtp-send` | 将 monitor 音频通过 RTP 发到远程 | `source=... destination/destination_ip=...` |
| `module-rtp-recv` | 接收 RTP 音频流 | `sap_address=... latency_msec=...` |
| `module-loopback` | 本地源→sink 直连 | `source=... sink=...` |

### 阶段 4：追踪 RTP 网络路径

```bash
# 查看发端目标 IP
paclt list modules | grep module-rtp-send

# 检查收端
ssh <host> "pactl list modules | grep module-rtp"
ssh <host> "pactl list sinks short"
```

---

## RTP 音频流：多播 vs 单播

### 选择发端参数 = 选择网络模式

| 发端参数 | 实际网络路径 | 收端所需配置 |
|---|---|---|
| `destination=<IP>` | **多播** `224.0.0.56:动态端口` | `module-rtp-recv`（无参数，SAP 自动发现多播） |
| `destination_ip=<IP> source_ip=<IP> port=<port>` | **单播** `发端IP→收端IP:端口` | `module-rtp-recv sap_address=0.0.0.0`（监听全接口发现单播 SAP） |

### ⚠️ 多播卡顿根因（关键发现）

**多播遇到多网卡机器（WiFi + Docker 桥 + Tailscale）时会卡顿。** 根因：

```
发端 wlp4s0 ──多播 224.0.0.56──▶ Wi-Fi AP
                                      │
                                 helix 收端
                                      │
                    ┌─────────────────┼─────────────────┐
                    ▼                 ▼                  ▼
               wlp3s0 (WiFi)    tailscale0         br-031c4f05174b (Docker)
                    │                 │                  │
                    └─────────┬───────┘──────────────────┘
                              ▼
                    pipewire-pulse 处理同一包 2-3 次
                         → 音频帧错乱 → 卡顿
```

**防火墙（nftables/iptables）无法解决此问题**，因为内核多播路由在 INPUT 链之前已经把包复制到了多个接口的上层协议栈。

**单播没有此问题** —— 只有一个目标 IP:端口，包只从 wlp3s0 进来一次。

---

## 实践验证过的稳定配置

### 最终方案：单播 + L16，端口 47024

双机拓扑：**x1tablet（192.168.1.249）→ helix（192.168.1.102，HDMI→飞利浦 BDM4065）**

**发端**（`~/.config/pipewire/pipewire-pulse.conf.d/99-rtp-send.conf`）：
```ini
context.exec = [
    { path = "pactl" args = "load-module module-null-sink sink_name=rtp_to_helix" }
    { path = "pactl" args = "load-module module-rtp-send
        source=rtp_to_helix.monitor
        destination_ip=192.168.1.102
        source_ip=192.168.1.249
        port=47024" }
    { path = "pactl" args = "set-default-sink rtp_to_helix" }
]
```

**收端**（在 helix 上，`~/.config/pipewire/pipewire-pulse.conf.d/99-rtp-recv.conf`）：
```ini
context.exec = [
    { path = "pactl" args = "load-module module-rtp-recv sap_address=0.0.0.0" }
]
```

### 其他可选但非必要的参数

| 参数 | 作用 | 是否必需 |
|---|---|---|
| `mtu=1400` | 防止 IP 分片 | 可选（默认 1280 也没问题） |
| `inhibit_auto_suspend=always` | 防止 null-sink 静音暂停 | 可选 |
| `enable_opus=true` | 用 OPUS 编码代替 L16（消除量化噪声） | 可选（单播 L16 也无杂音） |
| `latency_msec=XXX` | jitter buffer | **不需要**（单播本地 WiFi 无卡顿） |

### 重启后检查命令

```bash
# 发端
pactl list modules short | grep -E "rtp|null"

# 收端
ssh dr@helix "pactl list modules short | grep rtp"
ssh dr@helix "pw-link -l | grep -E 'x1tablet|hdmi'"
```

---

## SOP：从零搭建 x1tablet → helix RTP 音频流

### 第 1 步：检查双机连通性

```bash
ssh dr@helix "hostname"  # 确认 SSH 可达
ping -c 3 192.168.1.102  # 确认本地 IP 可达
```

### 第 2 步：创建发端配置

写入 `~/.config/pipewire/pipewire-pulse.conf.d/99-rtp-send.conf`（内容见上）。

### 第 3 步：创建收端配置

在 helix 上写入 `~/.config/pipewire/pipewire-pulse.conf.d/99-rtp-recv.conf`（内容见上）。

### 第 4 步：重启 pipewire 系统

```bash
# 两边都执行
systemctl --user restart pipewire pipewire-pulse wireplumber
sleep 4
```

### 第 5 步：验证链路

```bash
# 发端：模块加载 + 默认 sink
pactl list modules short | grep rtp
pactl info | grep "Default Sink"    # 应为 rtp_to_helix

# 收端：自动连线到 HDMI
ssh dr@helix "pw-link -l | grep x1tablet"
# 应看到 x1tablet:receive_* → hdmi-stereo:playback_*
```

### 第 6 步：放音测试

Chrome 或其他应用播放音频，确认 helix HDMI 出声。

---

## 热重载命令（不改配置文件时的即时测试）

### 发端

```bash
pactl unload-module <module-id>
pactl load-module module-null-sink sink_name=rtp_to_helix
pactl load-module module-rtp-send source=rtp_to_helix.monitor \
    destination_ip=192.168.1.102 source_ip=192.168.1.249 port=47024
pactl set-default-sink rtp_to_helix
```

### 收端

```bash
ssh dr@helix "pactl unload-module <id>; \
    pactl load-module module-rtp-recv sap_address=0.0.0.0"
```

---

## 故障排查清单

### 没声音

```bash
# 1. 发端有应用在播吗？
pactl list sink-inputs short

# 2. 收端收到 RTP 包了吗？
ssh dr@helix "ss -ulpn | grep pipewire"
# → 应看到 0.0.0.0:<port> 监听

# 3. 收端连线到 HDMI 了吗？
ssh dr@helix "pw-link -l | grep -E 'x1tablet|hdmi'"
# → 应有 x1tablet:receive_* → hdmi-stereo:playback_*

# 4. HDMI sink 是 RUNNING 吗？
ssh dr@helix "pactl list sinks short | grep hdmi"
# → State 应为 RUNNING
```

### 有杂音（爆音/噼啪声）

```bash
# 确认是 16-bit 量化噪声还是时钟漂移
# 16-bit 量化噪声 → 发端加 enable_opus=true 消除
# 时钟漂移爆音 → 一般是多播导致的、非单播
# 先确认网络模式：
pw-cli list-objects | grep rtp_session | grep destination
# destination.ip = 224.0.0.56 → 多播！改为单播
# destination.ip = 192.168.1.102 → 单播，检查其他因素
```

### 卡顿（断断续续）

```bash
# 排查网络模式（多播 90% 是根因）
# 多播解决方案：改用 destination_ip + source_ip + port 单播

# 如果已是单播，检查系统内存压力
free -h
# 可用 < 1GB 且 Swap 在用 → 内存压力导致 PipeWire 被换出

# 检查 quantum 设置
grep -r "quantum" /usr/share/pipewire/ /etc/pipewire/ ~/.config/pipewire/ 2>/dev/null
```

---

## 关键原理

### SAP 自动发现机制

发端 `module-rtp-send` 发送 **SAP 公告**（Session Announcement Protocol），内含 SDP 描述（IP、端口、格式、编码）。收端 `module-rtp-recv` 收到公告后，自动在对应地址开监听口。

- 多播模式：SAP 走 `224.0.0.56:9875`，RTP 数据走 `224.0.0.56:动态端口`
- 单播模式：SAP 走收端 IP:9875，RTP 数据走收端 IP:指定端口

**收端不需要"知道"发端用什么模式** —— 它只是照着 SAP 公告上的地址去听。

### 固定端口 vs 动态端口

- 动态端口（默认 46000–47024）→ 每次重加载变一次，排障困难
- 固定端口 → 防火墙、抓包、排障都方便
- 单一收端的场景无需动态端口，固定端口更优

---

## 参数发现技巧

PulseAudio 模块的所有可用参数可通过 `help` 查看：

```bash
pactl load-module module-rtp-send help
# → source=<name> format=<format> channels=<n> rate=<n>
#   destination_ip=<IP> source_ip=<IP> port=<n> mtu=<n>
#   enable_opus=<bool> inhibit_auto_suspend=<mode> ...
```

## 模块热重载（不改配置文件时）

### 完整重启（最干净）

```bash
# 两边都执行
systemctl --user restart pipewire pipewire-pulse wireplumber
```

### 仅热重载 RTP 模块

```bash
# 发端
RTP_ID=$(pactl list modules short | grep module-rtp-send | awk '{print $1}')
NULL_ID=$(pactl list modules short | grep module-null-sink | awk '{print $1}')
pactl unload-module $RTP_ID
pactl unload-module $NULL_ID
pactl load-module module-null-sink sink_name=rtp_to_helix
pactl load-module module-rtp-send source=rtp_to_helix.monitor \
    destination_ip=192.168.1.102 source_ip=192.168.1.249 port=47024
pactl set-default-sink rtp_to_helix

# 收端
RTP_ID=$(pactl list modules short | grep module-rtp-recv | awk '{print $1}')
pactl unload-module $RTP_ID
pactl load-module module-rtp-recv sap_address=0.0.0.0
```

## 麦克风输入诊断（白噪音 / 无声 / 声音过小）

麦克风问题 90% 不是 PipeWire 的事，是 ALSA / HDA codec 底层的事。诊断顺序：

### 第 1 步：确认当前 default source

```bash
pactl get-default-source
# → alsa_input.pci-0000_00_1f.3.analog-stereo   (笔记本内置麦)
# → alsa_input.usb-...                            (USB 麦)
# → alsa_input.pci-...monitor                     (某 sink 的 monitor —— 这不是真麦！)

# 列出所有 source + 活跃端口
pactl list sources short
pactl list sources | grep -A2 "Active Port"      # analog-input-internal-mic / analog-input-mic / analog-input-headset-mic
```

如果 Active Port 是 monitor 或错误的 jack，路由没配对，先修这个。

### 第 2 步：HDA codec pin 配置 —— 决定物理上哪些 pin 算输入

```bash
cat /sys/class/sound/hwC0D0/init_pin_configs
# 例：
#   0x12 0x90a60130   ← Internal Mic (pin 18)
#   0x18 0x411111f0   ← No Connection
#   0x19 0x04a11040   ← 物理是耳机孔，但 autoconfig 经常把它误判为 Mic
#   0x21 0x04211020   ← Headphone jack
```

每个 pin config word 的解码见 `references/x1tablet-ALC295-mic-bug.md` 末尾。

**关键诊断信号**：
- pin 0x12 配置成 Internal Mic + `Default Device: A (Mic in)` → 唯一真内置麦
- pin 0x19 物理是耳机孔但 kernel autoconfig 输出 `Mic=0x19` → autoconfig 在乱来，需要 fixup 或 hdajackretask 修正

### 第 3 步：检查 kernel 是否应用了 fixup

```bash
sudo dmesg | grep -E 'alc295|hdaudio' | head -20
# 期望看到 "picked fixup for PCI SSID 17aa:XXXX" → 有 quirk 介入
# 如果没这句 = 内核对这套硬件没专属 quirk，跑纯 autoconfig（容易出问题）
```

**对照内核源码**确认 fixup 是否存在（v6.12）：
```bash
curl -sL https://raw.githubusercontent.com/torvalds/linux/v6.12/sound/pci/hda/patch_realtek.c -o /tmp/pr.c
grep -E '0x17aa, 0x你机器的subsystem' /tmp/pr.c
# 0 matches = 没 quirk，需要 hdajackretask 或换 SOF 驱动
```

### 第 4 步：实测录一段 + 频谱分析

```bash
arecord -D plughw:0,0 -f S16_LE -r 48000 -d 3 /tmp/probe.wav
python3 /home/dr/.hermes/skills/local_share/sway/pipewire-audio-routing/scripts/mic-spectrum-probe.py /tmp/probe.wav
```

脚本会输出 DC 偏移 / RMS / 频谱峰值 / 分频段能量，自动判断是不是"悬空 pin"模式（白噪音经典症状）。退出码 1 = 是这个 bug。

**判定标准速查**：
| 症状 | DC 偏移 | RMS (dBFS) | 频谱特征 |
|---|---|---|---|
| 正常 | < 100 | < -35 | 300-3400 Hz 有峰 |
| 悬空 pin（白噪音） | > 200 | > -30 | DC + sub-200Hz 占大头，200-8000Hz 平坦 |
| Mute 了 | < 50 | < -60 | 全频都低 |

### 第 5 步：修复路径（按代价排）

1. **换 SOF 驱动**（首选，架构性修复）
   ```bash
   echo "options snd-intel-dspcfg dsp_driver=3" | sudo tee /etc/modprobe.d/sof-fix.conf
   sudo update-initramfs -u && sudo reboot
   ```
   Skylate/KabyLake/ApolloLake/CannonLake 之后机器优先用 SOF。前提：`/usr/lib/firmware/intel/sof-tplg/` 里有匹配的 topology。

2. **hdajackretask 手动 pin remap**（fallback）
   ```bash
   sudo apt install alsa-tools-gui
   hdajackretask
   ```
   找到错误归类的 pin（如 0x19），改成 "Not connected"，勾 "Install boot override"，重启。

3. **`options snd-hda-intel model=...` 强制 quirk**（针对已知相似机型的 fixup）
   先 `grep -E 'FIXUP.*你子型号相似' /tmp/pr.c` 找到候选 fixup 名，再 `echo "options snd-hda-intel model=<fixup-name>"`。

4. **外接 USB 麦**（兜底，绕开 HDA 整个问题）

### x1tablet 已知坑

Lenovo X1 Tablet Gen 3 (subsystem `17aa:2263`) 的 ALC295 在内核 fixup 表里**不存在条目**。症状 + 修复细节全部整理在：

📁 **`references/x1tablet-ALC295-mic-bug.md`**

---

## 注意

- **模块 ID ≥ 500M** 表示运行时动态加载（`pactl load-module`），重启 pipewire 后丢失。必须写入 `pipewire-pulse.conf.d/` 才能持久。
- **不要混用 `destination=` 和 `destination_ip=`** — 前者触发多播，后者触发单播。混用时最后一个参数生效。
- **原生 `libpipewire-module-rtp-sink/source`**（PipeWire 原生模块）有更多控制参数（`local.ifname`、`sess.ts-direct`、`audio.format`），但在 PipeWire 1.4.2 上测试未成功发流（模块加载为 running 但无网络包发出），暂不可用。PipeWire ≥ 1.6 可能已修复。
- **`format=` 参数限制**：`module-rtp-send` 只接受 `format=s16le`，更高位深（`S24_32LE`、`S32LE`、`float32le`）全部被拒。RTP payload 始终为 L16（16-bit）。想绕过此限制只能用 `enable_opus=true`。
- **`wpctl` ID 会变**：每次 PipeWire 重启 / set-default 之后 node ID 可能变。`wpctl inspect <id>` 之前**必须重新跑 `wpctl status`** 拿当前 ID，否则可能 inspect 到一个无关设备（如 V4L2 摄像头）。
