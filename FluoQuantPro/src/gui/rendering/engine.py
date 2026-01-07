from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple, Union
from PySide6.QtCore import QPointF, QRectF, QObject, Signal
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QPainterPath

class IRenderEngine(ABC):
    """
    Abstract Interface for the Rendering Engine.
    Defines the contract for drawing graphic elements on the canvas.
    """
    
    @abstractmethod
    def set_context(self, painter: QPainter, scale: float):
        """Sets the current painting context."""
        pass
        
    @abstractmethod
    def draw_path(self, path: QPainterPath, style: Dict[str, Any]):
        """Draws a QPainterPath with the given style."""
        pass
        
    @abstractmethod
    def draw_shape(self, shape_type: str, points: List[QPointF], style: Dict[str, Any]):
        """Draws a primitive shape (rect, ellipse, etc.)"""
        pass
        
    @abstractmethod
    def draw_text(self, text: str, pos: QPointF, style: Dict[str, Any]):
        """Draws text at the given position."""
        pass

class BaseAnnotationGraphic(ABC):
    """
    Base class for all graphic annotations.
    """
    def __init__(self, uid: str, visible: bool = True):
        self.uid = uid
        self.visible = visible
        self.selected = False
        self.hovered = False
        self._style = {}
        
    @abstractmethod
    def render(self, engine: IRenderEngine):
        """Delegates rendering to the engine."""
        pass
        
    @abstractmethod
    def contains(self, point: QPointF) -> bool:
        """Hit testing."""
        pass

class StyleConfigCenter(QObject):
    """
    Centralized configuration for rendering styles.
    Supports dynamic updates via signals.
    """
    _instance = None
    style_changed = Signal(str) # Emits the name of the style that changed, or "all"
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(StyleConfigCenter, cls).__new__(cls)
            # Initialize QObject
            # Note: QObject.__init__ is called in __init__, but for Singleton using __new__ we must be careful.
            # However, since we inherit QObject, we need to ensure it's initialized.
        return cls._instance
        
    def __init__(self):
        # Ensure __init__ only runs once
        if hasattr(self, '_initialized') and self._initialized:
            return
        super().__init__()
        self._init_defaults()
        self._initialized = True
        
    def _init_defaults(self):
        self.styles = {
            'default': {
                'pen_color': '#FFFF00',
                'pen_width': 2.0,
                'brush_color': None,
                'antialiasing': True,
                'pen_style': 'solid'
            },
            'selected': {
                'pen_color': '#FF0000',
                'pen_width': 2.0,
                'effect': 'glow',
                'glow_color': '#FF0000',
                'glow_width': 6,
                'glow_alpha': 60
            },
            'hover': {
                'pen_color': '#00FFFF',
                'pen_width': 2.0,
                'effect': 'glow',
                'glow_color': '#00FFFF',
                'glow_width': 6,
                'glow_alpha': 60
            },
            'roi_default': {
                'pen_color': '#FFFF00',
                'pen_width': 2.0,
                'pen_style': 'dash', # [3, 2.5]
                'brush_color': None
            }
        }
    
    def get_style(self, state: str = 'default') -> Dict[str, Any]:
        return self.styles.get(state, self.styles['default'])

    def update_style(self, state: str, updates: Dict[str, Any]):
        """Updates a style configuration and notifies listeners."""
        if state in self.styles:
            self.styles[state].update(updates)
            self.style_changed.emit(state)
