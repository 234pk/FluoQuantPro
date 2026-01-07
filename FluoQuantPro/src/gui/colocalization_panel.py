import numpy as np
import os
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                               QCheckBox, QPushButton, QGroupBox, 
                               QTableWidget, QTableWidgetItem, QHeaderView,
                               QScrollArea, QToolButton, QSizePolicy, QMessageBox, QDoubleSpinBox,
                               QFrame, QFileDialog, QApplication, QDialog, QRadioButton, QTextEdit,
                               QGridLayout)
from PySide6.QtCore import Qt, QPointF, QSize, QDateTime
import json
from PySide6.QtGui import QPalette

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
from scipy.stats import pearsonr
import matplotlib.pyplot as plt

# Fix for Matplotlib Chinese character display
plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'Arial Unicode MS', 'sans-serif']
plt.rcParams['axes.unicode_minus'] = False

from src.core.data_model import Session
from src.core.analysis import ColocalizationEngine
from src.core.language_manager import tr, LanguageManager
from src.gui.icon_manager import get_icon

from src.core.algorithms import bilinear_interpolate_numpy as bilinear_interpolate, sample_line_profile

class LineScanExportDialog(QDialog):
    def __init__(self, data, x_axis, metadata=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Export Line Scan Data"))
        self.resize(600, 500)
        self.data = data # dict of arrays
        self.x_axis = x_axis
        self.metadata = metadata or {}
        
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Format Selection
        grp_fmt = QGroupBox(tr("Export Format"))
        h_fmt = QHBoxLayout()
        self.rb_csv = QRadioButton("CSV")
        self.rb_csv.setChecked(True)
        self.rb_csv.toggled.connect(self._update_preview)
        self.rb_json = QRadioButton("JSON")
        self.rb_json.toggled.connect(self._update_preview)
        h_fmt.addWidget(self.rb_csv)
        h_fmt.addWidget(self.rb_json)
        h_fmt.addStretch()
        grp_fmt.setLayout(h_fmt)
        layout.addWidget(grp_fmt)
        
        # Preview Section
        grp_prev = QGroupBox(tr("Data Preview (First 5 Rows)"))
        v_prev = QVBoxLayout()
        
        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setFontFamily("Courier New")
        v_prev.addWidget(self.preview_text)
        
        grp_prev.setLayout(v_prev)
        layout.addWidget(grp_prev)
        
        # Buttons
        h_btns = QHBoxLayout()
        self.btn_cancel = QPushButton(tr("Cancel"))
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_save = QPushButton(tr("Export"))
        self.btn_save.clicked.connect(self.accept)
        self.btn_save.setDefault(True)
        
        h_btns.addStretch()
        h_btns.addWidget(self.btn_cancel)
        h_btns.addWidget(self.btn_save)
        layout.addLayout(h_btns)
        
        self._update_preview()
        
    def _update_preview(self):
        if self.rb_csv.isChecked():
            # Generate CSV Preview
            lines = []
            # Header
            header = [tr("Distance (px)")] + list(self.data.keys())
            lines.append(",".join(header))
            
            # Rows (Limit 5)
            limit = min(5, len(self.x_axis))
            for i in range(limit):
                row = [f"{self.x_axis[i]:.2f}"]
                for key in self.data:
                    vals = self.data[key]
                    if i < len(vals):
                        row.append(f"{vals[i]:.4f}")
                    else:
                        row.append("")
                lines.append(",".join(row))
            
            if len(self.x_axis) > 5:
                lines.append("...")
                
            self.preview_text.setText("\n".join(lines))
            
        else:
            # Generate JSON Preview
            preview_data = {
                "metadata": self.metadata,
                "data": {
                    "distance": self.x_axis[:5].tolist() if hasattr(self.x_axis, 'tolist') else self.x_axis[:5],
                    "channels": {k: v[:5].tolist() if hasattr(v, 'tolist') else v[:5] for k, v in self.data.items()}
                }
            }
            self.preview_text.setText(json.dumps(preview_data, indent=2))

    def get_export_format(self):
        return "json" if self.rb_json.isChecked() else "csv"

class ColocalizationPanel(QWidget):
    """
    Panel for multi-channel line scan colocalization analysis.
    Supports selecting multiple channels and calculating correlation matrix.
    """
    def __init__(self, session: Session, parent=None):
        super().__init__(parent)
        self.session = session
        self.current_line = None # (start_pos, end_pos)
        self.channel_colors = [
            '#e74c3c', '#2ecc71', '#3498db', '#f1c40f', '#9b59b6', '#1abc9c'
        ]
        self.last_profiles = {} # {channel_index: np.array}
        self.last_x_axis = None
        self.init_ui()
        
        # Connect Language Change
        LanguageManager.instance().language_changed.connect(self.retranslate_ui)
        
    def init_ui(self):
        self.setObjectName("card")
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(4)
        main_layout.setContentsMargins(6, 6, 6, 6)
        self.setMinimumWidth(0)
        
        # --- Top Section: Analysis Tools (Grid for Compactness) ---
        tool_layout = QGridLayout()
        tool_layout.setSpacing(4)
        
        # Line Scan Button
        self.btn_line_scan = QToolButton()
        self.btn_line_scan.setIcon(get_icon("coloc"))
        self.btn_line_scan.setIconSize(QSize(20, 20))
        self.btn_line_scan.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.btn_line_scan.setFixedSize(28, 28)
        self.btn_line_scan.setCheckable(True)
        self.btn_line_scan.setToolTip(tr("Click here then draw a line on the image to see intensity profiles"))
        self.btn_line_scan.setProperty("role", "accent")
        tool_layout.addWidget(self.btn_line_scan, 0, 0)
        
        # Clear Line Button
        self.btn_clear_line = QToolButton() # Changed from QPushButton to QToolButton for consistency
        self.btn_clear_line.setIcon(get_icon("clear", "edit-clear"))
        self.btn_clear_line.setIconSize(QSize(20, 20))
        self.btn_clear_line.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.btn_clear_line.setFixedSize(28, 28)
        self.btn_clear_line.setToolTip(tr("Clear current line and plot"))
        self.btn_clear_line.clicked.connect(self.clear_line)
        tool_layout.addWidget(self.btn_clear_line, 0, 1)
        
        # Global Colocalization Button
        self.btn_global_coloc = QPushButton(tr("Global Analysis"))
        self.btn_global_coloc.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.btn_global_coloc.setToolTip(tr("Calculate Pearson's Correlation (PCC) and Manders' Coefficients (M1/M2) for the entire image."))
        self.btn_global_coloc.clicked.connect(self.on_global_analysis_clicked)
        tool_layout.addWidget(self.btn_global_coloc, 1, 0)
        
        # Export Data Button
        self.btn_export_data = QPushButton(tr("Export Data"))
        self.btn_export_data.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.btn_export_data.clicked.connect(self.on_export_data_clicked)
        tool_layout.addWidget(self.btn_export_data, 1, 1)
        
        # Help Button
        self.btn_help = QToolButton()
        self.btn_help.setIcon(get_icon("help", "help-browser"))
        self.btn_help.setIconSize(QSize(20, 20))
        self.btn_help.setFixedSize(28, 28)
        self.btn_help.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.btn_help.setToolTip(tr("Show Analysis Guide"))
        self.btn_help.clicked.connect(self.show_help)
        tool_layout.addWidget(self.btn_help, 0, 2)
        
        main_layout.addLayout(tool_layout)
        
        self.chan_group = QGroupBox(tr("Channels"))
        chan_layout = QVBoxLayout()
        chan_layout.setContentsMargins(4, 8, 4, 4)
        
        self.chan_container = QWidget()
        self.chan_flow_layout = QHBoxLayout(self.chan_container)
        self.chan_flow_layout.setContentsMargins(0, 0, 0, 0)
        self.chan_flow_layout.setSpacing(6)
        
        chan_scroll = QScrollArea()
        chan_scroll.setWidgetResizable(True)
        chan_scroll.setWidget(self.chan_container)
        chan_scroll.setMinimumHeight(50)
        chan_scroll.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.MinimumExpanding)
        chan_scroll.setFrameShape(QFrame.NoFrame)
        chan_layout.addWidget(chan_scroll)
        
        self.chan_group.setLayout(chan_layout)
        main_layout.addWidget(self.chan_group)
        
        # Store buttons for access
        self.channel_buttons = []
        
        # --- Options Section (More Compact) ---
        opts_layout = QHBoxLayout()
        opts_layout.setSpacing(10)
        
        self.chk_normalize = QCheckBox(tr("Normalize"))
        self.chk_normalize.setChecked(True)
        self.chk_normalize.stateChanged.connect(self.update_plot)
        opts_layout.addWidget(self.chk_normalize)
        
        self.chk_bg_sub = QCheckBox(tr("BG Sub"))
        self.chk_bg_sub.stateChanged.connect(self.update_plot)
        opts_layout.addWidget(self.chk_bg_sub)
        
        opts_layout.addSpacing(10)
        self.lbl_global_thr = QLabel(tr("Global Thresholds:"))
        opts_layout.addWidget(self.lbl_global_thr)
        self.spin_t1 = QDoubleSpinBox()
        self.spin_t1.setRange(0, 65535)
        self.spin_t1.setValue(10)
        self.spin_t1.setMinimumWidth(50) # Changed from setFixedWidth(70)
        self.spin_t1.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        opts_layout.addWidget(self.spin_t1)
        
        self.spin_t2 = QDoubleSpinBox()
        self.spin_t2.setRange(0, 65535)
        self.spin_t2.setValue(10)
        self.spin_t2.setMinimumWidth(50) # Changed from setFixedWidth(70)
        self.spin_t2.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        opts_layout.addWidget(self.spin_t2)
        
        opts_layout.addStretch()
        main_layout.addLayout(opts_layout)
        
        # --- Plot Section ---
        # Removed inner ScrollArea to allow proper resizing controlled by main dock
        self.plot_container = QWidget()
        plot_layout = QVBoxLayout(self.plot_container)
        plot_layout.setContentsMargins(0, 0, 0, 0)
        
        self.figure = Figure(figsize=(5, 3), dpi=100)
        self.canvas = FigureCanvas(self.figure)
        self.ax = self.figure.add_subplot(111)
        
        # Allow canvas to shrink/expand
        self.canvas.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        self.canvas.setMinimumSize(0, 120)
        
        # Add Navigation Toolbar for Zoom/Pan
        self.toolbar = NavigationToolbar(self.canvas, self)
        self.toolbar.setFixedHeight(30) # Compact
        # Allow toolbar to shrink below its minimum size hint to prevent panel width locking
        self.toolbar.setMinimumWidth(0)
        self.toolbar.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        
        plot_layout.addWidget(self.toolbar)
        plot_layout.addWidget(self.canvas)
        
        main_layout.addWidget(self.plot_container)
        
        # Result Label
        self.lbl_pearson = QLabel(tr("Pearson r: --"))
        self.lbl_pearson.setAlignment(Qt.AlignCenter)
        self.lbl_pearson.setProperty("role", "status")
        main_layout.addWidget(self.lbl_pearson)

        self.roi_group = QGroupBox(tr("Saved Line Scans"))
        roi_layout = QVBoxLayout()
        
        self.table_rois = QTableWidget(0, 2)
        self.table_rois.setHorizontalHeaderLabels([tr("Label"), tr("Length")])
        self.table_rois.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_rois.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding) # Allow resizing
        self.table_rois.setMinimumHeight(50) # Allow shrinking further
        self.table_rois.itemSelectionChanged.connect(self.on_roi_selection_changed)
        roi_layout.addWidget(self.table_rois)
        
        self.roi_group.setLayout(roi_layout)
        main_layout.addWidget(self.roi_group)
        
        # Connect session signals
        self.session.roi_manager.roi_added.connect(self.refresh_roi_list)
        self.session.roi_manager.roi_removed.connect(self.refresh_roi_list)
        self.session.roi_manager.roi_updated.connect(self.refresh_roi_list)
        
        # Initial refresh
        self.refresh_channels()
        self.refresh_roi_list()

    def show_help(self):
        msg = QMessageBox(self)
        msg.setWindowTitle(tr("Colocalization Guide"))
        msg.setText(tr("<h3>Colocalization Analysis Guide</h3>"
                       "<p><b>Pearson's Correlation Coefficient (PCC):</b><br>"
                       "Measures the linear correlation between two channels. Range: -1 to +1.<br>"
                       "<i>+1 = Perfect correlation, 0 = No correlation, -1 = Anti-correlation.</i></p>"
                       "<p><b>Manders' Coefficients (M1 & M2):</b><br>"
                       "Measures the fraction of signal overlap above threshold.<br>"
                       "<i>M1: Fraction of Ch1 overlapping with Ch2.</i><br>"
                       "<i>M2: Fraction of Ch2 overlapping with Ch1.</i><br>"
                       "Range: 0 to 1.</p>"
                       "<p><b>Thresholds (t1, t2):</b><br>"
                       "Intensity values below these thresholds are ignored (treated as background) for Manders' calculation. "
                       "PCC is independent of thresholds (unless background subtracted).</p>"))
        msg.exec()

    def retranslate_ui(self):
        """Updates UI text based on current language."""
        self.btn_line_scan.setToolTip(tr("Click here then draw a line on the image to see intensity profiles"))
        self.btn_clear_line.setToolTip(tr("Clear current line and plot"))
        self.btn_global_coloc.setText(tr("Global Analysis"))
        self.btn_export_data.setText(tr("Export Data"))
        self.chan_group.setTitle(tr("Channels"))
        self.chk_normalize.setText(tr("Normalize"))
        self.chk_bg_sub.setText(tr("BG Sub"))
        self.lbl_global_thr.setText(tr("Global Thresholds:"))
        if "--" in self.lbl_pearson.text():
            self.lbl_pearson.setText(tr("Pearson r: --"))
        self.roi_group.setTitle(tr("Saved Line Scans"))
        self.table_rois.setHorizontalHeaderLabels([tr("Label"), tr("Length")])
        
        # Update channel buttons text
        self.refresh_channels()

    def clear_line(self):
        """Clears the current line scan and resets the plot."""
        self.current_line = None
        self.last_profiles = {}
        self.last_x_axis = None
        self.ax.clear()
        self.canvas.draw()
        self.lbl_pearson.setText("Pearson r: --")
        
        # Clear line ROIs from session
        if self.session and hasattr(self.session, 'roi_manager'):
            rois = self.session.roi_manager.get_all_rois()
            for roi in rois:
                if roi.roi_type == "line_scan":
                    self.session.roi_manager.remove_roi(roi.id, undoable=True)
        
        self.update_plot()

    def set_line_scan_action(self, action):
        """Connects the internal button to the global line scan action."""
        self.btn_line_scan.setDefaultAction(action)
        # Re-apply icon only settings because setDefaultAction might override them
        self.btn_line_scan.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.btn_line_scan.setIconSize(QSize(20, 20))
        self.btn_line_scan.setFixedSize(28, 28)

    def on_global_analysis_clicked(self):
        """Performs full-image colocalization analysis and displays results."""
        if not self.session.channels:
            QMessageBox.warning(self, tr("No Channels"), tr("Please load at least two channels for colocalization analysis."))
            return
            
        checked_indices = [btn.property("channel_index") for btn in self.channel_buttons if btn.isChecked()]
                
        if len(checked_indices) < 2:
            QMessageBox.warning(self, tr("Insufficient Channels"), tr("Please select at least two channels in the list for global analysis."))
            return
            
        # Analyze first two checked channels
        idx1, idx2 = checked_indices[0], checked_indices[1]
        ch1 = self.session.get_channel(idx1)
        ch2 = self.session.get_channel(idx2)
        
        if not ch1 or not ch2:
            return
            
        data1 = ch1.raw_data
        data2 = ch2.raw_data
        
        # Ensure 2D data for analysis (handle RGB/Pseudo-color) using Max Projection
        data1 = ColocalizationEngine._ensure_grayscale(data1)
        data2 = ColocalizationEngine._ensure_grayscale(data2)
            
        t1 = self.spin_t1.value()
        t2 = self.spin_t2.value()
        
        try:
            # PCC
            pcc = ColocalizationEngine.calculate_pcc(data1, data2)
            
            # Manders
            m1, m2 = ColocalizationEngine.calculate_manders(data1, data2, threshold1=t1, threshold2=t2)
            
            # Update summary label
            result_text = (
                tr("Global Results ({0} vs {1}):").format(ch1.name, ch2.name) + "\n" +
                tr("Pearson's (PCC): {0:.4f}").format(pcc) + "\n" +
                tr("Mander's M1 (Ch1 in Ch2): {0:.4f}").format(m1) + "\n" +
                tr("Mander's M2 (Ch2 in Ch1): {0:.4f}").format(m2)
            )
            self.lbl_pearson.setText(result_text)
            
            # Theme-aware success style
            # Update label style using global roles
            self.lbl_pearson.setProperty("role", "success")
            self.lbl_pearson.style().unpolish(self.lbl_pearson)
            self.lbl_pearson.style().polish(self.lbl_pearson)
            
            # --- USER REQUEST: Display Intensity Scatter Plot (Global Analysis) ---
            self.ax.clear()
            self.current_line = None # Clear line scan state when doing global analysis
            
            # Flatten and downsample for performance
            v1 = data1.flatten()
            v2 = data2.flatten()
            
            # Use max 10,000 points for the scatter plot to keep UI responsive
            max_points = 10000
            if v1.size > max_points:
                # Use a fixed seed for reproducibility or just random
                np.random.seed(42)
                indices = np.random.choice(v1.size, max_points, replace=False)
                s1 = v1[indices]
                s2 = v2[indices]
            else:
                s1 = v1
                s2 = v2
                
            # Plot scatter
            self.ax.scatter(s1, s2, s=2, alpha=0.4, color='#3498db', edgecolors='none')
            self.ax.set_xlabel(tr("Intensity {0}").format(ch1.name))
            self.ax.set_ylabel(tr("Intensity {0}").format(ch2.name))
            self.ax.set_title(tr("Global Colocalization (Downsampled n={0})").format(len(s1)))
            
            # Add threshold lines
            self.ax.axvline(t1, color='#e74c3c', linestyle='--', alpha=0.6, label=tr('Ch1 Thr: {0}').format(t1))
            self.ax.axhline(t2, color='#2ecc71', linestyle='--', alpha=0.6, label=tr('Ch2 Thr: {0}').format(t2))
            
            self.ax.grid(True, linestyle=':', alpha=0.5)
            self.ax.legend(fontsize='small')
            
            self.figure.tight_layout()
            self.canvas.draw()
            
        except Exception as e:
            QMessageBox.critical(self, tr("Analysis Error"), tr("Failed to perform global analysis: {0}").format(str(e)))

    def on_export_data_clicked(self):
        """Exports the current line scan data to CSV or JSON. Supports batch export of all saved line scans."""
        
        # Check for saved line scans first
        line_scans = [roi for roi in self.session.roi_manager.get_all_rois() 
                     if getattr(roi, 'roi_type', None) == 'line_scan']
        
        export_mode = "single"
        if line_scans:
            export_mode = "batch"
        elif self.last_profiles and self.last_x_axis is not None:
            export_mode = "single"
        else:
            QMessageBox.warning(self, tr("No Data"), tr("Please perform a line scan first to export data."))
            return

        checked_indices = [btn.property("channel_index") for btn in self.channel_buttons if btn.isChecked()]
        if not checked_indices:
             QMessageBox.warning(self, tr("No Channels"), tr("Please select channels to export."))
             return

        # Prepare Data
        data_dict = {}
        # We'll use a master x_axis for the dialog preview if single, or None if batch
        master_x_axis = self.last_x_axis if export_mode == "single" else None
        
        if export_mode == "batch":
            # Batch Export Logic
            for roi in line_scans:
                if not hasattr(roi, 'line_points'): continue
                p1, p2 = roi.line_points
                pt1 = (p1.x(), p1.y())
                pt2 = (p2.x(), p2.y())
                
                # Calculate X Axis
                dist = np.hypot(pt2[0] - pt1[0], pt2[1] - pt1[1])
                x_axis = np.linspace(0, dist, int(dist) + 1)
                
                # Use label as prefix
                label_safe = roi.label.replace(" ", "_")
                
                # Store Distance
                data_dict[f"{label_safe}_Distance"] = x_axis
                
                # Store Channels
                for idx in checked_indices:
                    ch = self.session.get_channel(idx)
                    if not ch: continue
                    
                    # Process Data (match plot settings)
                    raw_data = ColocalizationEngine._ensure_grayscale(ch.raw_data)
                    prof = sample_line_profile(raw_data, pt1, pt2)
                    
                    if self.chk_bg_sub.isChecked():
                        prof = np.maximum(0, prof - np.min(prof))
                    
                    if self.chk_normalize.isChecked():
                        p_max = np.max(prof) if np.max(prof) > 0 else 1
                        prof = (prof / p_max) * 100
                        
                    ch_name = ch.name.replace(" ", "_")
                    data_dict[f"{label_safe}_{ch_name}"] = prof
                    
            # Update master_x_axis for dialog to show *something* (e.g. longest one, or just the first one)
            # The dialog uses master_x_axis primarily for the "Distance" column in single mode.
            # In batch mode, we'll need to adapt the dialog or the data structure passed to it.
            # For simplicity, let's pass a dummy or the first one's axis to avoid dialog crash, 
            # but relies on keys in data_dict.
            if data_dict:
                first_key = list(data_dict.keys())[0]
                master_x_axis = data_dict[first_key] # Use first array as reference length

        else:
            # Single (Legacy) Logic
            for idx, prof in self.last_profiles.items():
                ch = self.session.get_channel(idx)
                name = ch.name if ch else tr("Channel_{0}").format(idx)
                # Ensure length match
                p_len = min(len(prof), len(self.last_x_axis))
                data_dict[tr("{0} Intensity").format(name)] = prof[:p_len]
        
        # Metadata
        metadata = {
            "created_at": QDateTime.currentDateTime().toString(Qt.DateFormat.ISODate),
            "software": "FluoQuantPro 3.0",
            "channels": [self.session.get_channel(idx).name for idx in checked_indices if self.session.get_channel(idx)],
            "roi_label": "Batch Export" if export_mode == "batch" else "Line Scan"
        }
        
        # Show Dialog
        # Note: LineScanExportDialog might need tweaks if x_axis is not the shared axis.
        # But for CSV export, we handle it below.
        dlg = LineScanExportDialog(data_dict, master_x_axis, metadata, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
            
        fmt = dlg.get_export_format()
        ext = "csv" if fmt == "csv" else "json"

        project_dir = ""
        try:
            main_window = getattr(self.session, 'main_window', None)
            project_path = getattr(main_window, 'current_project_path', None) if main_window else None
            if project_path:
                project_dir = os.path.dirname(project_path)
        except Exception:
            project_dir = ""

        ts = QDateTime.currentDateTime().toString("yyyyMMdd_HHmmss")
        mode_tag = "line_scans" if export_mode == "batch" else "line_scan"
        suggested_name = f"{mode_tag}_{ts}.{ext}"
        suggested_path = os.path.join(project_dir, suggested_name) if project_dir else suggested_name
        print(f"DEBUG: [Coloc] Suggest export path: {suggested_path}")

        file_path, _ = QFileDialog.getSaveFileName(
            self, tr("Export Data"), suggested_path, f"{ext.upper()} Files (*.{ext});;All Files (*)"
        )
        
        if not file_path:
            return
            
        try:
            if fmt == "csv":
                import pandas as pd
                
                if export_mode == "single":
                    # Single Mode: Shared Distance Column
                    df_data = {tr("Distance (px)"): self.last_x_axis}
                    df_data.update(data_dict)
                    df = pd.DataFrame({k: pd.Series(v) for k, v in df_data.items()})
                else:
                    # Batch Mode: Independent Columns
                    # data_dict already contains Distance columns for each ROI
                    # We just need to make a DataFrame from it (Series handles varying lengths)
                    df = pd.DataFrame({k: pd.Series(v) for k, v in data_dict.items()})
                    
                df.to_csv(file_path, index=False)
            else:
                # JSON
                json_data = {
                    "metadata": metadata,
                    "data": {
                        "mode": export_mode,
                        "content": {k: v.tolist() if hasattr(v, 'tolist') else v for k, v in data_dict.items()}
                    }
                }
                # If single, keep legacy structure for compatibility?
                if export_mode == "single":
                     json_data["data"] = {
                        "distance": self.last_x_axis.tolist(),
                        "channels": {k: v.tolist() if hasattr(v, 'tolist') else v for k, v in data_dict.items()}
                     }
                
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(json_data, f, indent=4)
                    
            QMessageBox.information(self, tr("Success"), tr("Data exported successfully to:\n{0}").format(file_path))
            
        except Exception as e:
            QMessageBox.critical(self, tr("Error"), tr("Failed to export data: {0}").format(str(e)))

    def refresh_channels(self):
        """Updates channel list with toggle buttons."""
        # Clear existing buttons
        for btn in self.channel_buttons:
            self.chan_flow_layout.removeWidget(btn)
            btn.deleteLater()
        self.channel_buttons.clear()
        
        for i, ch in enumerate(self.session.channels):
            if not getattr(ch, 'is_placeholder', False):
                btn = QPushButton(ch.name)
                btn.setCheckable(True)
                # Check first two by default if they were newly loaded
                btn.setChecked(i < 2)
                btn.setProperty("channel_index", i)
                
                # Dynamic style based on channel color
                color = self.channel_colors[i % len(self.channel_colors)]
                
                btn.setStyleSheet(f"""
                    QPushButton:checked {{
                        background-color: {color};
                        color: white;
                        font-weight: bold;
                        border: 1px solid {color};
                    }}
                """)
                btn.toggled.connect(self.update_plot)
                self.chan_flow_layout.addWidget(btn)
                self.channel_buttons.append(btn)
        
        # Add stretch to keep buttons on the left
        self.chan_flow_layout.addStretch()
        
        # Initial plot update
        self.update_plot()

    def on_line_updated(self, start_pos: QPointF, end_pos: QPointF):
        """Slot for real-time updates from LineScanTool."""
        try:
            main_window = getattr(self.session, 'main_window', None)
            pending_mode = getattr(main_window, 'pending_annotation_mode', None) if main_window else None
            if pending_mode in ('arrow', 'line'):
                print(f"DEBUG: [Coloc] Ignoring line update from annotation mode: {pending_mode}")
                return
        except Exception as e:
            print(f"WARNING: [Coloc] Failed to check annotation mode: {e}")
        self.current_line = (start_pos, end_pos)
        self.update_plot()

    def update_plot(self):
        """Calculates profiles for all checked channels and updates plot."""
        if not self.current_line or not self.session.channels:
            return
            
        checked_indices = [btn.property("channel_index") for btn in self.channel_buttons if btn.isChecked()]
        
        if len(checked_indices) == 0:
            self.ax.clear()
            self.canvas.draw()
            self.lbl_pearson.setText("Select channels to analyze")
            return
            
        p1, p2 = self.current_line
        pt1 = (p1.x(), p1.y())
        pt2 = (p2.x(), p2.y())
        
        profiles = {}
        channel_names = {}
        self.last_profiles = {}
        
        try:
            self.ax.clear()
            dist = np.hypot(pt2[0] - pt1[0], pt2[1] - pt1[1])
            x_axis = np.linspace(0, dist, int(dist) + 1)
            self.last_x_axis = x_axis
            
            for idx in checked_indices:
                ch = self.session.get_channel(idx)
                if ch:
                    # Ensure grayscale for analysis/line scan (weighted conversion for RGB)
                    raw_data = ColocalizationEngine._ensure_grayscale(ch.raw_data)
                    prof = sample_line_profile(raw_data, pt1, pt2)
                    
                    self.last_profiles[idx] = prof
                    
                    if self.chk_bg_sub.isChecked():
                        prof = np.maximum(0, prof - np.min(prof))
                    
                    if self.chk_normalize.isChecked():
                        p_max = np.max(prof) if np.max(prof) > 0 else 1
                        prof_plot = (prof / p_max) * 100
                    else:
                        prof_plot = prof
                    
                    profiles[idx] = prof
                    channel_names[idx] = ch.name
                    
                    color = self.channel_colors[idx % len(self.channel_colors)]
                    self.ax.plot(x_axis[:len(prof_plot)], prof_plot, color=color, label=ch.name, alpha=0.8)

            # Update Label with Pearson Correlation(s)
            pearson_texts = []
            if len(checked_indices) >= 2:
                # Calculate correlation between first two or pairs
                for i in range(len(checked_indices)):
                    for j in range(i + 1, len(checked_indices)):
                        idx1, idx2 = checked_indices[i], checked_indices[j]
                        p1_arr, p2_arr = profiles[idx1], profiles[idx2]
                        if len(p1_arr) > 1 and len(p2_arr) > 1:
                            try:
                                r_val, _ = pearsonr(p1_arr, p2_arr)
                                # Ensure r_val is a float for formatting
                                if isinstance(r_val, np.ndarray):
                                    r_val = float(r_val)
                                pearson_texts.append(f"{channel_names[idx1]} vs {channel_names[idx2]}: r={r_val:.3f}")
                            except Exception:
                                pearson_texts.append(f"{channel_names[idx1]} vs {channel_names[idx2]}: r=N/A")
            
            self.lbl_pearson.setText("\n".join(pearson_texts) if pearson_texts else "Pearson r: --")
            
            self.ax.set_xlabel("Distance (pixels)")
            self.ax.set_ylabel("Intensity (%)" if self.chk_normalize.isChecked() else "Intensity (Raw)")
            self.ax.legend(loc='upper right')
            self.ax.grid(True, linestyle='--', alpha=0.6)
            self.figure.tight_layout()
            self.canvas.draw()
            
        except Exception as e:
            print(f"Multi-Channel Line Scan Error: {e}")

    def refresh_roi_list(self):
        """Refreshes the table with ROIs of type 'line_scan'."""
        self.table_rois.setRowCount(0)
        line_scans = [roi for roi in self.session.roi_manager.get_all_rois() 
                     if getattr(roi, 'roi_type', None) == 'line_scan']
        
        for roi in line_scans:
            row = self.table_rois.rowCount()
            self.table_rois.insertRow(row)
            self.table_rois.setItem(row, 0, QTableWidgetItem(roi.label))
            
            if hasattr(roi, 'line_points'):
                p1, p2 = roi.line_points
                length = np.sqrt((p1.x()-p2.x())**2 + (p1.y()-p2.y())**2)
                self.table_rois.setItem(row, 1, QTableWidgetItem(f"{length:.1f} px"))
            
            self.table_rois.item(row, 0).setData(Qt.UserRole, roi)

    def on_roi_selection_changed(self):
        """Updates plot when a saved ROI is selected."""
        selected_items = self.table_rois.selectedItems()
        if not selected_items:
            return
            
        roi = self.table_rois.item(selected_items[0].row(), 0).data(Qt.UserRole)
        if roi and hasattr(roi, 'line_points'):
            self.current_line = roi.line_points
            self.update_plot()
