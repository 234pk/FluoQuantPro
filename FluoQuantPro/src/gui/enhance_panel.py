from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                               QToolButton, 
                               QInputDialog, QMessageBox, QScrollArea, QCheckBox, QSizePolicy,
                               QApplication, QGridLayout)
from PySide6.QtCore import Qt, Signal, QTimer, QSize
from PySide6.QtGui import QIcon
from src.core.data_model import Session
from src.core.enhance import EnhanceProcessor
from src.gui.histogram_panel import HistogramPanel
from src.gui.icon_manager import get_icon
from src.core.commands import EnhanceCommand
from src.core.language_manager import tr, LanguageManager

class PercentageControlWidget(QWidget):
    """
    Scientific Percentage Control Widget.
    Layout:
    [Parameter Name]    [Current %] (Editable)
    [-10] [-5] [-1] [+1] [+5] [+10]
    [Auto]
    """
    value_changed = Signal(float) # Emits new percentage (-1.0 to 1.0)
    
    def __init__(self, name, parent=None, min_val=-1.0, max_val=1.0, auto_val=0.0):
        super().__init__(parent)
        self.param_name = name
        self.min_val = min_val
        self.max_val = max_val
        self.auto_val = auto_val
        self.current_percent = 0.0 # Default to 0 initially
        self.setup_ui()
        LanguageManager.instance().language_changed.connect(self.retranslate_ui)
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 5, 0, 5)
        layout.setSpacing(5)
        
        # Header: Name and Value
        h_header = QHBoxLayout()
        self.lbl_name = QLabel(tr(self.param_name))
        self.lbl_name.setProperty("role", "subtitle")
        h_header.addWidget(self.lbl_name)
        
        h_header.addStretch()
        
        self.lbl_value = QLabel("0%")
        self.lbl_value.setProperty("role", "accent")
        self.lbl_value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.lbl_value.setFixedWidth(60)
        
        # Make double-clickable for input? Implement event filter or custom label
        self.lbl_value.mouseDoubleClickEvent = self.on_value_double_click
        h_header.addWidget(self.lbl_value)
        
        layout.addLayout(h_header)
        
        # Buttons Grid for compactness
        # Row 0: -10, -5, -1
        # Row 1: +1, +5, +10
        # Column 3 (spanning 2 rows): Max
        
        grid_btns = QGridLayout()
        grid_btns.setSpacing(4)
        grid_btns.setContentsMargins(0, 0, 0, 0)
        
        steps = [-10, -5, -1, 1, 5, 10]
        for i, step in enumerate(steps):
            btn = QToolButton()
            btn.setText(f"{step:+d}")
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            btn.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
            btn.setFixedSize(28, 28)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, s=step: self.adjust_value(s))
            
            # Layout Logic: 
            # i=0,1,2 -> row 0, col 0,1,2
            # i=3,4,5 -> row 1, col 0,1,2
            row = 0 if i < 3 else 1
            col = i if i < 3 else (i - 3)
            grid_btns.addWidget(btn, row, col)
            
        # Max Button integrated into grid
        self.btn_auto = QToolButton()
        self.btn_auto.setIcon(get_icon("auto"))
        self.btn_auto.setIconSize(QSize(20, 20))
        self.btn_auto.setFixedSize(28, 60) # Spans 2 rows (28*2 + 4 spacing)
        self.btn_auto.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.btn_auto.setToolTip(tr("Set to Recommended Maximum Value"))
        self.btn_auto.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_auto.setProperty("role", "accent")
        self.btn_auto.clicked.connect(self.reset_to_auto)
        
        # Add to row 0, col 3, span 2 rows
        grid_btns.addWidget(self.btn_auto, 0, 3, 2, 1)
        
        layout.addLayout(grid_btns)
        
        # Focus policy for keyboard
        self.setFocusPolicy(Qt.StrongFocus)

    def retranslate_ui(self):
        self.lbl_name.setText(tr(self.param_name))
        self.btn_auto.setToolTip(tr("Set to Recommended Maximum Value"))

    def adjust_value(self, step_percent):
        """Step is integer percentage (e.g. +5, -10)."""
        new_val = self.current_percent + (step_percent / 100.0)
        self.set_value(new_val)
        
    def set_value(self, val, silent=False):
        self.current_percent = max(self.min_val, min(self.max_val, val))
        self.update_display()
        if not silent:
            self.value_changed.emit(self.current_percent)
        
    def reset_to_auto(self):
        self.set_value(self.auto_val)
        
    def update_display(self):
        pct = int(self.current_percent * 100)
        
        # Special display for OFF state (0% for Additive, or explicit -100% for others)
        # Actually, if we use 0% = OFF, then we don't need special "OFF" text unless we want to emphasize it.
        # But if we use range 0 to 200, 0 is OFF.
        
        self.lbl_value.setText(f"{pct}%") # Removed + sign to allow 0-200
        if self.min_val < 0:
             self.lbl_value.setText(f"{pct:+d}%") # Use sign for bipolar controls
        
        # Use role properties instead of hardcoded styles
        abs_pct = abs(pct)
        if abs_pct > 150:
            self.lbl_value.setProperty("role", "error")
        elif abs_pct > 100:
            self.lbl_value.setProperty("role", "warning")
        elif pct == 0 and self.min_val >= 0:
            self.lbl_value.setProperty("role", "status")
        else:
            self.lbl_value.setProperty("role", "accent")
            
        # Refresh style
        self.lbl_value.style().unpolish(self.lbl_value)
        self.lbl_value.style().polish(self.lbl_value)
        
    def on_value_double_click(self, event):
        val, ok = QInputDialog.getInt(self, tr("Set {0} %").format(tr(self.param_name)), 
                                      tr("Percentage ({0} to {1}):").format(int(self.min_val*100), int(self.max_val*100)), 
                                      int(self.current_percent * 100), int(self.min_val*100), int(self.max_val*100), 1)
        if ok:
            self.set_value(val / 100.0)

    def set_compact_mode(self, is_compact, is_tiny):
        """Toggle UI elements based on width."""
        # 1. Header Visibility
        self.lbl_name.setVisible(not is_tiny)
        
        # 2. Grid Buttons Visibility
        # Find all buttons that ARE NOT the auto button
        for i in range(self.layout().count()):
            item = self.layout().itemAt(i)
            if item.layout() and isinstance(item.layout(), QGridLayout):
                grid = item.layout()
                for j in range(grid.count()):
                    w = grid.itemAt(j).widget()
                    if w and w != self.btn_auto:
                        w.setVisible(not is_compact)
                
                # If compact, make auto button smaller to fit
                if is_compact:
                    self.btn_auto.setFixedSize(28, 28)
                else:
                    self.btn_auto.setFixedSize(28, 60)

    # Keyboard Controls
    def keyPressEvent(self, event):
        step = 0
        if event.key() == Qt.Key_Up:
            step = 1
        elif event.key() == Qt.Key_Down:
            step = -1
            
        if step != 0:
            modifiers = event.modifiers()
            if modifiers & Qt.ControlModifier:
                step *= 10
            elif modifiers & Qt.ShiftModifier:
                step *= 5
            self.adjust_value(step)
        else:
            super().keyPressEvent(event)

class EnhancePanel(QWidget):
    """
    Scientific Image Enhancement Panel.
    Uses percentage-based controls mapped to algorithms.
    """
    settings_changed = Signal()
    channel_activated = Signal(int)
    
    def __init__(self, session: Session, parent=None):
        super().__init__(parent)
        self.session = session
        self.active_channel_index = -1
        self.parameter_lock = False
        self._last_applied_params = {} # Track for undo
        self._last_applied_percents = {} # Track for undo
        self.auto_params_cache = {} # Cache per channel or global if locked?
                                    # If locked, we use ONE global auto_params set.
        self.locked_auto_params = None
        
        # Debounce
        self.debounce_timer = QTimer()
        self.debounce_timer.setSingleShot(True)
        self.debounce_timer.setInterval(300) # 300ms debounce to prevent lag during dragging
        self.debounce_timer.timeout.connect(self.emit_settings_changed)
        
        # Connect to global session changes (for Undo/Redo support)
        self.session.data_changed.connect(self.update_controls_from_channel)
        
        self.setup_ui()
        LanguageManager.instance().language_changed.connect(self.retranslate_ui)
        
    def setup_ui(self):
        self.setObjectName("card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(10)
        
        # Histogram
        self.histogram_panel = HistogramPanel(self.session)
        self.histogram_panel.channel_activated.connect(self.channel_activated)
        self.histogram_panel.settings_changed.connect(self.settings_changed)
        layout.addWidget(self.histogram_panel)
        
        self.chk_lock = QCheckBox(tr("Lock enhancement parameters for all images (freeze auto-calculation)"))
        self.chk_lock.setToolTip(tr("Lock enhancement parameters for all images (freeze auto-calculation)"))
        self.chk_lock.toggled.connect(self.on_lock_toggled)
        layout.addWidget(self.chk_lock)
        
        # Controls Area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        
        content = QWidget()
        vbox = QVBoxLayout(content)
        vbox.setSpacing(15)
        
        # 1. Signal Stretch -> 亮度范围
        # Range: 0% (OFF) to 200% (Strong). Auto: 100%
        self.ctrl_stretch = PercentageControlWidget("Signal Range", min_val=0.0, max_val=2.0, auto_val=1.0)
        self.ctrl_stretch.value_changed.connect(self.on_param_changed)
        vbox.addWidget(self.ctrl_stretch)
        
        # 2. Background Suppression -> 背景清除
        # Range: 0% (OFF) to 200% (Strong). Auto: 100%
        # NOTE: Default MUST be 0.0 to prevent heavy background processing on load.
        self.ctrl_bg = PercentageControlWidget("Background Suppression", min_val=0.0, max_val=2.0, auto_val=1.0)
        self.ctrl_bg.set_value(0.0, silent=True) # Explicitly ensure OFF by default
        self.ctrl_bg.value_changed.connect(self.on_param_changed)
        vbox.addWidget(self.ctrl_bg)
        
        # 3. Local Contrast -> 结构突出
        # Range: 0% (OFF) to 200% (Strong). Auto: 100%
        self.ctrl_contrast = PercentageControlWidget("Local Contrast", min_val=0.0, max_val=2.0, auto_val=1.0)
        self.ctrl_contrast.value_changed.connect(self.on_param_changed)
        vbox.addWidget(self.ctrl_contrast)
        
        # 4. Noise Smoothing -> 噪声平滑
        # Range: 0% (OFF) to 200% (Strong). Auto: 100%
        self.ctrl_noise = PercentageControlWidget("Noise Smoothing", min_val=0.0, max_val=2.0, auto_val=1.0)
        self.ctrl_noise.value_changed.connect(self.on_param_changed)
        vbox.addWidget(self.ctrl_noise)
        
        # 5. Display Gamma -> 显示亮度
        # Range: -100% (Dark) to +100% (Bright). Auto: 0% (Neutral)
        self.ctrl_gamma = PercentageControlWidget("Display Gamma", min_val=-1.0, max_val=1.0, auto_val=0.0)
        self.ctrl_gamma.value_changed.connect(self.on_param_changed)
        vbox.addWidget(self.ctrl_gamma)
        
        # Export Button
        self.btn_export = QToolButton()
        self.btn_export.setIcon(get_icon("export_params", "document-save"))
        self.btn_export.setIconSize(QSize(20, 20))
        self.btn_export.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.btn_export.setToolTip(tr("Apply current enhancement parameters"))
        self.btn_export.setFixedSize(28, 28)
        self.btn_export.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_export.clicked.connect(self.export_params)
        
        h_export = QHBoxLayout()
        h_export.addWidget(self.btn_export)
        h_export.addStretch()
        vbox.addLayout(h_export)
        
        vbox.addStretch()
        # scroll.setWidget(content) # Move this to the end to ensure content is fully initialized? No, setWidget is fine.
        layout.addWidget(scroll)
        
        # Must set the widget AFTER layout is done?
        scroll.setWidget(content)

    def resizeEvent(self, event):
        width = self.width()
        is_compact = width < 120
        is_tiny = width < 80
        
        # 1. 直方图面板
        if hasattr(self, 'histogram_panel'):
            self.histogram_panel.setVisible(width > 100)
            
        # 2. 锁定复选框文字优化
        if hasattr(self, 'chk_lock'):
            self.chk_lock.setText("" if is_compact else tr("Lock enhancement parameters for all images (freeze auto-calculation)"))
            
        # 3. 遍历子控件分发尺寸变化
        for i in range(self.layout().count()):
            item = self.layout().itemAt(i)
            if item.widget() and isinstance(item.widget(), QScrollArea):
                scroll = item.widget()
                content = scroll.widget()
                if content:
                    for child in content.findChildren(PercentageControlWidget):
                        child.set_compact_mode(is_compact, is_tiny)

        super().resizeEvent(event)

    def retranslate_ui(self):
        self.chk_lock.setText(tr("Lock enhancement parameters for all images (freeze auto-calculation)"))
        self.chk_lock.setToolTip(tr("Lock enhancement parameters for all images (freeze auto-calculation)"))
        self.btn_export.setToolTip(tr("Apply current enhancement parameters"))
        
    def set_active_channel(self, index: int):
        self.active_channel_index = index
        self.histogram_panel.set_active_channel(index)
        
        # If panel is visible, update controls immediately to reflect the new channel's settings
        if self.isVisible():
            self.update_controls_from_channel()
        
    def on_panel_shown(self):
        """Called by MainWindow when this tab is selected."""
        # Only update if we haven't already initialized this channel
        # or if we need to refresh.
        # But set_active_channel is called first.
        # If we just switch tabs, we want to update controls.
        self.update_controls_from_channel()

    def showEvent(self, event):
        """Trigger update if pending when shown."""
        super().showEvent(event)
        # Avoid double update if on_panel_shown was called
        # Check visibility logic is handled by parent TabWidget mostly
        pass
        
    def update_controls_from_channel(self):
        ch = self.session.get_channel(self.active_channel_index)
        if not ch: return
        
        # Initialize auto params if needed
        # Logic: 
        # If Locked: use locked_auto_params (if exists).
        # If Not Locked: Estimate new auto params for this image.
        
        # Optimization: Only estimate auto params if we are actually going to use them
        # or if the user opens this panel.
        # But we need 'auto_p' to calculate the raw params below.
        
        if self.parameter_lock and self.locked_auto_params:
            auto_p = self.locked_auto_params
        else:
            # Estimate
            # Optimization: Use downsampled data inside estimate_auto_params (already implemented)
            if ch.raw_data is not None:
                auto_p = EnhanceProcessor.estimate_auto_params(ch.raw_data)
            else:
                auto_p = {}
                
            if self.parameter_lock and self.locked_auto_params is None:
                self.locked_auto_params = auto_p # First image sets the lock
                
        # Store auto params in channel for processing usage?
        # Actually, channel.display_settings should store the RESULTING raw params.
        # But UI state needs the Percentages.
        # Where do we store percentages? In display_settings.enhance_percents
        
        if not hasattr(ch.display_settings, 'enhance_percents'):
            ch.display_settings.enhance_percents = {
                'stretch': 0.0, # Default OFF
                'bg': 0.0, # Default OFF
                'contrast': 0.0, # Default OFF
                'noise': 0.0, # Default OFF
                'gamma': 0.0 # Default Neutral
            }
            
        # Temporarily store auto_p in display_settings to be used by calculate_raw_params
        ch.display_settings.auto_params = auto_p
        
        # Update UI
        p = ch.display_settings.enhance_percents
        self.ctrl_stretch.blockSignals(True)
        self.ctrl_stretch.set_value(p.get('stretch', 0.0), silent=True)
        self.ctrl_stretch.blockSignals(False)
        
        self.ctrl_bg.blockSignals(True)
        self.ctrl_bg.set_value(p.get('bg', 0.0), silent=True)
        self.ctrl_bg.blockSignals(False)
        
        self.ctrl_contrast.blockSignals(True)
        self.ctrl_contrast.set_value(p.get('contrast', 0.0), silent=True)
        self.ctrl_contrast.blockSignals(False)
        
        self.ctrl_noise.blockSignals(True)
        self.ctrl_noise.set_value(p.get('noise', 0.0), silent=True)
        self.ctrl_noise.blockSignals(False)
        
        self.ctrl_gamma.blockSignals(True)
        self.ctrl_gamma.set_value(p.get('gamma', 0.0), silent=True)
        self.ctrl_gamma.blockSignals(False)
        
        # Sync last applied for undo tracking
        self._last_applied_percents = p.copy()
        self._last_applied_params = ch.display_settings.enhance_params.copy()
        
        # Trigger calculation (only once)
        # OPTIMIZATION: Do NOT trigger calculation here if values are all zero (default).
        # Just update the internal state without triggering a re-render.
        # This prevents "Pipeline Total" log on initial load.
        
        # Check if current params are different from defaults (all 0.0)
        # We need to check if 'enhance_percents' implies any active enhancement.
        # Gamma 0.0 is neutral. Others 0.0 are OFF.
        has_any_active = any(abs(v) > 0.001 for k, v in p.items()) 
        
        if has_any_active:
            # If there are active params, trigger a calculation
            self.on_param_changed()
        else:
            # Just ensure display_settings are clean but don't fire signals
            # CRITICAL: Even if silent=True, we must ensure we don't accidentally set 'enhance_params' 
            # to something that triggers processing in Renderer if it's supposed to be OFF.
            self.calculate_and_apply_params(silent=True)

    def on_lock_toggled(self, checked):
        self.parameter_lock = checked
        if checked:
            # Lock current auto params
            ch = self.session.get_channel(self.active_channel_index)
            if ch and hasattr(ch.display_settings, 'auto_params'):
                self.locked_auto_params = ch.display_settings.auto_params
        else:
            self.locked_auto_params = None
            # Re-estimate for current image?
            self.update_controls_from_channel()

    def on_param_changed(self, val=None):
        self.calculate_and_apply_params()
        self.debounce_timer.start()
        
    def calculate_and_apply_params(self, silent=False):
        ch = self.session.get_channel(self.active_channel_index)
        if not ch: return
        
        # Get percentages
        pcts = {
            'stretch': self.ctrl_stretch.current_percent,
            'bg': self.ctrl_bg.current_percent,
            'contrast': self.ctrl_contrast.current_percent,
            'noise': self.ctrl_noise.current_percent,
            'gamma': self.ctrl_gamma.current_percent
        }
        
        # Save percentages
        ch.display_settings.enhance_percents = pcts
        
        # Get Auto Params
        if not hasattr(ch.display_settings, 'auto_params'):
             # Lazy init if missing (e.g. newly loaded image while panel is active)
             if ch.raw_data is not None:
                 ch.display_settings.auto_params = EnhanceProcessor.estimate_auto_params(ch.raw_data)
             else:
                 ch.display_settings.auto_params = {}
                 
        auto = ch.display_settings.auto_params
        if not auto: return
        
        # Mapping Logic
        # 1. Signal Stretch (Percentile Clip)
        # 0% -> OFF. 100% -> Auto (2.0%). 200% -> Strong (4.0%)
        # Formula: auto * percent
        clip_p = auto['stretch_clip'] * pcts['stretch']
        clip_p = max(0.0, clip_p)
        
        # 2. Background Suppression (Top-Hat Strength)
        # 0% -> OFF. 100% -> Standard (1.0).
        # Formula: percent
        bg_strength = pcts['bg']
        # Lower threshold to allow subtle effects (e.g. 1%)
        bg_enabled = (bg_strength > 0.001)
        # Kernel size is fixed from Auto (User: Radius estimated)
        k_size = int(auto['bg_kernel'])
            
        # 3. Local Contrast (Clip Limit)
        # 0% -> OFF. 100% -> Standard (1.5).
        # Formula: auto * (percent^2) for finer control at low levels
        # User Feedback: 1% was too strong with linear mapping.
        c_limit = auto['contrast_clip'] * (pcts['contrast'] ** 2)
        # Lower threshold to allow subtle effects
        contrast_enabled = (c_limit > 0.001)
        
        # 4. Noise Smoothing (Sigma)
        # 0% -> OFF. 100% -> Auto.
        # Formula: auto * percent
        sigma = auto['noise_sigma'] * pcts['noise']
        # Lower threshold to allow subtle effects
        noise_enabled = (sigma > 0.01)
            
        # 5. Gamma
        # -100% -> Dark. 0% -> Neutral. +100% -> Bright.
        # Formula: 1.0 / (1.0 + pct)
        # Map: gamma = 1.0 / (1.0 + pct * 0.8)
        gamma_val = 1.0 / (1.0 + pcts['gamma'] * 0.8) # Sens 0.8
        gamma_enabled = abs(gamma_val - 1.0) > 0.001
        
        # Build Raw Params
        raw_p = {
            'stretch_enabled': (clip_p > 0.001),
            'stretch_clip': clip_p,
            
            'bg_enabled': bg_enabled,
            'bg_kernel': k_size,
            'bg_strength': bg_strength,
            
            'contrast_enabled': contrast_enabled,
            'contrast_clip': c_limit,
            'contrast_tile': int(auto.get('contrast_tile', 8)),
            
            'noise_enabled': noise_enabled,
            'noise_sigma': sigma,
            
            'gamma_enabled': gamma_enabled,
            'gamma': gamma_val,
            'median_enabled': False # Explicitly disable median if not used
        }
        
        # Apply
        ch.display_settings.enhance_params = raw_p
        
        if not silent:
            self.emit_settings_changed()
        
    def emit_settings_changed(self):
        ch = self.session.get_channel(self.active_channel_index)
        if not ch: return
        
        new_percents = ch.display_settings.enhance_percents
        new_params = ch.display_settings.enhance_params
        
        # Only push if something changed
        if self._last_applied_percents == new_percents:
            return
            
        # Create and push command
        cmd = EnhanceCommand(
            self.session,
            self.active_channel_index,
            self._last_applied_params,
            new_params,
            self._last_applied_percents,
            new_percents
        )
        self.session.undo_stack.push(cmd)
        
        # Update local tracking
        self._last_applied_params = new_params.copy()
        self._last_applied_percents = new_percents.copy()
        
        self.settings_changed.emit()
        self.histogram_panel.update_from_channel()

    def export_params(self):
        ch = self.session.get_channel(self.active_channel_index)
        if not ch: return
        p = ch.display_settings.enhance_percents
        text = (f"荧光增强参数 (Fluorescence Enhancement Parameters):\n"
                f"--------------------------------\n"
                f"亮度范围 (Signal Range): {int(p['stretch']*100):+d}%\n"
                f"背景清除 (Background Suppression): {int(p['bg']*100):+d}%\n"
                f"结构突出 (Structure Visibility): {int(p['contrast']*100):+d}%\n"
                f"噪声平滑 (Noise Smoothing): {int(p['noise']*100):+d}%\n"
                f"显示亮度 (Display Gamma): {int(p['gamma']*100):+d}%\n"
                f"--------------------------------\n"
                f"说明: 0% 代表算法自动计算的最佳基准值。")
        
        QMessageBox.information(self, "导出参数", text)
