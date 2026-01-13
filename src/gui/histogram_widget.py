from PySide6.QtWidgets import QWidget, QMenu, QApplication
from PySide6.QtGui import QPainter, QColor, QBrush, QPen, QPolygonF, QCursor, QAction, QPalette, QPainterPath
from PySide6.QtCore import Qt, QPointF, Signal
import numpy as np
from src.core.language_manager import tr

class HistogramWidget(QWidget):
    """
    A lightweight widget to draw image histogram and min/max markers.
    Supports draggable markers and log/linear scale toggle.
    """
    range_changed = Signal(float, float) # Emits (min_val, max_val) when markers are dragged
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(100)
        self.setMinimumWidth(0) 
        palette = QApplication.palette()
        self.hist_color = palette.color(QPalette.ColorRole.Mid)
        self.min_val = 0      
        self.max_val = 65535  
        self.data_max_range = 65535 
        self.bins = 256
        self.hist_norm = None 
        self.enhanced_norm = None 
        self.log_scale = True 
        self.show_markers = True # New flag to toggle visibility of interactive markers
        
        self.dragging_min = False
        self.dragging_max = False
        self.drag_tolerance = 5 
        
        self.setAutoFillBackground(True)
        self.setMouseTracking(True) 

    def set_range_max(self, range_max):
        """Sets the logical maximum value for the X-axis (e.g., max pixel value)."""
        self.data_max_range = float(range_max) if range_max > 0 else 65535.0
        self.update()

    def set_data(self, hist_data: np.ndarray, color: str = "#888888", enhanced_hist: np.ndarray = None):
        """
        Updates the histogram data.
        hist_data: original array of length 256.
        enhanced_hist: optional enhanced array of length 256.
        """
        self.hist_data = hist_data
        self.enhanced_hist = enhanced_hist
        self.hist_color = QColor(color)
        self._update_norm_data()
        self.update()

    def set_log_scale(self, enabled: bool):
        """Toggles between Log and Linear scale."""
        self.log_scale = enabled
        self._update_norm_data()
        self.update()

    def _update_norm_data(self):
        """Recalculates normalized histogram data based on scale mode."""
        # 1. Normalize Original
        if self.hist_data is not None:
            self.hist_norm = self._normalize_array(self.hist_data)
        else:
            self.hist_norm = None
            
        # 2. Normalize Enhanced
        if self.enhanced_hist is not None:
            self.enhanced_norm = self._normalize_array(self.enhanced_hist)
        else:
            self.enhanced_norm = None

    def _normalize_array(self, data: np.ndarray) -> np.ndarray:
        if data is None or data.size == 0:
            return np.zeros(self.bins, dtype=np.float32)
            
        if self.log_scale:
            log_data = np.log1p(data)
            max_v = log_data.max()
            return log_data / max_v if max_v > 0 else np.zeros_like(log_data, dtype=np.float32)
        else:
            max_v = data.max()
            return data.astype(np.float32) / max_v if max_v > 0 else np.zeros_like(data, dtype=np.float32)

    def set_markers(self, min_val, max_val):
        """Updates min/max markers without recalculating histogram."""
        self.min_val = min_val
        self.max_val = max_val
        self.update()

    def _val_to_x(self, val):
        w = self.width()
        return (val / self.data_max_range) * w

    def _x_to_val(self, x):
        w = self.width()
        if w == 0: return 0
        return (x / w) * self.data_max_range

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if not self.show_markers or self.hist_norm is None:
                return
            x = event.position().x()
            w = self.width()
            
            # Calculate VISUAL positions (clamped to widget bounds)
            # This matches paintEvent logic so users can click what they see
            raw_x_min = self._val_to_x(self.min_val)
            x_min = max(0, min(w, raw_x_min))
            
            raw_x_max = self._val_to_x(self.max_val)
            x_max = max(0, min(w, raw_x_max))
            
            # Check if clicking near Max line (Prioritize Max to prevent deadlock if overlapped at 0)
            if abs(x - x_max) <= self.drag_tolerance:
                self.dragging_max = True
            # Check if clicking near Min line
            elif abs(x - x_min) <= self.drag_tolerance:
                self.dragging_min = True
                
        elif event.button() == Qt.RightButton:
             # Context Menu for Log/Linear Scale
             menu = QMenu(self)
             action_log = QAction(tr("Log Scale"), self)
             action_log.setCheckable(True)
             action_log.setChecked(self.log_scale)
             action_log.triggered.connect(lambda c: self.set_log_scale(c))
             menu.addAction(action_log)
             menu.exec(event.globalPosition().toPoint())

    def mouseMoveEvent(self, event):
        if not self.show_markers or self.hist_norm is None:
            return
        x = event.position().x()
        w = self.width()
        
        x_min = self._val_to_x(self.min_val)
        x_max = self._val_to_x(self.max_val)
        
        # Hover cursor feedback
        if abs(x - x_min) <= self.drag_tolerance or abs(x - x_max) <= self.drag_tolerance:
            self.setCursor(Qt.SizeHorCursor)
        else:
            self.setCursor(Qt.ArrowCursor)
            
        if self.dragging_min:
            new_min = self._x_to_val(x)
            # Clamp: 0 <= new_min < max_val
            new_min = max(0, min(new_min, self.max_val - 1))
            self.min_val = new_min
            self.range_changed.emit(self.min_val, self.max_val)
            self.update()
            
        elif self.dragging_max:
            new_max = self._x_to_val(x)
            # Clamp: min_val < new_max <= data_max_range
            new_max = max(self.min_val + 1, min(new_max, self.data_max_range))
            self.max_val = new_max
            self.range_changed.emit(self.min_val, self.max_val)
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragging_min = False
            self.dragging_max = False
            self.setCursor(Qt.ArrowCursor)

    def set_show_markers(self, show: bool):
        self.show_markers = show
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        if w < 10 or h < 10:
            return

        # Background
        painter.fillRect(self.rect(), Qt.GlobalColor.white)
        
        # Optional: Subtle border
        painter.setPen(QPen(QColor(220, 220, 220), 1))
        painter.drawRect(0, 0, w - 1, h - 1)

        if self.hist_norm is None:
            return

        # 1. Draw Original Histogram (Gray Background - Always visible as reference)
        # Use a slightly darker gray for the baseline to be visible on white
        self._draw_hist_path(painter, self.hist_norm, QColor(200, 200, 200, 100), QColor(180, 180, 180, 150))

        # 2. Draw Enhanced Histogram (Colored Overlay)
        if self.enhanced_norm is not None:
            # Use the channel color but make it distinct
            fill_color = QColor(self.hist_color)
            fill_color.setAlpha(100) # Increased transparency (was 160)
            
            # Draw with a stronger outline to make it pop
            outline_color = fill_color.darker(130)
            outline_color.setAlpha(200) # Keep outline relatively visible
            
            self._draw_hist_path(painter, self.enhanced_norm, fill_color, outline_color, line_width=1.5)
        else:
            # Only draw original in color if no enhanced version exists
            fill_color = QColor(self.hist_color)
            fill_color.setAlpha(100)
            outline_color = fill_color.darker(110)
            self._draw_hist_path(painter, self.hist_norm, fill_color, outline_color)

        # 3. Draw Markers (Only if enabled)
        if self.show_markers:
            self._draw_markers(painter, w, h)

    def _draw_hist_path(self, painter, norm_data, fill_color, outline_color, line_width=1):
        if norm_data is None or len(norm_data) == 0:
            return
            
        w = self.width()
        h = self.height()
        
        # Calculate x scale
        num_bins = len(norm_data)
        bin_width = w / num_bins if num_bins > 0 else 0
        
        path = QPainterPath()
        path.moveTo(0, h)

        for i, val in enumerate(norm_data):
            x = i * bin_width
            # Clamp y to [0, h] to prevent drawing outside or NaN issues
            y = h - (float(val) * h)
            y = max(0, min(h, y))
            
            # Use lineTo for a step-like histogram look or smooth look
            # Here we use a direct line to each point for simplicity and speed
            path.lineTo(x, y)
            path.lineTo(x + bin_width, y)

        path.lineTo(w, h)
        path.closeSubpath()

        painter.setBrush(QBrush(fill_color))
        painter.setPen(QPen(outline_color, line_width))
        painter.drawPath(path)

    def _draw_markers(self, painter, w, h):
        # Use a high-contrast color for markers on white background
        marker_color = QColor(60, 60, 60) # Dark gray
        
        x_min = (self.min_val / self.data_max_range) * w
        x_max = (self.max_val / self.data_max_range) * w
        x_min = max(0, min(w, x_min))
        x_max = max(0, min(w, x_max))
        
        # Draw dotted vertical lines for markers
        pen = QPen(marker_color, 1.5, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.drawLine(int(x_min), 0, int(x_min), h)
        painter.drawLine(int(x_max), 0, int(x_max), h)
        
        # Draw Min/Max Labels
        font = painter.font()
        font.setPointSize(8)
        font.setBold(True)
        painter.setFont(font)
        
        painter.setPen(marker_color)
        # Check if near left edge
        if x_min < 25:
            align_flag = Qt.AlignLeft
            pos_x = int(x_min) + 2
        else:
            align_flag = Qt.AlignRight
            pos_x = int(x_min) - 25
        painter.drawText(pos_x, 15, "Min")

        # Max Label
        # Check if near right edge
        if x_max > w - 25:
            align_flag = Qt.AlignRight
            pos_x = int(x_max) - 25
        else:
            align_flag = Qt.AlignLeft
            pos_x = int(x_max) + 2
        painter.drawText(pos_x, 15, "Max")

