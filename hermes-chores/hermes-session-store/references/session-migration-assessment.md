# Session Migration Assessment — serverhome 实例（实测数据）

日期：2026-05-29（实测）
来源会话：核查旧 `hermes-memory-store` 配置 + serverhome 实例会话迁移可行性 实证评估

## 背景

serverhome（`100.66.66.203`，`serverhome.tail2e6efb.ts.net`，Tailscale 直连 2ms）上有一个旧 Hermes 实例，数据在 `/home/dr/workspace/.hermes/`。用户希望评估能否将旧实例的**会话历史原文**（state.db）同步到本机。

## 获取数据的前置条件

本机公钥（`~/.ssh/id_rsa.pub`，锚定 `yansinan@163.com`）需要先添加到 serverhome 的 `~/.ssh/authorized_keys`。

```bash
ssh-copy-id dr@serverhome
# 之后即可直连：
ssh dr@serverhome "echo connected"
```

Tailscale 已直连（`tailscale status` 显示 `direct 192.168.1.1:8603`），不必开额外端口。

## 实测数据

### 旧实例 state.db

| 检查项 | 值 |
|---|---|
| 文件大小 | 420MB（+ 421MB WAL） |
| schema_version | **13**（本机当前：**14**） |
| sessions | **320** 条 |
| messages | **14,097** 条 |
| 时间范围 | 2026-04-21 ～ 2026-05-29（约 5 周） |
| 按 source | cli: 143, api_server: 84, webui: 64, cron: 16, weixin: 13 |

### Schema 兼容性验证

对比双方 `sessions` 和 `messages` 表的 CREATE TABLE 语句：

- 列完全相同
- v13 有几列是后来 ALTER TABLE 追加的（"api_call_count", "handoff_state", "handoff_platform", "handoff_error", "reasoning_content", "codex_message_items", "platform_message_id", "observed"），但字段集与 v14 一致
- **v13→v14 迁移仅更新 schema_version 值，无表结构变更**

即：scp 过来后，Hermes 启动时自动做一步简单的 UPDATE 即可完成迁移。

### 其他存储系统的实际状态

| 存储 | 大小 | 状态 |
|---|---|---|
| sessions/*.jsonl | 550MB（archived 170M + request_dump 380M） | state.db 的冗余转储，非必需 |
| memory_store.db | 188KB + 2.5MB WAL | 全息记忆插件数据，但 provider 未启用（memory.provider: honcho），不过期 |
| mem0.json | 119B | serverhome 独有 mem0 配置（指向 192.168.1.203:8888），本机无 |
| memories/MEMORY.md + USER.md | 12K | 文件记忆，本机已有独立副本 |
| **Honcho** | 远程 | ✅ **已共享** — 见下文 |

### Honcho 已共享（无需迁移）

两个 Honcho 配置指向同一服务：

```
serverhome: honcho.json → baseUrl = "http://honcho-api-1:8000"   # Docker 内部
本机:       honcho.json → baseUrl = "http://serverhome:8000"      # Tailscale
```

这俩实际是 serverhome 上同一个 Honcho 服务。所以用户的 Honcho 画像数据两个 Hermes 实例都已经能访问。

### 核心概念澄清：state.db vs Honcho

| 维度 | state.db（需要导入） | Honcho（已共享） |
|---|---|---|
| 存储内容 | 完整对话原文 | 提炼后的用户画像/结论性摘要 |
| 数据形态 | sessions + messages 表 + FTS5 全文索引 | peer card + 语义推理 |
| 对应工具 | session_search | honcho_profile/reasoning/conclude |
| 一句话 | "过去我说过什么" | "我是什么样的人" |

## 数据迁移方案

### 状态评估摘要

| 要素 | 结论 |
|---|---|
| 网络 | ✅ Tailscale 直连 2ms |
| SSH | ✅ ssh-copy-id 后可用 |
| Schema 兼容 | ✅ v13→v14 仅版本号变更，无结构冲突 |
| ID 冲突 | 极低风险（UUID 字符串 PK） |
| 迁移目标 | 仅 state.db（420MB），其他存储非必需 |

### 推荐方案：全量 scp + 合并脚本

```bash
# 1. 安全拷贝前，如有必要先停 serverhome 的 Hermes / checkpoint WAL
ssh dr@serverhome 'sqlite3 /home/dr/workspace/.hermes/state.db "PRAGMA wal_checkpoint(FULL)"'

# 2. 拷贝 DB
scp dr@serverhome:/home/dr/workspace/.hermes/state.db /tmp/old_state.db

# 3. 合并到本地 state.db
# 核心逻辑：
#   - 逐 session INSERT OR IGNORE INTO sessions
#   - 逐 message INSERT INTO messages（FTS5 触发器自动重建索引）
#   - 可添加过滤：只导入指定 source（webui / api_server），跳过 cron/weixin
```

可选过滤参数：
- --sources webui,api_server 导入 148 条活跃 session
- --since 2026-05-01 只导入最近一个月
- --limit 50 只导入最近 50 条

## 迁移可行性模板

跨实例迁移前回答：

1. **源实例可达？** → SSH / Tailscale / API
2. **SSH 认证就绪？** → ssh user@host -o BatchMode=yes 'echo ok'
3. **schema 兼容？** → 检查双方 schema_version，对比 CREATE TABLE
4. **ID 冲突风险？** → 极小（UUID），INSERT OR IGNORE 兜底
5. **Memory provider 数据是否已共享？** → 检查 Honcho 的 baseUrl
6. **选方案：** → 直接复制 DB（推荐）/ export + resume / rsync

## Used in

参考 hermes-session-store SKILL.md 中的 Cross-Instance Session Migration 章节。
