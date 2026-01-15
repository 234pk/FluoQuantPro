from PySide6.QtWidgets import (QWidget, QVBoxLayout, QGridLayout, QToolButton, 
                               QGroupBox, QLabel, QSizePolicy, QDoubleSpinBox, QHBoxLayout,
                               QApplication, QComboBox, QPushButton, QColorDialog, QMenu, QFrame)
from PySide6.QtCore import Qt, QSize, QSettings
from PySide6.QtGui import QPalette, QColor, QCursor, QAction
from src.core.language_manager import tr, LanguageManager
from src.core.logger import Logger

from src.gui.toggle_switch import ToggleSwitch
from src.gui.icon_manager import get_icon
from src.gui.theme_manager import ThemeManager

class RoiToolbox(QWidget):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.main_window = main_window
        self.settings = QSettings("FluoQuantPro", "AppSettings")
        
        # Allow panel to shrink very small
        self.setMinimumWidth(50)
        
        # Main Layout
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(5, 5, 5, 5)
        self.layout.setSpacing(10)
        
        # 1. Tools Group (Selection + Edit)
        self.create_tools_group()
        
        # 1.5 Size Settings (Contextual)
        self.create_size_group()
        
        # 2. Wand Options (Hidden by default or separate group)
        self.create_wand_options_group()
        
        # 3. Point Counter Options
        self.create_count_options_group()
        
        # 4. Analysis Group
        self.create_analysis_group()
        
        # Load persisted settings
        self.load_settings()
        
        # Connect Language Change
        LanguageManager.instance().language_changed.connect(self.retranslate_ui)
        
        # Connect Theme Change to refresh icons
        ThemeManager.instance().theme_changed.connect(self.refresh_icons)
        
        # Connect ROI Manager Signals
        if hasattr(self.main_window, 'session') and self.main_window.session.roi_manager:
            manager = self.main_window.session.roi_manager
            manager.selection_changed.connect(self._on_roi_selection_changed)
            manager.roi_updated.connect(self._on_roi_updated)
        
        # Spacer at bottom
        self.layout.addStretch()

    def _on_roi_updated(self, roi_or_id):
        """Update UI if the modified ROI is the currently selected one."""
        if self._updating_size_ui: return
        
        if not hasattr(self.main_window, 'session'): return

        # Handle ID string vs ROI object
        if isinstance(roi_or_id, str):
            roi_id = roi_or_id
            roi = self.main_window.session.roi_manager.get_roi(roi_id)
            if not roi: return
        else:
            roi = roi_or_id

        # Only update if visible and selected
        if self.size_group.isVisible() and roi.id in self.main_window.session.roi_manager.get_selected_ids():
            self._update_size_ui_from_roi(roi)

    def create_tools_group(self):
        self.tools_group = QGroupBox(tr("Tools"))
        layout = QGridLayout()
        layout.setSpacing(4)
        layout.setContentsMargins(2, 8, 2, 4) # Reduced margins
        
        # Tools definitions: (action_name, row, col, [row_span, col_span])
        self.main_window.action_export.setText(tr("Export Results (CSV)"))
        
        tools = [
            (self.main_window.action_wand, 0, 0),
            (self.main_window.action_polygon, 0, 1),
            (self.main_window.action_rect, 1, 0),
            (self.main_window.action_ellipse, 1, 1),
            (self.main_window.action_count, 2, 0),
            (self.main_window.action_pan, 2, 1),
            (self.main_window.action_crop, 3, 0),
            (self.main_window.action_clear, 3, 1),
            (self.main_window.action_undo, 4, 0),
            (self.main_window.action_redo, 4, 1),
            # (self.main_window.action_batch_select, 5, 0, 1, 2), # Hidden as per user request
        ]
        
        for tool_info in tools:
            action = tool_info[0]
            row, col = tool_info[1], tool_info[2]
            
            # Use IconOnly for compact look
            btn = self.create_button(action)
            # Fixed constraints removed for adaptive sizing (handled in resizeEvent/create_button)
            
            # Special handling for Polygon Tool Right-Click
            if action == self.main_window.action_polygon:
                btn.customContextMenuRequested.connect(self.on_polygon_context_menu)
                btn.setToolTip(tr("Polygon Tool\nLeft Click: Add Points\nRight Click: Close Polygon\nRight Click Button: Switch to Freehand Mode"))
            
            if len(tool_info) > 3:
                layout.addWidget(btn, row, col, tool_info[3], tool_info[4])
            else:
                layout.addWidget(btn, row, col)
        
        # Fixed Size Option
        # Fixed Shape Toggle
        row_layout = QHBoxLayout()
        self.lbl_fixed_size = QLabel(tr("Fixed Shape"))
        self.chk_fixed_size = ToggleSwitch()
        self.chk_fixed_size.setToolTip(tr("Lock ROI size to the last drawn shape"))
        self.chk_fixed_size.toggled.connect(self.save_settings)
        row_layout.addWidget(self.lbl_fixed_size)
        row_layout.addStretch()
        row_layout.addWidget(self.chk_fixed_size)
        layout.addLayout(row_layout, 7, 0, 1, 2)

        self.tools_group.setLayout(layout)
        self.layout.addWidget(self.tools_group)
                
    def create_size_group(self):
        """Creates the ROI Size settings group (Contextual)."""
        self.size_group = QGroupBox(tr("Selection Size"))
        layout = QGridLayout()
        layout.setSpacing(4)
        layout.setContentsMargins(4, 8, 4, 4)
        
        # Width
        layout.addWidget(QLabel(tr("W:")), 0, 0)
        self.spin_width = QDoubleSpinBox()
        self.spin_width.setRange(0.0, 9999.0)
        self.spin_width.setSingleStep(0.1)
        self.spin_width.setDecimals(2)
        self.spin_width.setSuffix(" cm")
        self.spin_width.setKeyboardTracking(False) # Wait for Enter or focus out
        self.spin_width.valueChanged.connect(self._on_size_value_changed)
        layout.addWidget(self.spin_width, 0, 1)
        
        # Height
        layout.addWidget(QLabel(tr("H:")), 1, 0)
        self.spin_height = QDoubleSpinBox()
        self.spin_height.setRange(0.0, 9999.0)
        self.spin_height.setSingleStep(0.1)
        self.spin_height.setDecimals(2)
        self.spin_height.setSuffix(" cm")
        self.spin_height.setKeyboardTracking(False)
        self.spin_height.valueChanged.connect(self._on_size_value_changed)
        layout.addWidget(self.spin_height, 1, 1)
        
        self.size_group.setLayout(layout)
        self.layout.addWidget(self.size_group)
        self.size_group.hide() # Hidden by default
        
        # Store blocking flag
        self._updating_size_ui = False

    def _on_size_value_changed(self):
        """Handle user input for width/height."""
        if self._updating_size_ui:
            return
            
        if not hasattr(self.main_window, 'session'): return
        
        # Get selected ROI
        selected_ids = self.main_window.session.roi_manager.get_selected_ids()
        if len(selected_ids) != 1:
            return
            
        roi = self.main_window.session.roi_manager.get_roi(list(selected_ids)[0])
        if not roi or roi.roi_type not in ['rectangle', 'ellipse', 'circle']:
            return
            
        # Convert cm to pixels (96 DPI)
        # 1 inch = 2.54 cm
        # px = cm / 2.54 * 96
        DPI = 96.0
        CM_TO_INCH = 1.0 / 2.54
        
        w_cm = self.spin_width.value()
        h_cm = self.spin_height.value()
        
        w_px = w_cm * CM_TO_INCH * DPI
        h_px = h_cm * CM_TO_INCH * DPI
        
        # Update ROI Geometry
        # We maintain Top-Left position
        from PySide6.QtCore import QPointF, QRectF
        from PySide6.QtGui import QPainterPath
        
        rect = roi.path.boundingRect()
        top_left = rect.topLeft()
        # Ensure we have valid width/height
        if w_px <= 0: w_px = 1.0
        if h_px <= 0: h_px = 1.0
        
        bottom_right = QPointF(top_left.x() + w_px, top_left.y() + h_px)
        
        # Reconstruct Path & Points (Critical for Sync)
        # We must update roi.points because Main.on_roi_updated uses points to sync to Annotation
        if roi.roi_type == 'circle':
            # Fallback for non-standard type 'circle', treat as ellipse
            roi.points = [top_left, bottom_right]
            new_path = QPainterPath()
            new_path.addEllipse(QRectF(top_left, bottom_right))
            roi.path = new_path
        else:
            # Use standard reconstruction
            roi.reconstruct_from_points([top_left, bottom_right], roi.roi_type)
        
        # Trigger update
        self.main_window.session.roi_manager.roi_updated.emit(roi)
        
    def _on_roi_selection_changed(self):
        """Update size panel visibility and values."""
        if not hasattr(self.main_window, 'session'): return
        
        selected_ids = self.main_window.session.roi_manager.get_selected_ids()
        
        should_show = False
        if len(selected_ids) == 1:
            roi = self.main_window.session.roi_manager.get_roi(list(selected_ids)[0])
            if roi and roi.roi_type in ['rectangle', 'ellipse', 'circle']:
                should_show = True
                self._update_size_ui_from_roi(roi)
                
        self.size_group.setVisible(should_show)
        
    def _update_size_ui_from_roi(self, roi):
        """Sync UI with ROI geometry."""
        self._updating_size_ui = True
        try:
            rect = roi.path.boundingRect()
            w_px = rect.width()
            h_px = rect.height()
            
            # px to cm
            DPI = 96.0
            INCH_TO_CM = 2.54
            
            w_cm = w_px / DPI * INCH_TO_CM
            h_cm = h_px / DPI * INCH_TO_CM
            
            self.spin_width.setValue(w_cm)
            self.spin_height.setValue(h_cm)
        finally:
            self._updating_size_ui = False

    def on_polygon_context_menu(self, pos):
        """Handle right-click on Polygon button to switch to Freehand mode."""
        menu = QMenu(self)
        action_freehand = QAction(tr("Switch to Freehand Mode"), self)
        action_polygon = QAction(tr("Switch to Polygon Mode"), self)
        
        # Check current mode if possible
        is_freehand = False
        if hasattr(self.main_window, 'polygon_tool'):
            is_freehand = getattr(self.main_window.polygon_tool, 'is_freehand_mode', False)
        
        if is_freehand:
            action_polygon.setFont(QApplication.font()) # Make it look clickable
            action_freehand.setEnabled(False)
        else:
            action_freehand.setFont(QApplication.font())
            action_polygon.setEnabled(False)

        action_freehand.triggered.connect(lambda: self.set_polygon_mode('freehand'))
        action_polygon.triggered.connect(lambda: self.set_polygon_mode('polygon'))
        
        menu.addAction(action_freehand)
        menu.addAction(action_polygon)
        
        # Add Fixed Size toggle here too for convenience?
        menu.addSeparator()
        action_fixed = QAction(tr("Fixed Shape"), self)
        action_fixed.setCheckable(True)
        if hasattr(self, 'chk_fixed_size'):
            action_fixed.setChecked(self.chk_fixed_size.isChecked())
            action_fixed.triggered.connect(lambda checked: self.chk_fixed_size.setChecked(checked))
        menu.addAction(action_fixed)

        menu.exec(QCursor.pos())

    def set_polygon_mode(self, mode):
        # Activate the tool first
        if hasattr(self.main_window, 'action_polygon'):
            self.main_window.action_polygon.trigger()
            
        # Then configure it
        if hasattr(self.main_window, 'polygon_tool'):
            self.main_window.polygon_tool.is_freehand_mode = (mode == 'freehand')
            mode_text = tr("Freehand") if mode == 'freehand' else tr("Polygon")
            Logger.debug(f"Polygon Tool switched to {mode_text} mode")
            
            # If switching to freehand, maybe disable fixed size?
            # Or keep it independent.


    def create_wand_options_group(self):
        self.wand_group = QGroupBox(tr("Magic Wand Options"))
        layout = QVBoxLayout()
        layout.setSpacing(4)
        layout.setContentsMargins(2, 8, 2, 4) # Reduced margins

        # 1. Default Tolerance
        h_layout0 = QHBoxLayout()
        self.lbl_wand_tol = QLabel(tr("Default Tolerance:"))
        self.lbl_wand_tol.setMinimumWidth(0) # Allow shrinking
        h_layout0.addWidget(self.lbl_wand_tol)
        self.spin_wand_tol = QDoubleSpinBox()
        self.spin_wand_tol.setRange(0.0, 10000.0)
        self.spin_wand_tol.setSingleStep(10.0)
        self.spin_wand_tol.setValue(100.0)
        self.spin_wand_tol.setToolTip(tr("Initial tolerance when clicking. Drag to adjust."))
        h_layout0.addWidget(self.spin_wand_tol)
        layout.addLayout(h_layout0)

        # 2. Smoothing
        h_layout1 = QHBoxLayout()
        self.lbl_wand_smooth = QLabel(tr("Smoothing:"))
        self.lbl_wand_smooth.setMinimumWidth(0) # Allow shrinking
        h_layout1.addWidget(self.lbl_wand_smooth)
        self.spin_wand_smooth = QDoubleSpinBox()
        self.spin_wand_smooth.setRange(0.0, 5.0)
        self.spin_wand_smooth.setSingleStep(0.1)
        self.spin_wand_smooth.setValue(5.0)
        self.spin_wand_smooth.setToolTip(tr("Gaussian blur sigma for noise reduction before selection."))
        h_layout1.addWidget(self.spin_wand_smooth)
        layout.addLayout(h_layout1)

        # 2. Relative Tolerance
        h_layout_rel = QHBoxLayout()
        self.lbl_wand_relative = QLabel(tr("Relative Tolerance (%)"))
        self.chk_wand_relative = ToggleSwitch()
        self.chk_wand_relative.setToolTip(tr("If checked, tolerance is a percentage of the clicked pixel value.\nUseful for images with high dynamic range."))
        self.chk_wand_relative.setChecked(False)
        h_layout_rel.addWidget(self.lbl_wand_relative)
        h_layout_rel.addStretch()
        h_layout_rel.addWidget(self.chk_wand_relative)
        layout.addLayout(h_layout_rel)

        h_layout_largest = QHBoxLayout()
        self.lbl_wand_largest = QLabel(tr("Keep Largest Only"))
        self.chk_wand_largest = ToggleSwitch()
        self.chk_wand_largest.setToolTip(tr("Only keep the largest connected region in the selection"))
        self.chk_wand_largest.setChecked(False)
        h_layout_largest.addWidget(self.lbl_wand_largest)
        h_layout_largest.addStretch()
        h_layout_largest.addWidget(self.chk_wand_largest)
        layout.addLayout(h_layout_largest)

        h_layout_split = QHBoxLayout()
        self.lbl_wand_split = QLabel(tr("Split by Region"))
        self.chk_wand_split = ToggleSwitch()
        self.chk_wand_split.setToolTip(tr("Split each connected region into independent ROIs"))
        self.chk_wand_split.setChecked(False)
        h_layout_split.addWidget(self.lbl_wand_split)
        h_layout_split.addStretch()
        h_layout_split.addWidget(self.chk_wand_split)
        layout.addLayout(h_layout_split)

        h_layout_poly = QHBoxLayout()
        self.lbl_wand_poly = QLabel(tr("Convert to Polygon"))
        self.chk_wand_polygon = ToggleSwitch()
        self.chk_wand_polygon.setToolTip(tr("Convert the wand selection directly to editable polygon points after drawing"))
        self.chk_wand_polygon.setChecked(False)
        h_layout_poly.addWidget(self.lbl_wand_poly)
        h_layout_poly.addStretch()
        h_layout_poly.addWidget(self.chk_wand_polygon)
        layout.addLayout(h_layout_poly)

        h_layout_smooth = QHBoxLayout()
        self.lbl_wand_smooth_contour = QLabel(tr("Smooth Edges"))
        self.chk_wand_smooth_contour = ToggleSwitch()
        self.chk_wand_smooth_contour.setToolTip(tr("Smooth selection edges to reduce aliasing"))
        self.chk_wand_smooth_contour.setChecked(True)
        h_layout_smooth.addWidget(self.lbl_wand_smooth_contour)
        h_layout_smooth.addStretch()
        h_layout_smooth.addWidget(self.chk_wand_smooth_contour)
        layout.addLayout(h_layout_smooth)

        self.wand_group.setLayout(layout)
        self.layout.addWidget(self.wand_group)
        
        # Connect signals (to be handled by main window)
        self.spin_wand_tol.valueChanged.connect(self.on_wand_settings_changed)
        self.spin_wand_smooth.valueChanged.connect(self.on_wand_settings_changed)
        self.chk_wand_relative.toggled.connect(self.on_wand_settings_changed)
        self.chk_wand_largest.toggled.connect(self.on_wand_settings_changed)
        self.chk_wand_split.toggled.connect(self.on_wand_settings_changed)
        self.chk_wand_polygon.toggled.connect(self.on_wand_settings_changed)
        self.chk_wand_smooth_contour.toggled.connect(self.on_wand_settings_changed)

    def on_wand_settings_changed(self):
        # We'll let main.py pick up these values when the tool is active
        # or we can push them to the tool directly if it's already set.
        if hasattr(self.main_window, 'wand_tool'):
            self.main_window.wand_tool.base_tolerance = self.spin_wand_tol.value()
            self.main_window.wand_tool.smoothing = self.spin_wand_smooth.value()
            self.main_window.wand_tool.relative = self.chk_wand_relative.isChecked()
            self.main_window.wand_tool.keep_largest = self.chk_wand_largest.isChecked()
            self.main_window.wand_tool.split_regions = self.chk_wand_split.isChecked()
            self.main_window.wand_tool.convert_to_polygon = self.chk_wand_polygon.isChecked()
            self.main_window.wand_tool.contour_smoothing = self.chk_wand_smooth_contour.isChecked()
        
        self.save_settings()

    def load_settings(self):
        """Load persisted tool settings from QSettings."""
        # Magic Wand Settings
        self.spin_wand_tol.setValue(float(self.settings.value("wand/tolerance", 100.0)))
        self.spin_wand_smooth.setValue(float(self.settings.value("wand/smoothing", 5.0)))
        self.chk_wand_relative.setChecked(self.settings.value("wand/relative", False, type=bool))
        self.chk_wand_largest.setChecked(self.settings.value("wand/keep_largest", False, type=bool))
        self.chk_wand_split.setChecked(self.settings.value("wand/split_regions", False, type=bool))
        self.chk_wand_polygon.setChecked(self.settings.value("wand/convert_to_polygon", False, type=bool))
        self.chk_wand_smooth_contour.setChecked(self.settings.value("wand/contour_smoothing", True, type=bool))
        
        # Point Counter Settings
        self.spin_count_radius.setValue(float(self.settings.value("count/radius", 3.0)))
        
        # Fixed Shape
        self.chk_fixed_size.setChecked(self.settings.value("tools/fixed_shape", False, type=bool))

    def save_settings(self):
        """Save current tool settings to QSettings."""
        # Magic Wand Settings
        self.settings.setValue("wand/tolerance", self.spin_wand_tol.value())
        self.settings.setValue("wand/smoothing", self.spin_wand_smooth.value())
        self.settings.setValue("wand/relative", self.chk_wand_relative.isChecked())
        self.settings.setValue("wand/keep_largest", self.chk_wand_largest.isChecked())
        self.settings.setValue("wand/split_regions", self.chk_wand_split.isChecked())
        self.settings.setValue("wand/convert_to_polygon", self.chk_wand_polygon.isChecked())
        self.settings.setValue("wand/contour_smoothing", self.chk_wand_smooth_contour.isChecked())
        
        # Point Counter Settings
        self.settings.setValue("count/radius", self.spin_count_radius.value())
        
        # Fixed Shape
        self.settings.setValue("tools/fixed_shape", self.chk_fixed_size.isChecked())

    def create_count_options_group(self):
        self.count_group = QGroupBox(tr("Point Counter Options"))
        layout = QVBoxLayout()
        layout.setSpacing(4)
        layout.setContentsMargins(2, 8, 2, 4) # Reduced margins

        # 1. Point Radius
        h_layout0 = QHBoxLayout()
        self.lbl_point_size = QLabel(tr("Point Size:"))
        self.lbl_point_size.setMinimumWidth(0) # Allow shrinking
        h_layout0.addWidget(self.lbl_point_size)
        self.spin_count_radius = QDoubleSpinBox()
        self.spin_count_radius.setRange(0.5, 50.0)
        self.spin_count_radius.setSingleStep(0.5)
        self.spin_count_radius.setValue(3.0)
        self.spin_count_radius.setToolTip(tr("Radius of the point markers."))
        h_layout0.addWidget(self.spin_count_radius)
        layout.addLayout(h_layout0)

        # 2. Channel Settings Container
        self.channel_settings_layout = QVBoxLayout()
        self.channel_settings_layout.setContentsMargins(0, 0, 0, 0) # Remove internal margins
        layout.addLayout(self.channel_settings_layout)
        
        # 3. Counts Summary
        self.lbl_counts_summary = QLabel(tr("Counts: 0 total"))
        self.lbl_counts_summary.setWordWrap(True)
        self.lbl_counts_summary = QLabel(tr("Total: 0 Puncta"))
        self.lbl_counts_summary.setStyleSheet("font-weight: bold;")
        layout.addWidget(self.lbl_counts_summary)

        # --- NEW: Classification Table ---
        from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QStyle
        self.count_table = QTableWidget(0, 3)
        self.count_table.setHorizontalHeaderLabels([tr("Channel/Category"), tr("Count"), tr("%")])
        self.count_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.count_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.count_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.count_table.setFixedHeight(150)
        # Style is now handled by Global QSS
        layout.addWidget(self.count_table)

        # --- Controls: Reset and Category Management ---
        h_ctrl = QHBoxLayout()
        self.btn_reset_counts = QPushButton(tr("Reset Counts"))
        self.btn_reset_counts.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogDiscardButton))
        self.btn_reset_counts.clicked.connect(self.on_reset_counts_clicked)
        
        self.btn_manage_categories = QPushButton(tr("Categories..."))
        self.btn_manage_categories.setToolTip(tr("Manage custom point categories"))
        self.btn_manage_categories.clicked.connect(self.on_manage_categories_clicked)
        
        h_ctrl.addWidget(self.btn_reset_counts)
        h_ctrl.addWidget(self.btn_manage_categories)
        layout.addLayout(h_ctrl)

        # --- Category Selector for active tool ---
        h_cat = QHBoxLayout()
        h_cat.addWidget(QLabel(tr("Current Category:")))
        self.combo_active_category = QComboBox()
        # 将 Puncta 放在首位作为默认值
        self.combo_active_category.addItems([tr("Puncta"), tr("Cells"), tr("Nuclei"), tr("Other")])
        self.combo_active_category.currentIndexChanged.connect(self.on_active_category_changed)
        h_cat.addWidget(self.combo_active_category)
        layout.addLayout(h_cat)

        # Connect radius change to tool
        self.spin_count_radius.valueChanged.connect(self.on_count_radius_changed)
        
        # Connect table changes for filtering (NEW: Move out of update_counts_summary)
        self.count_table.itemChanged.connect(self.on_count_table_item_changed)
        
        self.count_group.setLayout(layout)
        self.layout.addWidget(self.count_group)
        self.count_group.hide() # Hidden by default

    def refresh_point_counter_channels(self):
        """Rebuilds the per-channel settings UI for Point Counter."""
        # Clear existing
        while self.channel_settings_layout.count():
            item = self.channel_settings_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                # Recursively delete layout items
                def clear_layout(layout):
                    while layout.count():
                        sub = layout.takeAt(0)
                        if sub.widget(): sub.widget().deleteLater()
                        elif sub.layout(): clear_layout(sub.layout())
                clear_layout(item.layout())
                item.layout().deleteLater()
        
        if not hasattr(self.main_window, 'session'):
            return

        # Header - 使用最小宽度允许缩放，并与下方对齐
        h_header = QHBoxLayout()
        lbl_ch = QLabel(tr("Channel"))
        lbl_ch.setMinimumWidth(0)
        lbl_ch.setStyleSheet("font-weight: bold;")
        
        lbl_sh = QLabel(tr("Shape"))
        lbl_sh.setMinimumWidth(0)
        lbl_sh.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_sh.setStyleSheet("font-weight: bold;")
        
        lbl_sz = QLabel(tr("Size"))
        lbl_sz.setMinimumWidth(0)
        lbl_sz.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_sz.setStyleSheet("font-weight: bold;")
        
        lbl_co = QLabel(tr("Color"))
        lbl_co.setMinimumWidth(0)
        lbl_co.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_co.setStyleSheet("font-weight: bold;")
        
        # 初始宽度分配 - 使用 minimumWidth 而不是 fixedWidth 以允许在极窄模式下压缩
        lbl_ch.setMinimumWidth(0)
        lbl_sh.setMinimumWidth(0)
        lbl_sz.setMinimumWidth(0)
        lbl_co.setMinimumWidth(0)
        
        lbl_ch.setMaximumWidth(60)
        lbl_sh.setMaximumWidth(70)
        lbl_sz.setMaximumWidth(50)
        lbl_co.setMaximumWidth(30)
        
        h_header.addWidget(lbl_ch)
        h_header.addWidget(lbl_sh)
        h_header.addWidget(lbl_sz)
        h_header.addWidget(lbl_co)
        h_header.addStretch() # 添加弹簧防止撑开
        self.channel_settings_layout.addLayout(h_header)

        # Iterate channels
        if hasattr(self.main_window.session, 'channels'):
            for i, ch in enumerate(self.main_window.session.channels):
                self._add_channel_row(i, ch.name, ch.display_settings.color)
            
        # Add "Merge/Default" row
        self._add_channel_row(-1, tr("Merge/Default"), "#FFFFFF")

        # Target Selector
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        self.channel_settings_layout.addWidget(line)
        
        h_target = QHBoxLayout()
        self.lbl_count_target = QLabel(tr("Active Target:"))
        h_target.addWidget(self.lbl_count_target)
        self.combo_count_target = QComboBox()
        self.combo_count_target.addItem(tr("Auto (View Context)"), -1)
        if hasattr(self.main_window.session, 'channels'):
            for i, ch in enumerate(self.main_window.session.channels):
                self.combo_count_target.addItem(ch.name, i)
        
        # Restore previous selection if valid
        if hasattr(self.main_window, 'count_tool'):
             idx = self.combo_count_target.findData(self.main_window.count_tool.target_channel_idx)
             if idx >= 0: self.combo_count_target.setCurrentIndex(idx)
             
        self.combo_count_target.currentIndexChanged.connect(self.on_count_target_changed)
        h_target.addWidget(self.combo_count_target)
        self.channel_settings_layout.addLayout(h_target)
        
        # 强制更新布局
        self.channel_settings_layout.activate()

    def _add_channel_row(self, ch_idx, name, default_color):
        # 从工具中获取当前配置，如果没有则使用默认
        current_shape = "circle"
        current_radius = 3.0
        current_color = default_color
        
        if hasattr(self.main_window, 'count_tool'):
            color_obj, current_shape, current_radius = self.main_window.count_tool._get_channel_config(ch_idx)
            current_color = color_obj.name()

        h_row = QHBoxLayout()
        h_row.setSpacing(4) # 紧凑布局
        
        # Label
        lbl = QLabel(f"{name}:")
        lbl.setMinimumWidth(0)
        lbl.setMaximumWidth(60)
        lbl.setToolTip(name) # 长的通道名可以悬浮查看
        
        # Shape
        combo_shape = QComboBox()
        combo_shape.setMinimumWidth(0)
        for text, data in [
            (tr("Circle"), "circle"),
            (tr("Square"), "square"),
            (tr("Triangle"), "triangle"),
            (tr("Cross"), "cross"),
            (tr("Diamond"), "diamond")
        ]:
            combo_shape.addItem(text, data)
        combo_shape.setMaximumWidth(70)
        
        # 设置当前选中的形状
        idx = combo_shape.findData(current_shape)
        if idx >= 0: combo_shape.setCurrentIndex(idx)
        
        combo_shape.currentIndexChanged.connect(lambda idx, ch=ch_idx, cb=combo_shape: self._update_channel_shape(ch, cb.currentData()))
        
        # Size (Radius)
        spin_size = QDoubleSpinBox()
        spin_size.setMinimumWidth(0)
        spin_size.setRange(0.5, 50.0)
        spin_size.setSingleStep(0.5)
        spin_size.setValue(current_radius) # 使用当前半径
        spin_size.setMaximumWidth(50)
        spin_size.setToolTip(tr("Point Radius"))
        spin_size.valueChanged.connect(lambda val, i=ch_idx: self._update_channel_radius(i, val))

        # Color
        btn_color = QPushButton()
        btn_color.setProperty("role", "color_picker")
        btn_color.setToolTip(tr("Select Point Color"))
        # 使用当前颜色
        btn_color.setStyleSheet(f"background-color: {current_color}; border: 1px solid #dcdde1; border-radius: 2px;")
        btn_color.setFixedSize(24, 24)
        btn_color.clicked.connect(lambda checked=False, i=ch_idx, b=btn_color: self._pick_channel_color(i, b))
        
        # 居中对齐容器
        c_color = QWidget()
        c_color.setMinimumWidth(0)
        c_color.setMaximumWidth(30)
        cl = QHBoxLayout(c_color)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(btn_color)

        h_row.addWidget(lbl)
        h_row.addWidget(combo_shape)
        h_row.addWidget(spin_size)
        h_row.addWidget(c_color)
        h_row.addStretch() # 对应表头的弹簧
        
        self.channel_settings_layout.addLayout(h_row)
        
        # 不需要再次强制 push initial values，因为我们已经读取了当前状态并设置了信号连接

    def _pick_channel_color(self, ch_idx, btn):
        current_color = QColor(btn.palette().color(QPalette.ColorRole.Button))
        color = QColorDialog.getColor(current_color, self, tr("Select Point Color"))
        if color.isValid():
            hex_color = color.name()
            btn.setStyleSheet(f"background-color: {hex_color};")
            if hasattr(self.main_window, 'count_tool'):
                self.main_window.count_tool.set_channel_color_override(ch_idx, hex_color)

    def _update_channel_shape(self, ch_idx, shape):
        if hasattr(self.main_window, 'count_tool'):
            self.main_window.count_tool.set_channel_shape(ch_idx, shape)

    def _update_channel_radius(self, ch_idx, radius):
        if hasattr(self.main_window, 'count_tool'):
            self.main_window.count_tool.set_channel_radius(ch_idx, radius)

    def on_count_radius_changed(self, value):
        if hasattr(self.main_window, 'count_tool'):
            self.main_window.count_tool.radius = value
            
        # Also update selected point ROIs
        if hasattr(self.main_window, 'session'):
            selected_rois = [r for r in self.main_window.session.roi_manager.get_all_rois() 
                             if r.selected and r.roi_type == "point"]
            if selected_rois:
                for roi in selected_rois:
                    roi.properties['radius'] = value
                    # Trigger reconstruction to update the path
                    roi.reconstruct_from_points(roi.points)
                
                # Notify session about changes
                self.main_window.session.data_changed.emit()
                Logger.info(f"[RoiToolbox] Updated radius to {value} for {len(selected_rois)} selected points")
        
        self.save_settings()

    def on_count_target_changed(self, index):
        if hasattr(self.main_window, 'count_tool'):
            target_idx = self.combo_count_target.currentData()
            self.main_window.count_tool.target_channel_idx = target_idx

    def set_active_tool(self, tool_action):
        """Switches visible option groups based on the active tool."""
        # Use simple string-based identification to avoid reference mismatch
        tool_name = tool_action.objectName() if tool_action else ""
        tool_text = tool_action.text().lower() if tool_action else ""
        
        Logger.debug(f"[RoiToolbox.set_active_tool] ENTER - Tool: {tool_text} (ID: {tool_name})")
        
        # Hide all specific groups initially
        self.wand_group.hide()
        self.count_group.hide()
        
        is_wand = "wand" in tool_name or (hasattr(self.main_window, 'action_wand') and tool_action == self.main_window.action_wand)
        is_count = "count" in tool_name or (hasattr(self.main_window, 'action_count') and tool_action == self.main_window.action_count)
        
        # Show relevant group
        if is_wand:
            self.wand_group.show()
            Logger.debug("[RoiToolbox.set_active_tool] Showing Wand Group")
        elif is_count:
            try:
                # 先显示组，再刷新内容，有助于 Qt 计算布局
                self.count_group.show()
                self.refresh_point_counter_channels()
                self.update_counts_summary()
                
                # 显式同步一次分类设置，确保即使不手动切换也能正确统计 Puncta
                self.on_active_category_changed(self.combo_active_category.currentIndex())
                
                Logger.debug("[RoiToolbox.set_active_tool] Showing Count Group")
            except Exception as e:
                Logger.debug(f"[RoiToolbox.set_active_tool] Error showing count group: {e}")
        
        # FORCE UI REFRESH: This is critical for nested layouts
        self.updateGeometry()
        if self.parentWidget():
            self.parentWidget().updateGeometry()
            self.parentWidget().repaint()
        
        Logger.debug("[RoiToolbox.set_active_tool] EXIT")

    def on_active_category_changed(self, index):
        """Sync the selected category to the PointCounterTool."""
        category = self.combo_active_category.currentText()
        if hasattr(self.main_window, 'count_tool'):
            # Store the active category in the tool for new ROIs
            if not hasattr(self.main_window.count_tool, 'active_category'):
                self.main_window.count_tool.active_category = "Puncta" # 修改默认值为 Puncta
            self.main_window.count_tool.active_category = category
            Logger.debug(f"[RoiToolbox] Set active point category to: {category}")

    def on_reset_counts_clicked(self):
        """Clears all point ROIs after confirmation."""
        from PySide6.QtWidgets import QMessageBox
        reply = QMessageBox.question(self, tr("Reset Counts"), 
                                   tr("Are you sure you want to delete ALL point count ROIs? This cannot be undone."),
                                   QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        
        if reply == QMessageBox.StandardButton.Yes:
            if not hasattr(self.main_window, 'session'): return
            
            # Find all point ROIs
            rois_to_remove = [r.id for r in self.main_window.session.roi_manager.get_all_rois() 
                             if r.roi_type == "point" or r.label.startswith("Point_")]
            
            if rois_to_remove:
                for roi_id in rois_to_remove:
                    self.main_window.session.roi_manager.remove_roi(roi_id, undoable=True)
                Logger.info(f"[RoiToolbox] Reset counts: removed {len(rois_to_remove)} points")
                self.update_counts_summary()

    def on_manage_categories_clicked(self):
        """Dialog to add/remove custom categories."""
        from PySide6.QtWidgets import QInputDialog
        text, ok = QInputDialog.getText(self, tr("Manage Categories"), 
                                      tr("Add new category (comma separated):"),
                                      text=", ".join([self.combo_active_category.itemText(i) for i in range(self.combo_active_category.count())]))
        if ok and text:
            new_cats = [c.strip() for c in text.split(",") if c.strip()]
            self.combo_active_category.clear()
            self.combo_active_category.addItems(new_cats)
            # Notify tool if needed
            self.on_active_category_changed(0)

    def update_counts_summary(self):
        """
        Comprehensive update of count statistics.
        Calculates counts per channel and per category, including percentages.
        """
        Logger.debug("[RoiToolbox.update_counts_summary] ENTER")
        try:
            if not hasattr(self.main_window, 'session'):
                return
                
            rois = self.main_window.session.roi_manager.get_all_rois()
            # Filter for point ROIs (both by type and label convention)
            point_rois = [r for r in rois if r.roi_type == "point" or r.label.startswith("Point_")]
            
            total = len(point_rois)
            if hasattr(self, 'lbl_counts_summary'):
                self.lbl_counts_summary.setText(tr("Counts: {0} total").format(total))
            
            # 1. Gather Data: Breakdown by Channel and Category
            # ... (stats gathering logic same) ...
            stats = {}
            for r in point_rois:
                ch_idx = r.channel_index
                ch_name = tr("Merge") if ch_idx == -1 else (self.main_window.session.get_channel(ch_idx).name if self.main_window.session.get_channel(ch_idx) else f"Ch {ch_idx}")
                category = r.properties.get('category', 'Puncta') # 兜底值从 Other 改为 Puncta
                if ch_name not in stats: stats[ch_name] = {}
                stats[ch_name][category] = stats[ch_name].get(category, 0) + 1
                
            # 2. Update Table
            if hasattr(self, 'count_table'):
                # BLOCK SIGNALS to prevent recursion during table population
                self.count_table.blockSignals(True)
                from PySide6.QtWidgets import QTableWidgetItem
                self.count_table.setRowCount(0)
                
                sorted_channels = sorted(stats.keys())
                for ch in sorted_channels:
                     ch_total = sum(stats[ch].values())
                     row = self.count_table.rowCount()
                     self.count_table.insertRow(row)
                     
                     ch_item = QTableWidgetItem(ch)
                     ch_item.setFlags(ch_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                     ch_item.setCheckState(Qt.CheckState.Checked)
                     # 优化：使用浅色背景和深色加粗文字
                     ch_item.setBackground(QColor("#dfe6e9"))
                     ch_item.setForeground(QColor("#2d3436"))
                     font = ch_item.font()
                     font.setBold(True)
                     ch_item.setFont(font)
                     ch_item.setData(Qt.ItemDataRole.UserRole, ("channel", ch))
                     self.count_table.setItem(row, 0, ch_item)
                     self.count_table.setItem(row, 1, QTableWidgetItem(str(ch_total)))
                     perc = (ch_total / total * 100) if total > 0 else 0
                     self.count_table.setItem(row, 2, QTableWidgetItem(f"{perc:.1f}%"))
                     
                     for cat in sorted(stats[ch].keys()):
                         cat_count = stats[ch][cat]
                         row = self.count_table.rowCount()
                         self.count_table.insertRow(row)
                         cat_item = QTableWidgetItem(f"  └ {cat}")
                         cat_item.setFlags(cat_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                         cat_item.setCheckState(Qt.CheckState.Checked)
                         cat_item.setForeground(QColor("#636e72")) # 中深灰色，用于区分层级
                         cat_item.setData(Qt.ItemDataRole.UserRole, ("category", ch, cat))
                         self.count_table.setItem(row, 0, cat_item)
                         
                         count_item = QTableWidgetItem(str(cat_count))
                         count_item.setForeground(QColor("#2d3436"))
                         self.count_table.setItem(row, 1, count_item)
                         
                         cat_perc = (cat_count / ch_total * 100) if ch_total > 0 else 0
                         perc_item = QTableWidgetItem(f"{cat_perc:.1f}%")
                         perc_item.setForeground(QColor("#2d3436"))
                         self.count_table.setItem(row, 2, perc_item)
                
                # UNBLOCK SIGNALS
                self.count_table.blockSignals(False)
        except Exception as e:
            Logger.error(f"[RoiToolbox.update_counts_summary] Error: {e}")
            import traceback
            Logger.error(traceback.format_exc())
            if hasattr(self, 'count_table'):
                self.count_table.blockSignals(False)
            
        Logger.debug("[RoiToolbox.update_counts_summary] EXIT")

    def on_count_table_item_changed(self, item):
        """Handle checkbox toggling to filter ROI visibility."""
        if item.column() != 0: return
        
        data = item.data(Qt.ItemDataRole.UserRole)
        if not data or not hasattr(self.main_window, 'session'): return
        
        is_visible = (item.checkState() == Qt.CheckState.Checked)
        
        rois = self.main_window.session.roi_manager.get_all_rois()
        point_rois = [r for r in rois if r.roi_type == "point" or r.label.startswith("Point_")]
        
        if data[0] == "channel":
            target_ch_name = data[1]
            for r in point_rois:
                # Determine channel name
                ch_idx = r.channel_index
                if ch_idx == -1: ch_name = tr("Merge")
                else:
                    ch = self.main_window.session.get_channel(ch_idx)
                    ch_name = ch.name if ch else f"Ch {ch_idx}"
                
                if ch_name == target_ch_name:
                    r.visible = is_visible
                    self.main_window.session.roi_manager.roi_updated.emit(r)
                    
        elif data[0] == "category":
            target_ch_name = data[1]
            target_cat = data[2]
            for r in point_rois:
                ch_idx = r.channel_index
                if ch_idx == -1: ch_name = tr("Merge")
                else:
                    ch = self.main_window.session.get_channel(ch_idx)
                    ch_name = ch.name if ch else f"Ch {ch_idx}"
                
                cat = r.properties.get('category', 'Puncta')
                
                if ch_name == target_ch_name and cat == target_cat:
                    r.visible = is_visible
                    self.main_window.session.roi_manager.roi_updated.emit(r)

    def create_analysis_group(self):
        self.analysis_group = QGroupBox(tr("Analysis"))
        layout = QGridLayout()
        layout.setSpacing(4)
        layout.setContentsMargins(2, 8, 2, 4) # Reduced margins
        
        # Analysis buttons definitions: (action, row, col)
        analysis_tools = [
            (self.main_window.action_measure, 0, 0, 1, 2),
            (self.main_window.action_export, 1, 0),
            (self.main_window.action_export_images, 1, 1),
            (self.main_window.action_settings, 2, 0, 1, 2),
        ]
        
        for tool_info in analysis_tools:
            action = tool_info[0]
            row, col = tool_info[1], tool_info[2]
            # Use IconOnly for consistency
            btn = self.create_button(action)
            # btn.setFixedHeight(38) # REMOVED: Allow shrinking height in compact mode
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred) # Flexible height
            
            if len(tool_info) > 3:
                layout.addWidget(btn, row, col, tool_info[3], tool_info[4])
            else:
                layout.addWidget(btn, row, col)
        
        self.analysis_group.setLayout(layout)
        self.layout.addWidget(self.analysis_group)

    def retranslate_ui(self):
        """Updates UI text based on current language."""
        self.tools_group.setTitle(tr("Tools"))
        self.lbl_fixed_size.setText(tr("Fixed Shape"))
        self.chk_fixed_size.setToolTip(tr("Lock ROI size to the last drawn shape"))
        
        self.size_group.setTitle(tr("Selection Size"))
        # No easy way to find the QLabel(tr("W:")) without storing it, 
        # but the suffix can be updated.
        self.spin_width.setSuffix(tr(" cm"))
        self.spin_height.setSuffix(tr(" cm"))
        
        self.wand_group.setTitle(tr("Magic Wand Options"))
        self.lbl_wand_tol.setText(tr("Default Tolerance:"))
        self.spin_wand_tol.setToolTip(tr("Initial tolerance when clicking. Drag to adjust."))
        self.lbl_wand_smooth.setText(tr("Smoothing:"))
        self.spin_wand_smooth.setToolTip(tr("Gaussian blur sigma for noise reduction before selection."))
        self.lbl_wand_relative.setText(tr("Relative Tolerance (%)"))
        self.chk_wand_relative.setToolTip(tr("If checked, tolerance is a percentage of the clicked pixel value.\nUseful for images with high dynamic range."))
        
        self.lbl_wand_largest.setText(tr("Keep Largest Only"))
        self.chk_wand_largest.setToolTip(tr("Only keep the largest connected region in the selection"))
        self.lbl_wand_split.setText(tr("Split by Region"))
        self.chk_wand_split.setToolTip(tr("Split each connected region into independent ROIs"))
        self.lbl_wand_poly.setText(tr("Convert to Polygon"))
        self.chk_wand_polygon.setToolTip(tr("Convert the wand selection directly to editable polygon points after drawing"))
        self.lbl_wand_smooth_contour.setText(tr("Smooth Edges"))
        self.chk_wand_smooth_contour.setToolTip(tr("Smooth selection edges to reduce aliasing"))

        self.count_group.setTitle(tr("Point Counter Options"))
        self.lbl_point_size.setText(tr("Point Size:"))
        self.spin_count_radius.setToolTip(tr("Radius of the point markers."))
        
        if hasattr(self, 'lbl_count_target'):
            self.lbl_count_target.setText(tr("Active Target:"))
        
        if hasattr(self, 'combo_count_target'):
            self.combo_count_target.setItemText(0, tr("Auto (Current View)"))
            self.combo_count_target.setToolTip(tr("When clicking in Merge view, count will be assigned to this channel."))
            
        self.btn_reset_counts.setText(tr("Reset Counts"))
        self.btn_manage_categories.setText(tr("Categories..."))
        self.btn_manage_categories.setToolTip(tr("Manage custom point categories"))
        
        # Update Table Headers
        self.count_table.setHorizontalHeaderLabels([tr("Channel/Category"), tr("Count"), tr("%")])
        
        self.update_counts_summary()
        
        self.analysis_group.setTitle(tr("Analysis"))

    def create_button(self, action):
        btn = QToolButton()
        btn.setDefaultAction(action)
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        btn.setIconSize(QSize(20, 20))
        # Ensure it takes full width in grid if needed
        btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        return btn

    def refresh_icons(self):
        """Re-sets icons for all tool buttons to match the current theme."""
        # Main tools are linked to main_window actions
        # When we call action.setIcon, all buttons linked to it update.
        # But we need to know the icon name for each action.
        
        icon_map = {
            self.main_window.action_wand: "wand",
            self.main_window.action_polygon: "polygon",
            self.main_window.action_rect: "rect",
            self.main_window.action_ellipse: "ellipse",
            self.main_window.action_count: "count",
            self.main_window.action_pan: "hand",
            self.main_window.action_crop: "crop",
            self.main_window.action_clear: "clear",
            self.main_window.action_undo: "undo",
            self.main_window.action_redo: "redo",
            self.main_window.action_batch_select: "batch_select"
        }
        
        for action, icon_name in icon_map.items():
            action.setIcon(get_icon(icon_name))
            
        # Specific buttons in this panel
        if hasattr(self, 'btn_reset_counts'):
            self.btn_reset_counts.setIcon(get_icon("refresh"))
        if hasattr(self, 'btn_manage_categories'):
            self.btn_manage_categories.setIcon(get_icon("settings"))

    def resizeEvent(self, event):
        width = self.width()
        
        # 1. 状态阈值定义
        is_compact = width < 120
        is_transition = 120 <= width < 220
        is_comfort = width >= 220
        
        # 2. 按钮进化逻辑
        icon_size = 20
        for btn in self.findChildren(QToolButton):
            # 跳过非本面板管理的按钮
            if btn.parent() and "nav_btn" in btn.objectName():
                continue
                
            if is_compact:
                # 紧凑模式：纯图标，固定尺寸
                btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
                btn.setFixedSize(28, 28)
                btn.setIconSize(QSize(icon_size, icon_size))
            elif is_transition:
                # 过渡模式：弹性拉伸，高度固定
                btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
                btn.setMinimumHeight(24) # Reduced from 28
                btn.setMaximumHeight(32)
                btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
                # 取消宽度限制
                btn.setMinimumWidth(0)
                btn.setMaximumWidth(16777215)
            else:
                # 舒适模式：显示文字 + 图标，更宽大
                btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
                btn.setMinimumHeight(30) # Reduced from 34
                btn.setIconSize(QSize(icon_size, icon_size))
                btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
                btn.setMinimumWidth(0)
                btn.setMaximumWidth(16777215)

        # 3. 标签（QLabel）隐藏逻辑：宽度极窄时隐藏文字以允许进一步压缩
        for lbl in self.findChildren(QLabel):
            # 排除已经是 Icon 或特殊的 Label
            if lbl.text() and not lbl.pixmap():
                if width < 100:
                    lbl.setMinimumWidth(0)
                    lbl.setMaximumWidth(0) # 强制隐藏文字空间
                    lbl.setVisible(False)
                else:
                    lbl.setMinimumWidth(0)
                    lbl.setMaximumWidth(16777215)
                    lbl.setVisible(True)

        # 4. 通道配置行 (210px 矛盾点) 优化逻辑
        # 我们遍历所有的通道设置行布局，根据宽度切换方向
        if hasattr(self, 'channel_settings_layout'):
            is_ultra_compact = width < 100
            for i in range(self.channel_settings_layout.count()):
                item = self.channel_settings_layout.itemAt(i)
                if item and item.layout() and isinstance(item.layout(), QHBoxLayout):
                    layout = item.layout()
                    
                    if is_ultra_compact:
                        # 极端窄模式：只显示颜色块，隐藏其他
                        for j in range(layout.count()):
                            w = layout.itemAt(j).widget()
                            if w:
                                # 只有颜色按钮容器保持可见
                                is_color_container = isinstance(w, QWidget) and w.findChild(QPushButton)
                                w.setVisible(is_color_container)
                                if is_color_container:
                                    w.setMinimumWidth(0)
                                    w.setMaximumWidth(width - 10)
                    elif is_compact:
                        # 紧凑模式：压缩宽度，隐藏 Label
                        for j in range(layout.count()):
                            w = layout.itemAt(j).widget()
                            if w:
                                w.setVisible(True)
                                if j == 0: # Label
                                    w.setVisible(False)
                                elif j == 1: # Shape
                                    w.setMinimumWidth(0)
                                    w.setMaximumWidth(max(40, width // 3))
                                elif j == 2: # Size
                                    w.setMinimumWidth(0)
                                    w.setMaximumWidth(max(30, width // 4))
                                elif j == 3: # Color
                                    w.setMinimumWidth(0)
                                    w.setMaximumWidth(30)
                    else:
                        # 恢复所有可见性
                        for j in range(layout.count()):
                            w = layout.itemAt(j).widget()
                            if w:
                                w.setVisible(True)
                                if j == 0: 
                                    w.setMinimumWidth(0)
                                    w.setMaximumWidth(60)
                                elif j == 1: 
                                    w.setMinimumWidth(0)
                                    w.setMaximumWidth(70)
                                elif j == 2: 
                                    w.setMinimumWidth(0)
                                    w.setMaximumWidth(50)
                                elif j == 3: 
                                    w.setMinimumWidth(0)
                                    w.setMaximumWidth(30)

        super().resizeEvent(event)
