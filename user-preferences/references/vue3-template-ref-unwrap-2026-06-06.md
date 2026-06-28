# Vue 3 `<script setup>` 模板 ref 自动解包陷阱

## 发生场景

`PrimarySchoolMathematics` 项目 `StatsDrawer.vue` 中，使用 `const stats = useStatsDrawer()` 后在模板中访问 `stats.aggregatedStats.totalSessions`，`v-if` 始终为 false。`v-loading="stats.loading"` 始终显示加载遮罩。

## 根因

Vue 3 `<script setup>` 模板编译器只对**顶层绑定**（直接在 `<script setup>` 中用 `const` 定义的变量）进行 ref 自动解包。**对象属性中的 ref 不会自动解包**。

```js
// ❌ 对象属性中的 ref — 模板不会自动解包
const stats = useStatsDrawer()
// 模板中 stats.aggregatedStats 是 ComputedRef 对象（恒 truthy）
// stats.aggregatedStats.totalSessions → undefined
// v-loading="stats.loading" → ComputedRef（恒 truthy）

// ✅ 顶层解构 — 每个 ref 成为顶层绑定，模板自动解包生效
const { loading, aggregatedStats, sessions, ... } = useStatsDrawer()
// 模板中 directly: v-loading="loading", aggregatedStats.totalSessions
```

## 判断方法

通过 CDP 检查当前正在运行的组件实例：

```js
const comp = findStatsDrawer(instance) // 从子树查找目标组件
const ss = comp.setupState
const refValue = ss.stats.aggregatedStats

// 检查 __v_isRef 标志
refValue?.__v_isRef  // true = 这是 ref 对象，不是值
refValue?.value?.totalSessions  // 7 = 要从 .value 取实际值
```

## 受影响的范围

- `const stats = useStatsDrawer()` — 所有 `stats.xxx` 在模板中都是 ref 而非值
- `const profile = useAbilityProfile(options)` — 所有 `profile.xxx` 同理
- `const { a, b } = profile` — 解构后的变量是**顶层绑定**，模板能正确自动解包

## 额外影响：v-loading 恒显示

`v-loading="stats.loading"` 中 `stats.loading` 是 ComputedRef 对象。任何非空对象的布尔值都是 `true`，所以加载遮罩恒显示，即使数据已经加载完成。

## 修复方案

### 方案 A（推荐）：顶层解构

```js
const { 
  isDrawerOpen, toggleDrawer, loading, aggregatedStats,
  sessions, allAnswers, openSessionDetail, refreshAll, 
} = useStatsDrawer()
```

模板直接使用 `loading`、`aggregatedStats.totalSessions`、`sessions.slice(0, 10)` 等。

### 方案 B：在 `<script setup>` 中用解构赋值 + 保持 stats 对象（用于函数调用）

```js
const stats = useStatsDrawer()
const { loading, aggregatedStats, sessions } = stats
```

### 方案 C（不推荐）：模板中手动加 .value

```html
<template v-if="stats.aggregatedStats.value && stats.aggregatedStats.value.totalSessions > 0">
```

Vue 3 没有记录此方案，因为它绕过了自动解包，且与未来版本兼容性不确定。

## 验证清单

- [ ] 解构后 v-loading 正常（false 时遮罩消失）
- [ ] v-if 条件正常（`aggregatedStats.totalSessions > 0` 为 true 时渲染数据）
- [ ] v-for 正常（`sessions.slice(0, 10)` 遍历）
- [ ] 旧代码中的 `stats.xxx.value` 全部改回 `xxx`（无 .value）
- [ ] 组件传递的 function 回调不受影响（`toggleDrawer(v)`、`openSessionDetail(id)`）
