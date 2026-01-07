from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QSpinBox, 
                               QCheckBox, QDialogButtonBox, QWidget)
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

    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # Enable Auto Save
        self.chk_enable = QCheckBox("Enable Auto Save")
        layout.addWidget(self.chk_enable)
        
        # Interval
        h_layout = QHBoxLayout()
        h_layout.addWidget(QLabel("Interval (minutes):"))
        self.spin_interval = QSpinBox()
        self.spin_interval.setRange(1, 60)
        h_layout.addWidget(self.spin_interval)
        layout.addLayout(h_layout)
        
        # Logic: Disable spin if checkbox unchecked
        self.chk_enable.toggled.connect(self.spin_interval.setEnabled)
        
        layout.addStretch()

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
        self.setWindowTitle("Auto Save Settings")
        self.setFixedSize(300, 150)
        
        layout = QVBoxLayout(self)
        self.widget = AutoSaveSettingsWidget(self)
        layout.addWidget(self.widget)
        
        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.save_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
    def save_and_accept(self):
        self.widget.save_settings()
        self.accept()
        
    def get_settings(self):
        return self.widget.get_current_values()
