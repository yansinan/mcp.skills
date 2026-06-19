---
name: hermes-external-skills
description: "Install, configure, and manage third-party skill collections in Hermes Agent. Covers `skills.external_dirs` in config.yaml, project-level vs global installation patterns, and pitfalls."
version: 1.0.0
author: agent
tags:
  - hermes
  - skills
  - configuration
  - setup
platforms: [linux, macos]
related_skills: [user-preferences]
---

# Hermes External Skills

Hermes Agent loads skills from multiple sources. This skill covers adding **third-party skill collections** (e.g. [superpowers-zh](https://github.com/jnMetaCode/superpowers-zh)) globally via `external_dirs`.

## Skill Discovery Order

Hermes Agent finds skills in this order (later sources override on name collision):

| Priority | Source | Path |
|----------|--------|------|
| 1 (lowest) | Bundled | Hermes Agent repo's `skills/` |
| 2 | Profile | `~/.hermes/skills/<category>/` |
| 3 | Project | `./.hermes/skills/` |
| 4 | External dirs | `skills.external_dirs` in config.yaml |

## Two Installation Patterns

### Pattern A: Project-Level (recommended for per-project skills)

Run the skill framework's installer inside the project directory:

```bash
cd /path/to/project
npx superpowers-zh --tool hermes   # for superpowers-zh
```

This copies skills to `./.hermes/skills/` and generates a `HERMES.md` bootstrap file.

### Pattern B: Global via `external_dirs` (for shared skills)

1. Clone/copy the skill collection to a shared location:

```bash
mkdir -p /home/dr/workspace/skills
git clone --depth 1 https://github.com/jnMetaCode/superpowers-zh.git /tmp/superpowers-zh
cp -r /tmp/superpowers-zh/skills /home/dr/workspace/skills
```

2. Add the dir to `~/.hermes/config.yaml`:

```yaml
skills:
  external_dirs: [/home/dr/workspace/skills]
```

3. Start a new Hermes session to pick up the change.

## Config Reference

```yaml
skills:
  creation_nudge_interval: 15    # turns between skill-creation nudges
  external_dirs: []              # list of dirs containing skill subdirs
  guard_agent_created: false     # block agent-created skills
  inline_shell: false            # allow inline shell in skills
  inline_shell_timeout: 10
  template_vars: true            # enable {{var}} substitution
```

## Tool Mapping (Claude Code → Hermes Agent)

Third-party skills (especially those translated from Claude Code) reference Claude Code tool names. Map them manually:

| Claude Code | Hermes Agent |
|-------------|-------------|
| `Read` | `read_file` |
| `Write` | `write_file` |
| `Edit` | `patch` |
| `Bash` | `terminal` |
| `Grep` / `Glob` | `search_files` |
| `Skill` | `skill_view` |
| `Task` (subagent) | `delegate_task` |
| `WebSearch` | `web_search` |
| `WebFetch` | `web_extract` |
| `TodoWrite` | `todo` |

Hermes Agent also supports a three-level skill loading hierarchy:

```python
skills_list                                        # browse all available
skill_view("skill-name")                           # load full skill content
skill_view("skill-name", "references/file.md")     # access linked files
```

## Pitfalls

### 1. Confirm scope before installing
**Always clarify** whether the user wants **project-level** (Pattern A) or **global** (Pattern B). These have different locations and config changes. If uncertain, ask first.

### 2. Don't install at `~`
Running `npx superpowers-zh` in the home directory pollutes all projects with bootstrap files. The installer v1.2.1+ rejects this, but older versions don't. Always run in a project directory.

### 3. Config changes need a new session
`external_dirs` is read at session start. After changing config.yaml, start a new session (`/reset` or new `hermes` terminal) to see the skills.

### 4. Skill format compatibility
Each skill must be a subdirectory with a `SKILL.md` file. Third-party collections like superpowers-zh follow this format — verify by checking `ls <dir>/<skill>/SKILL.md`.

### 5. Skill naming collisions
If an external skill has the same name as a bundled/profile skill, the later source in the discovery order wins. Check `skills_list` after loading to confirm expected skills are active.

## Verification

After installation, verify skills are loaded:

```bash
# In a Hermes session:
skills_list

# Should show external skills listed alongside bundled ones.
# If missing, check:
# 1. config.yaml has the directory in external_dirs
# 2. Directory contains subdirectories with SKILL.md files
# 3. Start a fresh session
```

## References

- See `references/superpowers-zh-install-2026-06-01.md` for a concrete global installation example with superpowers-zh.
- [superpowers-zh GitHub](https://github.com/jnMetaCode/superpowers-zh)
- [Hermes Agent Skills Docs](https://hermes-agent.nousresearch.com/docs)
