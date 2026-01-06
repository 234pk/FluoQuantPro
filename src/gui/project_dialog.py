from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                               QCheckBox, QLineEdit, QToolButton, QColorDialog, 
                               QScrollArea, QWidget, QDialogButtonBox, QSizePolicy)
from src.gui.icon_manager import get_icon
from PySide6.QtGui import QColor
from PySide6.QtCore import Qt, QSize
from src.core.language_manager import tr, LanguageManager

class ProjectSetupDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("New Project Setup"))
        self.resize(400, 600)
        
        self.layout = QVBoxLayout(self)
        
        self.lbl_title = QLabel(tr("Select channels to include in this project:"))
        self.layout.addWidget(self.lbl_title)
        
        # Channel List Container
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll_widget = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_widget)
        self.scroll_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(self.scroll_widget)
        self.layout.addWidget(self.scroll)
        
        self.channel_rows = []
        
        # Predefined popular channels
        self.presets = [
            ("DAPI", "#0000FF"),
            ("GFP", "#00FF00"),
            ("RFP", "#FF0000"),
            ("CY5", "#FFFFFF"),
            ("TRITC", "#FF0000"),
            ("FITC", "#00FF00"),
            ("CY3", "#FF00FF"),
            ("YFP", "#FFFF00"),
            ("Phase", "#808080"),
            ("Brightfield", "#808080"),
        ]
        
        for name, color in self.presets:
            self.add_channel_row(name, color, checked=False)
            
        # Default checks (DAPI, GFP, RFP)
        for cb, name_edit, _ in self.channel_rows:
            if name_edit.text() in ["DAPI", "GFP", "RFP"]:
                cb.setChecked(True)
        
        # Add Custom Button
        self.btn_add = QToolButton()
        self.btn_add.setIcon(get_icon("add", "list-add"))
        self.btn_add.setIconSize(QSize(20, 20))
        self.btn_add.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.btn_add.setFixedSize(28, 28)
        self.btn_add.setToolTip(tr("Add a new custom channel to the project"))
        self.btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add.clicked.connect(lambda: self.add_channel_row("Custom", "#FFFFFF", checked=True))
        self.layout.addWidget(self.btn_add, 0, Qt.AlignmentFlag.AlignCenter)
        
        # Buttons
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self.layout.addWidget(self.buttons)
        
        # Connect Language Change
        LanguageManager.instance().language_changed.connect(self.retranslate_ui)
        
    def retranslate_ui(self):
        self.setWindowTitle(tr("New Project Setup"))
        self.lbl_title.setText(tr("Select channels to include in this project:"))
        self.btn_add.setToolTip(tr("Add a new custom channel to the project"))
        # We don't retranslate preset names as they are technical terms (DAPI, GFP etc)
        # But we could if needed.

    def add_channel_row(self, name, color_hex, checked=False):
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 2, 0, 2)
        
        # Checkbox
        cb = QCheckBox()
        cb.setChecked(checked)
        row_layout.addWidget(cb)
        
        # Name
        name_edit = QLineEdit(name)
        name_edit.setEnabled(checked)
        row_layout.addWidget(name_edit)
        
        # Color
        color_btn = QToolButton()
        color_btn.setProperty("role", "color_picker")
        color_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        color_btn.setToolTip(tr("Pick channel color"))
        color = QColor(color_hex)
        self.set_btn_color(color_btn, color)
        color_btn.setEnabled(checked)
        color_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        color_btn.clicked.connect(lambda checked=False, b=color_btn: self.pick_color(b))
        row_layout.addWidget(color_btn)
        
        # Enable/Disable logic
        cb.toggled.connect(name_edit.setEnabled)
        cb.toggled.connect(color_btn.setEnabled)
        
        self.scroll_layout.addWidget(row_widget)
        self.channel_rows.append((cb, name_edit, color_btn))
        
    def set_btn_color(self, btn, color):
        btn.setStyleSheet(f"background-color: {color.name()};")
        btn.setProperty("color_data", color)
        
    def pick_color(self, btn):
        current = btn.property("color_data")
        color = QColorDialog.getColor(current, self, tr("Select Channel Color"))
        if color.isValid():
            self.set_btn_color(btn, color)
            
    def get_template(self):
        template = []
        for cb, name_edit, color_btn in self.channel_rows:
            if cb.isChecked():
                name = (name_edit.text() or "").strip()
                if not name:
                    continue
                color = color_btn.property("color_data").name()
                template.append({'name': name, 'color': color})
        print(f"DEBUG: [ProjectSetupDialog] get_template returning: {template}")
        return template
