from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                               QComboBox, QToolButton, QScrollArea)
from PySide6.QtCore import Qt, Signal, QTimer, QSize
import numpy as np
import cv2
from src.core.data_model import Session, ImageChannel
from src.gui.histogram_widget import HistogramWidget
from src.gui.icon_manager import get_icon
from src.core.language_manager import LanguageManager, tr

class HistogramPanel(QWidget):
    """
    Panel containing the Channel Selector and Histogram Visualization.
    Placed above the Adjustment/Enhance tabs.
    """
    channel_activated = Signal(int)     # Emitted when channel is selected via ComboBox
    settings_changed = Signal()         # Emitted when histogram markers are dragged (modifies display settings)

    def __init__(self, session: Session, parent=None):
        super().__init__(parent)
        self.session = session
        self.active_channel_index = -1 
        
        # Debounce Timer for Marker Dragging
        self.debounce_timer = QTimer()
        self.debounce_timer.setSingleShot(True)
        self.debounce_timer.setInterval(50) # Fast response for dragging
        self.debounce_timer.timeout.connect(self.emit_settings_changed)

        self.setup_ui()
        LanguageManager.instance().language_changed.connect(self.retranslate_ui)

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)

        # 1. Channel Selector
        h_chan = QHBoxLayout()
        self.lbl_active_channel = QLabel(tr("Active Channel:"))
        h_chan.addWidget(self.lbl_active_channel)
        self.combo_channel = QComboBox()
        self.combo_channel.currentIndexChanged.connect(self.on_channel_combo_changed)
        h_chan.addWidget(self.combo_channel)
        layout.addLayout(h_chan)

        # 2. Histogram Area
        self.histogram = HistogramWidget()
        self.histogram.setMinimumHeight(120) # Allow expansion, but enforce minimum visibility
        self.histogram.setMinimumWidth(150) # Ensure readable width, triggers scroll if panel is narrower
        self.histogram.range_changed.connect(self.on_histogram_range_changed)
        
        self.hist_scroll = QScrollArea()
        self.hist_scroll.setWidgetResizable(True)
        self.hist_scroll.setWidget(self.histogram)
        layout.addWidget(self.hist_scroll)

        # 3. Histogram Controls (Log Scale, Auto)
        h_hist_ctrl = QHBoxLayout()
        h_hist_ctrl.setContentsMargins(0, 0, 0, 0)
        
        self.btn_log_scale = QToolButton()
        self.btn_log_scale.setIcon(get_icon("log", "format-list-unordered"))
        self.btn_log_scale.setCheckable(True)
        self.btn_log_scale.setChecked(True)
        self.btn_log_scale.setText(tr("Log"))
        self.btn_log_scale.setToolTip(tr("Toggle Log Scale"))
        self.btn_log_scale.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.btn_log_scale.setFixedHeight(24)
        self.btn_log_scale.toggled.connect(self.histogram.set_log_scale)
        h_hist_ctrl.addWidget(self.btn_log_scale)
        
        self.btn_auto = QToolButton()
        self.btn_auto.setIcon(get_icon("auto", "view-fullscreen"))
        self.btn_auto.setIconSize(QSize(16, 16))
        self.btn_auto.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.btn_auto.setText(tr("Auto"))
        self.btn_auto.setToolTip(tr("Auto-adjust Min/Max based on 0.1% - 99.9% percentiles"))
        self.btn_auto.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_auto.setFixedHeight(24)
        self.btn_auto.clicked.connect(self.apply_auto_contrast)
        h_hist_ctrl.addWidget(self.btn_auto)
        
        h_hist_ctrl.addStretch()
        layout.addLayout(h_hist_ctrl)

    def retranslate_ui(self):
        self.lbl_active_channel.setText(tr("Active Channel:"))
        self.btn_log_scale.setText(tr("Log"))
        self.btn_log_scale.setToolTip(tr("Toggle Log Scale"))
        self.btn_auto.setText(tr("Auto Contrast (Max)"))
        self.btn_auto.setToolTip(tr("Auto-adjust Min/Max based on 0.1% - 99.9% percentiles"))
        self.refresh_channel_list()

    def refresh_channel_list(self):
        self.combo_channel.blockSignals(True)
        self.combo_channel.clear()
        if not self.session.channels:
            self.combo_channel.addItem(tr("No Channels"))
            self.histogram.set_data(None)
            self.setEnabled(False)
        else:
            for i, ch in enumerate(self.session.channels):
                name = ch.name if ch.name else tr("Channel {0}").format(i+1)
                self.combo_channel.addItem(name, i)
            self.setEnabled(True)
        
        # Restore selection logic
        if 0 <= self.active_channel_index < self.combo_channel.count():
             self.combo_channel.setCurrentIndex(self.active_channel_index)
        else:
             if self.combo_channel.count() > 0:
                 self.active_channel_index = 0
                 self.combo_channel.setCurrentIndex(0)
             else:
                 self.active_channel_index = -1
        
        self.combo_channel.blockSignals(False)
        self.update_from_channel()

    def set_active_channel(self, index: int):
        # Called externally
        self.refresh_channel_list()
        if index < 0 or index >= self.combo_channel.count(): return
        
        self.active_channel_index = index
        self.combo_channel.blockSignals(True)
        self.combo_channel.setCurrentIndex(index)
        self.combo_channel.blockSignals(False)
        self.update_from_channel()

    def on_channel_combo_changed(self, index):
        self.active_channel_index = index
        self.update_from_channel()
        self.channel_activated.emit(index)

    def update_from_channel(self):
        """Updates histogram data and markers from the active channel."""
        ch = self.session.get_channel(self.active_channel_index)
        if not ch:
            self.histogram.set_data(None)
            return
            
        self.calculate_histogram(ch)
        self.update_markers_only()

    def update_markers_only(self):
        """Updates only the markers (Min/Max lines) without re-calculating histogram data."""
        ch = self.session.get_channel(self.active_channel_index)
        if not ch: return
        
        s = ch.display_settings
        self.histogram.blockSignals(True)
        self.histogram.set_markers(s.min_val, s.max_val)
        self.histogram.blockSignals(False)

    def calculate_histogram(self, channel: ImageChannel):
        if not channel:
            self.histogram.set_data(None)
            return
        
        # Use cached data if available for histogram to reflect enhancements
        if hasattr(channel, 'cached_processed_data') and channel.cached_processed_data is not None:
             data = channel.cached_processed_data
        elif channel.raw_data is not None:
             data = channel.raw_data
        else:
             self.histogram.set_data(None)
             return

        effective_max = max(int(data.max()), 255)
        self.histogram.set_range_max(effective_max)
        
        # Downsample for speed if large
        max_dim = 1024
        
        # Handle RGB or Grayscale shapes
        if data.ndim == 2:
            h, w = data.shape
            proc_data = data
        elif data.ndim == 3:
            h, w, c = data.shape
            # Convert to grayscale using Max Projection for scientific consistency
            proc_data = np.max(data[..., :3], axis=2)
        else:
            return

        scale = max_dim / max(h, w)
        if scale < 1.0:
            small_img = cv2.resize(proc_data, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        else:
            small_img = proc_data
            
        hist, _ = np.histogram(small_img, bins=256, range=(0, effective_max))
        self.histogram.set_data(hist, channel.display_settings.color)

    def on_histogram_range_changed(self, min_val, max_val):
        """Called when user drags markers on the histogram."""
        ch = self.session.get_channel(self.active_channel_index)
        if not ch: return
        
        ch.display_settings.min_val = min_val
        ch.display_settings.max_val = max_val
        
        self.debounce_timer.start()

    def emit_settings_changed(self):
        self.settings_changed.emit()

    def apply_auto_contrast(self):
        ch = self.session.get_channel(self.active_channel_index)
        if not ch: return
        data = ch.cached_processed_data if hasattr(ch, 'cached_processed_data') and ch.cached_processed_data is not None else ch.raw_data
        if data is None: return
            
        if data.size > 1000000:
            step = int(data.size / 1000000)
            sample = data.ravel()[::step]
        else:
            sample = data
        try:
            low = np.percentile(sample, 0.1)
            high = np.percentile(sample, 99.9)
        except:
            low = np.min(sample)
            high = np.max(sample)
            
        if high <= low: high = low + 1
        
        ch.display_settings.min_val = float(low)
        ch.display_settings.max_val = float(high)
        
        self.update_markers_only()
        self.settings_changed.emit()
