# RTK — Rust Token Killer

> Token 消费压缩工具，在终端输出到达 LLM 上下文前进行过滤压缩。
> 官方仓库：https://github.com/rtk-ai/rtk（⭐ 63.4k）
> 官网：https://www.rtk-ai.app

## 是什么

Rust 单二进制 CLI 代理，零依赖，延迟 <10ms。在 LLM agent 和 shell 之间插一层——命令输出经 RTK 过滤后再进上下文窗口。

## 原理

```
无 RTK: Agent → git status → shell → git → 原始输出(~2000 tokens) → Agent
有 RTK: Agent → git status → RTK → 过滤后输出(~200 tokens) → Agent
```

四条策略：
1. **Smart Filtering** — 去注释、空白、样板代码
2. **Grouping** — 相似项聚合（按目录分组文件，按类型分组错误）
3. **Truncation** — 保留关键上下文，裁掉冗余
4. **Deduplication** — 重复日志行折叠为计数

## Token 节省实测

| 操作 | 原始 | RTK 后 | 节省 |
|------|------|--------|------|
| `ls`/`tree` | 2000 | 400 | -80% |
| `cat`/`read` | 40000 | 12000 | -70% |
| `grep`/`rg` | 16000 | 3200 | -80% |
| `git status` | 3000 | 600 | -80% |
| `git diff` | 10000 | 2500 | -75% |
| `git add/commit/push` | 1600 | 120 | -92% |
| `cargo test`/`npm test` | 25000 | 2500 | -90% |
| `pytest` | 8000 | 800 | -90% |
| **总计(30min会话)** | **~118K** | **~24K** | **-80%** |

## Hermes 集成

**官方支持**：`rtk init --agent hermes` 一键启用。

Hermes 被列为支持 Agent 之一，走**插件 API** 模式（非 Bash hook），命令在到达 shell 前被 RTK 重写。

## 安装（Linux）

```bash
# 一键安装
curl -fsSL https://raw.githubusercontent.com/rtk-ai/rtk/refs/heads/master/install.sh | sh
# 或 via cargo
cargo install --git https://github.com/rtk-ai/rtk
# 启用 Hermes 集成
rtk init --agent hermes
```

安装到 `~/.local/bin/`，需要加入 PATH。

## 常用命令

| 命令 | 说明 |
|------|------|
| `rtk read file.rs -l aggressive` | 只保留函数签名（去掉函数体），激进模式 |
| `rtk git status` | `git status` 精简版 |
| `rtk git log -n 10` | 一行一条 commits |
| `rtk diff file1 file2` | 精简 diff |
| `rtk grep "pattern" .` | 分组搜索结果 |
| `rtk find "*.rs" .` | 精简版 find |
| `rtk test cargo test` | 通用测试包装器，只报失败 |
| `rtk err <cmd>` | 只保留 stderr 中的错误行 |
| `rtk gain` | Token 节省统计总览 |
| `rtk gain --graph` | ASCII 图表（近 30 天） |
| `rtk discover` | 发现遗漏的节省机会 |
| `rtk session` | 查看 RTK 在最近会话中的采用率 |

支持 Git、GitHub CLI、测试框架（pytest/cargo test/go test/jest/vitest/rspec）、
构建工具（cargo build/tsc/eslint/next build/ruff/golangci-lint）、
包管理器（pnpm/pip/bundle/prisma）、AWS CLI、容器（docker/kubectl）、
数据工具（json/log/curl/wget/env）等 100+ 命令。

全局标志：`-u`（超紧凑模式，额外省 Token）、`-v`（详细输出）。

## 与其他同类工具的关系

RTK 所属的 **Context Forge** 生态系统：
- **RTK** — 命令输出压缩（Token Killer）
- **ICM** — 持久化会话记忆（Infinite Context Memory）
- **Vox** — 语音输出（3 个 TTS 后端）

## 对当前环境的适用性分析

**优势**：
- Rust 单二进制，安装极简
- 对终端密集型工作流收益巨大（-60~90%）
- 有官方的 `--agent hermes` 集成模式

**需验证的点**：
- Hermes 内置工具（`read_file`、`search_files`、`patch`）不走 shell → 不走 RTK 管道。RTK 只压缩 `terminal()` 调用中的裸 shell 命令输出
- 当前工作流中 terminal 调用的比例决定了实际收益大小
- 若大量使用 `read_file`/`search_files` 替代 `cat`/`grep`，RTK 的收益会低于 Claude Code 那种场景

## 与 deepseek-cost 的关系

```
deepseek-cost  → 监控 Token 花了多少钱（花钱端）
RTK            → 压缩 Token 用量（省 Token 端）
```

两者互补。可 cron 结合：先 RTK 压用量，再 deepseek-cost 看余额走向。
