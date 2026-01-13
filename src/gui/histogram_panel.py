from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                               QComboBox, QToolButton, QScrollArea, QSizePolicy)
from PySide6.QtCore import Qt, Signal, QTimer, QSize
import numpy as np
import cv2
from src.core.data_model import Session, ImageChannel
from src.core.image_loader import ImageLoader
from src.gui.histogram_widget import HistogramWidget
from src.gui.icon_manager import get_icon
from src.core.language_manager import LanguageManager, tr

class HistogramPanel(QWidget):
    """
    Panel containing the Channel Selector and Histogram Visualization.
    Placed above the Adjustment/Enhance tabs.
    """
    channel_activated = Signal(int)     
    settings_changed = Signal()         

    def __init__(self, session: Session, parent=None, mode="adjustment"):
        super().__init__(parent)
        self.session = session
        self.active_channel_index = -1
        self.mode = mode # "adjustment" or "enhance"
        
        self.setup_ui()
        
        from src.gui.theme_manager import ThemeManager
        ThemeManager.instance().theme_changed.connect(self.refresh_icons)
        
        # Configure based on mode
        if self.mode == "enhance":
            self.histogram.set_show_markers(False)
            self.btn_auto.setVisible(False)
            self.lbl_hint.setText(tr("How to read: Gray is raw data; Colored is enhanced. Right shift = brighter; wider span = higher contrast; lower left peak = background removed."))
        else:
            self.lbl_hint.setText(tr("Tip: Drag markers to adjust display brightness/contrast range."))
        
        self.debounce_timer = QTimer()
        self.debounce_timer.setSingleShot(True)
        self.debounce_timer.setInterval(100)
        self.debounce_timer.timeout.connect(self.emit_settings_changed)

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
        self.histogram = HistogramWidget(self)
        self.histogram.setMinimumHeight(120) 
        self.histogram.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.histogram.range_changed.connect(self.on_histogram_range_changed)
        
        self.hist_scroll = QScrollArea(self)
        self.hist_scroll.setWidgetResizable(True)
        self.hist_scroll.setFrameShape(QScrollArea.NoFrame) # Clean look
        self.hist_scroll.setWidget(self.histogram)
        self.hist_scroll.setMinimumHeight(130) # Fixed minimum height for the scroll container
        layout.addWidget(self.hist_scroll)

        # 3. Histogram Controls (Log Scale, Auto)
        h_hist_ctrl = QHBoxLayout()
        h_hist_ctrl.setContentsMargins(0, 0, 0, 0)
        
        self.btn_log_scale = QToolButton()
        self.btn_log_scale.setIcon(get_icon("log", "format-list-unordered"))
        self.btn_log_scale.setCheckable(True)
        self.btn_log_scale.setChecked(True)
        self.btn_log_scale.setToolTip(tr("Toggle Log Scale"))
        self.btn_log_scale.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.btn_log_scale.setIconSize(QSize(20, 20))
        self.btn_log_scale.setFixedSize(28, 28)
        self.btn_log_scale.toggled.connect(self.histogram.set_log_scale)
        h_hist_ctrl.addWidget(self.btn_log_scale)
        
        self.btn_auto = QToolButton()
        self.btn_auto.setIcon(get_icon("auto", "view-fullscreen"))
        self.btn_auto.setIconSize(QSize(20, 20))
        self.btn_auto.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.btn_auto.setFixedSize(28, 28)
        self.btn_auto.setToolTip(tr("Auto-adjust Min/Max based on 0.1% - 99.9% percentiles"))
        self.btn_auto.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_auto.clicked.connect(self.apply_auto_contrast)
        h_hist_ctrl.addWidget(self.btn_auto)
        
        h_hist_ctrl.addStretch()
        layout.addLayout(h_hist_ctrl)

        # 4. Hint Label (Conditional)
        self.lbl_hint = QLabel()
        self.lbl_hint.setObjectName("lbl_hint")
        self.lbl_hint.setWordWrap(True)
        self.lbl_hint.setStyleSheet("font-size: 10px; font-style: italic; opacity: 0.7;")
        layout.addWidget(self.lbl_hint)

    def retranslate_ui(self):
        """Update UI texts on language change."""
        self.lbl_active_channel.setText(tr("Active Channel:"))
        self.btn_log_scale.setToolTip(tr("Toggle Log Scale"))
        self.btn_auto.setToolTip(tr("Auto-adjust Min/Max based on 0.1% - 99.9% percentiles"))
        
        if self.mode == "enhance":
            self.lbl_hint.setText(tr("How to read: Gray is raw data; Colored is enhanced. Right shift = brighter; wider span = higher contrast; lower left peak = background removed."))
        else:
            self.lbl_hint.setText(tr("Tip: Drag markers to adjust display brightness/contrast range."))

    def refresh_icons(self):
        """Refresh icons for the panel."""
        if hasattr(self, 'btn_log_scale'):
            self.btn_log_scale.setIcon(get_icon("log", "format-list-unordered"))
        if hasattr(self, 'btn_auto'):
            self.btn_auto.setIcon(get_icon("auto", "view-fullscreen"))
            
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

    def update_from_channel(self, enhanced_data: np.ndarray = None):
        """Updates histogram data and markers from the active channel."""
        ch = self.session.get_channel(self.active_channel_index)
        if not ch:
            self.histogram.set_data(None)
            return
            
        self.calculate_histogram(ch, enhanced_data)
        self.update_markers_only()

    def update_markers_only(self):
        """Updates only the markers (Min/Max lines) without re-calculating histogram data."""
        ch = self.session.get_channel(self.active_channel_index)
        if not ch: return
        
        s = ch.display_settings
        self.histogram.blockSignals(True)
        self.histogram.set_markers(s.min_val, s.max_val)
        self.histogram.blockSignals(False)

    def calculate_histogram(self, channel: ImageChannel, enhanced_data: np.ndarray = None):
        if not channel or channel.raw_data is None:
            self.histogram.set_data(None)
            return
        
        raw_data = channel.raw_data
        effective_max = max(int(raw_data.max()), 255)
        self.histogram.set_range_max(effective_max)
        
        # 1. Process Raw Data for Histogram (Use mapping-aware extraction)
        raw_hist = self._get_hist_for_data(raw_data, effective_max, channel_name=channel.name)
        
        # 2. Process Enhanced Data if provided
        enhanced_hist = None
        if enhanced_data is not None:
            enhanced_hist = self._get_hist_for_data(enhanced_data, effective_max, channel_name=channel.name)
            
        self.histogram.set_data(raw_hist, channel.display_settings.color, enhanced_hist)

    def _get_hist_for_data(self, data: np.ndarray, effective_max: int, channel_name: str = None) -> np.ndarray:
        # Downsample for speed
        max_dim = 1024
        
        # Use ImageLoader to extract the correct channel data for histogram calculation
        if data.ndim == 3:
            proc_data = ImageLoader.extract_channel_data(data, channel_name)
            # If still 3D (unknown channel fallback), use Max Projection
            if proc_data.ndim == 3:
                proc_data = np.max(proc_data[..., :3], axis=2)
        else:
            proc_data = data

        if proc_data is None:
            return None

        h, w = proc_data.shape[:2]
        scale = max_dim / max(h, w)
        if scale < 1.0:
            small_img = cv2.resize(proc_data, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        else:
            small_img = proc_data
            
        hist, _ = np.histogram(small_img, bins=256, range=(0, effective_max))
        return hist

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
