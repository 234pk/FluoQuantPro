from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QGroupBox)
from src.core.language_manager import LanguageManager, tr

class LanguageSettingsWidget(QWidget):
    """
    Widget for selecting the application language.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.lang_manager = LanguageManager.instance()
        self.init_ui()
        self.lang_manager.language_changed.connect(self.retranslate_ui)

    def init_ui(self):
        layout = QVBoxLayout(self)
        
        self.group = QGroupBox(tr("Language"))
        group_layout = QVBoxLayout(self.group)
        
        lang_layout = QHBoxLayout()
        self.label = QLabel(tr("Select Language:"))
        self.combo_lang = QComboBox()
        
        # Add supported languages
        self.combo_lang.addItem("English", "en")
        self.combo_lang.addItem("简体中文", "zh")
        
        # Set current selection
        current_lang = self.lang_manager.current_lang
        index = self.combo_lang.findData(current_lang)
        if index >= 0:
            self.combo_lang.setCurrentIndex(index)
            
        lang_layout.addWidget(self.label)
        lang_layout.addWidget(self.combo_lang)
        lang_layout.addStretch()
        
        group_layout.addLayout(lang_layout)
        layout.addWidget(self.group)
        layout.addStretch()

    def retranslate_ui(self):
        self.group.setTitle(tr("Language"))
        self.label.setText(tr("Select Language:"))

    def save_settings(self):
        """Save the selected language."""
        lang_code = self.combo_lang.currentData()
        self.lang_manager.set_language(lang_code)
