from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QSpinBox, 
                               QDialogButtonBox, QWidget)
from src.gui.toggle_switch import ToggleSwitch
from src.gui.theme_manager import ThemeManager
from src.core.language_manager import tr, LanguageManager
from PySide6.QtCore import Qt, QSettings

class AutoSaveSettingsWidget(QWidget):
    """
    Widget for Auto Save settings.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings = QSettings("FluoQuantPro", "AppSettings")
        self.init_ui()
        self.load_settings()
        LanguageManager.instance().language_changed.connect(self.retranslate_ui)

    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # Enable Auto Save
        self.row_enable = QHBoxLayout()
        self.lbl_enable = QLabel(tr("Enable Auto Save"))
        self.chk_enable = ToggleSwitch()
        self.row_enable.addWidget(self.lbl_enable)
        self.row_enable.addStretch()
        self.row_enable.addWidget(self.chk_enable)
        layout.addLayout(self.row_enable)
        
        # Interval
        h_layout = QHBoxLayout()
        self.lbl_interval = QLabel(tr("Interval (minutes):"))
        h_layout.addWidget(self.lbl_interval)
        self.spin_interval = QSpinBox()
        self.spin_interval.setRange(1, 60)
        h_layout.addWidget(self.spin_interval)
        layout.addLayout(h_layout)
        
        # Logic: Disable spin if checkbox unchecked
        self.chk_enable.toggled.connect(self.spin_interval.setEnabled)
        
        layout.addStretch()

    def retranslate_ui(self):
        self.lbl_enable.setText(tr("Enable Auto Save"))
        self.lbl_interval.setText(tr("Interval (minutes):"))

    def load_settings(self):
        enabled = self.settings.value("auto_save_enabled", True, type=bool)
        interval = self.settings.value("auto_save_interval", 3, type=int)
        
        self.chk_enable.setChecked(enabled)
        self.spin_interval.setValue(interval)
        self.spin_interval.setEnabled(enabled)

    def save_settings(self):
        self.settings.setValue("auto_save_enabled", self.chk_enable.isChecked())
        self.settings.setValue("auto_save_interval", self.spin_interval.value())

    def get_current_values(self):
        return {
            'enabled': self.chk_enable.isChecked(),
            'interval': self.spin_interval.value()
        }


class AutoSaveSettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Auto Save Settings"))
        self.setFixedSize(350, 180)
        
        layout = QVBoxLayout(self)
        self.widget = AutoSaveSettingsWidget(self)
        layout.addWidget(self.widget)
        
        # Buttons
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.save_and_accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        
        ThemeManager.instance().apply_theme(self)
        LanguageManager.instance().language_changed.connect(self.retranslate_ui)

    def retranslate_ui(self):
        self.setWindowTitle(tr("Auto Save Settings"))
        self.buttons.button(QDialogButtonBox.Ok).setText(tr("OK"))
        self.buttons.button(QDialogButtonBox.Cancel).setText(tr("Cancel"))
        
    def save_and_accept(self):
        self.widget.save_settings()
        self.accept()
        
    def get_settings(self):
        return self.widget.get_current_values()
