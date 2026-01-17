from PySide6.QtWidgets import (QDialog, QVBoxLayout, QTabWidget, QDialogButtonBox, QScrollArea, QWidget)
from src.gui.auto_save_dialog import AutoSaveSettingsWidget
from src.gui.measurement_dialog import MeasurementSettingsWidget
from src.gui.export_settings_dialog import ExportSettingsWidget
from src.gui.display_settings_widget import DisplaySettingsWidget
from src.gui.language_settings_widget import LanguageSettingsWidget
from src.gui.interface_settings_widget import InterfaceSettingsWidget
from src.core.language_manager import tr, LanguageManager
from src.gui.theme_manager import ThemeManager

class SettingsDialog(QDialog):
    """
    Unified settings dialog integrating Auto Save, Measurement, Export, and Display settings.
    """
    def __init__(self, parent=None, current_measurement_settings=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Preferences"))
        
        # Determine a reasonable size based on screen
        screen = self.screen().availableGeometry()
        width = min(650, screen.width() * 0.8)
        height = min(700, screen.height() * 0.8)
        self.resize(width, height)
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(10, 10, 10, 10)
        self.layout.setSpacing(10)
        
        # Tabs
        self.tabs = QTabWidget()
        self.layout.addWidget(self.tabs)
        
        # We will initialize tabs lazily or just ensure they are ready
        self._init_tabs(current_measurement_settings)
        
        # Buttons
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Apply)
        self.buttons.accepted.connect(self.save_and_accept)
        self.buttons.rejected.connect(self.reject)
        self.buttons.button(QDialogButtonBox.Apply).clicked.connect(self.apply_settings)
        
        self.layout.addWidget(self.buttons)
        
        # Set layout stretch to keep tabs at top and buttons at bottom
        self.layout.setStretch(0, 1) # TabWidget takes most space
        
        ThemeManager.instance().apply_theme(self)
        
        LanguageManager.instance().language_changed.connect(self.retranslate_ui)

    def _wrap_in_scroll(self, widget):
        """Wraps a widget in a QScrollArea for screen adaptability."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(widget)
        scroll.setFrameShape(QScrollArea.NoFrame)
        # Ensure the scroll area doesn't have a huge minimum size
        scroll.setMinimumHeight(100)
        return scroll

    def _init_tabs(self, current_measurement_settings):
        # 1. General (Auto Save)
        self.auto_save_widget = AutoSaveSettingsWidget(self)
        self.tabs.addTab(self._wrap_in_scroll(self.auto_save_widget), tr("General"))
        
        # 2. Interface
        self.interface_widget = InterfaceSettingsWidget(self)
        self.tabs.addTab(self._wrap_in_scroll(self.interface_widget), tr("Interface"))
        
        # 3. Display Quality
        self.display_widget = DisplaySettingsWidget(self)
        self.tabs.addTab(self._wrap_in_scroll(self.display_widget), tr("Display"))
        
        # 4. Measurement
        self.measurement_widget = MeasurementSettingsWidget(self, current_measurement_settings)
        self.tabs.addTab(self._wrap_in_scroll(self.measurement_widget), tr("Measurement"))
        
        # 5. Export
        self.export_widget = ExportSettingsWidget(self)
        self.tabs.addTab(self._wrap_in_scroll(self.export_widget), tr("Export"))
        
        # 6. Language
        self.language_widget = LanguageSettingsWidget(self)
        self.tabs.addTab(self._wrap_in_scroll(self.language_widget), tr("Language"))

    def retranslate_ui(self):
        self.setWindowTitle(tr("Preferences"))
        
        # Update Tab Titles
        self.tabs.setTabText(0, tr("General"))
        self.tabs.setTabText(1, tr("Interface"))
        self.tabs.setTabText(2, tr("Display"))
        self.tabs.setTabText(3, tr("Measurement"))
        self.tabs.setTabText(4, tr("Export"))
        self.tabs.setTabText(5, tr("Language"))
        
        # Update Buttons
        self.buttons.button(QDialogButtonBox.Ok).setText(tr("OK"))
        self.buttons.button(QDialogButtonBox.Cancel).setText(tr("Cancel"))
        self.buttons.button(QDialogButtonBox.Apply).setText(tr("Apply"))
        
    def apply_settings(self):
        """Apply all settings immediately without closing."""
        self.auto_save_widget.save_settings()
        self.interface_widget.save_settings()
        self.display_widget.save_settings()
        self.export_widget.save_settings()
        self.language_widget.save_settings()
        
        # Notify parent (MainWindow) to refresh
        if self.parent():
            if hasattr(self.parent(), 'measurement_settings'):
                self.parent().measurement_settings = self.get_measurement_settings()
            if hasattr(self.parent(), 'update_tab_visibility'):
                self.parent().update_tab_visibility()
            if hasattr(self.parent(), 'multi_view'):
                self.parent().multi_view.initialize_views()
            if hasattr(self.parent(), 'refresh_display'):
                self.parent().refresh_display()
                
    def save_and_accept(self):
        """Save all settings and close."""
        self.apply_settings()
        self.accept()
        
    def get_measurement_settings(self):
        """Retrieve updated measurement settings."""
        return self.measurement_widget.get_settings()
