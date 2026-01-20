from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QDoubleSpinBox, 
                               QGroupBox, QSizePolicy)
from PySide6.QtCore import QSettings
from src.gui.toggle_switch import ToggleSwitch
from src.core.language_manager import tr, LanguageManager
from src.gui.theme_manager import ThemeManager

class PerformanceSettingsWidget(QWidget):
    """
    Widget for performance and memory management settings.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings = QSettings("FluoQuantPro", "AppSettings")
        self.init_ui()
        self.load_settings()
        LanguageManager.instance().language_changed.connect(self.retranslate_ui)

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(15)

        # 1. Memory Management Group
        self.memory_group = QGroupBox(tr("Memory Management"))
        mem_layout = QVBoxLayout(self.memory_group)
        
        # Enable Auto Cleanup
        h_auto = QHBoxLayout()
        self.lbl_auto_cleanup = QLabel(tr("Enable Auto Memory Cleanup"))
        self.chk_auto_cleanup = ToggleSwitch()
        h_auto.addWidget(self.lbl_auto_cleanup)
        h_auto.addStretch()
        h_auto.addWidget(self.chk_auto_cleanup)
        mem_layout.addLayout(h_auto)
        
        self.lbl_auto_info = QLabel(tr("Automatically clears image caches when memory usage is high."))
        self.lbl_auto_info.setWordWrap(True)
        self.lbl_auto_info.setStyleSheet("font-style: italic; color: gray; font-size: 10px;")
        mem_layout.addWidget(self.lbl_auto_info)
        
        # Memory Threshold
        h_thresh = QHBoxLayout()
        self.lbl_threshold = QLabel(tr("Memory Threshold (GB):"))
        h_thresh.addWidget(self.lbl_threshold)
        self.spin_threshold = QDoubleSpinBox()
        self.spin_threshold.setRange(1.0, 128.0)
        self.spin_threshold.setSingleStep(0.5)
        self.spin_threshold.setSuffix(" GB")
        h_thresh.addWidget(self.spin_threshold)
        mem_layout.addLayout(h_thresh)
        
        self.lbl_thresh_info = QLabel(tr("Cleanup will trigger when application memory exceeds this value."))
        self.lbl_thresh_info.setWordWrap(True)
        self.lbl_thresh_info.setStyleSheet("font-style: italic; color: gray; font-size: 10px;")
        mem_layout.addWidget(self.lbl_thresh_info)
        
        # Connect toggle to enable/disable threshold spin
        self.chk_auto_cleanup.toggled.connect(self.spin_threshold.setEnabled)
        
        layout.addWidget(self.memory_group)
        
        # 2. Cache Info (Optional future enhancement)
        # We could add a "Clear Cache Now" button here
        
        layout.addStretch()

    def retranslate_ui(self):
        self.memory_group.setTitle(tr("Memory Management"))
        self.lbl_auto_cleanup.setText(tr("Enable Auto Memory Cleanup"))
        self.lbl_auto_info.setText(tr("Automatically clears image caches when memory usage is high."))
        self.lbl_threshold.setText(tr("Memory Threshold (GB):"))
        self.lbl_thresh_info.setText(tr("Cleanup will trigger when application memory exceeds this value."))

    def load_settings(self):
        # Match keys used in PerformanceMonitor
        enabled = self.settings.value("performance/auto_cleanup", True, type=bool)
        
        # Calculate a safe default threshold if not set (similar to PerformanceMonitor)
        import psutil
        total_mem = psutil.virtual_memory().total
        default_threshold = min(6.0, (total_mem / 1024**3) * 0.75)
        
        threshold = float(self.settings.value("performance/memory_threshold_gb", default_threshold))
        
        self.chk_auto_cleanup.setChecked(enabled)
        self.spin_threshold.setValue(threshold)
        self.spin_threshold.setEnabled(enabled)

    def save_settings(self):
        enabled = self.chk_auto_cleanup.isChecked()
        threshold = self.spin_threshold.value()
        
        self.settings.setValue("performance/auto_cleanup", enabled)
        self.settings.setValue("performance/memory_threshold_gb", threshold)
        
        # Update PerformanceMonitor if it's running
        from PySide6.QtWidgets import QApplication
        for widget in QApplication.topLevelWidgets():
            if hasattr(widget, 'perf_monitor'):
                widget.perf_monitor.set_memory_settings(enabled, threshold)

    def get_current_values(self):
        return {
            'auto_cleanup': self.chk_auto_cleanup.isChecked(),
            'threshold_gb': self.spin_threshold.value()
        }
