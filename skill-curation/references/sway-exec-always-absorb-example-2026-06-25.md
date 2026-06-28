# 吸收示例: sway-exec-always-safety (2026-06-25)

## 背景

`sway-exec-always-safety` skill 之前被合并过一次 (commit 17c3ed7),但那
次是"复制": 把 helix 机器的 swayidle/UxPlay 修复过程直接 append 到现有
dedup-pattern skill 里,保留了"helix 上怎么修"的叙事。

## 诊断: 4 个复制信号

1. **语言**: §2 标题说"以下陷阱来源于 helix 机器上 swayidle 屏保和 uxplay
   投屏配置的实际修复过程" — 会话纪要,不是 reference
2. **范围漂移**: §2.6 讲"跨机调 Hermes API 探活" — 跟 sway config 完全无关
3. **悬空引用**: §4 引用了三个不存在的 support files
4. **切割不清**: §5 "跨机分享" 属于发布流程,不属 sway exec_always

## 吸收结果

| 指标 | 原来 | 吸收后 |
|------|------|--------|
| 字节 | 6128 | 5753 |
| 行数 | 223 | 156 |
| 章节 | 5 § (含无关内容) | 4 § + 历史上下文 |
| 风格 | 会话纪要 | reference |

具体改动:
- §2.1-§2.5 每条都改写为"规则 + 反例 + 正解"三段式,去掉 helix 叙事
- §2.6 跨机 API → 删除 (不属于)
- §4 三个不存在的文件引用 → 替换为"本 skill 自包含"声明
- §5 跨机分享 → 删除 (应独立成 skill)
- frontmatter tags 从 16 个精简到 6 个

## 关键区分: copy vs absorb

| 面向 | 复制 (copy) | 吸收 (absorb) |
|------|-------------|---------------|
| 读者 | 原会话参与者 | 未来 agent / 用户 |
| 叙事 | "我们修了什么" | "规则是什么,为什么" |
| 例子 | helix 屏保修复 | sway exec_always 通用写法 |
| 前沿 | 原始内容段落 append | 分析 → 归纳 → 重写 |
