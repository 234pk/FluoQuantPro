## 2026-01-03 更新记录 (Part 5)

### 1. 严重 Bug 修复: ROI 绘制崩溃 (Critical Fix: ROI Drawing Crash)
- **问题原因**: `RoiGraphicsItem` 类在重构为使用统一渲染引擎 (`QtRenderEngine`) 时，缺少了 `engine` 和 `style_center` 的初始化代码。导致在 `paint` 方法调用时触发 `AttributeError`，进而导致程序在渲染新 ROI 时崩溃。
- **修复措施**: 在 `src/gui/canvas_view.py` 的 `RoiGraphicsItem.__init__` 方法中添加了缺失的初始化代码：
  ```python
  self.engine = QtRenderEngine()
  self.style_center = StyleConfigCenter()
  ```
- **影响范围**: 修复了所有类型的 ROI (矩形、多边形、椭圆等) 在绘制完成后导致程序崩溃的问题。

### 2. 代码清理
- **调试日志**: 保留了 `RectangleSelectionTool` 中的调试日志，以便后续观察，但崩溃的根本原因已定位并修复。
