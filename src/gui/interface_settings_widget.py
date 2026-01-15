from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox, QComboBox)
from PySide6.QtCore import QSettings, Qt
from src.core.language_manager import tr, LanguageManager
from src.gui.theme_manager import ThemeManager
from src.gui.toggle_switch import ToggleSwitch

class InterfaceSettingsWidget(QWidget):
    """
    Widget to control UI interface settings, specifically tab visibility.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings = QSettings("FluoQuantPro", "AppSettings")
        self.checkboxes = {}
        self.labels = {}
        self.init_ui()
        self.load_settings()
        LanguageManager.instance().language_changed.connect(self.retranslate_ui)

    def _add_toggle_row(self, layout, label_text, key=None):
        """Helper to add a row with label and toggle switch."""
        row_layout = QHBoxLayout()
        label = QLabel(label_text)
        toggle = ToggleSwitch()
        row_layout.addWidget(label)
        row_layout.addStretch()
        row_layout.addWidget(toggle)
        layout.addLayout(row_layout)
        if key:
            self.checkboxes[key] = toggle
            self.labels[key] = label
        return toggle, label

    def init_ui(self):
        layout = QVBoxLayout(self)
        
        self.group_visibility = QGroupBox(tr("Control Panel Tabs Visibility"))
        group_layout = QVBoxLayout(self.group_visibility)
        
        self.tabs_info = [
            ("toolbox", tr("Toolbox")),
            ("adjustments", tr("Adjustments")),
            ("enhance", tr("Enhance")),
            ("colocalization", tr("Colocalization")),
            ("annotation", tr("Annotations")),
            ("results", tr("Measure Results"))
        ]
        
        for key, label in self.tabs_info:
            self._add_toggle_row(group_layout, label, key)
            
        layout.addWidget(self.group_visibility)
        
        # --- ROI Persistence Settings ---
        self.roi_group = QGroupBox(tr("ROI Persistence"))
        roi_layout = QVBoxLayout(self.roi_group)
        
        self.chk_roi_save_on_switch, self.lbl_roi_save_on_switch = self._add_toggle_row(roi_layout, tr("Auto-save ROI when switching samples"))
        self.chk_roi_save_on_switch.setToolTip(tr("If checked, ROIs will be saved to memory/disk when you switch to another sample."))
        
        self.chk_roi_save_on_close, self.lbl_roi_save_on_close = self._add_toggle_row(roi_layout, tr("Save ROI when closing project"))
        self.chk_roi_save_on_close.setToolTip(tr("If checked, ROIs will be saved to project.json when you close the application."))
        
        layout.addWidget(self.roi_group)
        
        # --- Import Settings ---
        self.import_group = QGroupBox(tr("Import Settings"))
        import_layout = QVBoxLayout(self.import_group)
        
        self.chk_recursive_import, self.lbl_recursive_import = self._add_toggle_row(import_layout, tr("Import images from subfolders"))
        self.chk_recursive_import.setToolTip(tr("If checked, importing a folder will also search all subdirectories for images."))
        
        layout.addWidget(self.import_group)

        # --- Privacy Settings ---
        self.privacy_group = QGroupBox(tr("Privacy"))
        privacy_layout = QVBoxLayout(self.privacy_group)
        
        self.chk_telemetry, self.lbl_telemetry = self._add_toggle_row(privacy_layout, tr("Send anonymous usage data"), "telemetry_enabled")
        self.chk_telemetry.setToolTip(tr("Help us improve by sending anonymous usage statistics. No personal data is collected."))
        
        layout.addWidget(self.privacy_group)

        # --- Theme Settings ---
        self.theme_group = QGroupBox(tr("Theme Selection"))
        theme_layout = QVBoxLayout(self.theme_group)
        
        self.theme_combo = QComboBox()
        # Get theme names from ThemeManager
        themes = ThemeManager.instance().THEMES
        for theme_id, display_name in themes.items():
            self.theme_combo.addItem(display_name, theme_id)
            
        theme_layout.addWidget(self.theme_combo)
        layout.addWidget(self.theme_group)
        
        layout.addStretch()

    def retranslate_ui(self):
        self.group_visibility.setTitle(tr("Control Panel Tabs Visibility"))
        
        # Update tab labels
        tab_labels = {
            "toolbox": tr("Toolbox"),
            "adjustments": tr("Adjustments"),
            "enhance": tr("Enhance"),
            "colocalization": tr("Colocalization"),
            "annotation": tr("Annotations"),
            "results": tr("Measure Results")
        }
        for key, label in self.labels.items():
            if key in tab_labels:
                label.setText(tab_labels[key])
        
        self.roi_group.setTitle(tr("ROI Persistence"))
        self.lbl_roi_save_on_switch.setText(tr("Auto-save ROI when switching samples"))
        self.chk_roi_save_on_switch.setToolTip(tr("If checked, ROIs will be saved to memory/disk when you switch to another sample."))
        self.lbl_roi_save_on_close.setText(tr("Save ROI when closing project"))
        self.chk_roi_save_on_close.setToolTip(tr("If checked, ROIs will be saved to project.json when you close the application."))
        
        self.import_group.setTitle(tr("Import Settings"))
        self.lbl_recursive_import.setText(tr("Import images from subfolders"))
        self.chk_recursive_import.setToolTip(tr("If checked, importing a folder will also search all subdirectories for images."))
        
        self.privacy_group.setTitle(tr("Privacy"))
        self.lbl_telemetry.setText(tr("Send anonymous usage data"))
        self.chk_telemetry.setToolTip(tr("Help us improve by sending anonymous usage statistics. No personal data is collected."))
        
        self.theme_group.setTitle(tr("Theme Selection"))

    def load_settings(self):
        # Default all to True if not set
        visible_tabs = self.settings.value("interface/visible_tabs", "toolbox,adjustments,enhance,colocalization,annotation,results")
        visible_list = visible_tabs.split(",")
        
        # Backward compatibility for 'overlay'
        if "overlay" in visible_list and "annotation" not in visible_list:
            visible_list.append("annotation")
        
        for key, cb in self.checkboxes.items():
            cb.setChecked(key in visible_list)
            
        # ROI Settings
        # Default: False (per previous user preference "Best not to save")
        self.chk_roi_save_on_switch.setChecked(self.settings.value("roi/save_on_switch", False, type=bool))
        self.chk_roi_save_on_close.setChecked(self.settings.value("roi/save_on_close", False, type=bool))
        
        # Import Settings
        self.chk_recursive_import.setChecked(self.settings.value("import/recursive", False, type=bool))

        # Privacy Settings
        self.chk_telemetry.setChecked(self.settings.value("telemetry/enabled", True, type=bool))

        # Theme Settings
        current_theme = ThemeManager.instance().get_current_theme()
        index = self.theme_combo.findData(current_theme)
        if index >= 0:
            self.theme_combo.setCurrentIndex(index)

    def save_settings(self):
        visible_list = []
        for key, cb in self.checkboxes.items():
            if cb.isChecked():
                visible_list.append(key)
        
        self.settings.setValue("interface/visible_tabs", ",".join(visible_list))
        
        # ROI Settings
        self.settings.setValue("roi/save_on_switch", self.chk_roi_save_on_switch.isChecked())
        self.settings.setValue("roi/save_on_close", self.chk_roi_save_on_close.isChecked())
        
        # Import Settings
        self.settings.setValue("import/recursive", self.chk_recursive_import.isChecked())

        # Privacy Settings
        self.settings.setValue("telemetry/enabled", self.chk_telemetry.isChecked())

        # Theme Settings
        new_theme = self.theme_combo.currentData()
        if new_theme:
            ThemeManager.instance().set_theme(new_theme)
