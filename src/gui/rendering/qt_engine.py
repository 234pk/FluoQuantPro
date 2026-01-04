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
        
    def set_context(self, painter: QPainter, scale: float):
        self.painter = painter
        self.scale = scale
        
    def draw_path(self, path: QPainterPath, style: Dict[str, Any]):
        if not self.painter:
            return
            
        self._apply_style(style)
        self.painter.drawPath(path)
        
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
        font_family = style.get('font_family', 'Arial')
        color = style.get('text_color', style.get('pen_color', '#FFFFFF'))
        
        font = QFont(font_family, int(font_size))
        self.painter.setFont(font)
        self.painter.setPen(QColor(color))
        self.painter.drawText(pos, text)

    def _apply_style(self, style: Dict[str, Any]):
        # Pen
        color = QColor(style.get('pen_color', '#FFFF00'))
        width = style.get('pen_width', 2.0)
        pen_style_str = style.get('pen_style', 'solid')
        
        # Effect: Glow
        effect = style.get('effect')
        if effect == 'glow':
            # For QPainter, we can't easily add a glow effect filter on the fly without layers.
            # But we can simulate it by drawing a thick semi-transparent line behind.
            # This is usually done by the caller calling draw twice (glow then main).
            # Or the engine can handle it.
            # Let's handle simple glow here if requested?
            # Drawing twice inside draw_path might be expensive or interfere with composition.
            # Better to let the graphic object handle multi-pass rendering.
            # So here we just set the main pen.
            pass

        pen = QPen(color, width)
        
        if pen_style_str == 'dash':
            pen.setStyle(Qt.PenStyle.DashLine)
        elif pen_style_str == 'dot':
            pen.setStyle(Qt.PenStyle.DotLine)
        else:
            pen.setStyle(Qt.PenStyle.SolidLine)
            
        # Cosmetic pen?
        # If we want consistent screen width regardless of zoom:
        # pen.setCosmetic(True)
        # But if we want it to scale, False.
        # The 'scale' param might be used here.
        # For now, let's assume non-cosmetic (scales with zoom) or follow style config.
        is_cosmetic = style.get('cosmetic', True)
        pen.setCosmetic(is_cosmetic)
        
        self.painter.setPen(pen)
        
        # Brush
        brush_color = style.get('brush_color')
        if brush_color:
            self.painter.setBrush(QBrush(QColor(brush_color)))
        else:
            self.painter.setBrush(Qt.BrushStyle.NoBrush)
            
        # Antialiasing
        if style.get('antialiasing', True):
            self.painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        else:
            self.painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
