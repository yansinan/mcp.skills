# LiteLLM PostgreSQL DB 调查与清理

当 `STORE_MODEL_IN_DB=True` 时，LiteLLM 将运行时配置（router_settings、fallbacks、模型列表等）持久化到 PostgreSQL。修改 `config.yaml` 后，旧的 DB 配置**不会自动清除**，可能导致：

- 已删除的 `model_group` 仍被引用（warning: `is not in model_list`）
- 过期的 `fallbacks` 仍生效
- 残留的 `ProxyModelTable` 条目（废弃模型的加密凭证）

## 识别信号

LiteLLM 日志中出现：

```
routing_groups: model_name 'dashscope/qwen-coder' (group 'groupFree') is not in model_list
```

说明 DB 里有路由组引用了 config.yaml 中不存在的模型。

## 调查方法（只读）

通过 LiteLLM 容器内部 Prisma ORM 查询：

```python
# docker exec litellm /app/.venv/bin/python3 -c "..."
import asyncio
from prisma import Prisma

async def main():
    db = Prisma()
    await db.connect()

    # 1. 查看所有配置项
    configs = await db.litellm_config.find_many()
    for c in configs:
        print(c.param_name, '=')
        import json
        print(json.dumps(c.param_value, indent=2))

    # 2. 查看 ProxyModelTable（所有在 DB 注册的模型）
    models = await db.litellm_proxymodeltable.find_many()
    print(f'Proxy models: {len(models)}')
    for m in models:
        print(f'  {m.model_name} blocked={m.blocked}')

    # 3. 查看 ModelTable（config.yaml 加载的）
    yaml_models = await db.litellm_modeltable.find_many()
    print(f'YAML models: {len(yaml_models)}')

    await db.disconnect()

asyncio.run(main())
```

## 常见问题

### 1. router_settings 里的过期 fallback

`litellm_config` 表 `router_settings` 可能残留：

```json
{
  "fallbacks": [
    {"minimax": ["deepseek-v4-flash"]},
    {"free": ["minimax", "deepseek-v4-flash"]}  // ← free 组已不存在
  ]
}
```

即使路由组已删除，fallback 条目仍留在 DB 里，每次请求匹配到该 fallback 时都会触发 warning。

### 2. ProxyModelTable 大量残留

通过 UI/API 添加过的模型不会被 `config.yaml` 覆盖删除。典型残留：

- `free` 组下多个版本（10-20 条）
- 已废弃的 `nvidia/*:free`、`github_copilot/*`
- 历史 embedding 模型

### 3. store_model_in_db 覆盖

DB 中 `general_settings.store_model_in_db` 会覆盖环境变量 `STORE_MODEL_IN_DB=True`。

## 清理方案

通过 LiteLLM API（使用 master key）：

### 删除 router_settings 中的过期 fallback

```python
import requests, os, json
master_key = os.environ['LITELLM_MASTER_KEY']
headers = {'Authorization': f'Bearer {master_key}', 'Content-Type': 'application/json'}

# 获取当前 router_settings
r = requests.get('http://localhost:4000/config', headers=headers)
config = r.json()

# 删掉 free 的 fallback
settings = config['router_settings']
settings['fallbacks'] = [fb for fb in settings['fallbacks']
                         if 'free' not in fb]

# 写回
requests.post('http://localhost:4000/config/update', headers=headers,
              json={'router_settings': settings})
```

### 删除 ProxyModelTable 中的过期模型

```python
# 先列出
r = requests.get('http://localhost:4000/model/info', headers=headers)
for m in r.json()['data']:
    if m['model_name'] in ['free', 'embedding', 'nvidia/*']:
        # 通过 model_id 删除
        requests.post('http://localhost:4000/model/delete', headers=headers,
                      json={'model_id': m['model_info']['id']})
```

### 完整重置（更激进）

1. 更新 `config.yaml` 只保留需要的模型
2. 清空 `ProxyModelTable`
3. 重启 LiteLLM（重启时从 config.yaml 重载全部配置）

## 内部表结构

| 表名 | 用途 | 关键字段 |
|---|---|---|
| `litellm_config` | KV 存储运行时配置 | `param_name`, `param_value` (JSON) |
| `litellm_proxymodeltable` | 通过 API/UI 注册的模型（非 config.yaml） | `model_name`, `litellm_params` (加密), `blocked`, `model_info` |
| `litellm_modeltable` | config.yaml 加载的模型 | 同 ProxyModelTable |
| `litellm_verificationtoken` | 虚拟 API key | `token`, `expires`, `models` |
