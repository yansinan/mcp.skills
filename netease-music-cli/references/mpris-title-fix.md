# MPRIS 歌名修正（force-media-title）

## 问题

ncm-cli 通过 mpv 播放歌曲时，直接把音频 URL 传给 mpv，导致 **MPRIS 标题显示 URL 文件名**（如 `96edd3549b92f30c4d67af168e90b049.mp3`），而非真实歌名。

```bash
playerctl -p mpv metadata xesam:title
# → 96edd3549b92f30c4d67af168e90b049.mp3  ❌
```

## 原因

mpv 加载 URL 时没有 metadata 源。`ncm-cli state --output json` 的 `title` 字段包含正确歌名（来自 API 响应），但不会传递给 mpv。

## 修复

播放后通过 mpv IPC 设置 `force-media-title` 属性：

```bash
mpv_set_title() {
  local title="$1"
  for sock in /home/dr/.config/ncm-cli/mpv.sock /tmp/ncm-mpv.sock; do
    [ -S "$sock" ] || continue
    python3 -c "
import socket, json
try:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(2)
    s.connect('$sock')
    s.sendall(json.dumps({'command':['set_property','force-media-title','$title'],'request_id':1}).encode()+b'\\n')
    s.close()
except: pass
" 2>/dev/null || true
    return 0
  done
}
```

调用方式（延迟 2 秒等 mpv 加载完成）：
```bash
ncm-cli play --song --encrypted-id "<ID>"
(sleep 2; mpv_set_title "歌手 - 歌名") &
```

## 验证

```bash
# IPC 响应
python3 -c "
import socket, json
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.settimeout(2)
s.connect('/home/dr/.config/ncm-cli/mpv.sock')
s.sendall(json.dumps({'command':['set_property','force-media-title','测试标题'],'request_id':1}).encode()+b'\n')
import time; time.sleep(0.5)
resp = s.recv(4096)
s.close()
print('IPC response:', resp)
"

# MPRIS 确认
sleep 1
playerctl -p mpv metadata xesam:title
# → 测试标题  ✅
```

## 注意事项

- ncm-cli 以 `--idle` 模式启动 mpv，IPC socket 路径固定为 `/home/dr/.config/ncm-cli/mpv.sock`
- `force-media-title` 可以随时设置，不要求文件已加载
- 设标题后 mpv-mpris 自动发出 `org.mpris.MediaPlayer2.PropertiesChanged` 信号，waybar 实时更新
