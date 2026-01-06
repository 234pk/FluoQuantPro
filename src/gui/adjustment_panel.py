from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                               QSlider, QGroupBox, QDoubleSpinBox, QToolButton, QSizePolicy)
from PySide6.QtCore import Qt, Signal, QTimer, QSize
from src.gui.icon_manager import get_icon
from src.core.data_model import Session
from src.gui.histogram_panel import HistogramPanel
from src.core.commands import AdjustmentCommand
from src.core.language_manager import tr, LanguageManager

class AdjustmentPanel(QWidget):
    """
    Panel for adjusting Brightness, Contrast (Min/Max), and Gamma.
    Includes an embedded HistogramPanel for visualization.
    """
    settings_changed = Signal() # Emitted when any slider moves (debounced)
    channel_activated = Signal(int) # Forward signal from embedded histogram

    def __init__(self, session: Session, parent=None):
        super().__init__(parent)
        self.session = session
        self.active_channel_index = -1 
        self._last_applied_settings = None # Track for undo
        
        # Debounce Timer
        self.debounce_timer = QTimer()
        self.debounce_timer.setSingleShot(True)
        self.debounce_timer.setInterval(100) # 100ms debounce
        self.debounce_timer.timeout.connect(self._apply_display_settings)
        
        # Connect to global session changes (for Undo/Redo support)
        self.session.data_changed.connect(self.update_controls_from_channel)
        
        self.setup_ui()
        LanguageManager.instance().language_changed.connect(self.retranslate_ui)
        
    def setup_ui(self):
        self.setObjectName("card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(10)
        
        # Use a splitter for Histogram vs Controls
        from PySide6.QtWidgets import QSplitter, QApplication
        
        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.splitter.setHandleWidth(4)
        
        # 1. Histogram (Embedded)
        self.histogram_panel = HistogramPanel(self.session)
        # Connect signals
        self.histogram_panel.channel_activated.connect(self.channel_activated)
        self.histogram_panel.settings_changed.connect(self.update_controls_from_channel) # Sync markers -> sliders
        self.histogram_panel.settings_changed.connect(self.settings_changed) # Propagate change
        self.splitter.addWidget(self.histogram_panel)

        # 3. Basic Adjustments
        adjustment_widget = QWidget()
        adjustment_vbox = QVBoxLayout(adjustment_widget)
        adjustment_vbox.setContentsMargins(0, 0, 0, 0)

        self.grp_controls = QGroupBox(tr("Basic Adjustments"))
        vbox = QVBoxLayout()
        
        # Min (Black Point)
        self.container_min, self.slider_min, self.spin_min, self.lbl_min = self.create_fine_control(tr("Min (Black Point)"), 0, 65535, 0, self.on_min_changed)
        vbox.addLayout(self.container_min)
        
        # Max (White Point)
        self.container_max, self.slider_max, self.spin_max, self.lbl_max = self.create_fine_control(tr("Max (White Point)"), 0, 65535, 65535, self.on_max_changed)
        vbox.addLayout(self.container_max)
        
        # Gamma
        self.container_gamma, self.slider_gamma, self.spin_gamma, self.lbl_gamma = self.create_fine_control(tr("Gamma"), 10, 500, 100, self.on_gamma_changed, scale=0.01)
        vbox.addLayout(self.container_gamma)
        
        self.grp_controls.setLayout(vbox)
        adjustment_vbox.addWidget(self.grp_controls)
        
        # Reset Button
        self.btn_reset = QToolButton()
        self.btn_reset.setIcon(get_icon("refresh", "view-refresh"))
        self.btn_reset.setIconSize(QSize(20, 20))
        self.btn_reset.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.btn_reset.setFixedSize(28, 28)
        self.btn_reset.setToolTip(tr("Reset brightness/contrast to default"))
        self.btn_reset.clicked.connect(self.reset_current_channel)
        
        # Style reset button specifically for this panel if needed, but the global style might handle it
        # Let's add a layout to center it or just add it to the vbox
        h_reset = QHBoxLayout()
        h_reset.addWidget(self.btn_reset)
        h_reset.addStretch()
        adjustment_vbox.addLayout(h_reset)
        adjustment_vbox.addStretch()
        
        self.splitter.addWidget(adjustment_widget)
        
        layout.addWidget(self.splitter)
        
        # Initial State
        self.grp_controls.setEnabled(False)

    def retranslate_ui(self):
        self.grp_controls.setTitle(tr("Basic Adjustments"))
        self.lbl_min.setText(tr("Min (Black Point)"))
        self.lbl_max.setText(tr("Max (White Point)"))
        self.lbl_gamma.setText(tr("Gamma"))
        self.btn_reset.setToolTip(tr("Reset brightness/contrast to default"))

    def create_fine_control(self, label_text, min_val, max_val, init_val, callback, scale=1.0):
        layout_container = QVBoxLayout()
        layout_container.setSpacing(2)
        lbl = QLabel(label_text)
        lbl.setProperty("role", "subtitle")
        layout_container.addWidget(lbl)
        
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(min_val, max_val)
        slider.setValue(init_val)
        
        if scale != 1.0:
            spin = QDoubleSpinBox()
            spin.setRange(min_val * scale, max_val * scale)
            spin.setSingleStep(scale)
            spin.setValue(init_val * scale)
            spin.setDecimals(2)
        else:
            spin = QDoubleSpinBox()
            spin.setDecimals(0)
            spin.setRange(min_val, max_val)
            spin.setSingleStep(1)
            spin.setValue(init_val)

        def on_slider_changed(val):
            spin.blockSignals(True)
            spin.setValue(val * scale)
            spin.blockSignals(False)
            callback(val)
        def on_spin_changed(val):
            slider.blockSignals(True)
            slider.setValue(int(val / scale))
            slider.blockSignals(False)
            callback(val)
            
        slider.valueChanged.connect(on_slider_changed)
        spin.valueChanged.connect(on_spin_changed)
        
        h_layout = QHBoxLayout()
        h_layout.addWidget(slider)
        h_layout.addWidget(spin)
        layout_container.addLayout(h_layout)
        
        return layout_container, slider, spin, lbl

    def refresh_channel_list(self):
        # Just update controls, checking if channel exists
        self.update_controls_from_channel()

    def set_active_channel(self, index: int):
        self.active_channel_index = index
        # Also update embedded histogram
        self.histogram_panel.set_active_channel(index)
        self.update_controls_from_channel()

    def update_controls_from_channel(self):
        ch = self.session.get_channel(self.active_channel_index)
        if not ch:
            self.grp_controls.setEnabled(False)
            # Histogram handles its own empty state
            return
            
        self.grp_controls.setEnabled(True)
        s = ch.display_settings
        
        # Determine Max Range for Sliders based on image data depth if possible?
        # For now, 65535 is safe for 16-bit. 
        # But HistogramPanel might calculate 'effective_max'. 
        # Ideally we should get effective_max from somewhere, but hardcoding 65535 is robust for now.
        
        # Block signals
        self.slider_min.blockSignals(True); self.spin_min.blockSignals(True)
        self.slider_max.blockSignals(True); self.spin_max.blockSignals(True)
        self.slider_gamma.blockSignals(True); self.spin_gamma.blockSignals(True)
        
        self.slider_min.setValue(int(s.min_val)); self.spin_min.setValue(s.min_val)
        self.slider_max.setValue(int(s.max_val)); self.spin_max.setValue(s.max_val)
        self.slider_gamma.setValue(int(s.gamma * 100)); self.spin_gamma.setValue(s.gamma)
        
        # Sync last applied for undo tracking
        self._last_applied_settings = {
            'min': s.min_val,
            'max': s.max_val,
            'gamma': s.gamma
        }
        
        self.slider_min.blockSignals(False); self.spin_min.blockSignals(False)
        self.slider_max.blockSignals(False); self.spin_max.blockSignals(False)
        self.slider_gamma.blockSignals(False); self.spin_gamma.blockSignals(False)
        
        # Also ensure histogram markers are synced (if this update came from external selection)
        self.histogram_panel.update_markers_only()

    def _apply_display_settings(self):
        ch = self.session.get_channel(self.active_channel_index)
        if not ch: return
            
        new_settings = {
            'min': self.spin_min.value(),
            'max': self.spin_max.value(),
            'gamma': self.spin_gamma.value()
        }
        
        # Only push if something actually changed
        if self._last_applied_settings and self._last_applied_settings == new_settings:
            return

        # Create and push command
        cmd = AdjustmentCommand(
            self.session, 
            self.active_channel_index, 
            self._last_applied_settings if self._last_applied_settings else new_settings,
            new_settings
        )
        self.session.undo_stack.push(cmd)
        
        # Update local tracking
        self._last_applied_settings = new_settings
        
        # Sync histogram markers immediately
        self.histogram_panel.update_markers_only()
        
        self.settings_changed.emit()

    def on_min_changed(self, val):
        self.debounce_timer.start()
    def on_max_changed(self, val):
        self.debounce_timer.start()
    def on_gamma_changed(self, val):
        self.debounce_timer.start()
        
    def reset_current_channel(self):
        ch = self.session.get_channel(self.active_channel_index)
        if not ch: return
        ch.display_settings.min_val = 0
        ch.display_settings.max_val = 65535
        ch.display_settings.gamma = 1.0
        self.update_controls_from_channel()
        self.settings_changed.emit()
