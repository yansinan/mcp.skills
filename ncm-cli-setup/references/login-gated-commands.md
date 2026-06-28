# ncm-cli 登录门控命令

## 发现

`ncm-cli v0.1.6` 的命令输出依赖登录状态。`ncm-cli commands` 在登录前后输出完全不同的命令集：

**登录前**：仅约 10 个播放控制命令
**登录后**：约 40+ 命令，包含搜索/推荐/红心/歌单管理/用户数据/专辑/歌词/评论/笔记等

## 测试确认过程

1. `ncm-cli login --check --output json` 确认登录态（`"success": true`）
2. `ncm-cli commands` 在登录后首次调用时显示完整命令树
3. 所有数据操作命令在登录前直接调用会报错（命令不存在）

## 命令分类（登录后）

### 播放控制
```bash
ncm-cli play --song --encrypted-id <32位hex> --original-id <数字ID>
ncm-cli play --playlist --encrypted-id <id> --original-id <id>
ncm-cli pause / resume / stop / next / prev
ncm-cli seek <秒> / volume <0-100>
ncm-cli queue [add|clear] [--encrypted-id <id>]
ncm-cli state
```

### 搜索
```bash
ncm-cli search song --keyword <词> --limit 30 --output json
ncm-cli search album --keyword <词> --output json
ncm-cli search playlist --keyword <词> --output json
ncm-cli search all --keyword <词> --output json
```

### 推荐
```bash
ncm-cli recommend daily --output json          # 30首每日推荐
ncm-cli recommend heartbeat --playlistId <id> --songId <id> --count 20  # 心动模式
ncm-cli recommend fm --type <场景> --code <场景code>  # 私人漫游
```

### 红心 & 歌词
```bash
ncm-cli song like --songId <32位hex> --output json
ncm-cli song dislike --songId <32位hex> --output json
ncm-cli song lyric --songId <32位hex> --output json
```

### 用户
```bash
ncm-cli user favorite --output json        # 红心歌单 {id, name, trackCount}
ncm-cli user history --limit 50 --output json
ncm-cli user listen-ranking --output json
ncm-cli user info --uid <用户ID> --output json
```

### 歌单
```bash
ncm-cli playlist collected --output json      # 收藏的歌单
ncm-cli playlist created --output json        # 创建的歌单
ncm-cli playlist radar --output json          # 雷达歌单
ncm-cli playlist get --id <id> --output json  # 详情
ncm-cli playlist tracks --playlistId <id> --output json # 歌曲列表
ncm-cli playlist add --id <id> --songIds <csv> # 加歌
ncm-cli playlist remove --id <id> --songIds <csv> # 删歌
ncm-cli playlist create --name <名> --output json # 创建
```

## 搜索结果 JSON 结构

```json
{
  "code": 200,
  "data": {
    "records": [{
      "id": "19F4FB008BF6...",           // 32位hex加密ID → --encrypted-id
      "originalId": 509781655,           // 数字明文ID → 链接
      "name": "想你就写信 (Live)",
      "artists": [{"name": "周杰伦"}],
      "album": {"name": "中国新歌声...", "id": "1BBE81..."},
      "visible": true,                   // false=不可播放
      "liked": false,                    // 是否已红心
      "coverImgUrl": "http://p1.music.126.net/..."
    }]
  }
}
```
