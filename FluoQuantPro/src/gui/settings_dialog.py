from PySide6.QtWidgets import (QDialog, QVBoxLayout, QTabWidget, QDialogButtonBox)
from src.gui.auto_save_dialog import AutoSaveSettingsWidget
from src.gui.measurement_dialog import MeasurementSettingsWidget
from src.gui.export_settings_dialog import ExportSettingsWidget
from src.gui.display_settings_widget import DisplaySettingsWidget
from src.gui.language_settings_widget import LanguageSettingsWidget
from src.gui.interface_settings_widget import InterfaceSettingsWidget
from src.core.language_manager import tr

class SettingsDialog(QDialog):
    """
    Unified settings dialog integrating Auto Save, Measurement, Export, and Display settings.
    """
    def __init__(self, parent=None, current_measurement_settings=None):
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.resize(550, 500)
        
        self.layout = QVBoxLayout(self)
        
        # Tabs
        self.tabs = QTabWidget()
        self.layout.addWidget(self.tabs)
        
        # 1. General (Auto Save)
        self.auto_save_widget = AutoSaveSettingsWidget(self)
        self.tabs.addTab(self.auto_save_widget, tr("General"))
        
        # 2. Interface (New)
        self.interface_widget = InterfaceSettingsWidget(self)
        self.tabs.addTab(self.interface_widget, tr("Interface"))
        
        # 3. Display Quality
        self.display_widget = DisplaySettingsWidget(self)
        self.tabs.addTab(self.display_widget, tr("Display"))
        
        # 4. Measurement
        self.measurement_widget = MeasurementSettingsWidget(self, current_measurement_settings)
        self.tabs.addTab(self.measurement_widget, tr("Measurement"))
        
        # 5. Export
        self.export_widget = ExportSettingsWidget(self)
        self.tabs.addTab(self.export_widget, tr("Export"))
        
        # 6. Language
        self.language_widget = LanguageSettingsWidget(self)
        self.tabs.addTab(self.language_widget, tr("Language"))
        
        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.save_and_accept)
        buttons.rejected.connect(self.reject)
        self.layout.addWidget(buttons)
        
    def save_and_accept(self):
        """Save all settings."""
        # Save Auto Save settings (persisted to QSettings)
        self.auto_save_widget.save_settings()
        
        # Save Interface settings
        self.interface_widget.save_settings()
        
        # Save Display settings (persisted to QSettings)
        self.display_widget.save_settings()
        
        # Save Export settings (persisted to QSettings)
        self.export_widget.save_settings()
        
        # Save Language settings
        self.language_widget.save_settings()
        
        self.accept()
        
        # Measurement settings are returned, not persisted globally here
        # (They are stateful in MainWindow)
        
        self.accept()
        
    def get_measurement_settings(self):
        """Retrieve updated measurement settings."""
        return self.measurement_widget.get_settings()
