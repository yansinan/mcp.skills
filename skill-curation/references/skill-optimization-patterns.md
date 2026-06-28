# Skill Optimization Patterns

When migrating or curating a skill from another host (or from an earlier iteration), apply these optimization criteria.

## 1. 优先 Hermes 工具，替代 shell 脚本

| 原始做法 | 优化为 |
|---------|--------|
| `for name in $(cat ...); do hermes skills reset; done` | 嵌入引用，指出应通过 `terminal(background=true, notify_on_complete=true)` 运行 |
| Python 脚本批量操作（依赖 hermes 内部 import） | CLI 循环 + background terminal（免 venv 依赖） |
| 用 `notify-send` 通知 | 用 terminal 的 `notify_on_complete=True` 机制 |

**原则**：Hermes terminal 自己管理超时、后台通知、进程生命周期。shell 包装器增加一层不需要的依赖。

## 2. 简化错误过程描述

错误过程的篇幅 = 用户必须读的噪音。

| 规则 | 示例（冗余 → 精简） |
|------|---------------------|
| 同类错误合并 | 三处分散的 "70+ skill 超时警告" → 一条表格行 |
| 弃用路径的陷阱整个删除 | "脚本 import 陷阱" 段落：既然不推荐脚本，就不花篇幅解释它的坑 |
| 用户配置错误不提 | "不要把 `--yes` 当成 reset 参数" → 放表格，不单独成段 |

**原则**：如果某个做法已被判定为不推荐，删除它的错误说明也一并带走。

## 3. 强化正确的解决方案

正确路径应该是流程中的**默认路线**，不是列表中的选项之一。

- 正确做法放**第二步**（第一步是 dry-run 枚举），不要先介绍踩坑再讲正确方法
- 正确做法的前置条件（如 background terminal）直接写在步骤里，不要放在远处备注
- 如果两种方案都能工作但一种显著更优，删掉劣质方案，不提

## 4. 结构化呈现

| 信息类型 | 格式 |
|---------|------|
| 步骤 | 编号列表，每步一行 |
| 坑和修复 | 表格：问题列 / 正确做法列 |
| 配置项 | 代码块 + 行内注释 |
| 参考文件 | 末尾链接列表 |

**原则**：表格替代段落。用户扫一眼比读三段快。

## 5. 修剪传递依赖

- 如果不推荐 Python 脚本路径，不要保留它的 import 错误解释
- 如果不推荐某条替代命令，不要保留它的参数列表
- 如果不推荐某个工具，不要保留它的安装步骤

**原则**：每段文字都有维护成本。删除一个错误路径的解释 = 减少未来两份维护工作（路径变了 + 解释过时了）。
