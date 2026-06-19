---
name: rclone
source: https://rclone.org/docs/
description: "Configure and use rclone — the rsync-for-cloud-storage CLI. Covers remote setup, 2FA, per-backend quirks, sync/copy/mount operations, rcd daemon + web UI, and common pitfalls."
tags: [rclone, cloud, storage, sync, backup, icloud]
---

# rclone

`rclone` 是统一的 CLI，对接 70+ 云存储提供商。本技能覆盖通用配置模式和各后端的专属坑点。

## 何时加载

- 用户要"配置 rclone"、"搭建云同步"、"挂载云盘"
- 新增 remote、刷新过期 auth、调试 rclone 错误
- 本地文件备份到云，或云间互拷
- 启动/重启/调试 rcd 守护进程或 Web UI

## 快速起步

```bash
rclone version              # 确认 v1.65+（iCloud 需要）
rclone listremotes          # 查看已有 remotes
rclone lsd <name>:          # 测试单个 remote 访问
```

## 基本流程

### 预检

```bash
rclone version              # 确认版本够新
rclone listremotes          # 现有 remotes
```

### 交互式配置

```bash
rclone config
```

1. `n` → 新 remote，取短名（如 `gd`、`icloud`）
2. 找到 backend — 在长列表里 `/icloud` 搜索，或直接输编号
3. 按提示输入凭据
4. **最后执行 `s) Set configuration password`** 加密 config 文件

**用户偏好**：交互式配置（需要密码/2FA）让用户在自有终端执行，不通过 PTY 驱动。给出步骤清单即可。

### 常见操作

```bash
rclone lsd remote:                          # 列出顶层目录
rclone tree remote: --max-depth 2           # 树形目录
rclone copy /local/path remote:dest/ -P     # 上传（带进度）
rclone sync remote:src/ /local/dest/ -P     # 镜像（⚠ 目标端文件会删除）
rclone mount remote: ~/mnt/cloud --vfs-cache-mode full  # FUSE 挂载
rclone ncdu remote:                         # 交互式磁盘用量
rclone config reconnect <name>:             # 刷新 2FA token
```

### 验证

```bash
rclone lsd remote: --max-depth 1
rclone copy remote:small-file /tmp/
```

用最小的读取测试 auth/permission，避免在大量数据前踩坑。

## 2FA / 认证

### 2FA 代码与 rclone session 绑定（关键）

Apple 的 2FA push 代码与特定的 SRP 握手绑定。每次 `rclone config reconnect` 产生新的 push → 新代码。**旧代码（来自之前的 push）会被 Apple 拒绝**（错误 -21669）。

**标准流程：**
1. 运行 `rclone config reconnect icloud:`（触发新的 SRP 握手 + push）
2. **等** 2FA 提示出现后，再去手机上点 Allow
3. 输入手机上的新鲜代码
4. 不要提前要代码 —— 用完即废

**SMS 替代方案（推荐用于 agent 驱动）：**
在 `config_2fa>` 提示处输入 `sms` 而非 6 位数。Apple 发短信，短信代码不严格绑定 session，时序更宽松。

### 命令名随版本变化

`rclone reconnect` 在官方文档有提及，但在 **v1.74.x 不是顶层命令**。用 `rclone config reconnect <name>:`（config 的子命令）。新版本已加顶层 `rclone reconnect`。

### 编辑 remote 时遇 2FA 提示

如果在 `rclone config → e` 时看到 `config_2fa>`，说明 token 已过期。**不要输 `q` 退出** —— rclone 把 `q` 当 2FA 码发给 Apple 返回验证失败并退出。用 **Ctrl+C** 干净退出，然后 `rclone config reconnect <name>:` 走正常续期路径。

## 配置文件

- 位置：`~/.config/rclone/rclone.conf`（建议 0600 权限）
- **默认明文**——密码可见。执行 `s) Set configuration password` 加密整个文件
- web UI 密码（与 config 加密无关）存在 `~/.config/rclone/webui-password`（从 `--rc-pass` 读取）

**⚠ webui-password 与 systemd unit 的 `--rc-pass=` 必须同步。** 改密码需同时更新两个地方 + `daemon-reload + restart`。

## rcd（守护进程）和 Web UI

`rclone rcd --rc-web-gui` 作为守护进程运行。

- **rcd 启动时加载 `rclone.conf`**。新增/修改 remote 后必须重启。
- Web UI 首次启动下载 ~50MB 资源到 `~/.cache/rclone/webgui/`
- 通过 `rclone rc` CLI 访问 API，**不要用 curl 直接调 `/rc/` 路径**

## 后端专属坑点

### iCloud（参见 `references/icloud.md`）

| 问题 | 说明 |
|------|------|
| app-specific 密码 | ❌ 不接受，必须用主密码 + 2FA |
| 国内 Apple ID | ❌ v1.74.3 不支持 `iCloud.com.cn`（issue #8257），用非国内 ID |
| 2FA session-bound | 见上节 |
| Photos 需要初始化 zone | 新 Apple ID 需先登录 icloud.com 启用 Photos |
| Trust token 有效期 | ~30 天，提前 `rclone config reconnect` |

### S3 兼容后端

MinIO、Backblaze B2、Wasabi、阿里云 OSS 等需要明确 region + endpoint，即使文档未强调。

### 其他

- `rclone sync` 是**破坏性**操作。总加 `--dry-run`。
- FUSE 挂载需要 `fusermount3` + 用户在 `fuse` 组。
- iCloud Drive 元数据写入受限 —— 上传可以，元数据操作可能报错。
- 不要高频写挂载点 —— 云速率限制会触发，Apple/Google 可能标记设备。

## iCloud Photos 目录结构

```
<remote>:
├── PrimarySync/               ← 个人照片库
│   ├── All Photos/            ← 所有照片（按日期）
│   ├── Favorites/             ← 收藏
│   ├── <album-name>/          ← 用户创建相册
│   └── Recently Deleted/
└── Shared/                    ← 共享相簿
    └── <shared-album-name>/
```

`ZONE_NOT_FOUND` → Photos 从未初始化，需要登录 icloud.com 启用。

## 参考文件

- `references/icloud.md` — iCloud Drive + iCloud Photos (SRP auth, 2FA, 国内 ID, ZONE_NOT_FOUND)
