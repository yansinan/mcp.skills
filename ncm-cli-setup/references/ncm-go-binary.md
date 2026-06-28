# ncm Go 二进制 (Davied-H/ncm-cli)

## 来源

Go 二进制 `~/.local/bin/ncm` 来自 **Davied-H/ncm-cli**，Go 编写的网易云音乐 CLI 工具。

- **仓库**: https://github.com/Davied-H/ncm-cli
- **版本**: v0.2.1 (commit `7cd31ae24f76`)
- **安装**:

```bash
npx --yes github:Davied-H/ncm-cli install --dir ~/.local/bin
```

从 GitHub Release 下载预编译二进制，不依赖 Go 编译器。

## 关系

| | `ncm` (Go) | `ncm-cli` (npm) |
|---|---|---|
| **来源** | `github:Davied-H/ncm-cli` | `npm install -g @music163/ncm-cli` |
| **版本** | v0.2.1 | v0.1.6 |
| **用途** | 数据层：搜索/歌单/推荐/歌曲信息 | 播放层：play/pause/next/state |
| **登录** | Playwright 浏览器（拒用） | `login --background` 二维码（推荐） |
| **session** | 与 ncm-cli 不共享 | 与 ncm 不共享 |

## 部署

```bash
# 安装/恢复
npx --yes github:Davied-H/ncm-cli install --dir ~/.local/bin

# 验证
ncm --version
# 期望: ncm 0.2.1 (7cd31ae24f76)
```

## 重要

- **不要改名** `~/.local/bin/ncm` — 它是 Go 二进制
- **不要用** `ncm login`（Playwright）
- 登录走 `ncm-cli login --background` 二维码
- waybar 配置始终调用 `ncm-player`，不调用 `ncm`
