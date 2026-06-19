# LiteLLM Runtime Error Patterns — duplicate keyword arguments

## 症状

```
TypeError: functools.partial() got multiple values for keyword argument '<key>'
```

封装后变成 `litellm.APIConnectionError` 或 `Github_copilotException`。

## 根因

LiteLLM 的 `acompletion()`（`litellm/main.py` ~line 623）构造了 `completion_kwargs` 字典，里面显式设置了特定 key（如 `"acompletion": True`），然后展开两个 dict：

```python
func = partial(completion, **completion_kwargs, **kwargs)
```

当 `kwargs`（调用者传入的原始参数）中也包含同名 key 时，Python 报 `got multiple values for keyword argument`。

## 已知变体

| 重复的 key | 触发路径 | Issue | 修复 PR |
|---|---|---|---|
| `acompletion` | Responses API bridge → `acompletion()` health check | [#16820](https://github.com/BerriAI/litellm/issues/16820) (Copilot codex) | [#16845](https://github.com/BerriAI/litellm/pull/16845) |
| `litellm_trace_id` | Responses API → litellm_proxy 回环 | [#12194](https://github.com/BerriAI/litellm/issues/12194) | [#12225](https://github.com/BerriAI/litellm/pull/12225) |
| `model` | Fallbacks 路径 | [#7807](https://github.com/BerriAI/litellm/issues/7807) | |

## 修复方式

### 升级法（推荐）
升级到已包含修复的 LiteLLM 版本。PR #12225 修复了 `handler.py` 中的参数合并：

```python
# 修复前
response = await litellm.acompletion(**kwargs, **litellm_completion_request)

# 修复后
acompletion_args = {}
acompletion_args.update(kwargs)
acompletion_args.update(litellm_completion_request)
response = await litellm.acompletion(**acompletion_args)
```

### 临时 patch（docker 内）
把冲突的展开改为先合并再展开：

```python
# 改前
func = partial(completion, **completion_kwargs, **kwargs)

# 改后
merged = {**kwargs, **completion_kwargs}
func = partial(completion, **merged)
```

`completion_kwargs` 的值覆盖 `kwargs` 中同名 key，消除冲突。

## 排查步骤

1. 从堆栈确认触发路径：`ahealth_check` → `mode_handlers[mode]()` → `acompletion`？还是 Responses API → handler → `acompletion`？
2. 确认 LiteLLM 版本：`pip show litellm` 或 docker 内 `pip show litellm`
3. 在 GitHub issues 搜索 `got multiple values for keyword argument` + 重复的 key 名称
4. 修复：升级或临时 patch
