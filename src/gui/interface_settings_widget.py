from PySide6.QtWidgets import (QWidget, QVBoxLayout, QCheckBox, QLabel, QGroupBox)
from PySide6.QtCore import QSettings
from src.core.language_manager import tr

class InterfaceSettingsWidget(QWidget):
    """
    Widget to control UI interface settings, specifically tab visibility.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings = QSettings("FluoQuantPro", "AppSettings")
        self.init_ui()
        self.load_settings()

    def init_ui(self):
        layout = QVBoxLayout(self)
        
        group = QGroupBox(tr("Control Panel Tabs Visibility"))
        group_layout = QVBoxLayout(group)
        
        self.tabs_info = [
            ("toolbox", tr("Toolbox")),
            ("adjustments", tr("Adjustments")),
            ("enhance", tr("Enhance")),
            ("colocalization", tr("Colocalization")),
            ("annotation", tr("annotation")),
            ("results", tr("Measure Results"))
        ]
        
        self.checkboxes = {}
        for key, label in self.tabs_info:
            cb = QCheckBox(label)
            group_layout.addWidget(cb)
            self.checkboxes[key] = cb
            
        layout.addWidget(group)
        
        # --- ROI Persistence Settings ---
        roi_group = QGroupBox(tr("ROI Persistence"))
        roi_layout = QVBoxLayout(roi_group)
        
        self.chk_roi_save_on_switch = QCheckBox(tr("Auto-save ROI when switching samples"))
        self.chk_roi_save_on_switch.setToolTip(tr("If checked, ROIs will be saved to memory/disk when you switch to another sample."))
        roi_layout.addWidget(self.chk_roi_save_on_switch)
        
        self.chk_roi_save_on_close = QCheckBox(tr("Save ROI when closing project"))
        self.chk_roi_save_on_close.setToolTip(tr("If checked, ROIs will be saved to project.json when you close the application."))
        roi_layout.addWidget(self.chk_roi_save_on_close)
        
        layout.addWidget(roi_group)
        
        # --- Import Settings ---
        import_group = QGroupBox(tr("Import Settings"))
        import_layout = QVBoxLayout(import_group)
        
        self.chk_recursive_import = QCheckBox(tr("Import images from subfolders"))
        self.chk_recursive_import.setToolTip(tr("If checked, importing a folder will also search all subdirectories for images."))
        import_layout.addWidget(self.chk_recursive_import)
        
        layout.addWidget(import_group)
        
        layout.addStretch()

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
