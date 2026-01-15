from PySide6.QtWidgets import QAbstractButton, QSizePolicy, QApplication
from PySide6.QtCore import Qt, QPropertyAnimation, Property, QPoint, QRect, QEasingCurve, QSize
from PySide6.QtGui import QPainter, QColor, QBrush, QPen
from src.gui.theme_manager import ThemeManager

class ToggleSwitch(QAbstractButton):
    def __init__(self, parent=None, track_radius=8, thumb_radius=6):
        # Initialize attributes BEFORE super().__init__ in case sizeHint is called
        self._track_radius = track_radius
        self._thumb_radius = thumb_radius
        self._margin = 2
        self._base_width = (self._track_radius * 2) * 2
        self._base_height = self._track_radius * 2
        
        # Initial thumb position based on checked state will be set in resizeEvent or first paint
        self._thumb_pos = self._margin + self._thumb_radius

        super().__init__(parent)
        self.setCheckable(True)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        
        self.setFixedSize(self._base_width, self._base_height)
        self._animation = QPropertyAnimation(self, b"thumb_pos", self)
        self._animation.setDuration(200)
        self._animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
        
        # Colors (Default)
        self._active_color = QColor("#4CAF50")
        self._disabled_color = QColor("#CCCCCC")
        self._thumb_color = QColor("#FFFFFF")
        
        # Initialize colors from theme
        self.update_colors()
        
        # Connect to theme changes
        ThemeManager.instance().theme_changed.connect(self.update_colors)

    def setChecked(self, checked):
        """Override setChecked to update thumb position without animation."""
        super().setChecked(checked)
        self._thumb_pos = self.width() - self._margin - self._thumb_radius if checked else self._margin + self._thumb_radius
        self.update()

    def update_colors(self):
        """Update colors based on the current theme."""
        palette = QApplication.palette()
        
        # Track active color (Highlight)
        self._active_color = palette.color(palette.ColorRole.Highlight)
        
        # Thumb color (usually white/very light)
        # We try to use Base or a fixed white depending on theme
        window_color = palette.color(palette.ColorRole.Window)
        if window_color.lightness() < 128: # Dark theme
            self._thumb_color = QColor("#FFFFFF")
            # Inactive track for dark theme
            self._disabled_color = QColor("#555555")
        else: # Light theme
            self._thumb_color = QColor("#FFFFFF")
            # Inactive track for light theme
            self._disabled_color = QColor("#CCCCCC")
        
        self.update()
        
    @Property(float)
    def thumb_pos(self):
        return self._thumb_pos
        
    @thumb_pos.setter
    def thumb_pos(self, pos):
        self._thumb_pos = pos
        self.update()
        
    def nextCheckState(self):
        super().nextCheckState()
        start = self._thumb_pos
        end = self.width() - self._margin - self._thumb_radius if self.isChecked() else self._margin + self._thumb_radius
        self._animation.setStartValue(start)
        self._animation.setEndValue(end)
        self._animation.start()
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # 确保初始位置正确（如果没有进行过动画或设置）
        if not self._animation.state() == QPropertyAnimation.State.Running:
            end_pos = self.width() - self._margin - self._thumb_radius if self.isChecked() else self._margin + self._thumb_radius
            if self._thumb_pos != end_pos and not self._animation.state() == QPropertyAnimation.State.Running:
                self._thumb_pos = end_pos

        # Draw track
        track_rect = QRect(0, 0, self.width(), self.height())
        color = self._active_color if self.isChecked() else self._disabled_color
        if not self.isEnabled():
            color = color.lighter(150)
            
        painter.setBrush(QBrush(color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(track_rect, self._track_radius, self._track_radius)
        
        # Draw thumb
        painter.setBrush(QBrush(self._thumb_color))
        thumb_rect = QRect(0, 0, self._thumb_radius * 2, self._thumb_radius * 2)
        thumb_rect.moveCenter(QPoint(int(self._thumb_pos), self.height() // 2))
        painter.drawEllipse(thumb_rect)
        
    def sizeHint(self):
        return QSize(self._base_width, self._base_height)

    def minimumSizeHint(self):
        return self.sizeHint()
