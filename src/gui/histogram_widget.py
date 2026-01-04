from PySide6.QtWidgets import QWidget, QMenu, QApplication
from PySide6.QtGui import QPainter, QColor, QBrush, QPen, QPolygonF, QCursor, QAction, QPalette
from PySide6.QtCore import Qt, QPointF, Signal
import numpy as np

class HistogramWidget(QWidget):
    """
    A lightweight widget to draw image histogram and min/max markers.
    Supports draggable markers and log/linear scale toggle.
    """
    range_changed = Signal(float, float) # Emits (min_val, max_val) when markers are dragged
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(100)
        # Allow width to shrink (remove implicit constraints)
        self.setMinimumWidth(0) 
        self.hist_data = None
        self.hist_color = QColor("#888888")
        self.min_val = 0      
        self.max_val = 65535  
        self.data_max_range = 65535 # The logical maximum value of the x-axis (e.g. image max)
        self.bins = 256
        self.hist_norm = None # Initialize to None
        self.log_scale = True # Default to Log scale
        
        # Interaction state
        self.dragging_min = False
        self.dragging_max = False
        self.drag_tolerance = 5 # pixels
        
        # Theme-aware style: Use palette instead of hardcoded white
        self.setAutoFillBackground(True)
        self.setMouseTracking(True) # Enable mouse tracking for hover effects

    def set_range_max(self, range_max):
        """Sets the logical maximum value for the X-axis (e.g., max pixel value)."""
        self.data_max_range = float(range_max) if range_max > 0 else 65535.0
        self.update()

    def set_data(self, hist_data: np.ndarray, color: str = "#888888"):
        """
        Updates the histogram data.
        hist_data: array of length 256 (binned counts).
        """
        self.hist_data = hist_data
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
        if self.hist_data is not None and self.hist_data.max() > 0:
            if self.log_scale:
                # Log Scale: log(1 + x)
                log_data = np.log1p(self.hist_data)
                max_log = log_data.max()
                if max_log > 0:
                    self.hist_norm = log_data / max_log
                else:
                    self.hist_norm = np.zeros_like(log_data)
            else:
                # Linear Scale
                max_val = self.hist_data.max()
                self.hist_norm = self.hist_data.astype(np.float32) / max_val
        else:
            self.hist_norm = None

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
             action_log = QAction("Log Scale", self)
             action_log.setCheckable(True)
             action_log.setChecked(self.log_scale)
             action_log.triggered.connect(lambda c: self.set_log_scale(c))
             menu.addAction(action_log)
             menu.exec(event.globalPosition().toPoint())

    def mouseMoveEvent(self, event):
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

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        palette = QApplication.palette()
        bg_color = palette.color(QPalette.ColorRole.Base)
        text_color = palette.color(QPalette.ColorRole.WindowText)
        
        w = self.width()
        h = self.height()
        
        # Draw Background
        painter.fillRect(0, 0, w, h, bg_color)
        
        if self.hist_norm is None:
            painter.setPen(text_color)
            painter.drawText(self.rect(), Qt.AlignCenter, "No Data")
            return

        # Draw Histogram
        # Map 0-255 bins to 0-w width
        bin_width = w / self.bins
        
        path = QPolygonF()
        path.append(QPointF(0, h)) # Start bottom-left
        
        for i, val in enumerate(self.hist_norm):
            x = i * bin_width
            y = h - (val * h) # Invert y (0 is top)
            path.append(QPointF(x, y))
            path.append(QPointF(x + bin_width, y))
            
        path.append(QPointF(w, h)) # End bottom-right
        
        # Smart visibility adjustment based on background brightness
        fill_color = QColor(self.hist_color)
        is_dark_bg = bg_color.lightness() < 128
        
        if is_dark_bg:
            # On dark background, very dark colors should be lightened
            if fill_color.lightness() < 50:
                fill_color = fill_color.lighter(150)
        else:
            # On light background, very light colors should be darkened
            if fill_color.lightness() > 220:
                fill_color = QColor("#888888")
            
        fill_color.setAlpha(200) # Slightly transparent
        painter.setBrush(QBrush(fill_color))
        
        # Add Outline for visibility
        # Create a darker version of the channel color for the outline
        outline_color = QColor(self.hist_color)
        if outline_color.lightness() > 150:
             outline_color = outline_color.darker(150) # Make it darker
        
        # Fallback if still too light
        if outline_color.lightness() > 200:
            outline_color = QColor("#666666")
            
        pen = QPen(outline_color)
        pen.setWidth(1)
        painter.setPen(pen)
        
        painter.drawPolygon(path)
        
        # Draw Markers (Min/Max)
        # Map 0-data_max_range to 0-w
        # Clamp marker positions to widget width
        x_min = (self.min_val / self.data_max_range) * w
        x_max = (self.max_val / self.data_max_range) * w
        
        # Clamp for display
        x_min = max(0, min(w, x_min))
        x_max = max(0, min(w, x_max))
        
        # Draw active range highlight (Optional: darken outside or highlight inside?)
        # Let's highlight inside with very subtle color or just rely on markers
        
        # Draw Lines (Distinguish Min and Max)
        
        # Min Line
        palette = QApplication.palette()
        is_dark = palette.color(QPalette.ColorRole.Window).lightness() < 128
        
        # Min Line (Cyan-ish)
        min_line_color = QColor("#00FFFF") if is_dark else QColor("#008B8B")
        pen_min = QPen(min_line_color)
        pen_min.setWidth(2)
        pen_min.setStyle(Qt.PenStyle.SolidLine)
        painter.setPen(pen_min)
        painter.drawLine(int(x_min), 0, int(x_min), h)
        
        # Max Line (Orange-ish)
        max_line_color = QColor("#FF4500") if is_dark else QColor("#CC3300")
        pen_max = QPen(max_line_color)
        pen_max.setWidth(2)
        pen_max.setStyle(Qt.PenStyle.SolidLine)
        painter.setPen(pen_max)
        painter.drawLine(int(x_max), 0, int(x_max), h)
        
        # Draw Min/Max Labels
        font = painter.font()
        font.setPointSize(8)
        font.setBold(True)
        painter.setFont(font)
        
        # Min Label
        if is_dark_bg:
            painter.setPen(QColor("#00FFFF")) # Cyan for dark bg
        else:
            painter.setPen(QColor("#008B8B")) # Dark Cyan for light bg
        # Check if near left edge
        if x_min < 25:
            align_flag = Qt.AlignLeft
            pos_x = int(x_min) + 2
        else:
            align_flag = Qt.AlignRight
            pos_x = int(x_min) - 25
        painter.drawText(pos_x, 15, "Min")

        # Max Label
        if is_dark_bg:
            painter.setPen(QColor("#FF7F50")) # Coral for dark bg
        else:
            painter.setPen(QColor("#CC3300")) # Dark Red for light bg
        # Check if near right edge
        if x_max > w - 25:
            align_flag = Qt.AlignRight
            pos_x = int(x_max) - 25
        else:
            align_flag = Qt.AlignLeft
            pos_x = int(x_max) + 2
        painter.drawText(pos_x, 15, "Max")

