# P5: 画像驱动的智能出题策略 — 会话记录

> 2026-06-06 | PrimarySchoolMathematics 项目 | 见设计文档 `designDocs/PLAN-v2-roadmap.md § 5`

## 设计目标

让用户画像（strongLevels / weakLevels）从"展示用"变成"驱动出题"。
按强/弱项比例生成题库排列方案，每答一题动态微调。

## 关键设计决策

1. **直接用 DIFFICULTY_LEVELS 索引**，不创建额外映射层。`matchLevel` 反推已够。
2. **强/弱项使用 `useAbilityProfile` 中的 label 数组**，不从诊断 L1-L5 ID 映射。
3. **weak/strong 权重可调变量**（`PROFILE_RATIOS` in constants）。
4. **排列方案随机打乱**（Fisher-Yates），不固定顺序。
5. **最后一组预测法**：`totalAnswered + groupSize × 1.5 >= targetMax`。
6. **动态微调每答一题触发**，不等待组结束。

## 修复的 Bug

### ASSIST_LEVELS 顺序颠倒
- **原**：`vertical > choice4 > choice2 > horizontal`（与难度方向相反）
- **改**：`choice2 < choice4 < vertical < horizontal`（从易→难）
- **连带**：`pickInputMode` 概率表重写，`evaluateGroup` assistLevel 方向翻转

### 注释块吞 export
- **现象**：`SyntaxError: does not provide an export named 'ASSIST_LEVELS'`
- **原因**：`/* =======` 多行注释缺少 `*/` 闭合
- **修复**：补上 `*/`
- **教训**：修改文件后必须 `node --check file.js` 再跑浏览器

### Mastery Check 从组级改为每题级
- **原**：`evaluateGroup` 中组结束后统一判断 → 4/4 全对就 50% 概率整组横式
- **改**：`adjustNextQuestion` 中 "连续答对 2 题→下一题进横式"
- **优点**：不打断组节奏，更细腻

## 架构违规修复

- **违规**：`Practice.vue` (V) 直接 `import { adjustNextQuestion } from '@/utils/algorithm/adaptiveEngine'` (U)
- **规则**：`V → U = ❌` (ARCHITECTURE.md §1.2)
- **修复**：改走 C 层 `useAdaptiveSession.afterAnswer()`
- **教训**：每次新功能需要检查跨层规则表，尤其是 V 层新 import

## 用户偏好信号

- "少自造" — 优先复用现有概念（`matchLevel`、`strongLevels` labels）
- "弃用代码用注释占位，不要删"
- "profileWeights.js 是否有必要独立一个文件" — 合入 `adaptiveEngine.js`
- "如果弃用，先全段注释占位" — `generatePracticeConfig` 注释不删
