from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QDialogButtonBox, 
                               QGroupBox, QGridLayout, QWidget, QLabel)
from PySide6.QtCore import Qt
from src.core.language_manager import tr, LanguageManager
from src.gui.toggle_switch import ToggleSwitch

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
            'CorrectedMean': False,
            'Accumulate': True
        }
        self.init_ui()
        LanguageManager.instance().language_changed.connect(self.retranslate_ui)

    def _add_toggle_row(self, layout, label_text, key):
        """Helper to add a row with label and toggle switch."""
        row_layout = QHBoxLayout()
        label = QLabel(label_text)
        toggle = ToggleSwitch()
        toggle.setChecked(self.settings.get(key, False))
        row_layout.addWidget(label)
        row_layout.addStretch()
        row_layout.addWidget(toggle)
        layout.addLayout(row_layout)
        self.checks[key] = toggle
        self.labels[key] = label
        return toggle

    def _add_help_label(self, layout, text):
        """Helper to add a grey help label."""
        label = QLabel(text)
        label.setWordWrap(True)
        label.setStyleSheet("color: #888888; font-size: 11px; margin-bottom: 5px;")
        layout.addWidget(label)
        return label

    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # Metrics Group
        self.group = QGroupBox(tr("Select Metrics"))
        group_layout = QVBoxLayout()
        
        self.checks = {}
        self.labels = {}
        for key in ['Area', 'Mean', 'IntDen', 'Min', 'Max', 'BgMean', 'CorrectedMean']:
            self._add_toggle_row(group_layout, tr(key), key)
            
        self.group.setLayout(group_layout)
        layout.addWidget(self.group)
        
        # Behavior Group
        self.behavior_group = QGroupBox(tr("Behavior"))
        behavior_layout = QVBoxLayout()
        
        # Overlap toggle
        self._add_toggle_row(behavior_layout, tr("Calculate Overlap"), 'Overlap')
        self.lbl_overlap_help = self._add_help_label(behavior_layout, 
            tr("Calculate spatial overlap (Intersection, IoU, etc.) between selected ROIs. Note: May increase calculation time with many ROIs."))
        
        # Accumulate Results toggle
        row_layout = QHBoxLayout()
        self.lbl_accumulate = QLabel(tr("Accumulate Results"))
        self.chk_accumulate = ToggleSwitch()
        self.chk_accumulate.setChecked(self.settings.get('Accumulate', True))
        row_layout.addWidget(self.lbl_accumulate)
        row_layout.addStretch()
        row_layout.addWidget(self.chk_accumulate)
        behavior_layout.addLayout(row_layout)
        
        self.lbl_accumulate_help = self._add_help_label(behavior_layout,
            tr("When enabled, new measurement results will be appended to the table; when disabled, they will overwrite old results."))
        
        self.behavior_group.setLayout(behavior_layout)
        layout.addWidget(self.behavior_group)
        
        layout.addStretch()

    def retranslate_ui(self):
        self.group.setTitle(tr("Select Metrics"))
        for key, label in self.labels.items():
            label.setText(tr(key))
            
        self.behavior_group.setTitle(tr("Behavior"))
        self.lbl_accumulate.setText(tr("Accumulate Results"))
        
        self.lbl_overlap_help.setText(tr("Calculate spatial overlap (Intersection, IoU, etc.) between selected ROIs. Note: May increase calculation time with many ROIs."))
        self.lbl_accumulate_help.setText(tr("When enabled, new measurement results will be appended to the table; when disabled, they will overwrite old results."))

    def get_settings(self):
        settings = {key: chk.isChecked() for key, chk in self.checks.items()}
        settings['Accumulate'] = self.chk_accumulate.isChecked()
        return settings


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
        
        from src.gui.theme_manager import ThemeManager
        ThemeManager.instance().apply_theme(self)
        
        LanguageManager.instance().language_changed.connect(self.retranslate_ui)

    def retranslate_ui(self):
        self.setWindowTitle(tr("Measurement Settings"))
        
    def get_settings(self):
        return self.widget.get_settings()
