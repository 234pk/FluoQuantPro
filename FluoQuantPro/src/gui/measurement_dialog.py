from PySide6.QtWidgets import (QDialog, QVBoxLayout, QCheckBox, QDialogButtonBox, 
                               QGroupBox, QGridLayout, QWidget)
from PySide6.QtCore import Qt
from src.core.language_manager import tr, LanguageManager

class MeasurementSettingsWidget(QWidget):
    """
    Widget to select which measurement metrics to display.
    """
    def __init__(self, parent=None, current_settings=None):
        super().__init__(parent)
        self.settings = current_settings or {
            'Area': True,
            'Mean': True,
            'IntDen': True,
            'Min': True,
            'Max': True,
            'BgMean': False,
            'CorrectedMean': False
        }
        self.init_ui()
        LanguageManager.instance().language_changed.connect(self.retranslate_ui)

    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # Metrics Group
        self.group = QGroupBox(tr("Select Metrics"))
        grid = QGridLayout()
        
        self.checks = {}
        row = 0
        for key in ['Area', 'Mean', 'IntDen', 'Min', 'Max', 'BgMean', 'CorrectedMean']:
            chk = QCheckBox(tr(key))
            chk.setChecked(self.settings.get(key, False))
            self.checks[key] = chk
            grid.addWidget(chk, row, 0)
            row += 1
            
        self.group.setLayout(grid)
        layout.addWidget(self.group)
        layout.addStretch()

    def retranslate_ui(self):
        self.group.setTitle(tr("Select Metrics"))
        for key, chk in self.checks.items():
            chk.setText(tr(key))

    def get_settings(self):
        return {key: chk.isChecked() for key, chk in self.checks.items()}


class MeasurementSettingsDialog(QDialog):
    """
    Dialog to select which measurement metrics to display.
    """
    def __init__(self, parent=None, current_settings=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Measurement Settings"))
        self.resize(300, 400)
        
        layout = QVBoxLayout(self)
        self.widget = MeasurementSettingsWidget(self, current_settings)
        layout.addWidget(self.widget)
        
        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
        LanguageManager.instance().language_changed.connect(self.retranslate_ui)

    def retranslate_ui(self):
        self.setWindowTitle(tr("Measurement Settings"))
        
    def get_settings(self):
        return self.widget.get_settings()
