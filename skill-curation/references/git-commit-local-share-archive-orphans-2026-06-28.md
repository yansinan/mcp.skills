# local_share 仓库提交时的孤儿目录处理

## 场景

`~/.hermes/skills/local_share/` 是 `git@github.com:yansinan/mcp.skills.git` 的 working tree。
每日 cron "本地技能审计推送" 步骤会 `git add -A` 后提交推送。

## 陷阱：孤儿 `.archive/` 目录会被一起 commit

`local_share` 下常出现 `.archive/<legacy-skill>/` 目录，存放某个被废弃 skill
的历史 reference / 文档，**没有任何父级 SKILL.md 引用它们**。

直接 `git add -A` 会把 88+ 个孤儿文件全部提交，导致 commit 体积膨胀（实测
+14054 行），仓库历史被噪音淹没。

## 诊断：识别真假 modified

```bash
# 34 modified? 还是 7 modified?
git status -s | wc -l                  # 报告 34（很多是 phantom modified）
git diff --name-only HEAD | wc -l      # 实际只有 7（其余是 touched-but-identical）

# 真相：被改的全是元数据/mtime，内容与 HEAD 相同
```

Phantom modified 出现的原因：之前 reset 或 sync 操作 touch 了文件 mtime，
但内容没动。`git status` 用 mtime 判断 modified，`git diff` 比内容。

## 正确做法：add -A 后精准 unstage

```bash
cd ~/.hermes/skills/local_share

# 先全 add，再 unstage 不该提交的内容
git add -A
git reset HEAD -- .archive/            # 排除孤儿归档目录
git diff --cached --stat | tail -1     # 确认 "N files changed"
```

或者一步到位（pathspec）：

```bash
git add -A -- ':(exclude).archive/'
```

注意：`git reset HEAD` 对 pathspec 的语法在某些版本下不工作，
**先 `add -A` 再 `reset HEAD -- <dir>` 是兼容性最好的版本**。

## 推到下一步：是否要清理孤儿

`.gitignore` 当前只写了"不成熟技能"注释，**没有 `.archive/`**。两种选择：

| 选择 | 何时用 |
|------|-------|
| 加 `archive/` 到 `.gitignore`（推荐） | 长期保留旧参考供人查阅，但不希望进 git |
| 删除 `.archive/` 目录 | 确认无价值，且用户已批准删除 |

按 Hermes "不删用户文件"红线，cron 维护 agent 应只加 `.gitignore`，把删除
权限留给用户。即使加了 `.gitignore`，已 tracked 的文件不会被自动 untrack，
需要 `git rm --cached -r .archive/`。

## 教训

- `git status` 数字会误导 —— 用 `git diff --name-only HEAD` 看真相
- `git add -A` + 精准 unstage 比 `git add <specific-paths>` 更稳（避免漏文件）
- phantom modified 是 mtime 噪音，不影响 git 内容等价