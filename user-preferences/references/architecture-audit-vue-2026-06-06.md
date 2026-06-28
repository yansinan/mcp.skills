# Architecture Audit: Vue Component Layer Compliance

Session: 2026-06-06
Project: PrimarySchoolMathematics
Architecture doc: `designDocs/ARCHITECTURE.md` (六层模型: V/C/S/U/M/K)

## Audit Procedure

1. **Read the architecture doc** — extract layer definitions and cross-layer rules table.
2. **List all imports** in the target Vue component — classify each by layer (V/C/S/U/M/K).
3. **Check each import** against the allowed-V→x table:
   - V→C ✅, V→M(read-only) ✅, V→K ✅
   - V→S ❌, V→U ❌ (iron rule 5: "跨层跳调用")
4. **Scan template** for: store actions (V→M mutation), direct utils calls, business logic in event handlers.
5. **Scan `<script setup>`** for: state management patterns, composable delegation, business rule leakage.

## Violations Found & Fixes

### Violation: V→U direct import
Symptoms: `import { extractQuestionMetadata } from '@/utils/equationParser'` in Practice.vue
Fix: Create thin C-layer composable that wraps the U function:
```
// composables/useAnswerBuilder.js (C layer)
import { extractQuestionMetadata } from '@/utils/equationParser'
export function useAnswerBuilder() {
  function buildAnswerMeta(equation, question) {
    return extractQuestionMetadata(equation, question)
  }
  return { buildAnswerMeta, buildScore }
}
```

### Violation: V→M mutation (non-read-only)
Symptoms: `@click="statsStore.toggleDrawer()"` in template
Fix: Delegate through C-layer composable that calls the store internally:
```
// composables/usePracticeDialogs.js (C layer)
function toggleStatsDrawer() {
  const statsStore = useStatsStore()
  statsStore.toggleDrawer()
}
```

### Violation: Business logic in V
Symptoms: `handleSubmit` in Practice.vue containing ~120 lines of answer validation,
metadata extraction, score computation, dedup, persistence trigger, feedback routing.
Fix: Extract into `useSubmitHandler` composable. V keeps only ElMessage and event forwarding.

## Key Lesson
Always audit imports against the architecture's cross-layer rules BEFORE writing code.
The architecture doc's layer table is the single source of truth — if an import isn't
listed as allowed in that table, it's a violation regardless of whether the code works.
