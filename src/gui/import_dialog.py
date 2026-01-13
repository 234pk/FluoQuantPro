from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QToolButton, 
                               QTableWidget, QTableWidgetItem, QFileDialog, QHeaderView,
                               QComboBox, QColorDialog, QWidget, QLabel, QSizePolicy, QGridLayout, QPushButton)
from src.gui.icon_manager import get_icon
from PySide6.QtGui import QColor
from PySide6.QtCore import Qt, QSize
from src.core.language_manager import LanguageManager, tr
import os

class FluorophoreAssignmentDialog(QDialog):
    """
    Dialog for assigning fluorophores to R, G, B channels of a merge image.
    """
    def __init__(self, parent=None, filename=""):
        super().__init__(parent)
        self.filename = filename
        self.setWindowTitle(tr("Assign Fluorophores"))
        self.resize(400, 250)
        
        # Predefined Channel Configs
        self.fluorophores = [tr("<None>"), "DAPI", "GFP", "RFP", "CY3", "CY5", "YFP", tr("Other")]
        self.colors = {
            "DAPI": "#0000FF",
            "GFP": "#00FF00",
            "RFP": "#FF0000",
            "CY3": "#FF00FF",
            "CY5": "#FFFFFF",
            "YFP": "#FFFF00",
            tr("Other"): "#808080"
        }
        
        self.setup_ui(filename)
        LanguageManager.instance().language_changed.connect(self.retranslate_ui)

    def setup_ui(self, filename):
        layout = QVBoxLayout(self)
        
        self.info_label = QLabel(tr("Assign fluorophores for RGB Merge image:\n<b>{0}</b>").format(filename))
        self.info_label.setWordWrap(True)
        layout.addWidget(self.info_label)
        layout.addSpacing(10)
        
        grid = QGridLayout()
        layout.addLayout(grid)
        
        self.combos = {}
        self.labels = {}
        channels = [("Red Channel:", "Red"), ("Green Channel:", "Green"), ("Blue Channel:", "Blue")]
        for i, (label_text, ch_key) in enumerate(channels):
            label = QLabel(tr(label_text))
            self.labels[ch_key] = label
            combo = QComboBox()
            combo.addItems(self.fluorophores)
            grid.addWidget(label, i, 0)
            grid.addWidget(combo, i, 1)
            self.combos[ch_key] = combo
            
        layout.addStretch()
        
        # Buttons
        btn_layout = QHBoxLayout()
        self.btn_cancel = QPushButton(tr("Cancel"))
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_ok = QPushButton(tr("OK"))
        self.btn_ok.setDefault(True)
        self.btn_ok.clicked.connect(self.accept)
        
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_ok)
        layout.addLayout(btn_layout)
        
    def retranslate_ui(self):
        self.setWindowTitle(tr("Assign Fluorophores"))
        self.info_label.setText(tr("Assign fluorophores for RGB Merge image:\n<b>{0}</b>").format(self.filename))
        self.labels["Red"].setText(tr("Red Channel:"))
        self.labels["Green"].setText(tr("Green Channel:"))
        self.labels["Blue"].setText(tr("Blue Channel:"))
        self.btn_cancel.setText(tr("Cancel"))
        self.btn_ok.setText(tr("OK"))
        
        # Update combo items
        self.fluorophores = [tr("<None>"), "DAPI", "GFP", "RFP", "CY3", "CY5", "YFP", tr("Other")]
        for combo in self.combos.values():
            current = combo.currentText()
            combo.clear()
            combo.addItems(self.fluorophores)
            combo.setCurrentText(current)
        
    def get_assignments(self):
        """Returns a dict mapping channel key to fluorophore info or None."""
        results = {}
        none_text = tr("<None>")
        for ch, combo in self.combos.items():
            val = combo.currentText()
            if val == none_text:
                results[ch] = None
            else:
                results[ch] = {
                    "fluorophore": val,
                    "color": self.colors.get(val, "#FFFFFF")
                }
        return results

class ImportDialog(QDialog):
    """
    Dialog for batch importing multi-channel TIFF images.
    Allows user to assign Channel Type and Color for each file.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Import Images"))
        self.resize(800, 400)
        
        self.selected_files = [] # List of tuples: (path, name, type, color_hex)
        
        # Predefined Channel Configs
        self.channel_presets = {
            "DAPI": "#0000FF",    # Blue
            "GFP": "#00FF00",     # Green
            "RFP": "#FF0000",     # Red
            "YFP": "#FFFF00",     # Yellow
            "CY3": "#FF0000",     # Red
            "CY5": "#FF00FF",     # Magenta
            "Other": "#808080"    # Gray
        }
        
        self.setup_ui()
        LanguageManager.instance().language_changed.connect(self.retranslate_ui)
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Top: Add Files Button
        top_layout = QHBoxLayout()
        self.btn_add_files = QToolButton()
        self.btn_add_files.setIcon(get_icon("add", "list-add"))
        self.btn_add_files.setIconSize(QSize(20, 20))
        self.btn_add_files.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.btn_add_files.setFixedSize(28, 28)
        self.btn_add_files.setToolTip(tr("Select image files to import"))
        self.btn_add_files.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add_files.clicked.connect(self.browse_files)
        top_layout.addWidget(self.btn_add_files)
        top_layout.addStretch()
        layout.addLayout(top_layout)
        
        # Center: File List Table
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels([tr("Filename"), tr("Path"), tr("Channel Type"), tr("Color")])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self.table)
        
        # Bottom: Dialog Buttons
        btn_layout = QHBoxLayout()
        self.btn_cancel = QPushButton(tr("Cancel"))
        self.btn_cancel.setIcon(get_icon("cancel", "process-stop"))
        self.btn_cancel.setFixedSize(100, 32)
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.clicked.connect(self.reject)
        
        self.btn_import = QPushButton(tr("Import"))
        self.btn_import.setIcon(get_icon("import", "document-import"))
        self.btn_import.setFixedSize(100, 32)
        self.btn_import.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_import.setObjectName("action_btn") # For special styling
        self.btn_import.clicked.connect(self.finalize_import)
        
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_import)
        layout.addLayout(btn_layout)

    def retranslate_ui(self):
        self.setWindowTitle(tr("Import Images"))
        self.btn_add_files.setToolTip(tr("Select image files to import"))
        self.table.setHorizontalHeaderLabels([tr("Filename"), tr("Path"), tr("Channel Type"), tr("Color")])
        self.btn_cancel.setText(tr("Cancel"))
        self.btn_import.setText(tr("Import"))
        
    def browse_files(self):
        file_paths, _ = QFileDialog.getOpenFileNames(
            self, 
            tr("Select Images"), 
            "", 
            "Images (*.tif *.tiff *.png *.jpg);;All Files (*)"
        )
        
        if file_paths:
            self.add_files_to_table(file_paths)
            
    def add_files_to_table(self, paths):
        current_row = self.table.rowCount()
        for path in paths:
            filename = os.path.basename(path)
            self.table.insertRow(current_row)
            
            # 1. Filename
            self.table.setItem(current_row, 0, QTableWidgetItem(filename))
            
            # 2. Path
            self.table.setItem(current_row, 1, QTableWidgetItem(path))
            
            # 3. Channel Type (ComboBox)
            combo_type = QComboBox()
            combo_type.addItems(self.channel_presets.keys())
            
            # Auto-guess type from filename
            guessed_type = self.guess_channel_type(filename)
            if guessed_type:
                combo_type.setCurrentText(guessed_type)
            
            # Connect change signal to auto-update color
            # Use a closure/partial to capture the current row index is risky if rows move, 
            # but here rows are append-only. Better to find row by widget position.
            combo_type.currentTextChanged.connect(lambda text, r=current_row: self.on_type_changed(r, text))
            
            self.table.setCellWidget(current_row, 2, combo_type)
            
            # 4. Color (Button with Color)
            btn_color = QToolButton()
            initial_color = self.channel_presets[combo_type.currentText()]
            self.set_button_color(btn_color, initial_color)
            btn_color.clicked.connect(lambda checked=False, r=current_row: self.pick_color(r))
            self.table.setCellWidget(current_row, 3, btn_color)
            
            current_row += 1
            
    def guess_channel_type(self, filename):
        upper_name = filename.upper()
        for key in self.channel_presets.keys():
            if key in upper_name:
                return key
        return "Other"

    def on_type_changed(self, row, new_type):
        if new_type in self.channel_presets:
            color = self.channel_presets[new_type]
            btn_color = self.table.cellWidget(row, 3)
            if btn_color:
                self.set_button_color(btn_color, color)

    def set_button_color(self, button, color_hex):
        button.setText(color_hex)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        button.setProperty("role", "color_picker")
        button.setStyleSheet(f"background-color: {color_hex};")
        button.setProperty("color_hex", color_hex) # Store data

    def pick_color(self, row):
        btn_color = self.table.cellWidget(row, 3)
        current_hex = btn_color.property("color_hex")
        color = QColorDialog.getColor(QColor(current_hex), self, tr("Select Channel Color"))
        
        if color.isValid():
            self.set_button_color(btn_color, color.name().upper())

    def finalize_import(self):
        """Collects data and closes dialog."""
        self.selected_files = []
        
        for row in range(self.table.rowCount()):
            path_item = self.table.item(row, 1)
            if not path_item: continue
            
            path = path_item.text()
            name = self.table.item(row, 0).text()
            
            combo_type = self.table.cellWidget(row, 2)
            channel_type = combo_type.currentText()
            
            btn_color = self.table.cellWidget(row, 3)
            color_hex = btn_color.property("color_hex")
            
            self.selected_files.append({
                "path": path,
                "name": name,
                "type": channel_type,
                "color": color_hex
            })
            
        self.accept()

    def get_result(self):
        return self.selected_files
