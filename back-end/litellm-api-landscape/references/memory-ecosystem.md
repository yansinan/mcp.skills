# LiteLLM 数据检索体系对比

数据来源：https://docs.litellm.ai/docs/memory_management 、 https://docs.litellm.ai/docs/completion/knowledgebase

## LiteLLM 的两套系统

### `/v1/memory` — 持久化 KV 存储

- **数据模型**：key → value（字符串）+ metadata（任意 JSON）
- **查询方式**：精确 key 匹配 / key_prefix 前缀过滤
- **作用域**：user_id + team_id 双维度隔离（RBAC）
- **语义搜索**：❌ 不支持
- **需要后端**：❌ LiteLLM 自带数据库
- **典型场景**：用户偏好、系统配置、Agent 简短记忆

```bash
# 写入
curl -X PUT http://localhost:4000/v1/memory/user:123:preferences \
  -d '{"value": "Prefers concise responses."}'
# 读出后自行注入 system prompt
```

### Vector Store / RAG — 语义检索

- **端点**：`/v1/vector_stores/`（创建/管理）+ `/v1/vector_stores/{id}/search`（检索）
- **自动注入**：在 `/v1/chat/completions` 中传 `tools=[{type: file_search, vector_store_ids: [...]}]`，LiteLLM 自动检索→注入→回答
- **引用溯源**：✅ 返回 score + filename + file_id
- **需要后端**：✅ OpenAI / Bedrock / Vertex AI / PG Vector / Gemini File Search / Azure AI
- **典型场景**：知识库 QA、文档搜索

```python
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[...],
    tools=[{"type": "file_search", "vector_store_ids": ["vs_abc123"]}]
)
# 结果在 response.choices[0].message.provider_specific_fields["search_results"]
```

## 与 Honcho / Mem0 的对比

| 维度 | LiteLLM Memory (KV) | LiteLLM RAG (Vector Store) | Honcho | Mem0 |
|---|---|---|---|---|
| **需额外后端** | ❌ 自带 | ✅ 向量库 | ❌ 自带 | ❌ 自带 |
| **数据来源** | 手动写入 | 手动上传文档 | 对话消息自动记录 | 对话自动提取 |
| **理解能力** | 无 | 无（只管检索） | 有（会话摘要+画像） | 有（事实提取+分类） |
| **搜索方式** | 精确匹配 | 语义相似度 | 语义+metadata过滤 | 语义+类别过滤 |
| **自动注入** | ❌ 手动 | ✅ 自动 | ❌ 手动查 honcho_reasoning | ❌ 手动查 |
| **引用溯源** | ❌ | ✅ score+filename | ✅ 会话来源 | ✅ 消息来源 |
| **定位** | 简单 KV 存读 | 文档级语义搜索 | 跨会话 Agent 记忆 | 事实提取 + 管理 |

## 选型建议

- **短小的用户偏好** → `/v1/memory`（精确读取）
- **大量文档需要语义搜索** → Vector Store（需额外后端）
- **跨会话 Agent 记忆（对话历史 + 画像）** → Honcho（Hermes 已集成，零配置）
- **从对话自动提炼事实** → Mem0（事实提取能力强，需额外维护）
- **两者互补不冲突**：Honcho 做跨会话记忆 + LiteLLM RAG 做知识库检索
