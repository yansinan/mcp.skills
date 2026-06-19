# 完整调试记录：x1tablet → helix RTP 音频流

> 2026年6月调试会话记录。记录了从原始配置到最终稳定方案的完整过程，包括所有失败的尝试和根因分析。

---

## 环境

|  | 发端 | 收端 |
|---|---|---|
| 主机 | x1tablet | helix |
| OS | Debian 13, PipeWire 1.4.2 | 同左 |
| IP | 192.168.1.249（wlp4s0） | 192.168.1.102（wlp3s0） |
| 其他网络 | tailscale0, docker0 | tailscale0, docker0, br-* |
| 音频输出 | — | HDMI → PHL BDM4065 显示器 |

---

## 初始状态

原始配置（来源未知，动态加载）：
- 发端：`module-rtp-send source=rtp_to_helix.monitor destination=100.66.66.102`
- 收端：`module-rtp-recv`（无参数）
- 实际网络路径：多播 `224.0.0.56:动态端口`，L16 编码
- 问题：**卡顿**（断断续续）

---

## 调试过程（按顺序）

### 尝试 1：加 OPUS + MTU + jitter buffer ❌ 更卡了

发端加 `enable_opus=true mtu=1400 inhibit_auto_suspend=always`，收端加 `latency_msec=100`。

**结果：更卡。** 原因：收端无 OPUS 解码能力（`module-rtp-recv` 不处理 OPUS）。

### 尝试 2：原生 PipeWire RTP 模块 ❌ 没声音

改用 `libpipewire-module-rtp-sink/source`（PipeWire 原生），配置 `destination.ip=192.168.1.102:5004`。

**结果：没声音。** 原生模块可加载，RTP 包未成功发出。回退。

### 尝试 3：单播 + OPUS + jitter buffer 250ms ✅ 不卡但有杂音

改为 `destination_ip=192.168.1.102 source_ip=192.168.1.249 port=5004`，收端 `sap_address=0.0.0.0 latency_msec=250`。

**结果：不卡了！但有杂音（爆音）。** 这是第一次确认单播能解决卡顿。

### 尝试 4：单播 + OPUS + jitter buffer 500ms ❌ 杂音依旧

加大缓冲未改善杂音。

### 尝试 5：单播 + OPUS（不用 jitter buffer）✅ 不卡不杂音

去掉 `latency_msec`，发现杂音来自 jitter buffer 的 DLL 时钟补偿重同步，而非 L16 量化噪声。**首次确认单播 + OPUS = 稳定。**

### ← 关键转折：逐步隔离实验 →

### 测试 A：原始多播（全默认）❌ 卡顿

`destination=100.66.66.102`，收端无参数，L16。**卡顿。** → 确认多播是卡顿嫌疑。

### 测试 B：多播 + OPUS 仅改这一个变量 ❌ 卡顿

发端 `enable_opus=true`，其他全部默认。**卡顿。** → 确认 OPUS 不解决卡顿，卡顿是网络路径问题。

### 测试 C：单播 + OPUS ✅ 不卡

发端 `destination_ip=192.168.1.102 source_ip=192.168.1.249 port=5004 enable_opus=true`，收端 `sap_address=0.0.0.0`。**不卡。** → 确认单播解决卡顿。

### 测试 D：多播 + OPUS + 本地网段 ❌ 卡顿

发端 `destination=192.168.1.102 enable_opus=true`。**卡顿。** → 确认多播无论什么 destination IP 都卡。

### 测试 E：单播 + L16（无 OPUS）✅ 不卡、无杂音

去掉 `enable_opus=true`，保留单播。**不卡、无杂音。** → **确认最终方案：单播 + L16，OPUS 非必需。**

---

## 根因

**多播卡顿 = 两台机器都有多个网络接口，同一个多播包被收端处理了多次。**

x1tablet 发 `224.0.0.56:46694`（多播） → Wi-Fi AP 转发 → helix 的 wlp3s0 收到。但 helix 的 Docker 桥（br-031c4f05174b）和 tailscale0 也可能加入同一多播组 → 内核把同一个包递送给 pipewire-pulse 多次 → 音频帧时间戳错乱 → 卡顿。

**防火墙不能解决**：因为内核多播路由在 INPUT 链过滤之前已经把包复制到了多个接口的上层。

**单播完美回避**：包只有一个目标 IP:端口，只从 wlp3s0 进来一次。

---

## 最终稳定配置

### 发端（x1tablet）

`~/.config/pipewire/pipewire-pulse.conf.d/99-rtp-send.conf`：
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

### 收端（helix）

`~/.config/pipewire/pipewire-pulse.conf.d/99-rtp-recv.conf`：
```ini
context.exec = [
    { path = "pactl" args = "load-module module-rtp-recv sap_address=0.0.0.0" }
]
```

### 端口选择

固定 47024（避开了常见的 Docker/Tailscale 端口区间）。收端用 `sap_address=0.0.0.0` 自动发现发端端口，无需显式配置端口。

### 可选参数（纯可选，非必需）

| 参数 | 加在哪 | 作用 | 验证结果 |
|---|---|---|---|
| `mtu=1400` | 发端 | 防 IP 分片 | 不加也没问题 |
| `inhibit_auto_suspend=always` | 发端 | 防 null-sink 暂停 | 不加也没问题 |
| `enable_opus=true` | 发端 | 用 OPUS 代替 L16 | L16 单播已无杂音，非必需 |
| `latency_msec=XXX` | 收端 | jitter buffer | 不加更干净 |

---

## 重启测试验证

重启 `systemctl --user restart pipewire pipewire-pulse wireplumber` 后：

```
发端：module-rtp-send  单播 192.168.1.249→192.168.1.102:47024
收端：module-rtp-recv  sap_address=0.0.0.0 → 监听 0.0.0.0:47024
连线：x1tablet:receive_AUX1 → hdmi-stereo:playback_FL  (WirePlumber 自动连接)
```

放音正常，无卡顿、无杂音。
