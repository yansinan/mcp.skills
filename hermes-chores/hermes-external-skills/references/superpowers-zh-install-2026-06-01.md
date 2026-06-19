# superpowers-zh Global Installation (2026-06-01)

## Context

User wanted superpowers-zh (20 skills, https://github.com/jnMetaCode/superpowers-zh) installed globally for Hermes Agent, with skill files at `/home/dr/workspace/skills/`.

## Initial mistake

Ran `npx superpowers-zh --tool hermes` inside an empty project dir (`mcp/`), installing project-level skills to `./.hermes/skills/`. User corrected: wanted **global** install, not project-level.

## Correct approach

1. Clean up project-level install: `rm -rf mcp/.hermes mcp/HERMES.md`
2. Clone framework: `git clone --depth 1 https://github.com/jnMetaCode/superpowers-zh.git /tmp/superpowers-zh`
3. Copy skills to desired location: `cp -r /tmp/superpowers-zh/skills /home/dr/workspace/skills`
4. Configure global external_dirs in `~/.hermes/config.yaml`:
   ```yaml
   skills:
     external_dirs: [/home/dr/workspace/skills]
   ```
5. Start a new Hermes session to load the skills.

## Result

20 skills (14 translated + 4 Chinese-original + 2 upstream historical) available globally across all projects.

## Lesson

Always confirm **scope** (project-level vs global) and **skill location** before executing installation. The `npx` installer defaults to project-level — global requires manual steps plus config.yaml changes.
