---
name: bundle-skill-restore-all
description: >
  Batch-restore all user-modified bundled skills to their original bundled
  version. Calls sync_skills() to detect which bundled skills have been
  modified, then runs reset_bundled_skill(name, restore=True) for each one.
source: hermes
tags:
  - hermes
  - skills
  - bundled-skills
  - restore
  - batch
---

# bundle-skill-restore-all

## What it does

`hermes skills restore <name>` resets **one** bundled skill: clears the sync
manifest entry and re-copies the bundled source. Doing this manually for N
modified skills is tedious.

This skill batch-restores **all** user-modified bundled skills at once.

## The script

`scripts/restore_all.py` — call it from the Hermes venv:

```bash
cd ~/.hermes/hermes-agent && source venv/bin/activate
python3 ~/.hermes/skills/local/hermes_chores/bundle_skill_restore_all/scripts/restore_all.py
```

Flags:

| Flag | Purpose |
|---|---|
| `--check` | Only list user-modified skills, don't restore |
| `--dry-run` / `-n` | Show what would be done without modifying |
| `--help` / `-h` | Show help |

Quick verification after restore:

```bash
cd ~/.hermes/hermes-agent && source venv/bin/activate
~/.hermes/skills/local/hermes_chores/bundle_skill_restore_all/scripts/restore_all.py --check
# Should print: ✓ All N bundled skills are in sync. Nothing to restore.
```

## Key functions referenced

| Function | Location | Purpose |
|---|---|---|
| `sync_skills(quiet=True)` | `tools.skills_sync` | Detect user-modified skills + re-sync |
| `reset_bundled_skill(name, restore=True)` | `tools.skills_sync` | Clear manifest + delete + re-copy from bundled |

## Pitfalls

- Only works with **bundled** skills (those synced from `skills/` dir in the
  Hermes repo). Hub-installed skills are NOT affected.
- `--restore` deletes your local edits — make sure you haven't customized a
  bundled skill you want to keep. The `user_modified` list only catches skills
  that differ from the origin hash, so customisations are respected until you
  deliberately reset them.
- Requires the Hermes venv to be active (`~/.hermes/hermes-agent/venv`).
