# `/v1/completions` 端点状态和弃用时间线

数据来源：https://developers.openai.com/api/docs/deprecations（2026-06 确认）

## 现状：只剩 1 个模型可用

`/v1/completions`（纯文本补全）端点上，当前 OpenAI **只有一个活跃模型**：
- `gpt-3.5-turbo-instruct`

其余所有 GPT-3 系列文本补全模型（`text-davinci-003`、`text-curie-001`、`text-ada-001` 等）**已于 2024-01-04 关停**。

## 弃用时间表

| 关停日期 | 模型/别名 | 推荐替代 |
|---|---|---|
| **2026-09-28** | `gpt-3.5-turbo-instruct` | `gpt-5.4-mini` 或 `gpt-5-mini` |
| **2026-09-28** | `babbage-002` | `gpt-5.4-mini` 或 `gpt-5-mini` |
| **2026-09-28** | `davinci-002` | `gpt-5.4-mini` 或 `gpt-5-mini` |
| **2026-10-23** | `gpt-3.5-turbo-completions`（别名） | `gpt-5.4-mini` |
| **2026-10-23** | `gpt-4-completions` / `gpt-4-0613-completions`（别名） | `gpt-5.5` |

**注意**：`gpt-3.5-turbo-instruct` 是最后一款同时支持 `/v1/completions` 和 `/v1/chat/completions` 的模型。

## LiteLLM 中的处理

在 LiteLLM config 中通过 `text-completion-openai/` 前缀指定：

```yaml
model_list:
  - model_name: gpt-3.5-turbo-instruct
    litellm_params:
      model: text-completion-openai/gpt-3.5-turbo-instruct
      # ↑ 此前缀告诉 LiteLLM 调用 openai.completions.create
      #   而非默认的 openai.chat.completions.create
```

所有现代 OpenAI 模型（GPT-4o、GPT-4.1、GPT-5 系列）调用 `/v1/completions` 会报错：

> *"This is a chat model and not supported in the v1/completions endpoint."*

## 历史回顾

| 年代 | 事件 |
|---|---|
| 2020 | GPT-3 发布，仅有 `/v1/completions` |
| 2022-11 | ChatGPT + GPT-3.5 引入 `/v1/chat/completions` |
| 2024-01 | text-davinci-003 等所有 GPT-3 文本补全模型关停 |
| 2025-03 | OpenAI 发布 Responses API |
| 2026-09 | `gpt-3.5-turbo-instruct` 关停，`/v1/completions` 端点实质终结 |

## 结论

**`/v1/completions` 已进入生命末期。** 2026-09-28 之后将没有任何 OpenAI 模型支持此端点。新项目应当只使用 `/v1/chat/completions`。
