# 合并两个互补 skill 为一

## 场景

两个 skill 内容互补但独立存在：一个讲进程去重（pkill + exec），一个讲写法陷阱（续行、引号、patch 转义）。合并成一个 skill，避免分裂。

## 步骤

### 1. 确定 frontmatter schema

用内容较完整的 source 的 schema（name / title / category / tags / description / source），但：
- **description** 改得更宽泛，覆盖两层主题
- 不要保留两个 frontmatter（会冲突）

### 2. 决定 name 字段

两个目录都保留（.hermes 的 local_share 目录 + mcpSway 仓库目录），但内容完全相同。

有三种策略：
- **策略 A**（本 session 使用）：两个文件内容完全一致（byte-for-byte identical），共享同一个 name。简单，但在 hermes skill view 里只显示一个 name。
- **策略 B**（用户本次指令）：frontmatter 里 source A 路径用 name=sway-config-exec-always，source B 路径用 name=sway-exec-always-safety，但 body 内容完全相同。两个 skill 在 hermes 中显示不同名字，但共享 body。
- **策略 C**：合并成一个 skill，删除另一个目录。最干净，但丢失历史引用。

### 3. 章节排序

- 先放通用 pattern（进程去重），再放具体陷阱（写法坑）
- 每个主题用独立的 `##` 章节
- 各自保留原有的反例 + 正确写法对比

### 4. 同步到两处

```bash
# 写入 .hermes
mkdir -p /home/dr/.hermes/skills/local_share/<category>/<name>
cat > /home/dr/.hermes/skills/local_share/<category>/<name>/SKILL.md <<'SKILLEOF'
[merged content]
SKILLEOF

# 拷贝到 mcpSway 仓库
mkdir -p /home/dr/workspace/mcpSway/skills/<repo-name>
cp /home/dr/.hermes/skills/local_share/<category>/<name>/SKILL.md \
   /home/dr/workspace/mcpSway/skills/<repo-name>/SKILL.md

# 验证
diff /home/dr/.hermes/skills/local_share/<category>/<name>/SKILL.md \
     /home/dr/workspace/mcpSway/skills/<repo-name>/SKILL.md \
&& echo IDENTICAL || echo MISMATCH

# Git 提交推送
cd /home/dr/workspace/mcpSway
git add skills/<repo-name>/SKILL.md
git commit -m "docs(<repo-name>): merge <topic-a> into <topic-b>"
git push origin HEAD
```

### 5. 验证

- 两个文件字节数一致
- diff 返回 0
- commit SHA 确认已推送至 origin/master
- git status 确认无 pending changes

## 本 session 实例

- Source A: sway-config-exec-always（4555 字节，helix 的 exec_always 写法坑）
- Source B: sway-exec-always-safety（2548 字节，x1tablet 的 pkill+exec 进程去重）
- Frontmatter: 使用策略 A（同一 name、同一内容）
- 结果: 8190 字节，两处文件 byte-for-byte 一致
- Commit: 17c3ed7c ("docs(sway-exec-always-safety): merge helix exec_always pitfalls...")
