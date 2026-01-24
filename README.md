# FluoQuantPro (v3.0)

[![Release](https://img.shields.io/badge/release-v3.0-blue.svg)](https://github.com/234pk/FluoQuantPro/releases)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS-lightgrey.svg)](#)

[English Manual](#fluoquantpro-software-manual) | [中文说明书](#fluoquantpro-软件说明书)

---

<div align="center">
  <img src="FluoQuantPro.gif" alt="FluoQuantPro Demo" width="100%">
  <br>
  <a href="https://www.youtube.com/watch?v=8KVSKE3WlKM">📺 Watch Demo Video on YouTube</a>
</div>

---

# FluoQuantPro Software Manual
**Version:** v3.0+  
**Release Date:** January 24, 2026  
**Platforms:** Windows, macOS

## I. Software Overview
FluoQuantPro is a high-performance, open-source image analysis software tailored for biomedical and fluorescence microscopy research. It addresses three core pain points encountered by researchers when processing multi-channel fluorescence images (e.g., Immunofluorescence, FISH): **Data Integrity**, **Analysis Efficiency**, and **Visual Experience**.

The core design philosophy is **"Dual-Track Processing"**: strict separation between the **Measurement Data Track** (based on raw scientific data) and the **Rendering Display Track** (used for visual adjustment). This means users can freely adjust brightness, contrast, and color to optimize visualization, while the underlying pixel values used for quantitative analysis (e.g., intensity measurement, colocalization) remain unchanged, fundamentally guaranteeing the rigor and reproducibility of scientific data.

## II. Core Functions & Features

### 1. High-Performance Rendering & Interaction Engine
FluoQuantPro features an advanced built-in rendering optimization algorithm, ensuring smooth operation even when processing ultra-large multi-channel images (e.g., over 10,000 pixels).

*   **Smart Hierarchical Rendering:** During interactive operations like zooming and panning, the system automatically switches to a low-resolution preview mode to ensure extreme fluidity. Once the operation stops, after a brief stabilization delay, the view smoothly restores to the high-definition original image, effectively eliminating flickering and stuttering during rapid manipulation.
*   **Multiple Rendering Quality Presets:** Four rendering quality modes are available to suit hardware performance and task needs:
    *   **1K (Performance Mode):** Limits display resolution to 1024px, maximizing resource saving.
    *   **2.5K (Balanced Mode):** Limits display resolution to 2560px, balancing clarity and performance.
    *   **4K (Ultra Quality):** Limits display resolution to 3840px, suitable for high-res monitors.
    *   **Original:** No limit, displays original image resolution directly.
*   **Magnetic Zoom Snapping:** When manually zooming, if the view ratio approaches "Fit Width" or "Fit Height", a subtle magnetic snapping effect occurs. It intelligently locks onto a single target, making view adjustments fast, precise, and stable.

### 2. Powerful Region Selection & Analysis Tools
A complete set of Region of Interest (ROI) tools is provided for target identification and quantitative analysis.

*   **Smart Magic Wand Tool:**
    *   **Precise Coordinate Mapping:** Automatically corrects click positions to ensure perfect alignment between the selection and target cells, even when the image is centered or zoomed.
    *   **Smooth Edges & Polygon Conversion:** Generated selection edges are smoothed for a natural look. You can enable **"Convert to Polygon"** in the property bar to instantly convert Magic Wand selections into editable polygon ROIs for fine-tuning local edges.
    *   **Continuous Selection Mode:** Optimized to remain active after a selection, supporting continuous and efficient selection of multiple targets without auto-switching tools.
*   **Diverse Basic Tools:** In addition to the Magic Wand, standard drawing tools like Rectangle, Ellipse, Polygon, Line, and Point Count are available to meet various annotation needs.
*   **Full-Featured ROI Management:** All created ROIs can be selected, moved, rotated, and edited. The system uses lazy loading and Level of Detail (LOD) technology to keep the interface responsive even with hundreds or thousands of ROIs.

### 3. Professional Measurement & Statistical Analysis
*   **Measurement Result Accumulation:** Enabled by default. When you move or adjust an existing ROI and measure again, new results are appended to the history rather than overwriting old data. This facilitates comparison of the same structure under different conditions. Results are automatically renamed (e.g., ROI 1, ROI 1 (2)) for distinction.
*   **One-Click Export:** A prominent **"Export Results (CSV)..."** button is located at the bottom of the measurement panel. It quickly exports data to CSV format using **utf-8-sig** encoding, ensuring correct display of special characters in software like Microsoft Excel.
*   **Colocalization Analysis:** Built-in algorithms calculate colocalization metrics such as Pearson's Correlation Coefficient (PCC) and Manders' Coefficients (M1, M2) to analyze the spatial overlap of signals from different fluorescence channels.

### 4. Intelligent System & Resource Management
*   **Real-Time Memory Monitoring:** The status bar displays **"App Memory Usage"** and **"System Total Memory Usage"** (e.g., App: 324.0MB (Sys: 80%)). If usage becomes too high, the bar changes color (Orange/Red) to warn the user.
*   **Configurable Caching Policy:** In "Settings" -> "Display", you can customize caching behavior to balance memory usage and switching speed:
    *   **None:** No caching, lowest memory usage.
    *   **Current Sample Only:** (**Recommended**) Automatically clears the previous sample's cache when switching.
    *   **Cache Recent 5:** Uses LRU algorithm to keep the most recent samples.
    *   **All Samples:** Keeps all loaded samples for the fastest re-opening.
*   **Automatic Memory Cleanup:** When memory usage exceeds a safety threshold, the software triggers a cleanup process to release image caches and intermediate data, and invokes system-level calls to reclaim physical memory, ensuring stability during long-term, high-volume processing.

### 5. Modern UI & Personalized Experience
*   **Rich Theme System:** 8 carefully designed UI themes are built-in, including Light, Dark, Cappuccino, Sakura, Deep Ocean, Dopamine, Macaron, and Comfort Eye-Care. Switch quickly via **Ctrl+T** (Windows/Linux) or **Cmd+T** (macOS), or select permanently in settings. Icon colors adapt to themes for better visibility.
*   **Platform-Native Interaction:** On macOS, the software adapts to the native style, adjusting shortcuts to **Cmd / Option** and integrating the menu bar into the system menu.
*   **Compact Layout Design:** The sidebar, toolbar, and control panels are optimized for scalability and compactness, maximizing screen space for the image itself.

### 6. Project & Data Management
*   **Unified Project File:** Work is saved in the professional `.fluo` format, containing all image channel info, ROI data, measurement results, and display settings.
*   **Complete Import/Export:** Supports importing various scientific image formats. The current view (including all ROIs and annotations) can be exported as high-resolution (up to 1200 DPI) PNG or TIFF images, realizing true **"What You See Is What You Get"**.
*   **Undo/Redo & Persistence:** Supports multi-step undo/redo. Manual project save forces retention of all ROIs; options are available to control auto-saving of measurement data when switching samples or closing.

## III. Quick Start Guide

### 1. Basic Workflow
1.  **New/Open Project:** Use the "File" menu to create a new project or open an existing `.fluo` file.
2.  **Import Images:** Use "File" -> "Import" to add fluorescence image files (supports multi-channel TIFF, Z-stack, etc.). The software automatically identifies channels or allows manual specification.
3.  **Channel Management & Pseudo-Color:** Assign pseudo-colors (e.g., Blue for DAPI, Green for FITC) in the "Adjust" panel or the bottom filmstrip. Common biological fluorescence colors are preset.
4.  **Image Analysis:**
    *   Select the **Magic Wand Tool** or other ROI tools from the left toolbar.
    *   Select target regions on the image. Adjust tolerance in real-time by dragging the mouse with the Magic Wand.
    *   In the ROI property bar, adjust selection smoothing or enable "Convert to Polygon".
5.  **Execute Measurement:** After drawing ROIs, click the **"Measure"** button in the top toolbar or "Analyze" menu. Results appear in the "Measurement Results" panel on the right.
6.  **Export Results:** Click **"Export Results (CSV)..."** in the panel to save data. Or use "File" -> "Export" -> "Rendered Image" to export images with annotations.

### 2. Key Tips
*   **View Control:**
    *   Mouse Wheel to Zoom.
    *   Right-click drag (or Space + Left-click) to Pan.
    *   Click the **"Refresh/Fit Width"** button (top-right toolbar) to quickly fit the image to the window.
*   **Efficient Magic Wand:** When selecting cells continuously, no need to click the toolbar repeatedly; just select one target and immediately click the next.
*   **Theme Switching:** Use **Ctrl+T / Cmd+T** to find the best theme. The Eye-Care theme is recommended for long analysis sessions.

## IV. System Requirements & Installation
*   **OS:** Windows 10/11 or macOS 11.0 (Big Sur) and above.
*   **Memory:** 8 GB recommended; 16 GB recommended for large images/datasets.
*   **Storage:** At least 500 MB available space.
*   **Graphics:** OpenGL-compatible graphics card for better rendering performance.

## V. Privacy & Data Security
FluoQuantPro respects user privacy. It includes an optional anonymous usage statistics feature to help developers improve the product.
*   **Collected Content:** Only strictly anonymous info: random instance ID, OS type/version, software version, Python version/arch. **Never collects PII, file paths, image content, or measurement data.**
*   **User Control:** Enabled by default. You can disable **"Send Anonymous Usage Data"** at any time in **"Settings" -> "Interface" -> "Privacy"**.
*   **Data Usage:** Solely for macro-level software improvement analysis.

## VI. Conclusion
FluoQuantPro is not just an image viewer; it is an integrated analysis platform built for rigorous scientific workflows. By combining cutting-edge performance, user-friendly interaction, professional analysis tools, and a highly customizable interface, it aims to significantly improve efficiency, accuracy, and enjoyment for researchers in fluorescence image quantitative analysis.

We hope this manual helps you make the most of FluoQuantPro. For questions or feedback, please contact us via project channels.

## Disclaimer
This software is a research tool. Users are responsible for the scientific validity and accuracy of their data analysis results. The developers assume no liability for any data or research losses directly or indirectly caused by the use of this software.

---

# FluoQuantPro 软件说明书
**版本：** v3.0+  
**发布日期：** 2026年1月24日  
**适用平台：** Windows, macOS

## 一、 软件概述
FluoQuantPro 是一款专为生物医学和荧光显微成像研究设计的高性能、开源图像分析软件。它致力于解决科研人员在处理多通道荧光图像（如免疫荧光、FISH等）时遇到的三大核心痛点：**数据完整性**、**分析效率**和**视觉体验**。

软件的核心设计理念是**“双轨制处理”**：严格区分**测量数据轨道**（基于原始科学数据）与**渲染显示轨道**（用于可视化调整）。这意味着用户可以自由调整图像的亮度、对比度和色彩以优化视觉效果，而用于定量分析（如强度测量、共定位分析）的底层像素值始终保持不变，从根本上保证了科研数据的严谨性和可重复性。

## 二、 核心功能与特性

### 1. 高性能图像渲染与交互引擎
FluoQuantPro 内置了先进的渲染优化算法，确保即使处理超大尺寸（如10,000像素以上）的多通道图像也能流畅操作。

*   **智能分级渲染：** 在您进行缩放、平移等交互操作时，系统会自动切换到低分辨率预览模式以保证极致流畅；当您停止操作后，经过短暂防抖延时，画面会平滑恢复至高清晰度原图，有效消除了快速操作时的画面闪烁和卡顿。
*   **多重渲染质量预设：** 软件提供四种渲染质量模式，您可以根据硬件性能和任务需求灵活选择：
    *   **1K (性能模式)：** 限制显示分辨率为1024px，最大限度节省资源。
    *   **2.5K (平衡模式)：** 限制显示分辨率为2560px，兼顾清晰度与性能。
    *   **4K (超高质量)：** 限制显示分辨率为3840px，适用于高分辨率显示器。
    *   **原图：** 无限制，直接显示原始图像分辨率。
*   **磁性缩放吸附：** 手动缩放图像时，当视图比例接近“适应窗口宽度”或“适应窗口高度”时，会产生轻微的磁性吸附效果，并能智能锁定单一目标，使视图调整快速、精准且稳定。

### 2. 强大的区域选取与分析工具
软件提供了一套完整的区域感兴趣（ROI）工具集，用于目标识别和定量分析。

*   **智能魔棒工具：**
    *   **精准坐标映射：** 自动校正点击位置，确保在图像居中或缩放显示时，选区与目标细胞完美匹配。
    *   **圆滑边缘与多边形转换：** 生成的选区边缘经过平滑算法处理，更加自然。您可以在属性栏中开启“**转化为多边形**”功能，将魔棒选区瞬间转换为可编辑的多边形ROI，方便后续对局部边缘进行精细化微调。
    *   **连续选取模式：** 优化后，魔棒工具在完成一次选取后不会自动切换，支持您连续、高效地选取多个目标。
*   **多样化基础工具：** 除了魔棒，还提供矩形、椭圆、多边形、线条、点计数等标准绘图工具，满足不同形状目标的标注需求。
*   **全功能ROI管理：** 所有创建的ROI都可以被选中、移动、旋转、编辑。系统采用延迟加载和细节层次（LOD）技术，即使面对成百上千个ROI，界面依然保持流畅响应。

### 3. 专业的测量与统计分析
*   **测量结果累加：** 默认开启。当您移动或调整同一个ROI并再次测量时，新的测量结果会追加到历史记录中，而非覆盖旧数据，方便对比同一结构在不同条件下的变化。结果会自动重命名（如 ROI 1 , ROI 1 (2) ）以示区分。
*   **一键导出：** 测量结果面板下方设有醒目的 “**导出测量结果 (CSV)...**” 按钮，可快速将数据导出为CSV文件，并自动使用 `utf-8-sig` 编码，确保在Microsoft Excel等软件中打开时中文不乱码。
*   **共定位分析：** 软件内置算法，可计算皮尔逊相关系数（PCC）和曼德斯系数（M1, M2）等共定位指标，用于分析不同荧光通道信号的空间重叠关系。

### 4. 智能化的系统与资源管理
*   **实时内存监控：** 主界面状态栏实时显示 “**应用内存占用**” 和 “**系统总内存使用率**” （格式如： App: 324.0MB (Sys: 80%) ）。当应用自身内存占用过高或系统内存极度紧张时，显示条会变色预警（橙色/红色）。
*   **可配置缓存策略：** 在“设置”->“显示”中，您可以自定义缓存行为，平衡内存占用与切换速度：
    *   **无：** 不缓存，内存占用最低。
    *   **仅当前样本：** （**推荐**）切换样本时自动清理上一个样本的缓存。
    *   **缓存最近5个样本：** 采用LRU算法，保留最近使用的样本缓存。
    *   **所有样本：** 保留所有加载过的样本缓存，再次打开时速度最快。
*   **自动内存清理：** 当内存占用超过安全阈值时，软件会自动触发清理流程，释放图像缓存和中间数据，并通过系统级调用尽可能回收物理内存，保障长时间、多批次处理的稳定性。

### 5. 现代化的用户界面与个性化体验
*   **丰富的主题系统：** 软件内置8种精心设计的UI主题，包括浅色、深色、卡布奇诺、樱花、深邃海洋、多巴胺、马卡龙、舒适护眼主题。您可通过 **Ctrl+T** （Windows/Linux）或 **Cmd+T** （macOS）快速切换，也可以在设置中永久选择。图标颜色会随主题自动变化，提升视觉舒适度和辨识度。
*   **符合平台习惯的交互：** 在macOS上，软件自动适配原生风格，快捷键调整为 **Cmd / Option**，菜单栏整合至系统菜单，提供地道的使用体验。
*   **紧凑的布局设计：** 侧边栏、工具栏和控制面板均经过优化，支持缩放和紧凑布局，有效利用屏幕空间，专注于图像本身。

### 6. 项目与数据管理
*   **统一的项目文件：** 工作保存为 `.fluo` 格式的专业项目文件，包含所有图像通道信息、ROI数据、测量结果及显示设置。
*   **完整的导入导出：** 支持导入多种格式的科学图像，并可将当前视图（包含所有ROI和标注）以高分辨率（最高1200 DPI）导出为PNG、TIFF等格式，真正实现“**所见即所得**”。
*   **撤销/重做与持久化：** 支持多步撤销/重做操作。项目手动保存时会强制保留所有ROI；软件也提供选项，控制是否在切换样本或关闭时自动保存测量相关数据。

## 三、 快速入门指南

### 1. 基本工作流程
1.  **新建/打开项目：** 通过“文件”菜单创建新项目或打开已有的 `.fluo` 项目文件。
2.  **导入图像：** 通过“文件”->“导入”功能，添加您的荧光图像文件（支持多通道TIFF、Z-stack等）。软件会自动识别通道或允许您手动指定。
3.  **通道管理与伪彩：** 在右侧的“调整”面板或底部的胶片栏中，为每个通道分配伪彩色（如DAPI用蓝色，FITC用绿色）。软件已预设了生物学常用的荧光通道颜色。
4.  **图像分析：**
    *   从左侧工具栏选择 **魔棒工具** 或其它ROI工具。
    *   在图像上选取目标区域。使用魔棒工具时，可通过拖动鼠标实时调整容差。
    *   在ROI属性栏中，可以调整选区平滑度或启用“转化为多边形”。
5.  **执行测量：** 完成ROI绘制后，点击顶部工具栏或“分析”菜单中的 “**测量**” 按钮。结果将显示在右侧的“测量结果”面板中。
6.  **导出结果：** 在“测量结果”面板中，点击 “**导出测量结果 (CSV)...**” 按钮保存数据。或通过“文件”->“导出”->“渲染图像”来导出带标注的图片。

### 2. 关键操作技巧
*   **视图控制：**
    *   使用鼠标滚轮进行缩放。
    *   按住鼠标右键（或空格键+左键）进行平移。
    *   点击右上角工具栏的 “**刷新/适应宽度**” 按钮（位于重做和导出按钮之间），可快速将图像适配到窗口宽度。
*   **魔棒工具高效使用：** 在连续选取细胞时，无需反复点击工具栏，选取一个目标后直接点击下一个即可。
*   **主题切换：** 使用快捷键 **Ctrl+T** / **Cmd+T** 探索最适合您工作环境的主题，护眼主题尤其适合长时间分析。

## 四、 系统要求与安装
*   **操作系统：** Windows 10/11 或 macOS 11.0 (Big Sur) 及以上版本。
*   **内存：** 建议 8 GB 或以上，处理大图或大量样本时推荐 16 GB。
*   **存储空间：** 至少 500 MB 可用空间。
*   **显卡：** 支持 OpenGL 的显卡将能获得更好的渲染性能。

## 五、 隐私与数据安全
FluoQuantPro 尊重用户隐私。软件包含一个可选的匿名使用统计功能，用于帮助开发者了解软件使用情况以改进产品。
*   **收集内容：** 仅收集完全匿名的信息，包括随机生成的软件实例ID、操作系统类型和版本、软件版本、Python版本和架构。**绝不收集任何个人身份信息、文件路径、图像内容或测量数据**。
*   **用户控制：** 该功能默认开启，但您可以在 “设置” -> “界面” -> “隐私” 中，随时关闭 “**发送匿名使用数据**” 选项。
*   **数据用途：** 所有数据仅用于宏观的软件改进分析。

## 六、 与 ImageJ (Fiji) 的对比

| 功能环节 | ImageJ (Fiji) | FluoQuantPro |
| :--- | :--- | :--- |
| **导入与通道** | **“盲读取”模式**：先将文件作为通用像素块（RGB/堆栈）读入。用户必须在读取后手动“拆分通道”并赋予其生物学意义（如“通道1是DAPI”）。 | **“语义读取”模式（预设优先）**：用户将文件指定给特定的生物学通道（如“DAPI”）。引擎根据这一**生物学意图**，在读取时智能提取源文件中对应的信号数据（如自动提取RGB中的蓝色分量）。 |
| **设计理念** | **“工具箱”**：功能强大但零件散落，适合深度定制。 | **“一体化仪器”**：为荧光定量分析精心调校，追求开箱即用与流程顺畅。 |
| **图像调整** | 调整亮度/对比度时，若点击“Apply”会直接修改像素值，存在数据被篡改的风险。 | **“双轨制”架构**：显示调整与原始数据完全分离。调整只为看清，**绝不改变**定量分析所用的底层数据。 |
| **ROI与测量** | 标准工具。复杂分析需组合多步操作。背景扣除通常需手动计算。 | **增强魔棒**（精准、平滑、可转多边形）。**流线型测量**，结果自动累加。内置共定位分析与一键导出。 |
| **科学性保障** | 灵活性高，但对用户要求高，易产生误操作（如测量处理后的图像）。 | **数据完整性第一**：测量引擎始终读取原始数据的 `RawIntDen`（像素总和），从底层逻辑保障结果的可重复性。 |

## 七、 总结
FluoQuantPro 不仅仅是一个图像查看器，它是一个为严谨科研工作流程打造的集成化分析平台。通过将尖端的性能优化、人性化的交互设计、专业的数据分析工具和高度可定制化的界面相结合，它旨在显著提升研究人员在荧光图像定量分析工作中的效率、准确性和愉悦感。

我们希望这份说明书能帮助您更好地利用 FluoQuantPro 的强大功能。如有任何问题或反馈，欢迎通过项目渠道与我们联系。

## 免责声明
本软件为科研工具，使用者应对其数据分析结果的科学性和准确性负责。开发者不对因使用本软件直接或间接导致的任何数据或研究损失承担责任。
