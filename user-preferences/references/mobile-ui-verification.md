# 手机端 UI 复查与对齐修正（2026-06-01）

## 场景
用户在 PrimarySchoolMathematics 的手机端布局上明确要求：
- 页面保持不可滚动
- 生成题目按钮在手机端必须可见
- 答案横线与答案位必须对齐
- 仅在实际渲染后截图复查，不接受只看代码的结论

## 有效做法
1. **先改代码，再用浏览器真实渲染验证**：不要只靠静态阅读判断对齐是否修好。
2. **用截图/几何信息确认问题**：
   - `browser_snapshot` 看元素树是否存在
   - `browser_console` 取 `getBoundingClientRect()` 和 `getComputedStyle()`
   - 必要时 `Page.captureScreenshot` 复查整体视觉
3. **浮动按钮“消失”优先排查这三类问题**：
   - 被手机端媒体查询隐藏
   - 被父容器 `overflow/stacking` 遮住
   - 层级不够，需提高 `z-index`
4. **答案横线偏移优先调这几项**：
   - `line-height`
   - `padding-bottom`
   - `display: inline-flex` / `align-items: flex-end`
   - 列容器的 `align-items` 与底部 padding
5. **用户明确说“截图看一下/自己改完要截图复查”时**，必须完成截图验证后再汇报，不要只给口头结论。

## 可复用的检查顺序
- 看元素是否存在
- 看元素是否可见（display / visibility / opacity）
- 看元素是否被遮挡（position / z-index / overflow）
- 看文本基线与底线是否错位（line-height / padding / align-items）
- 看最终截图是否符合视觉预期
