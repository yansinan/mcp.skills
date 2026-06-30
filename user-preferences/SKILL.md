---
name: user-preferences
description: "User-specific preferences and interaction conventions to guide agent behaviour. Class-level umbrella skill for personal style, verbosity, and action policy."
---

# Hermes Agent — User Preferences

This skill captures durable preferences expressed by the user that affect how the agent should behave across tasks.

## Code style preferences (2026-05-29, updated 2026-06-06)

- **Chinese comments throughout**: every significant function/block gets a Chinese docstring or inline comment explaining its purpose.
- **Chinese comment notation**: use Chinese descriptions with `[variableName]` inline annotations — e.g. `/** 强项等级[strongLevels]：该档位所有题目 100% 正确 */` or `<span class="dl">阶段[phase]</span>`. This is preferred over English-only comments.
- **Documentation URL anchors**: every external API call (CDP command, DOM API, npm package) gets a URL to its official docs. `_cdp_send` calls should cite the CDP domain page. JS/DOM calls should cite MDN.
- **Code backed by docs, not guesses**: before writing code that interacts with a protocol or API, verify the behavior against the actual spec (chromedevtools.github.io, MDN, npm package docs). Do not assume behavior based on quick tests.
- **If unsure about a flag or option name, check the man page / --help / official docs first. Never guess.** User explicitly corrected: "你要注意查文档，不要猜" (check docs, don't guess). This applies to all CLI tools (Sway, Timeshift, btrfs, GRUB, etc.). Running `man 5 sway` or `cmd --help` before writing config is mandatory when you don't know the exact syntax.
- **Only describe what the docs say**: when explaining a tool's capabilities, quote or paraphrase the official documentation. Do NOT invent features, describe use cases not documented, or extrapolate "this probably works" scenarios. User explicitly corrected: "这从文档来的信源，跟你前面说的差别太大了，根本是风马牛不相及" — describing capabilities not in the docs is fabrication. Give the user the source text and let them decide.
- **Parameter syntax must match docs exactly**: if the docs say `-vs "waylandsink fullscreen=true"` (quotes enclosing the full value as one argument), write it exactly that way. Dropping quotes, reordering, or otherwise altering the documented syntax is an error. User explicitly corrected: "没有严格按照文档说明写".
- **Clean file structure per phase**: each project phase gets its own git commit with a descriptive Chinese message. New files get proper README, .gitignore, and metadata.

## Key Preferences

- Language: Chinese (中文)。
- Tone: concise, direct, focus on essential steps and results only. Avoid long background explanations.
- Execution-first: when user asks for configuration or actions, prefer to execute them immediately using available tools rather than only describing steps. Obtain confirmation for destructive actions (file deletions, system reboots, irreversible changes) before proceeding.
- Skill updates: after completing a task that changes workflows or uncovers a new pattern, persist lessons as skill patches (one-line additions or references) so future sessions load the updated guidance.
- Auxiliary config: for auxiliary tasks (compression, vision, session_search), reuse the existing proxy provider (custom:litellm) — do not spin up separate providers or touch .env credentials unless explicitly directed.
- .env is off-limits: do not attempt to uncomment/modify ~/.hermes/.env unless the user explicitly asks you to. It contains credential configuration; leave its comment/state as-is.
- **极端极简主义 (Extreme minimalism)**: eliminate unnecessary abstraction layers. One file should have one clear purpose. If a layer doesn't add value (e.g. manager.py in Docker deployment, watchdog scripts), delete it. Docker-native solutions (restart policies, host networking, volumes, on-failure:N) are preferred over custom scripts. Config: one canonical file at root, no separate config/ directory. When agents are distinguished by port number, prefer `network_mode: \"host\"` over `ports:` mapping.

## Workflow preferences (2026-06-23)

- **Mouse-only control for media playback**: never propose sway keybinds for media control — user finds too many keybinds unmemorable. All control goes through waybar on-click buttons (toggle/like/fm/pl/status). Sway keybinds only for window management ($mod+1/2/3, focus, etc.), not media.
- **No scattered files for application logic**: consolidate all app-specific logic into `~/.config/<app>/scripts/<svc>.lua` (one file). GUI helpers (login, playlist picker) stay slim in `~/.local/bin/`. Avoid "1 Python script per subcommand" pattern. From mpv-mpris-media-stack User-specific preferences.
- **Self-verify before reporting — drive the browser yourself (2026-06-30)**: hard rule — never hand the user something unverified AND never bounce browser/GUI testing back to the user. If the deliverable is a web UI, drive a browser via CDP yourself and read the live state (DOM, console, network) before reporting. User's explicit correction: "你自己用浏览器实测，别老让我测试，我只要正确运行的结果，有结果再跟我说" — translates to: I want a working result, not a hand-off. The existing self-verify rule covers "run the CLI yourself" (waybar, swaymsg, playerctl); the browser equivalent is `browser_cdp` / `browser_console` / `browser_snapshot` against an existing CDP tab or a new one. Diagnostic moves: `process(action="log")` to read background-process stderr; `curl http://127.0.0.1:9222/json/list` to enumerate existing chrome tabs; `browser_cdp` with `target_id=<tabId>` to inject JS and read state; `browser_console` to read console output. **Pitfall**: when /tmp is 100% full from chrome RSS, `browser_navigate` returns code 101 because the browser tool can't spawn a new chrome. Fall back to driving the user's existing CDP tab via `browser_cdp` (no new chrome needed).
- **Don't touch user's already-configured files without asking**: when extending a waybar/sway config, *append* to `modules-left` / `modules-right` and add new sections — do not reorder, prune, or rewrite the user's PWA shortcuts / system-status modules. If a layout change forces a tradeoff, ASK which of the user's existing modules to drop, never decide silently. User has explicit opinion here: "你别改中间的标题 和 右边的系统状态啊".
- **Concepts before code**: when introducing tools (mpv, MPRIS, fuzzel, chafa), explain what they are first — the user prefers understanding over copy-paste recipes.

## Implementation notes for the agent

- Load this skill automatically for session planning when user is the same known identity.
- When preparing responses, prefer bullet lists with 3–5 items: Source / Action taken / Result / Next steps / Short summary.
- Always show the concrete commands run (or the Hermes tool calls) when making environment changes.

### Workspace enforcement (new)
- Always respect the most recent [Workspace::v1: /absolute/path] tag provided by the user's message and treat it as the authoritative working directory for all file and shell operations (git clone, read_file, write_file, patch, terminal commands).
- Before performing any filesystem operation, the agent MUST either cd into that workspace or pass the workspace path as an explicit working directory to the tool (e.g., `cd /workspace && git clone ...` or terminal(workdir='/workspace', command='...')).
- If a previous step created or modified files outside the declared workspace, the agent should: (a) notify the user, (b) move or copy artifacts into the declared workspace when safe, and (c) record the action in a session references file under the relevant skill.
- Pitfall: defaulting to the agent process cwd (e.g. /home/dr/.hermes/hermes-agent) causes surprising placements. Always derive working path from the Workspace tag.

### Repository operations and defaults
- When cloning repositories, prefer `git clone <url> <workspace>/<repo>` or `cd <workspace> && git clone <url>` so the location is explicit.
- If a clone ended up in the wrong place, prefer safe, explicit remediation: `mv <wrong> <workspace>` then run `git status` and commit any agent-made changes in the moved repo (record commit IDs in references). Notify the user of the move and the exact commands performed.
- When editing project files, run `git status --porcelain` and `git diff --name-only` before committing; include a concise commit message in Chinese mentioning the change and reason.

### File placement discipline (2026-06-29, tightened 2026-06-30)
- **Rule**: ALL file writes (write_file, terminal output redirects, temp data, reference copies, debug logs) MUST go inside the declared workspace or project directory path. Never write to `/home/dr/`, `~/`, or `/tmp/` directly unless the user explicitly tells you to.
- **Canonical scratch location for this user**: `<workspace>/.cache-uv/tmp/` — use this for *every* temp file (curl downloads, server.log, e2e test scripts, JSON dumps, intermediate outputs). User's strongest-ever correction: "不要再 ~/ 下面写文件，把你的垃圾 放到 工作目录的 tmp/" + "严格禁止文件溢出工作目录！！！！！！！！！！！！！！！！！！" — the `~/` home dir is treated as user personal space and the user is hostile to any agent scratch file landing there.
- **Allowed locations**: `~/workspace/<project>/`, project-local `./cache/`, project-local `./.cache-uv/tmp/` (canonical scratch — create it on demand with `mkdir -p`), or a path under the workspace tag provided by the user.
- **Forbidden by default**: `/home/dr/<filename>` (user home — strict ban), `/tmp/` (shared tmpfs fills up from chrome RSS and breaks other tools), `~/` (user's home — pollutes shell directory and confuses `ls`), `~/.hermes/` (Hermes config — keep hands off).
- **Cleanup obligation**: at the end of any multi-step work, sweep the scratch dir: `rm -rf <workspace>/.cache-uv/tmp/*` before reporting done. If a debug file was created at a forbidden path, move it into the project dir and clean up the original. Report the relocation.
- **Rationale**: the user has been bitten by stray files in `/home/dr/` and `/tmp/` multiple times. Agent scratch files block `ls`, confuse `find`, survive session boundaries, and `/tmp` saturation blocks `execute_code` and the browser tool.
- **Signal**: user says "你文件写哪了" or "清理干净" or "不要写到我 home 里" or any variant — stop, locate the strays, clean up, and continue inside the workspace.
- **First action when starting a new task**: `mkdir -p <workspace>/.cache-uv/tmp` and use it as the scratch root for the rest of the session.
- **See also**: `references/browser-cdp-without-tmp.md` — concrete workaround when /tmp tmpfs is 100% full from chrome RSS and `browser_navigate` returns code 101; uses existing CDP tabs via `browser_cdp` + enumerates `Runtime.evaluate` binding-parser gotcha.

### Execution-first policy (clarified)
- If the user asks for an actionable change (install, patch, run), act by default using available tools and report concrete commands and outputs.
- Ask for explicit confirmation only for destructive or irreversible changes (deletions, overwrites of non-temporary configuration, cross-profile edits outside current workspace). Use the Sample checklist below for guidance.
- **找依据再改 (Find evidence before changing)**: when debugging a reported issue, ALWAYS run diagnostic commands first (check logs, test the exact command that's failing, inspect config files) and present the evidence before proposing any fix. Do NOT guess the root cause. The user explicitly corrected this pattern: "你能不能找找依据再改".

### Code deprecation pattern (2026-06-06)
- **Never delete deprecated code in-place.** Use full-block comment-out with `/* === START DEPRECATED (<reason>) ===` / `=== END DEPRECATED (<reason>) ===` markers. This preserves git blame and lets readers understand what was replaced.
- If the deprecated function is exported and imported elsewhere, keep a minimal stub that delegates or returns defaults. Remove the stub when all callers are migrated.

### V→U import is NOT allowed (2026-06-06)
- **Architecture rule enforcement**: ARCHITECTURE.md §1.2 cross-layer table shows `V → U = ❌`. `V → C → U` is the correct chain.
- **Pattern**: When a U-layer function needs to be called from a Vue component:
  1. Add the import to the relevant C-layer composable (e.g. `useAdaptiveSession`)
  2. Expose a thin wrapper method from the composable
  3. The Vue component calls `composable.method()`, never imports U directly
- **Pitfall**: U-layer functions like `adjustNextQuestion` that modify engine/state are tempting to import directly from Vue. This is a violation even when the function is "just a utility." Route through the composable.
- **Reference**: session 2026-06-06 — `Practice.vue` had `import { adjustNextQuestion } from '@/utils/algorithm/adaptiveEngine'` which was detected and fixed by routing through `useAdaptiveSession.afterAnswer()`.

### One-step-at-a-time execution (2026-06-18)
- **Rule**: execute exactly one step, report completion, wait for user acknowledgement before moving to the next. Do NOT batch 4+ steps into a single response — if one is wrong, all are wasted.
- **Signal**: user says 你刚才半天10+分钟在干嘛 = you skipped steps or batched too many actions without intermediate checkpoints.
- **Applies to**: git operations, config edits, multi-step deployments, chained commands.

### Don't invent content (2026-06-18)
- **Rule**: do exactly what was asked, nothing more. User says fork template = fork template. Not fork template + add 4 skills + update docs + create submodule.
- **Signal**: user says 这些技能从哪里来的 = you created content that was never requested. Revert immediately.
- **Pitfall**: when copying from a template repo, copy ONLY the template files. Do not add bonus features, extra directories, or sample content unless explicitly asked.

### Know which repo you're in (2026-06-18)
- **Rule**: before any git operation (git rm --cached, git add, git commit, .gitignore edit), run pwd and verify against the target repo. The most common error is operating on ~/.hermes/ when you should be in ~/workspace/ or ~/.hermes/skills/local/.
- **Cross-check**: is the file path you're about to edit inside the repo your pwd shows? If not, change directory first.
- **Submodule awareness**: a standalone git repo inside another repo (e.g. ~/.hermes/skills/local/ with its own .git) is a SEPARATE repo. git rm --cached in the parent removes from parent's index; to remove from the standalone repo, operate INSIDE that repo.

### Stage-only convention (2026-06-18)
- **Default workflow**: git add, present the diff, ask user for commit message. Do NOT commit or push without the user's commit message.
- **Exception**: if user explicitly says 你自己来 commit message，再直接推, write your own and push.
- **Rationale**: the user reviews every diff before it lands. Staged-but-uncommitted changes are reviewable; committed changes are history.

### Local-only submodule pattern (2026-06-18)
- **When user wants a local git repo without a remote**, set .gitmodules URL to a relative local path: url = ./path/to/repo.
- Then run git submodule absorbgitdirs <path> to move the nested .git into the parent's .git/modules/ directory.
- **Pitfall**: git submodule add fails if the target directory has staged content. First remove it from the index with git rm --cached -f <path>, then add with --force.
- **Pitfall**: git checkout HEAD -- path/ restores individual files, NOT a submodule entry. After checkout, init the nested repo, then convert to submodule.

### Minimal-change preference when user suggests a specific approach (2026-06-24)

- **Rule**: when the user suggests a specific fix or approach ("改用 killall", "用 killall 试试"), implement EXACTLY that — don't add complexity, don't write wrapper scripts, don't introduce additional layers. The user's suggestion is intentional; they've already considered the trade-offs.
- **Signal**: user says "你越走越偏了，又去写脚本。停止。改用我说的 killall 方法". This is a hard stop — drop what you're building, back out, and apply the user's approach as-is.
- **Anti-pattern**: when debugging fails, default reaction is to add abstraction (e.g., write a `waybar-restart.sh` wrapper script with PID file tracking). Stop and ask: "can the user's suggested one-liner solve this?" If yes, use that.
- **Applies to**: any time the user names a specific tool/method/command to try. Especially after multiple debugging attempts have failed — the user's suggestion is a course-correction, not a suggestion to combine with prior attempts.
- **Wrong**: keep building the PID-file-tracking wrapper while ALSO incorporating the user's killall idea. Pick one path.
- **Right**: delete the wrapper script, write the one-liner with killall, move on.

### "少自造 principle" (2026-06-06)
- **Before creating a new mapping, data structure, or algorithm**, search the existing codebase for a function that does it already. The user has a low tolerance for redundant abstractions.
- **Signals for "少自造" violations**:
  - Proposing a new `WEAK_DIFF_MAP` when `matchLevel + DIFFICULTY_LEVELS` already achieves the goal.
  - Creating a separate `profileWeights.js` when a 30-line function fits naturally in the existing `adaptiveEngine.js`.
  - Adding a new concept when an existing concept (e.g. `strongLevels`/`weakLevels` label arrays from `useAbilityProfile`) could be reused with a straightforward adaptation.
- **Safety check**: before adding any new file, ask: "does this belong inside an existing file near related logic?" The threshold for a new file should be >= ~150 lines or a genuinely different concern.

### Test-driven debugging pattern (2026-06-06)
- **When user reports an error in the running app**, follow this sequence:
  1. Open browser console to capture live JS errors first (before refreshing/navigating).
  2. If no errors, navigate to the broken feature and re-check.
  3. Read the full error traceback — trace from the import/export chain that failed.
  4. For `SyntaxError: The requested module does not provide an export named 'X'`, suspect a syntax error (unclosed `/* */`, mismatched braces) that silently killed the export.
  5. After fixing, reload and verify console is clean AND the feature works visually (screenshot).
  6. Run a full end-to-end cycle before declaring fixed.
- **Reference**: session 2026-06-06 — `ASSIST_LEVELS` export missing because `/* =======` never closed with `*/`. Pattern: multi-line comment swallows sibling exports.
- **Array-ordering pitfall**: when an array is index-ordered by semantic axis (e.g. ASSIST_LEVELS from easiest→hardest), AND multiple functions index into it with direction-dependent logic (pickInputMode, evaluateGroup), verify ALL consumers agree on the axis direction. A single wrong sort order propagates silently through the entire chain.
  - Fix pattern: add the axis direction as an explicit comment on the array definition. When changing array order, trace all index-dependent consumers and update them.
  - Reference: session 2026-06-06 — ASSIST_LEVELS was `[vertical, choice4, choice2]` (hard→easy) but consumers treated it as easy→hard.

### Architecture-compliance mandate (2026-06-06, updated 2026-06-09 with barrel conflict pitfall)
- **Before any code change, first load and verify against the project's ARCHITECTURE.md or equivalent design docs.** The user expects all modifications to respect the documented layer model, cross-layer rules, and directory structure. Violations (e.g. V→U import, V→M mutation, V containing business logic) are rejected on review.
- **Systematic audit procedure** for Vue component architecture compliance:
  1. Read the project's ARCHITECTURE.md to extract the layer model (V/C/S/U/M/K) and cross-layer rules table.
  2. For the target Vue component (V layer), list ALL `import` statements and classify each by target layer.
  3. Check each import against the allowed-V→x table from the architecture doc. Flag violations immediately.
  4. Scan `<script setup>` and `<template>` for business logic, store mutations, or U-layer function calls that should go through composable.
  5. For each violation, create a thin C-layer composable that wraps the U/S function and delegates it. Never add direct U/S imports to a V layer file.
  6. Verify: all tests pass + browser navigation confirms the feature works.
- **Barrel export conflict pitfall (2026-06-09)**: when two modules under the same `export * from './xxx'` barrel export a function with the same name, the Vue build silently produces unexpected behavior — the page loads but `#app` is empty (`<!---->`). ES module star-export bindings silently drop duplicate names (only one version survives). Detection: the app renders but has 0 interactive elements. Fix: change the problematic import to a direct path (e.g. `import { getWrongAnswers } from '@/services/wrongAnswerService'` instead of `from '@/services'`), or rename one export, or use named re-export. **Rule**: barrel re-exported files must NOT have overlapping export names. Before adding a new `export *` to a barrel, grep for the name across all other `export *` in that barrel.
- **Pitfall**: old code may have accumulated layer violations. The architecture document may list known "层泄漏" entries — treat those as a todo list, not permission to leave them.
- **Pitfall: V→U imports**. Even though V is allowed to import from `constants` and `components`, it is NOT allowed to import from `utils/algorithm`, `services`, or any U/S layer directly. The cross-layer rule table explicitly marks `V → U = ❌`. Route through a composable.
- **First thing before any change**: load and verify the ARCHITECTURE.md. The user's standard workflow is: 先查构架文档 → 定位根因 → 制定修改方案 → 实施. Don't skip to implementation.
- **Reference**: `references/architecture-audit-vue-2026-06-06.md` for the full audit walkthrough.

### Audit review response pattern (2026-06-06)
- **When receiving a multi-item review**, process each item independently with this triage:
  1. Categorize — Valid bug? Documentation/comment issue? No practical impact?
  2. Estimate fix scope — Changes behavior? Naming/docs only? Caller changes needed?
  3. Respond with clear assessment per item, then ask user which to act on.
- **Common categories from this session's A3/A4/A5 review**:
  - **A3-type** (functional bug): behavior diverges from design (pick level could exceed difficulty range) → fix immediately.
  - **A4-type** (documentation/confusion): code is correct but comments or variable names mislead (assistLevel semantics) → fix comments, not code.
  - **A5-type** (duplicate/smell): two implementations exist but produce same results in current usage (groupAnswersByLevel divergence) → log as debt, don't fix unless user asks.
- **Always bundle fix commits with the audit response**. Don't leave fix PRs dangling.

### Step-by-step rebuild pattern
- When building/replacing a module, prefer to **clear existing logic first**, then rebuild step by step. Don't leave old code that might be confused with the new implementation.
- Each phase should be independently testable before moving to the next.
- Track phases with git commits: each phase gets its own commit with a clear Chinese commit message.

### Interface-exact alignment for parallel replacement
- When a new module is meant to eventually replace an existing one from another project, the **output interface must be byte-identical**. Every field name, type, and optional/required status must match.
- Optional fields must be `undefined` (not empty string `""`) when absent — otherwise downstream consumers can't distinguish "absent" from "present but empty".

### Minimize unnecessary dependencies
- Before adding a dependency, check if the functionality is already available:
  - Turndown takes HTML strings directly — no DOM wrapper needed for it.
  - `@mozilla/readability` is zero-dependency but needs an external DOM in Node.js — use `linkedom` over `jsdom` (lighter).
  - Python `requests` is a Hermes core dependency; don't pip-install alternatives.
- **Never install system packages without asking first**: the user explicitly corrected this with "装notify-send 干嘛用？禁止私自装依赖". Terminal output (echo to stderr) is sufficient for feedback — desktop notifications (`notify-send`/`libnotify-bin`/`mako`/`dunst`) require a notification daemon which may not be running. If a tool needs an extra package, ASK before apt-get install.

### Visual feedback for browser operations
- When performing CDP-based browser extraction (e.g., `cdp-extract`), after `Page.navigate`, call `window.focus()` via `Runtime.evaluate` to bring the new tab to the foreground. This lets the user visually confirm the browser is active.
- For lazy-loaded pages, use multi-pass scroll with visible browser tab so user can watch the scrolling progress.
- Default: no silent CDP operations. User should be able to see what the agent is doing in the browser.

### Browser testing: use debug tools for keypad questions (2026-06-10)
- **User preference**: when testing apps with keypad input (like PSMath), do NOT click keypad digits one-by-one. The digit input direction (ones-first/tens-first) varies and manual clicking is slow and error-prone.
- **Instead**: use the app's debug API (`window.__psm_debug.answerN(n, correct)`) to answer questions programmatically. This bypasses keypad entry and the normal submit flow (including feedback animation timing).
- **Choice questions** can be clicked directly (one click per answer through DOM buttons) OR answered via `answerN`.
- **After `answerN` completes a group** (last question answered → `completeGroup` → modal dialog appears), the dialog needs manual closing. The Hermes browser tool may not interact with Element Plus dialogs reliably (close button, overlay click, Escape all may fail). Use `document.querySelectorAll('.el-overlay')` to remove overlays programmatically if needed, then verify the store state progressed to the next group via `__psm_debug.state()`.
- **Fallback**: if `answerN` times out (because a modal blocked the next question), check `__psm_debug.state()` — it likely completed the in-progress action. Then handle the modal and continue.
- **Reference**: PrimarySchoolMathematics session 2026-06-10.

### Vue 3 模板 ref 自动解包陷阱 (2026-06-06)

- **问题**：`<script setup>` 中 `const stats = useStatsDrawer()` 返回一个普通对象，其属性是 ComputedRef/Ref。Vue 3 模板只对**顶层绑定**自动解包 ref，不会对**对象属性中的 ref** 自动解包。因此模板中 `stats.aggregatedStats` 是 ComputedRef **对象本身**（恒 truthy），`.totalSessions` 为 `undefined` → `v-if` 永远 false。`v-loading="stats.loading"` 也是恒 truthy → loading 遮罩一直显示。
- **正确模式**：顶层解构，让每个 ref 成为顶层绑定：
  ```js
  // ✅ 顶层解构 → 模板自动解包 ref
  const { loading, aggregatedStats, sessions } = useStatsDrawer()
  // 模板直接使用: v-loading="loading", aggregatedStats.totalSessions
  ```
- **判断方法**：如果模板中 `stats.xxx` 的值是 Ref 对象（有 `__v_isRef: true`），说明自动解包没生效，需要解构。
- 验证方式：`component.setupState.stats.aggregatedStats.__v_isRef === true` 说明是 ref 而非值。
- 参考：`references/vue3-template-ref-unwrap-2026-06-06.md`
- **Problem**: when a dialog emits an event (`emit('select', score)`) that triggers a parent async handler (`completeGroup`), and the same setTimeout also emits `update:visible` to close the dialog, the parent may re-open the dialog before the close takes effect (because the watchers triggered by `completeGroup` set `evalVisible` back to true).
- **Fixed pattern**: do NOT emit close from inside the dialog component. Instead, close the dialog in the parent's event handler (`onEvalSelect`) by directly setting `evalVisible.value = false` BEFORE the async handler resumes. This ensures the dialog is already closed when the parent's watchers fire.
  ```
  // ✅ Parent composable (C layer):
  function onEvalSelect(score) {
    if (evalResolver) { evalResolver(score); evalResolver = null }
    evalVisible.value = false  // close BEFORE completeGroup continues
  }
  ```
- Component (V layer): `selectScore()` only emits `select`, never emits `update:visible`.
- Reference: `references/vue-dialog-promise-timing-2026-06-06.md`

## Sample checklist (apply before destructive ops)
1. Is the action irreversible? If yes, ask user to confirm explicitly ("Confirm: delete X? Y/N").
2. If the user already authorized this session to do destructive actions, proceed and log the command in the session transcript.
3. After execution, report success/failure and any saved backups.

## How to record post-mortem for incidents
- Create a references note under this skill named `references/<short>-YYYY-MM-DD.md` with:
  - What happened (one-paragraph), exact commands run, the remediation performed, commit hashes, and any files moved.
  - A one-line "preventive" checklist entry to avoid same mistake next time (e.g., always use workspace-aware clone).
- Link the new reference file from this SKILL.md by name.

### Keypad auto-submit pattern (2026-06-06)
- **When**: keypad input is active and user has typed digits matching the solution exactly (by numeric value).
- **How**: after `session.currentAnswer` is updated in `handleInput`, check `Number(session.value.currentAnswer) === currentQuestion.value.solution`. If true, call `handleSubmit()` with NO arguments — passing a string causes `"39" === 39` type mismatch.
- **Pitfall**: `handleSubmit(answer)` with a string argument makes `processAnswer` take `answer !== undefined ? answer : Number(rawAnswer)` → string `"39"` used directly → `"39" === 39` is `false` → answer marked wrong. Always call `handleSubmit()` without args in keypad context so it reads `session.currentAnswer` internally via `Number(session.currentAnswer)`.
- **Reference**: session 2026-06-06, Practice.vue handleInput.

### Reserve pool must be fully diversified (2026-06-06)
- **Problem**: reserve pool questions generated with `generateOneQuestion()` return `{equation, solution, type}` only — no `inputMode` or `options`. When `adjustNextQuestion` swaps one in via `listPractices[nextIdx] = poolQ`, Vue renders it with stale options from the previous question (wrong answer displayed).
- **Fix**: run reserve pool through `diversifyBatch()` just like the main batch. Both the main `questions` and `reservePool` arrays must be diversified before return.
- **Reference**: session 2026-06-06, `11+28=__` displayed options `[68, 67]` instead of `[39, ...]`.

### pickStrongLevel/pickWeakLevel difficulty ceiling (2026-06-06)
- **Must constrain selected levels to a range around `engine.difficultyIdx`**. Otherwise `pickStrongLevel` with all-correct profile (all 12 levels are "strong") can pick level 11 (综合挑战) at 34.7% probability even when engine is at level 4.
- **Ranges**: Strong: `[current-1, current+3]`, Weak: `[current-2, current]`. These are tuned to allow upward exploration without jumping too far.
- **Fallback**: if constrained list is empty, return `currentDifficulty` directly.
- **Reference**: session 2026-06-06, audit item A3.

### "再来一轮" restart — engine must be nulled before watch (2026-06-06)
- **Problem**: after completeGroup returns 'restart', the watch on listPractices checks `abilityProfile.value && !adaptiveEngine.value`. If `adaptiveEngine` is still set, the condition fails and `startNewAdaptiveSession()` never fires → stuck on loading screen.
- **Fix**: in the `action === 'confirm'` branch of completeGroup, set `adaptiveEngine.value = null`, `adaptiveGroupIndex.value = 0`, `groupAnswerOffset.value = 0` before returning 'restart'.
- **Reference**: session 2026-06-06.

### Per-question mastery check (2026-06-06)
- **Old (removed)**: evaluateGroup had a state machine that triggered mastery check on group completion — fired too early (G1 all-correct → 50% chance G2 all horizontal_keypad).
- **New**: adjustNextQuestion checks `roundAnswers.slice(-2)` for 2 consecutive correct answers → sets next question's `inputMode` to `horizontal_keypad`. Runs per-question, not per-group. Only at `assistLevel <= 1`.
- **evaluateGroup retains only a minimal fallback**: if `masteryCheck.active && horizontalGood >= targetPasses` (stale state from a previous round), advance difficulty.
- **Reference**: session 2026-06-06.

### Getter-first domain model pattern (2026-06-09)
- **Principle**: domain models (Answer/Question/WrongAnswer) should compute derived state via getters from stored primitive fields, NOT by reading stored boolean/numeric fields. `isCorrect` is computed from `Number(userAnswer) === Number(solution)`, never stored. `score` is computed from `isCorrect * computeScore(attemptCount)`, never stored. `attemptCount = previousAttemptCount + 1`, never stored.
- **Static helper pattern**: `Answer.isCorrect(answerLike)` static method performs the getter computation on plain objects without instantiating an Answer. Use this in services/analytics where plain DB rows are iterated, to avoid the cost of wrapping every row.
- **Fallback chain**: when reading a derived property (e.g., `score`), prefer: 1. Instance is Answer → use getter; 2. Wrap in `new Answer(answer)` → use getter; 3. Stored field `answer.score` (legacy); 4. Stored field `answer.isCorrect` (very old).
- **Constructor defaults must match null semantics**: when a field can be legitimately null (e.g. `responseTime` was not recorded), default to `?? null` NOT `?? 0`. `responseTime: null` means "no time data"; `responseTime: 0` means "instant". Same for `startedAt`/`endedAt`: default to `?? null` not `?? timestamp` so `effectiveResponseTime` getter works correctly.
- **`previousAttemptCount` backward compat**: when constructing Answer, derive `previousAttemptCount` from stored `attemptCount`: `this.previousAttemptCount = raw.previousAttemptCount ?? (raw.attemptCount != null ? raw.attemptCount - 1 : 0)`.

### Wrong-answer filter semantics (2026-06-09)
- **`isWrong` vs `!isCorrect`**: `Answer.isWrong` includes `!isFixed` check → items with `correctedAt != null` are NOT wrong. When building a "get all wrong answers" query (including corrected ones), use `!Answer.isCorrect(a)` to filter, NOT `a.isWrong`. The `isWrong` getter is for "currently wrong (active)" display purposes.
- **`includeFixed` UX**: the API `getWrongAnswers({ includeFixed: true })` should be backed by `!isCorrect` filter + skip the `!isFixed` check. Using `isWrong` to pre-filter makes `includeFixed` ineffective because `isWrong` already excludes fixed.
- **Reference**: services/wrongAnswerService.js and services/analysis.js, bug fixed 2026-06-09.

### S-layer database proxy pattern (2026-06-09)
- **Problem**: U-layer `database.js` contains critical DB access. All S-layer services import from `@/utils/store/database`. When we need to migrate U-layer code to S-layer (per architecture doc), we'd need to update every import site simultaneously — risky.
- **Pattern**: create a **thin re-export proxy** at `services/database.js` that re-exports every export from the U-layer source:
  ```js
  // src/services/database.js (~18 lines)
  export { default as DB, saveSession, getSessions, getAllAnswers, ... } from '@/utils/store/database'
  ```
  New S-layer code imports from `@/services/database`, not from `@/utils/store/database`. Over time, existing import sites are migrated one by one. When ALL sites are migrated, `services/database.js` becomes the canonical file (replace re-exports with native implementation), and `utils/store/database.js` is deleted — with zero risk of breaking any consumer.
- **Reference**: PrimarySchoolMathematics v4.0a, commit `37a3e69`.
- **Pitfall**: do NOT expose the proxy through the `services/index.js` barrel if it has name conflicts with other `export *` modules (e.g. `analysis.js` also exports `getWrongAnswers` → barrel conflict blocks page mount). Import the proxy directly: `import { getAllAnswers } from '@/services/database'`.

### Test fixture self-consistency with getter-first (2026-06-09)
- **Problem**: after switching domain models to getter-first (e.g., `Answer.isCorrect` computes `userAnswer === solution` instead of reading stored `isCorrect` boolean), test fixtures that set `isCorrect: false` without adjusting `userAnswer`/`solution` produce contradictory states. The getter returns `true` (because default `userAnswer` equals default `solution`), but the test expects `false`.
- **Rule**: when a test fixture sets `isCorrect`, it MUST also set `userAnswer` and `solution` to values consistent with the getter. Any override of `isCorrect` without corresponding `userAnswer`/`solution` overrides is a bug. The cleanest approach: make the fixture builder derive `isCorrect` from `userAnswer === solution` instead of storing it.
- **Reference**: PrimarySchoolMathematics session 2026-06-09, multiple test failures tracing to `mkAnswer({ isCorrect: false })` with default `userAnswer: 70, solution: 70`.
- **Pitfall**: `getAnswerScore(a)` with getter-first: when passing a plain object, it wraps in `new Answer(a)`. If `a.userAnswer == null`, the getter computes `Number(undefined) === Number(undefined)` = `NaN === NaN` = `false`. Always ensure fixtures have explicit `userAnswer` and `solution`.

### CDP 数据提取偏好（2026-06-20）
- **过滤时机**: 在提取时就排除，不做后处理。用户要求"排除没有免费额度的行"时，在 `browser_console` 的 JS 语句里加 `.filter()`，不要全量提取后再用 Python 过滤。
- **输出格式**: 最终结果输出为 Markdown 文件（`write_file`），不要打印到终端。中间调试数据可存 `/tmp/` 文本文件供用户自行查看。
- **参考**: `../browser-content-extraction/references/cdp-table-scraping.md`

## References
- Session: 2026-05-28 — configured GitHub MCP server, saved PAT to ~/.hermes/.env, deleted local clone on user confirmation.
- Session: 2026-05-28 — set auxiliary.compression to deepseek-chat via custom:litellm (not separate deepseek provider). Key lesson: reuse existing proxy, don't touch .env.
- Session: 2026-05-29 — built cdp-extract plugin + read_down Node.js module. Key lessons: interface alignment across projects, minimize dependencies (linkedom over jsdom, Turndown direct HTML), user plugin relative imports, step-by-step rebuild with phase commits.
- Session: 2026-05-29 — CDP scroll strategy for lazy-loaded content (WeChat). Added `window.focus()` for visual browser feedback. Reference: `../browser-content-extraction/references/cdp-scroll-lazy-load.md`.
- ~~Session: 2026-05-30 — CDP buffer pollution breakthrough. Reference: `start-remote-browser-tunnel/references/cdp-websocket-buffer.md` (skill deleted).~~
- ~~Session: 2026-05-30 — wechat-route Dockerization + repo cleanup. Reference: `python-dockerize/references/wechat-route-dockerization-2026-05-30.md` (skill deleted).~~
- Session: 2026-06-01 — superpowers-zh 全局安装. Lesson: confirm scope (project vs global) before installing third-party skill frameworks.
- Session: 2026-06-01 — mobile UI alignment verification. Reference: `references/mobile-ui-verification.md`.
- ~~Session: 2026-05-31 — wechat-route path-based proxy. Reference: `python-dockerize/references/wechat-route-proxy-2026-05-31.md` (skill deleted).~~
- **Session: 2026-06-06 — PrimarySchoolMathematics StatsDrawer/Vue3 模板 ref 解包调试 + matchLevel 算法**  
  StatsDrawer 加载卡死根因：`const stats = useStatsDrawer()` 对象属性中的 ref 不自动解包。  
  修复：顶层解构。  
  Adaptive engine 新增 `matchLevel` 纯函数：动态匹配 DIFFICULTY_LEVELS。  
  DebugPanel 面包屑分页 + `?debug=true` 控制。  
  参考：`references/vue3-template-ref-unwrap-2026-06-06.md`.
- **Session: 2026-06-06 — P5 画像驱动出题策略**  \
  PrimarySchoolMathematics P5 完整设计与实现。  \
  关键教训：V→U import 违规修复、ASSIST_LEVELS 顺序颠倒修复、Mastery Check 每答一题触发、少自造原则。  \
  参考：`references/p5-profile-q-strategy-2026-06-06.md`.
- **Session: 2026-06-06 — Audit review response pattern**  \
  A3/A4/A5 分类法：功能性 bug / 注释误导 / 无实际影响。Always bundle fix commits with audit response.  \
  参考：本 skill `Audit review response pattern` 节.