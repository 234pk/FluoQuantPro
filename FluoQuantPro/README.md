# FluoQuantPro

[English](#english) | [中文](#中文)

---

<a name="english"></a>
## English

FluoQuantPro is a professional software designed for high-performance analysis and quantification of immunofluorescence (IF) images. It provides a comprehensive set of tools for researchers to process, analyze, and visualize multi-channel fluorescence microscopy data with precision and efficiency.

### Key Features
- **Multi-channel Support**: Seamlessly import and manage complex multi-channel TIF images.
- **Advanced ROI Management**: Powerful tools for creating and managing Regions of Interest (ROI) including rectangles, ellipses, polygons, and magic wand selection.
- **Real-time Quantification**: Instant measurement of fluorescence intensity, area, and co-localization metrics.
- **Image Enhancement**: Built-in algorithms for noise reduction, contrast adjustment, and image sharpening.
- **Smooth Polygon Rendering**: Professional-grade Catmull-Rom spline smoothing for organic-shaped ROIs.
- **Annotation System**: Robust annotation tools for adding text and markings to your analysis.
- **Batch Processing**: Tools designed to handle multiple samples and large datasets efficiently.
- **Export Capabilities**: Comprehensive export options for results (CSV) and publication-quality images.

### System Requirements
- Windows 10/11 or macOS
- Python 3.10+ (for development)
- Key Dependencies: PySide6, NumPy, OpenCV, Scikit-Image, Tifffile.

### macOS Installation Troubleshooting
If you encounter "App is damaged" or "Developer cannot be verified" on macOS:
1. Open **Terminal**.
2. Run the following command (replace `/Applications` with your actual path):
   ```bash
   sudo xattr -rd com.apple.quarantine /Applications/FluoQuantPro.app
   ```
3. Enter your password and try opening the app again.

---

<a name="中文"></a>
## 中文

FluoQuantPro 是一款专为免疫荧光 (IF) 图像设计的高性能分析与定量软件。它为研究人员提供了一套全面的工具，能够精确且高效地处理、分析和可视化多通道荧光显微镜数据。

### 核心功能
- **多通道支持**: 无缝导入和管理复杂的 TIF 多通道图像。
- **高级 ROI 管理**: 提供矩形、椭圆、多边形及魔棒选择等多种 ROI 创建与管理工具。
- **实时定量**: 瞬时测量荧光强度、面积及共定位指标。
- **图像增强**: 内置降噪、对比度调整及图像锐化等算法。
- **平滑多边形渲染**: 采用专业的 Catmull-Rom 样条曲线平滑技术，适用于不规则形状的 ROI。
- **标注系统**: 强大的标注工具，可在分析过程中添加文字说明和标记。
- **批量处理**: 专为处理多个样本和大型数据集而设计的工具流。
- **结果导出**: 支持导出详细的测量数据 (CSV) 及出版级质量的图像。

### 系统要求
- Windows 10/11 或 macOS
- Python 3.10+ (开发环境)
- 核心依赖: PySide6, NumPy, OpenCV, Scikit-Image, Tifffile。

### macOS 安装故障排除
如果在 macOS 上遇到“应用已损坏”或“无法验证开发者”提示：
1. 打开 **终端 (Terminal)**。
2. 输入以下命令（将 `/Applications` 替换为实际安装路径）：
   ```bash
   sudo xattr -rd com.apple.quarantine /Applications/FluoQuantPro.app
   ```
3. 输入密码并回车，然后重新尝试打开应用。
