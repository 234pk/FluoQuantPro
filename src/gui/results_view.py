from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView
from PySide6.QtCore import Qt, Signal
from typing import List
from src.core.roi_model import ROI
from src.core.language_manager import tr, LanguageManager

class ResultsWidget(QTableWidget):
    """
    Displays ROI measurement results in a spreadsheet-like view.
    Supports row selection to highlight ROIs.
    """
    roi_selected = Signal(str) # Emits ROI ID when row is clicked

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setColumnCount(0)
        self.setRowCount(0)
        
        # Appearance
        self.setAlternatingRowColors(True)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        
        # Signals
        self.itemSelectionChanged.connect(self._on_selection_changed)
        
        # Map Row Index -> ROI ID
        self._row_to_roi_id = {}
        
        # Store data for retranslation
        self._last_rois = []
        
        LanguageManager.instance().language_changed.connect(self.retranslate_ui)

    def retranslate_ui(self):
        """Update UI text when language changes."""
        if self._last_rois:
            self.update_data(self._last_rois)
        else:
            # At least update static headers if no data
            columns = [tr("Label"), tr("ID"), tr("Area")]
            if self.columnCount() >= 3:
                for i, col in enumerate(columns):
                    self.setHorizontalHeaderItem(i, QTableWidgetItem(col))

    def update_data(self, rois: List[ROI]):
        """
        Populates the table with ROI statistics.
        Expects ROI.stats to be populated (e.g. after Measure).
        """
        self._last_rois = rois
        self.blockSignals(True)
        self.clear()
        self._row_to_roi_id = {}
        
        if not rois:
            self.setColumnCount(0)
            self.setRowCount(0)
            self.blockSignals(False)
            return

        # 1. Collect all unique keys from all ROIs to form columns
        # Start with standard columns
        columns = [tr("Label"), tr("ID"), tr("Area")]
        
        # Collect dynamic columns (e.g. Ch1_Mean, Ch2_Mean...)
        dynamic_keys = set()
        for roi in rois:
            for k in roi.stats.keys():
                if k != "Area": # Already added
                    dynamic_keys.add(k)
        
        # Sort dynamic keys for consistency (e.g. Ch1 before Ch2)
        sorted_keys = sorted(list(dynamic_keys))
        columns.extend(sorted_keys)
        
        # 2. Setup Table Structure
        self.setColumnCount(len(columns))
        self.setHorizontalHeaderLabels(columns)
        self.setRowCount(len(rois))
        
        # 3. Fill Data
        for row_idx, roi in enumerate(rois):
            self._row_to_roi_id[row_idx] = roi.id
            
            # Label
            self.setItem(row_idx, 0, QTableWidgetItem(str(roi.label)))
            # ID (Shortened)
            self.setItem(row_idx, 1, QTableWidgetItem(roi.id[:8]))
            # Area
            area_val = roi.stats.get("Area", 0)
            self.setItem(row_idx, 2, QTableWidgetItem(f"{area_val:.1f}"))
            
            # Dynamic Stats
            for col_idx, key in enumerate(sorted_keys, start=3):
                val = roi.stats.get(key, "")
                if isinstance(val, float):
                    item_text = f"{val:.2f}"
                else:
                    item_text = str(val)
                self.setItem(row_idx, col_idx, QTableWidgetItem(item_text))

        self.blockSignals(False)

    def _on_selection_changed(self):
        """Handle row selection by user."""
        rows = self.selectionModel().selectedRows()
        if rows:
            row_idx = rows[0].row()
            roi_id = self._row_to_roi_id.get(row_idx)
            if roi_id:
                self.roi_selected.emit(roi_id)

    def select_roi(self, roi_id: str):
        """Programmatically select a row based on ROI ID."""
        # Find row with this ID
        target_row = -1
        for row, rid in self._row_to_roi_id.items():
            if rid == roi_id:
                target_row = row
                break
        
        if target_row != -1:
            self.blockSignals(True)
            self.selectRow(target_row)
            self.scrollToItem(self.item(target_row, 0))
            self.blockSignals(False)
        else:
            self.clearSelection()
