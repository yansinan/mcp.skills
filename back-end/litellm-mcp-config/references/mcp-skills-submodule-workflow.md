# mcp.skills — 子模块技能库工作流

## 模式概述

将本地成熟技能分类组织，发布为独立 GitHub 仓库，作为 MCP 服务仓库的 **git submodule**，
实现 serverHome LiteLLM 定期拉取同步，多 agent 共享。

```
本地 ~/.hermes/skills/local/ (mcp.skills repo)
  ├── back-end/          ← 成熟技能分类
  │   ├── deepseek-cost
  │   ├── litellm-api-landscape
  │   └── litellm-mcp-config
  └── hermes-chores/     ← 成熟技能分类
      ├── bundle_skill_restore_all
      ├── hermes-webui
      └── systemd-resolved-dns-triage

GitHub: yansinan/mcp.skills ← git push
              │
              ▼ (git submodule)
hermes-chores.mcp/skills/  ← MCP 服务暴露
              │
              ▼ (git submodule update --remote)
serverHome LiteLLM ← 定期拉取最新技能
```

## 初始化流程

### 1. 分类 skills/local/ 中的成熟技能

```bash
# 已有分类目录（子目录）
cd ~/.hermes/skills/local
mkdir -p back-end hermes-chores

# 移动成熟技能到对应分类
mv deepseek-cost/ back-end/
mv litellm-api-landscape/ back-end/
mv bundle_skill_restore_all/ hermes-chores/
```

### 2. 移除不成熟技能

```bash
# 从 ~/.hermes/ 父仓库跟踪中移除（文件保留磁盘）
cd ~/.hermes
git rm --cached skills/local/<immature-skill>/SKILL.md

# 在父仓库 .gitignore 中添加排除规则
echo "skills/local/" >> ~/.hermes/.gitignore
```

### 3. 创建独立 git 仓库

```bash
cd ~/.hermes/skills/local
git init
git branch -m main

# .gitignore 排除不成熟技能
cat > .gitignore << 'EOF'
# 不成熟技能 — 不包括在 mcp.skills 仓库中
browser-content-extraction/
cdp-search/
...
EOF

git add back-end/ hermes-chores/ .gitignore
git commit -m "init: mature skills from skills/local/"
git remote add origin git@github.com:yansinan/mcp.skills.git
git push -u origin main
```

### 4. 作为子模块添加到 MCP 服务仓库

```bash
cd ~/workspace/hermes-chores.mcp
rm -rf skills/
git submodule add git@github.com:yansinan/mcp.skills.git skills
git add .gitmodules skills/
git commit
```

### 5. serverHome 定期拉取

```bash
cd /path/to/hermes-chores.mcp
git submodule update --remote skills
# 之后重启 LiteLLM 生效
```

## 重要约束

### 父仓库 .gitignore 需要排除嵌套 git

嵌套 git 仓库（`~/.hermes/skills/local/.git/`）会使父仓库看到整个目录为 `??`（untracked）。
必须在父仓 `.gitignore` 中添加：

```bash
echo "# Nested git repo — mcp.skills" >> ~/.hermes/.gitignore
echo "skills/local/" >> ~/.hermes/.gitignore
```

### 子模块与 MCP 服务的关系

| 层 | 角色 | 同步方向 |
|---|---|---|
| `~/.hermes/skills/local/` | 日常维护的源仓库 | push → GitHub |
| `yansinan/mcp.skills` | GitHub 中央仓库 | 双向 |
| `hermes-chores.mcp/skills/` | MCP 服务子模块 | pull from GitHub |
| serverHome LiteLLM | MCP Gateway 消费端 | `git submodule update --remote` |

### 工作流程

1. **日常维护**：在本机 `~/.hermes/skills/local/` 中编辑技能
2. **推送更新**：`git add -A && git commit && git push`
3. **serverHome 同步**：`cd /mcps/hermes-chores.mcp && git submodule update --remote skills`
4. **LiteLLM 生效**：重启 LiteLLM 容器

### 不成熟的技能

- 留在 `~/.hermes/skills/local/` 磁盘上（不推送到 GitHub）
- 通过 `.gitignore` 排除
- 等成熟后再移入分类目录，push 到 GitHub
- 从父仓库 `~/.hermes/` 中 `git rm --cached` 移出跟踪（避免误 commit）
