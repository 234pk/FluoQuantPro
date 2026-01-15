from typing import Any, Dict, List
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QPainterPath, QFont
from PySide6.QtCore import QPointF, Qt
from .engine import IRenderEngine

class QtRenderEngine(IRenderEngine):
    """
    Concrete implementation of IRenderEngine using QPainter.
    """
    
    def __init__(self):
        self.painter: QPainter = None
        self.scale: float = 1.0
        
        # --- Performance Optimization: Object Caching ---
        self._pen_cache = {}
        self._brush_cache = {}
        # ------------------------------------------------
        
    def set_context(self, painter: QPainter, scale: float):
        self.painter = painter
        self.scale = scale
        
    def draw_path(self, path: QPainterPath, style: Dict[str, Any]):
        if not self.painter:
            return
            
        # LOD Optimization: If zoom is very low, we can simplify the path
        # or use a cheaper drawing method.
        effective_path = path
        if self.scale < 0.1: # Deeply zoomed out
             # For very small items, we might just draw a bounding rect instead of complex path
             # but QPainter is already quite fast with bounding box culling.
             # The real cost is many points.
             if path.elementCount() > 50:
                 # Simplified rendering: draw simplified version if path is complex
                 # Qt doesn't have a built-in RDP, but we can use path.simplified() 
                 # which is better than nothing, though it's more for self-intersections.
                 # Alternatively, just use the bounding rect for EXTREME zoom levels.
                 if self.scale < 0.02:
                     self.painter.drawRect(path.boundingRect())
                     return
        
        self._apply_style(style)
        self.painter.drawPath(effective_path)
        
    def draw_shape(self, shape_type: str, points: List[QPointF], style: Dict[str, Any]):
        if not self.painter or not points:
            return
            
        self._apply_style(style)
        
        if shape_type == 'rect' and len(points) == 2:
            rect = QRectF(points[0], points[1]).normalized()
            self.painter.drawRect(rect)
        elif shape_type == 'ellipse' and len(points) == 2:
            rect = QRectF(points[0], points[1]).normalized()
            self.painter.drawEllipse(rect)
        elif shape_type == 'line' and len(points) == 2:
            self.painter.drawLine(points[0], points[1])
        elif shape_type == 'polygon':
            self.painter.drawPolygon(points)
            
    def draw_text(self, text: str, pos: QPointF, style: Dict[str, Any]):
        if not self.painter:
            return
            
        # Text specific style
        font_size = style.get('font_size', 12)
        # Ensure font_size is at least 1 to avoid QFont warning
        if font_size <= 0:
            font_size = 12
        font_family = style.get('font_family', 'Arial')
        color = style.get('text_color', style.get('pen_color', '#FFFFFF'))
        
        font = QFont(font_family, int(font_size))
        self.painter.setFont(font)
        self.painter.setPen(QColor(color))
        self.painter.drawText(pos, text)

    def _apply_style(self, style: Dict[str, Any]):
        # 1. Pen Caching Logic
        color_name = style.get('pen_color', '#FFFF00')
        width = style.get('pen_width', 2.0)
        pen_style_str = style.get('pen_style', 'solid')
        is_cosmetic = style.get('cosmetic', True)
        
        pen_key = (color_name, width, pen_style_str, is_cosmetic)
        pen = self._pen_cache.get(pen_key)
        
        if pen is None:
            color = QColor(color_name)
            pen = QPen(color, width)
            
            if pen_style_str == 'dash':
                pen.setStyle(Qt.PenStyle.DashLine)
            elif pen_style_str == 'dot':
                pen.setStyle(Qt.PenStyle.DotLine)
            else:
                pen.setStyle(Qt.PenStyle.SolidLine)
                
            pen.setCosmetic(is_cosmetic)
            self._pen_cache[pen_key] = pen
            
        self.painter.setPen(pen)
        
        # 2. Brush Caching Logic
        brush_color = style.get('brush_color')
        if brush_color:
            brush_alpha = style.get('brush_alpha', 255)
            brush_key = (brush_color, brush_alpha)
            brush = self._brush_cache.get(brush_key)
            
            if brush is None:
                color = QColor(brush_color)
                color.setAlpha(brush_alpha)
                brush = QBrush(color)
                self._brush_cache[brush_key] = brush
                
            self.painter.setBrush(brush)
        else:
            self.painter.setBrush(Qt.BrushStyle.NoBrush)
            
        # Antialiasing
        if style.get('antialiasing', True):
            self.painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        else:
            self.painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
