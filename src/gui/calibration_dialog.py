from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                               QLineEdit, QPushButton, QComboBox, QDialogButtonBox,
                               QGroupBox, QFormLayout)
from PySide6.QtCore import Qt
from src.core.language_manager import tr, LanguageManager

class CalibrationDialog(QDialog):
    def __init__(self, current_pixel_size, selected_line_length_px=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Set Scale"))
        self.resize(350, 250)
        
        self.current_pixel_size = current_pixel_size
        self.selected_line_length_px = selected_line_length_px
        
        self.init_ui()
        LanguageManager.instance().language_changed.connect(self.retranslate_ui)

    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # Info Group
        form_layout = QFormLayout()
        
        self.lbl_distance_px = QLabel(f"{self.selected_line_length_px:.2f}" if self.selected_line_length_px else "0.00")
        form_layout.addRow(tr("Distance in Pixels:"), self.lbl_distance_px)
        
        self.edit_known_distance = QLineEdit("1.0")
        form_layout.addRow(tr("Known Distance:"), self.edit_known_distance)
        
        self.combo_unit = QComboBox()
        self.combo_unit.addItems(["um", "mm", "nm", "pixel"])
        form_layout.addRow(tr("Unit of Length:"), self.combo_unit)
        
        self.lbl_current_scale = QLabel(f"{self.current_pixel_size:.4f} um/px")
        form_layout.addRow(tr("Current Scale:"), self.lbl_current_scale)
        
        layout.addLayout(form_layout)
        
        # Result Preview
        self.lbl_result = QLabel("")
        self.lbl_result.setAlignment(Qt.AlignCenter)
        self.lbl_result.setStyleSheet("font-weight: bold; color: green;")
        layout.addWidget(self.lbl_result)
        
        # Calculate Button
        # Actually, we can update automatically on text change
        self.edit_known_distance.textChanged.connect(self.update_preview)
        self.combo_unit.currentTextChanged.connect(self.update_preview)
        
        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
        self.update_preview()

    def retranslate_ui(self):
        self.setWindowTitle(tr("Set Scale"))
        # Update labels... (simplified for now)
        
    def update_preview(self):
        try:
            dist_px = float(self.lbl_distance_px.text())
            known_dist = float(self.edit_known_distance.text())
            unit = self.combo_unit.currentText()
            
            if dist_px > 0:
                pixel_size = known_dist / dist_px
                self.lbl_result.setText(tr("New Scale: {0:.4f} {1}/px").format(pixel_size, unit))
            else:
                self.lbl_result.setText(tr("Draw a line to calculate scale"))
                
        except ValueError:
            self.lbl_result.setText("")

    def get_result(self):
        try:
            dist_px = float(self.lbl_distance_px.text())
            known_dist = float(self.edit_known_distance.text())
            if dist_px > 0:
                return known_dist / dist_px
        except:
            pass
        return None
