from PySide6.QtWidgets import (QVBoxLayout, 
                               QLabel, QGroupBox, 
                               QComboBox, QWidget, QToolButton, QHBoxLayout,
                               QDialog, QDialogButtonBox, QFormLayout, QLineEdit,
                               QFileDialog)
from PySide6.QtCore import Qt, QSettings, QSize
from src.gui.icon_manager import get_icon
from src.core.language_manager import LanguageManager, tr
from src.gui.toggle_switch import ToggleSwitch
from src.gui.theme_manager import ThemeManager

class ExportSettingsWidget(QWidget):
    """
    Widget for Image Export settings.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings = QSettings("FluoQuantPro", "ExportSettings")
        self.init_ui()
        self.load_settings()
        ThemeManager.instance().apply_theme(self)
        LanguageManager.instance().language_changed.connect(self.retranslate_ui)
        ThemeManager.instance().theme_changed.connect(self.refresh_icons)

    def refresh_icons(self):
        """Refresh icons for the widget."""
        if hasattr(self, 'btn_browse'):
            self.btn_browse.setIcon(get_icon("folder", "folder-open"))

    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # 1. Export Content
        self.gb_content = QGroupBox(tr("Content Selection"))
        vbox_content = QVBoxLayout()
        
        # Channel Export Toggle
        self.row_channels = QHBoxLayout()
        self.lbl_channels = QLabel(tr("Export Single Channels"))
        self.chk_channels = ToggleSwitch()
        self.chk_channels.setToolTip(tr("If checked, individual image files will be generated for each channel (e.g., DAPI, GFP)."))
        self.row_channels.addWidget(self.lbl_channels)
        self.row_channels.addStretch()
        self.row_channels.addWidget(self.chk_channels)
        vbox_content.addLayout(self.row_channels)
        
        self.lbl_channels_desc = QLabel(f"<i>{tr('Generates separate files for each channel.')}</i>")
        self.lbl_channels_desc.setProperty("role", "description")
        vbox_content.addWidget(self.lbl_channels_desc)
        
        vbox_content.addSpacing(5)
        
        # Merge Export Toggle
        self.row_merge = QHBoxLayout()
        self.lbl_merge = QLabel(tr("Export Merge Image (Composite)"))
        self.chk_merge = ToggleSwitch()
        self.chk_merge.setToolTip(tr("If checked, a combined multi-channel image will be generated."))
        self.row_merge.addWidget(self.lbl_merge)
        self.row_merge.addStretch()
        self.row_merge.addWidget(self.chk_merge)
        vbox_content.addLayout(self.row_merge)
        
        self.lbl_merge_desc = QLabel(f"<i>{tr('Generates a single composite image of all visible channels.')}</i>")
        self.lbl_merge_desc.setProperty("role", "description")
        vbox_content.addWidget(self.lbl_merge_desc)
        
        self.gb_content.setLayout(vbox_content)
        layout.addWidget(self.gb_content)
        
        # 2. Export Mode
        self.gb_mode = QGroupBox(tr("Data Mode"))
        vbox_mode = QVBoxLayout()
        
        # Raw Data Toggle
        self.row_raw = QHBoxLayout()
        self.lbl_raw = QLabel(tr("Raw Data (Scientific)"))
        self.chk_raw = ToggleSwitch()
        self.chk_raw.setToolTip(tr("Best for quantification. Preserves original 16-bit pixel values."))
        self.row_raw.addWidget(self.lbl_raw)
        self.row_raw.addStretch()
        self.row_raw.addWidget(self.chk_raw)
        vbox_mode.addLayout(self.row_raw)
        
        self.lbl_raw_desc = QLabel(f"<b>{tr('Format:')}</b> 16-bit Grayscale TIFF<br><b>{tr('Use for:')}</b> Analysis, Quantification (ImageJ/Fiji)<br><i>{tr('Note: Ignores display adjustments.')}</i>")
        self.lbl_raw_desc.setProperty("role", "description")
        self.lbl_raw_desc.setTextFormat(Qt.TextFormat.RichText)
        vbox_mode.addWidget(self.lbl_raw_desc)
        
        vbox_mode.addSpacing(10)
        
        # Rendered Toggle
        self.row_rendered = QHBoxLayout()
        self.lbl_rendered = QLabel(tr("Rendered (Presentation)"))
        self.chk_rendered = ToggleSwitch()
        self.chk_rendered.setToolTip(tr("Best for display. Applies current brightness, contrast, and color settings."))
        self.row_rendered.addWidget(self.lbl_rendered)
        self.row_rendered.addStretch()
        self.row_rendered.addWidget(self.chk_rendered)
        vbox_mode.addLayout(self.row_rendered)
        
        format_str = tr("Format:")
        use_for_str = tr("Use for:")
        note_str = tr("Note: 'What You See Is What You Get'.")
        
        self.lbl_rend_desc = QLabel(tr("<b>{0}</b> RGB TIFF (Full Color)<br><b>{1}</b> Publications, Presentations, Visual Inspection<br><i>{2}</i>").format(format_str, use_for_str, note_str))
        self.lbl_rend_desc.setProperty("role", "description")
        self.lbl_rend_desc.setTextFormat(Qt.TextFormat.RichText)
        vbox_mode.addWidget(self.lbl_rend_desc)
        
        # 2.1 Bit Depth and DPI for Rendered
        self.rendered_options_widget = QWidget()
        vbox_rend_opts = QVBoxLayout(self.rendered_options_widget)
        vbox_rend_opts.setContentsMargins(40, 0, 0, 0)
        vbox_rend_opts.setSpacing(8)

        # Bit Depth
        hbox_depth = QHBoxLayout()
        self.lbl_depth = QLabel(tr("Bit Depth:"))
        hbox_depth.addWidget(self.lbl_depth)
        self.combo_depth = QComboBox()
        self.combo_depth.addItems([tr("8-bit RGB (Standard)"), tr("16-bit RGB (High Precision)")])
        self.combo_depth.setToolTip(tr("16-bit RGB preserves more intensity detail but files are larger and not all viewers support it."))
        hbox_depth.addWidget(self.combo_depth)
        hbox_depth.addStretch()
        vbox_rend_opts.addLayout(hbox_depth)

        # DPI Setting
        hbox_dpi = QHBoxLayout()
        self.lbl_dpi = QLabel(tr("Resolution (DPI):"))
        hbox_dpi.addWidget(self.lbl_dpi)
        self.combo_dpi = QComboBox()
        self.dpi_options = [
            (tr("150 DPI (Draft/Internal)"), 150),
            (tr("300 DPI (Standard Publication)"), 300),
            (tr("400 DPI (High Detail)"), 400),
            (tr("600 DPI (🌟 High Quality Publication)"), 600),
            (tr("900 DPI (Ultra High Definition)"), 900),
            (tr("1200 DPI (Professional Print)"), 1200)
        ]
        for text, val in self.dpi_options:
            self.combo_dpi.addItem(text, val)
        
        # Default to 600 DPI (Index 3)
        self.combo_dpi.setCurrentIndex(3)
        self.combo_dpi.setToolTip(tr("Higher DPI increases print quality and detail but also increases file size."))
        hbox_dpi.addWidget(self.combo_dpi)
        hbox_dpi.addStretch()
        vbox_rend_opts.addLayout(hbox_dpi)
        
        # Line scans are now controlled by individual ROI properties in the annotation list.
        # Global checkbox removed to avoid confusion.
        
        vbox_mode.addWidget(self.rendered_options_widget)
        
        self.chk_rendered.toggled.connect(self.rendered_options_widget.setVisible)
        
        self.gb_mode.setLayout(vbox_mode)
        layout.addWidget(self.gb_mode)

        # 3. Annotations
        self.gb_ann = QGroupBox(tr("Annotations & ROIs"))
        vbox_ann = QVBoxLayout()
        
        # Include Annotations Toggle
        self.row_ann = QHBoxLayout()
        self.lbl_include_ann = QLabel(tr("Include Graphic Annotations"))
        self.chk_include_ann = ToggleSwitch()
        self.chk_include_ann.setToolTip(tr("If checked, visible arrows, shapes, and text will be drawn on rendered images."))
        self.row_ann.addWidget(self.lbl_include_ann)
        self.row_ann.addStretch()
        self.row_ann.addWidget(self.chk_include_ann)
        vbox_ann.addLayout(self.row_ann)
        
        self.lbl_ann_desc = QLabel(f"<i>{tr('Includes user-drawn annotations and synchronized ROIs.')}</i>")
        self.lbl_ann_desc.setProperty("role", "description")
        vbox_ann.addWidget(self.lbl_ann_desc)
        
        self.gb_ann.setLayout(vbox_ann)
        layout.addWidget(self.gb_ann)

        # 4. Output Path (Optional override)
        self.gb_path = QGroupBox(tr("Custom Export Path (Optional)"))
        self.form_layout = QFormLayout()
        
        self.le_export_path = QLineEdit()
        self.le_export_path.setPlaceholderText(tr("Default: Project/exports"))
        
        self.btn_browse = QToolButton()
        self.btn_browse.setIcon(get_icon("folder", "folder-open"))
        self.btn_browse.setIconSize(QSize(20, 20))
        self.btn_browse.setFixedSize(28, 28)
        self.btn_browse.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.btn_browse.setToolTip(tr("Browse for export folder"))
        self.btn_browse.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_browse.clicked.connect(self.browse_folder)
        
        path_widget = QWidget()
        hbox_path = QHBoxLayout(path_widget)
        hbox_path.setContentsMargins(0,0,0,0)
        hbox_path.addWidget(self.le_export_path)
        hbox_path.addWidget(self.btn_browse)
        
        self.form_layout.addRow(tr("Folder:"), path_widget)
        self.gb_path.setLayout(self.form_layout)
        
        layout.addWidget(self.gb_path)
        layout.addStretch()

    def retranslate_ui(self):
        self.gb_content.setTitle(tr("Content Selection"))
        self.lbl_channels.setText(tr("Export Single Channels"))
        self.chk_channels.setToolTip(tr("If checked, individual image files will be generated for each channel (e.g., DAPI, GFP)."))
        self.lbl_channels_desc.setText(f"<i>{tr('Generates separate files for each channel.')}</i>")
        self.lbl_merge.setText(tr("Export Merge Image (Composite)"))
        self.chk_merge.setToolTip(tr("If checked, a combined multi-channel image will be generated."))
        self.lbl_merge_desc.setText(f"<i>{tr('Generates a single composite image of all visible channels.')}</i>")
        
        self.gb_mode.setTitle(tr("Data Mode"))
        self.lbl_raw.setText(tr("Raw Data (Scientific)"))
        self.chk_raw.setToolTip(tr("Best for quantification. Preserves original 16-bit pixel values."))
        self.lbl_raw_desc.setText(f"<b>{tr('Format:')}</b> 16-bit Grayscale TIFF<br><b>{tr('Use for:')}</b> Analysis, Quantification (ImageJ/Fiji)<br><i>{tr('Note: Ignores display adjustments.')}</i>")
        
        self.lbl_rendered.setText(tr("Rendered (Presentation)"))
        self.chk_rendered.setToolTip(tr("Best for display. Applies current brightness, contrast, and color settings."))
        
        format_str = tr("Format:")
        use_for_str = tr("Use for:")
        note_str = tr("Note: 'What You See Is What You Get'.")
        self.lbl_rend_desc.setText(tr("<b>{0}</b> RGB TIFF (Full Color)<br><b>{1}</b> Publications, Presentations, Visual Inspection<br><i>{2}</i>").format(format_str, use_for_str, note_str))
        
        self.lbl_depth.setText(tr("Bit Depth:"))
        current_depth_idx = self.combo_depth.currentIndex()
        self.combo_depth.clear()
        self.combo_depth.addItems([tr("8-bit RGB (Standard)"), tr("16-bit RGB (High Precision)")])
        self.combo_depth.setCurrentIndex(current_depth_idx)
        self.combo_depth.setToolTip(tr("16-bit RGB preserves more intensity detail but files are larger and not all viewers support it."))
        
        self.lbl_dpi.setText(tr("Resolution (DPI):"))
        current_dpi_idx = self.combo_dpi.currentIndex()
        self.combo_dpi.clear()
        self.dpi_options = [
            (tr("150 DPI (Draft/Internal)"), 150),
            (tr("300 DPI (Standard Publication)"), 300),
            (tr("400 DPI (High Detail)"), 400),
            (tr("600 DPI (🌟 High Quality Publication)"), 600),
            (tr("900 DPI (Ultra High Definition)"), 900),
            (tr("1200 DPI (Professional Print)"), 1200)
        ]
        for text, val in self.dpi_options:
            self.combo_dpi.addItem(text, val)
        self.combo_dpi.setCurrentIndex(current_dpi_idx)
        self.combo_dpi.setToolTip(tr("Higher DPI increases print quality and detail but also increases file size."))

        self.gb_ann.setTitle(tr("Annotations & ROIs"))
        self.lbl_include_ann.setText(tr("Include Graphic Annotations"))
        self.chk_include_ann.setToolTip(tr("If checked, visible arrows, shapes, and text will be drawn on rendered images."))
        self.lbl_ann_desc.setText(f"<i>{tr('Includes user-drawn annotations and synchronized ROIs.')}</i>")

        self.gb_path.setTitle(tr("Custom Export Path (Optional)"))
        self.le_export_path.setPlaceholderText(tr("Default: Project/exports"))
        self.btn_browse.setToolTip(tr("Browse for export folder"))
        
        # Form layout row label update
        label = self.form_layout.labelForField(self.le_export_path.parentWidget())
        if isinstance(label, QLabel):
            label.setText(tr("Folder:"))

    def load_settings(self):
        """Load from QSettings or defaults."""
        self.chk_channels.setChecked(self.settings.value("export_channels", True, type=bool))
        self.chk_merge.setChecked(self.settings.value("export_merge", True, type=bool))
        
        # Support both new multi-select and old single-select settings
        export_raw = self.settings.value("export_raw", True, type=bool)
        export_rendered = self.settings.value("export_rendered", False, type=bool)
        
        # Migrate from old "export_mode" if exists
        old_mode = self.settings.value("export_mode", None)
        if old_mode:
            export_raw = (old_mode == "raw")
            export_rendered = (old_mode == "rendered")
            # Remove old setting to avoid confusion next time
            self.settings.remove("export_mode")
            
        self.chk_raw.setChecked(export_raw)
        self.chk_rendered.setChecked(export_rendered)
        self.rendered_options_widget.setVisible(export_rendered)
            
        depth_idx = self.settings.value("export_depth_idx", 0, type=int)
        self.combo_depth.setCurrentIndex(depth_idx)
        
        dpi_val = self.settings.value("export_dpi", 600, type=int)
        # Find index for DPI value
        for i in range(self.combo_dpi.count()):
            if self.combo_dpi.itemData(i) == dpi_val:
                self.combo_dpi.setCurrentIndex(i)
                break
            
        self.le_export_path.setText(self.settings.value("export_path", "", type=str))
        self.chk_include_ann.setChecked(self.settings.value("export_include_ann", True, type=bool))

    def save_settings(self):
        """Save to QSettings."""
        self.settings.setValue("export_channels", self.chk_channels.isChecked())
        self.settings.setValue("export_merge", self.chk_merge.isChecked())
        self.settings.setValue("export_raw", self.chk_raw.isChecked())
        self.settings.setValue("export_rendered", self.chk_rendered.isChecked())
        self.settings.setValue("export_depth_idx", self.combo_depth.currentIndex())
        self.settings.setValue("export_dpi", self.combo_dpi.currentData())
        self.settings.setValue("export_path", self.le_export_path.text())
        self.settings.setValue("export_include_ann", self.chk_include_ann.isChecked())

    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, tr("Select Export Folder"))
        if folder:
            self.le_export_path.setText(folder)


import os

class ExportSettingsDialog(QDialog):
    """
    Global configuration dialog for Image Export settings.
    Settings are persisted using QSettings.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Export Configuration"))
        self.resize(400, 450)
        
        layout = QVBoxLayout(self)
        self.widget = ExportSettingsWidget(self)
        layout.addWidget(self.widget)
        
        # Buttons
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.save_and_accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        ThemeManager.instance().apply_theme(self)
        LanguageManager.instance().language_changed.connect(self.retranslate_ui)

    def retranslate_ui(self):
        self.setWindowTitle(tr("Export Configuration"))
        self.buttons.button(QDialogButtonBox.Ok).setText(tr("OK"))
        self.buttons.button(QDialogButtonBox.Cancel).setText(tr("Cancel"))

    def save_and_accept(self):
        self.widget.save_settings()
        self.accept()

    @staticmethod
    def get_current_options():
        """Static helper to get settings without instantiating dialog."""
        settings = QSettings("FluoQuantPro", "ExportSettings")
        depth_idx = settings.value("export_depth_idx", 0, type=int)
        bit_depth = 16 if depth_idx == 1 else 8
        dpi = settings.value("export_dpi", 600, type=int)
        
        # Migration logic for static method
        old_mode = settings.value("export_mode", None)
        if old_mode:
            export_raw = (old_mode == "raw")
            export_rendered = (old_mode == "rendered")
        else:
            export_raw = settings.value("export_raw", True, type=bool)
            export_rendered = settings.value("export_rendered", False, type=bool)

        return {
            "export_channels": settings.value("export_channels", True, type=bool),
            "export_merge": settings.value("export_merge", True, type=bool),
            "export_raw": export_raw,
            "export_rendered": export_rendered,
            "bit_depth": bit_depth,
            "dpi": dpi,
            "export_path": settings.value("export_path", "", type=str),
            "export_include_ann": settings.value("export_include_ann", True, type=bool)
        }
