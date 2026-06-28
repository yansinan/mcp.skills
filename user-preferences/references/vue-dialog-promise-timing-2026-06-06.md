# Vue 3 Dialog Promise Timing Pattern

Session: 2026-06-06
Context: SelfEvaluationDialog in PrimarySchoolMathematics (Element Plus `el-dialog`)

## Problem

A dialog component (V layer) uses `setTimeout` to delay emitting a `select` event,
then also emits `update:visible` to close itself:

```vue
<!-- ❌ Broken pattern -->
<script setup>
function selectScore(score) {
  selectedScore.value = score
  setTimeout(() => {
    emit('select', score)           // triggers parent async handler
    emit('update:visible', false)   // tries to close dialog
  }, 800)
}
</script>
```

The parent's async handler (`completeGroup`) runs synchronously after the `await`
resolves: evaluates group, advances groupIdx, calls `setListPractices`. The
`watch(listPractices)` fires and re-opens the dialog because `evalVisible` is still
`true` — the close emit hasn't been processed yet.

## Fix

Two changes:

1. **Dialog component**: only emit `select`, never emits `update:visible`:
```vue
<!-- ✅ Fixed pattern -->
<script setup>
function selectScore(score) {
  selectedScore.value = score
  setTimeout(() => {
    emit('select', score)
  }, SELECT_CONFIRM_DELAY_MS)
}
</script>
```

2. **Parent composable** (C layer): close the dialog synchronously when handling the select event,
   BEFORE the async handler resumes:
```js
// composables/usePracticeDialogs.js
function onEvalSelect(score) {
  if (evalResolver) {
    evalResolver(score)      // resumes the await in completeGroup
    evalResolver = null
  }
  evalVisible.value = false  // ← close NOW, before completeGroup continues
}
```

## Why This Works

The `evalVisible.value = false` is set synchronously in the event handler,
before `completeGroup` resumes its async execution. When the watchers fire
during `completeGroup`, `evalVisible` is already `false`, so no re-open.

## Alternative That Did NOT Work

Using `nextTick(() => emit('update:visible', false))` from the dialog's setTimeout —
the nextTick fires in the same microtask cycle and the parent's reactive watchers
already re-opened the dialog by then.

## Key Principle

Dialog close should be the responsibility of the **caller** (parent/C layer),
not the dialog itself. The dialog only sends the data; the caller decides
when and how to dismiss it.