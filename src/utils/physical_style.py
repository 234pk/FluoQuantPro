from PySide6.QtGui import QFont, QFontMetrics

class PhysicalRenderStyle:
    """
    Provides rendering style calculation based on Fixed Pixel Width (Scientific Style).
    Ensures that line width remains constant in pixels (e.g., 2px) regardless of image resolution or DPI.
    
    Why:
    - Scientific images often have huge resolutions (24k+) but small physical field of view.
    - Scaling line width by DPI (ImageJ Print Logic) or Resolution (Map Logic) often results in
      lines that are too thick ("Reinforced Bars") on downsampled exports or obscure details on high-res exports.
    - Fixed Pixel Width ensures lines are always crisp and minimal, suitable for zooming in on details.
    """
    
    # Reference Constants (kept for compatibility but unused for scaling)
    REFERENCE_WIDTH = 1920.0
    LOGICAL_DPI = 96.0
    
    # Base Line Width
    BASE_LINE_WIDTH = 2.0
    
    # Base Dash Pattern
    BASE_DASH_PATTERN = [4.0, 2.0]

    @staticmethod
    def get_scale_factor(target_metric: float) -> float:
        """
        Returns fixed scale factor 1.0.
        Ignores target_metric (DPI or Width) to ensure fixed pixel width.
        """
        return 1.0

    @staticmethod
    def get_line_width(target_metric: float, base_width: float = None) -> float:
        """Calculates line width (Fixed)."""
        if base_width is None:
            base_width = PhysicalRenderStyle.BASE_LINE_WIDTH
        if base_width <= 0:
            return 0.0
        return max(1.0, float(base_width))

    @staticmethod
    def get_dash_pattern(target_metric: float, pattern: list = None) -> list:
        """Calculates dash pattern (Fixed)."""
        if pattern is None:
            pattern = PhysicalRenderStyle.BASE_DASH_PATTERN
        return [float(p) for p in pattern]

    @staticmethod
    def get_font_size(target_metric: float, base_size: int = 12) -> float:
        """
        Calculates font size (Fixed).
        User should adjust base font size if larger text is needed.
        """
        return float(base_size)
