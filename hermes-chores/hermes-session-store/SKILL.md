---
name: hermes-session-store
description: "Hermes 内部 session 存储（state.db）：schema 结构、会话迁移、memory provider 对比和切换。跨实例数据操作时加载此技能。"
---

# Hermes Session Store — 内部数据操作

Hermes 的会话历史持久化在 `state.db`（SQLite + FTS5），memory 则有多种 provider 可选。本技能覆盖这些内部数据结构的理解、迁移和运维。

## state.db 结构

位置：`~/.hermes/state.db`

### 核心表

| 表 | 用途 |
|---|---|
| `sessions` | 会话元数据：id, source, model, tokens, title, started_at, ended_at |
| `messages` | 消息内容：role, content, tool_calls, timestamp, token_count |
| `messages_fts` | FTS5 全文索引（standard tokenizer），自动维护 |
| `messages_fts_trigram` | FTS5 trigram 索引，支持模糊匹配 |
| `compression_locks` | 上下文压缩并发锁 |
| `schema_version` | 版本号（当前：14） |
| `state_meta` | 运行时元数据 |

### 表间关系

- `messages.session_id` → `sessions.id`（外键）
- FTS 索引通过触发器自动维护（INSERT / UPDATE / DELETE）

### sessions 表关键字段

- `id` — TEXT PK（UUID 类字符串，非整数自增）
- `source` — 来源标签（`cli`, `webui`, `api_server`, `telegram` 等）
- `title` — 会话标题（可为 NULL，有唯一索引）
- `model`, `input_tokens`, `output_tokens`, `reasoning_tokens`, `estimated_cost_usd`
- `parent_session_id` — 父子关系（分支会话）

### 检查当前状态

```python
import sqlite3
conn = sqlite3.connect('~/.hermes/state.db')
# 版本
conn.execute('SELECT * FROM schema_version').fetchone()
# 会话数量
conn.execute('SELECT COUNT(*) FROM sessions').fetchone()
# 按 source 统计
conn.execute('SELECT source, COUNT(*) FROM sessions GROUP BY source').fetchall()
```

## Cross-Instance Session Migration

将一台机器上的会话迁移到另一台 Hermes 实例。

### 前置检查顺序

1. **网络连通性** — ping / Tailscale 状态
2. **SSH 认证** — `ssh -o BatchMode=yes user@host 'echo ok'`
3. **Schema 兼容性** — 源和目标 `state.db` 的 `schema_version` 必须一致，或源版本 ≤ 目标版本（可升级）。对比双方的 CREATE TABLE 确认列集一致。当前已知：v13→v14 仅版本号变更，无表结构变化。
4. **Honcho 是否已共享** — 检查双方 `honcho.json` 的 `baseUrl`。如果指向同一服务，Honcho 数据不需要迁移。
4. **ID 冲突风险** — `sessions.id` 是 UUID 类字符串，碰撞概率极低

### 迁移方案（按推荐顺序）

**A. 直接复制 state.db（推荐）**
```bash
# 先配对 SSH
ssh-copy-id user@remote

# 取 DB
scp user@remote:~/.hermes/state.db /tmp/old_state.db

# 合并脚本核心逻辑
python3 -c "
import sqlite3

src = sqlite3.connect('/tmp/old_state.db')
dst = sqlite3.connect(dst_path)

# 1. 检查 schema 版本
src_ver = src.execute('SELECT version FROM schema_version').fetchone()[0]
dst_ver = dst.execute('SELECT version FROM schema_version').fetchone()[0]
assert src_ver <= dst_ver, f'源版本 {src_ver} > 目标版本 {dst_ver}，无法直接合并'

# 2. 导入 sessions（INSERT OR IGNORE 防冲突）
src.execute(\"SELECT * FROM sessions\").fetchall()
# → INSERT OR IGNORE INTO sessions

# 3. 导入 messages（FTS5 触发器自动重建索引）
src.execute(\"SELECT * FROM messages\").fetchall()
# → INSERT INTO messages
"
```

**B. `hermes sessions export` + `--resume`**
```bash
ssh user@remote 'hermes sessions export /tmp/export.jsonl'
scp user@remote:/tmp/export.jsonl .
# 然后在目标上逐个 resume
```
- 更安全，但要求远程 Hermes CLI 可用且版本够新

**C. rsync 整个 `.hermes` 目录**
```bash
rsync -avz user@remote:~/.hermes/ /tmp/backup-hermes/
```
- 覆盖面最全但可能包含不需要的缓存/tmp 文件

### 迁移风险

| 风险 | 概率 | 缓解 |
|---|---|---|
| schema 版本不兼容 | 低～中 | 检查 schema_version，拒绝降级导入 |
| session ID 冲突 | 极低 | INSERT OR IGNORE |
| FTS5 索引重建开销 | 可忽略 | INSERT 触发器自动处理 |

## Memory Provider 对比

Hermes 当前的 memory provider 架构通过 `memory.provider` 配置。

### 概念澄清：state.db vs Memory Provider

一个常见混淆点 — state.db 和 memory provider 的角色完全不同：

| | **state.db**（本技能核心） | **Memory Provider**（Honcho / Holographic） |
|---|---|---|
| 存什么 | 对话原文 + FTS5 全文索引 | 提炼后的画像/事实/结论 |
| 大小 | 成百 MB（含全文消息） | KB 到 MB 级别（仅概要） |
| 跨实例迁移 | 需要手动合并/复制 state.db | 如果指向同一后端即已共享 |
| 对应工具 | `session_search` | `memory` / `honcho_profile` / `fact_store` |

**通俗说：** state.db = "过去我说过什么"（历史原文），Memory Provider = "我是什么样的人"（总结画像）。迁移会话历史只动 state.db，不动 memory provider。Honcho 数据如果两个实例指向同一 baseUrl，不需要迁移。

### Honcho（当前在用）

| 属性 | 说明 |
|---|---|
| 类型 | 云端/外部语义推理引擎 |
| 数据位置 | 远程 Honcho 服务 |
| 暴露工具 | `honcho_profile`, `honcho_search`, `honcho_reasoning`, `honcho_conclude` |
| 存储内容 | 提炼后的用户画像、结论性摘要（非对话原文） |
| 特征 | 跨会话深层语义推理，用户画像 persistence |
| 启用 | `memory.provider: honcho`（config.yaml） |

**跨实例共享：** 如果两个 Hermes 实例的 `honcho.json` 指向同一 baseUrl，Honcho 数据即已共享，不需要迁移。state.db 存"对话原文"，Honcho 存"用户画像"，两者角色不同。

### Holographic（bundled 插件，可选）

| 属性 | 说明 |
|---|---|
| 类型 | 本地 SQLite + HRR 向量存储 |
| 数据位置 | `$HERMES_HOME/memory_store.db` |
| 暴露工具 | `fact_store`（9 actions），`fact_feedback` |
| 特征 | 结构化事实存储，实体解析，信任评分，代数检索 |
| 启用 | `memory.provider: holographic` + 插件启用 |
| 配置 | 在 `plugins.hermes-memory-store` 下 |

**能否同时启用？** 两个 provider 可以并存（Honcho 做语义画像 + holographic 做事实存储），但是 `memory.provider` 只能选一个作为 primary。另一个需要通过插件注册作为 secondary provider 使用。

### Holographic 配置参数

```yaml
plugins:
  hermes-memory-store:
    db_path: $HERMES_HOME/memory_store.db   # SQLite 路径
    auto_extract: false                       # 会话结束时自动提取事实
    default_trust: 0.5                        # 新事实默认信任分
    min_trust_threshold: 0.3                  # 检索最小信任阈值
    hrr_dim: 1024                             # HRR 向量维度
    temporal_decay_half_life: 0               # 时间衰减半衰期（0=不衰减）
    hrr_weight: 0.3                           # HRR 相似度权重
```

## 状态排查命令

```bash
# 查看当前 memory provider
hermes memory status

# 切换 provider
hermes memory setup

# 查看插件列表
hermes plugins list

# 导出现有会话
hermes sessions export /tmp/export.jsonl

# 查看 session store 统计
hermes sessions stats
```

## Pitfalls

- ⚠️ **不要直接删除 state.db** - 所有会话和 FTS5 索引丢失。备份再操作。
- ⚠️ **FTS5 索引在 DELETE 后不会自动重建** - 如果手动操作 state.db，FTS 触发器和 content 表可能不同步。`INSERT OPTIMIZE` 可强制重建。
- ⚠️ **切换 memory provider 不会自动迁移数据** - Honcho 的 peer profile 和 Holographic 的 facts 储存在不同位置，切换后旧数据不可见。
- ⚠️ **Honcho 数据随 baseUrl 独立** - 如果两个 Hermes 实例的 `honcho.json.baseUrl` 指向同一服务，Honcho 数据已共享。但 state.db 的会话原文仍需手动合并。
- ⚠️ **跨 schema 版本复制数据** - 如果源 state.db 版本低于目标，目标 SQLite 的 schema 可能已变更。用 `hermes config migrate` 升级旧配置，但 state.db 的迁移需手动处理（如果 schema_version 差距大，建议只复制 messages 表内容）。

## References

- `references/session-migration-assessment.md` — 跨实例会话迁移可行性评估模板（含本会话的 serverhome 迁移分析案例）
