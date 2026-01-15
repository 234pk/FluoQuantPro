from PySide6.QtWidgets import QFrame, QPushButton, QToolButton, QGraphicsDropShadowEffect
from PySide6.QtGui import QColor
from PySide6.QtCore import QEvent, QRect, QPoint, QPropertyAnimation, QEasingCurve

class HoverEffectFilter(QFrame):
    """
    Event filter to provide advanced hover/press effects for buttons:
    - Scaling (105% hover, 98% press)
    - Dynamic Shadows (Blur/Opacity)
    - Elastic Animations
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self._animations = {}
        self._shadows = {}

    def eventFilter(self, obj, event):
        # Strict type checking to avoid interfering with CanvasView or other widgets
        if type(obj) not in (QPushButton, QToolButton):
            return False

        # Only handle basic mouse/hover events for buttons
        if not obj.isEnabled():
            return False

        if event.type() == QEvent.Type.Enter:
            self._apply_hover_effect(obj, True)
        elif event.type() == QEvent.Type.Leave:
            self._apply_hover_effect(obj, False)
        elif event.type() == QEvent.Type.MouseButtonPress:
            self._apply_press_effect(obj, True)
        elif event.type() == QEvent.Type.MouseButtonRelease:
            self._apply_press_effect(obj, False)
            
        return False # IMPORTANT: Never return True, always let the original widget handle the event

    def _apply_hover_effect(self, btn, hovering):
        # 1. Scaling Animation - Subtler scaling
        scale = 1.02 if hovering else 1.0
        self._animate_geometry(btn, scale, tilt=hovering)
        
        # 2. Shadow Effect - Subtler shadow
        if hovering:
            shadow = QGraphicsDropShadowEffect(btn)
            shadow.setBlurRadius(10) # Reduced spread
            shadow.setOffset(0, 3) # Reduced offset
            shadow.setColor(QColor(0, 0, 0, 40)) # Lighter shadow
            btn.setGraphicsEffect(shadow)
            self._shadows[btn] = shadow
        else:
            btn.setGraphicsEffect(None)
            if btn in self._shadows:
                del self._shadows[btn]

    def _apply_press_effect(self, btn, pressed):
        scale = 0.98 if pressed else 1.02
        self._animate_geometry(btn, scale, tilt=not pressed)

    def _animate_geometry(self, btn, scale_factor, tilt=False):
        base_geo = btn.property("base_geometry")
        if base_geo is None:
            base_geo = btn.geometry()
            btn.setProperty("base_geometry", base_geo)

        center = base_geo.center()
        
        # Add very slight offset for dynamic feel
        if tilt:
            center += QPoint(0, -1) # Move up only 1px on hover
            
        new_w = int(base_geo.width() * scale_factor)
        new_h = int(base_geo.height() * scale_factor)
        
        target_geo = QRect(0, 0, new_w, new_h)
        target_geo.moveCenter(center)

        anim = self._animations.get(btn)
        if anim:
            anim.stop()
        else:
            anim = QPropertyAnimation(btn, b"geometry")
            self._animations[btn] = anim

        anim.setDuration(150) # Faster transition (150ms)
        anim.setStartValue(btn.geometry())
        anim.setEndValue(target_geo)
        
        # Use smoother curves without overshoot
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            
        anim.start()
