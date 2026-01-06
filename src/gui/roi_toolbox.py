from PySide6.QtWidgets import (QWidget, QVBoxLayout, QGridLayout, QToolButton, 
                               QGroupBox, QLabel, QSizePolicy, QCheckBox, QDoubleSpinBox, QHBoxLayout,
                               QApplication, QComboBox, QPushButton, QColorDialog, QMenu)
from PySide6.QtCore import Qt, QSize, QSettings
from PySide6.QtGui import QPalette, QColor, QCursor, QAction
from src.core.language_manager import tr, LanguageManager
from src.core.logger import Logger

class RoiToolbox(QWidget):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.main_window = main_window
        
        # Allow panel to shrink very small
        self.setMinimumWidth(50)
        
        # Main Layout
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(5, 5, 5, 5)
        self.layout.setSpacing(10)
        
        # 1. Tools Group (Selection + Edit)
        self.create_tools_group()
        
        # 2. Wand Options (Hidden by default or separate group)
        self.create_wand_options_group()
        
        # 3. Point Counter Options
        self.create_count_options_group()
        
        # 4. Analysis Group
        self.create_analysis_group()
        
        # Connect Language Change
        LanguageManager.instance().language_changed.connect(self.retranslate_ui)
        
        # Spacer at bottom
        self.layout.addStretch()

    def create_tools_group(self):
        self.tools_group = QGroupBox(tr("Tools"))
        layout = QGridLayout()
        layout.setSpacing(4)
        layout.setContentsMargins(2, 8, 2, 4) # Reduced margins
        
        # Tools definitions: (action_name, row, col, [row_span, col_span])
        self.main_window.action_export.setText(tr("导出测量结果"))
        
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
            (self.main_window.action_batch_select, 5, 0, 1, 2),
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
        self.chk_fixed_size = QCheckBox(tr("Fixed Shape"))
        self.chk_fixed_size.setToolTip(tr("Lock ROI size to the last drawn shape"))
        layout.addWidget(self.chk_fixed_size, 7, 0, 1, 2)

        # Sync ROIs as Annotations
        self.chk_sync_rois = QCheckBox(tr("Sync ROIs as Annotations"))
        self.settings = QSettings("FluoQuantPro", "AppSettings")
        sync_default = self.settings.value("interface/sync_rois_as_annotations", True, type=bool)
        self.chk_sync_rois.setChecked(sync_default)
        self.chk_sync_rois.setToolTip(tr("Automatically include ROIs in annotation list and exports"))
        self.chk_sync_rois.toggled.connect(self._on_sync_rois_toggled)
        layout.addWidget(self.chk_sync_rois, 8, 0, 1, 2)

        self.tools_group.setLayout(layout)
        self.layout.addWidget(self.tools_group)
                
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

    def _on_sync_rois_toggled(self, checked):
        """Persist the sync setting and notify related components."""
        self.settings.setValue("interface/sync_rois_as_annotations", checked)
        # Update session property if it exists
        if hasattr(self.main_window, 'session'):
            if hasattr(self.main_window.session, 'sync_rois_as_annotations'):
                self.main_window.session.sync_rois_as_annotations = checked
            
            # USER REQUEST: When enabled, convert existing ROIs to annotations too
            if checked:
                Logger.info("[RoiToolbox] Sync enabled: Converting existing ROIs to annotations...")
                self.main_window.session.sync_existing_rois_to_annotations()
        
        # Notify annotation panel to refresh if needed
        if hasattr(self.main_window, 'annotation_panel'):
            self.main_window.annotation_panel.annotation_updated.emit()
        
        Logger.info(f"[RoiToolbox] Sync ROIs as Annotations: {checked}")

    def set_polygon_mode(self, mode):
        # Activate the tool first
        if hasattr(self.main_window, 'action_polygon'):
            self.main_window.action_polygon.trigger()
            
        # Then configure it
        if hasattr(self.main_window, 'polygon_tool'):
            self.main_window.polygon_tool.is_freehand_mode = (mode == 'freehand')
            mode_text = tr("Freehand") if mode == 'freehand' else tr("Polygon")
            print(f"Polygon Tool switched to {mode_text} mode")
            
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
        self.spin_wand_smooth.setValue(1.0)
        self.spin_wand_smooth.setToolTip(tr("Gaussian blur sigma for noise reduction before selection."))
        h_layout1.addWidget(self.spin_wand_smooth)
        layout.addLayout(h_layout1)

        # 2. Relative Tolerance
        self.chk_wand_relative = QCheckBox(tr("Relative Tolerance (%)"))
        self.chk_wand_relative.setToolTip(tr("If checked, tolerance is a percentage of the clicked pixel value.\nUseful for images with high dynamic range."))
        self.chk_wand_relative.setChecked(False)
        layout.addWidget(self.chk_wand_relative)

        self.wand_group.setLayout(layout)
        self.layout.addWidget(self.wand_group)
        
        # Connect signals (to be handled by main window)
        self.spin_wand_tol.valueChanged.connect(self.on_wand_settings_changed)
        self.spin_wand_smooth.valueChanged.connect(self.on_wand_settings_changed)
        self.chk_wand_relative.stateChanged.connect(self.on_wand_settings_changed)

    def on_wand_settings_changed(self):
        # We'll let main.py pick up these values when the tool is active
        # or we can push them to the tool directly if it's already set.
        if hasattr(self.main_window, 'wand_tool'):
            self.main_window.wand_tool.base_tolerance = self.spin_wand_tol.value()
            self.main_window.wand_tool.smoothing = self.spin_wand_smooth.value()
            self.main_window.wand_tool.relative = self.chk_wand_relative.isChecked()

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
        self.lbl_counts_summary.setWordWrap(True) # Allow wrapping
        self.lbl_counts_summary.setProperty("role", "accent")
        layout.addWidget(self.lbl_counts_summary)
        
        # Connect radius change to tool
        self.spin_count_radius.valueChanged.connect(self.on_count_radius_changed)

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
        
        if not hasattr(self.main_window, 'session'):
            return

        # Header
        h_header = QHBoxLayout()
        h_header.addWidget(QLabel(tr("Channel")))
        h_header.addWidget(QLabel(tr("Shape")))
        h_header.addWidget(QLabel(tr("Color")))
        self.channel_settings_layout.addLayout(h_header)

        # Iterate channels
        for i, ch in enumerate(self.main_window.session.channels):
            self._add_channel_row(i, ch.name, ch.display_settings.color)
            
        # Add "Merge/Default" row for cases where no specific channel is targeted (or explicitly Merge)
        self._add_channel_row(-1, tr("Merge/Default"), "#FFFFFF")

        # Target Selector
        h_target = QHBoxLayout()
        self.lbl_count_target = QLabel(tr("Active Target:"))
        h_target.addWidget(self.lbl_count_target)
        self.combo_count_target = QComboBox()
        self.combo_count_target.addItem(tr("Auto (View Context)"), -1)
        for i, ch in enumerate(self.main_window.session.channels):
            self.combo_count_target.addItem(ch.name, i)
        
        # Restore previous selection if valid
        if hasattr(self.main_window, 'count_tool'):
             idx = self.combo_count_target.findData(self.main_window.count_tool.target_channel_idx)
             if idx >= 0: self.combo_count_target.setCurrentIndex(idx)
             
        self.combo_count_target.currentIndexChanged.connect(self.on_count_target_changed)
        h_target.addWidget(self.combo_count_target)
        self.channel_settings_layout.addLayout(h_target)

    def _add_channel_row(self, ch_idx, name, default_color):
        h_row = QHBoxLayout()
        
        # Label
        lbl = QLabel(f"{name}:")
        lbl.setFixedWidth(60)
        
        # Shape
        combo_shape = QComboBox()
        combo_shape.addItems([tr("Circle"), tr("Square"), tr("Triangle")])
        combo_shape.setItemData(0, "circle")
        combo_shape.setItemData(1, "square")
        combo_shape.setItemData(2, "triangle")
        combo_shape.currentIndexChanged.connect(lambda idx: self._update_channel_shape(ch_idx, combo_shape.currentData()))
        
        # Color
        btn_color = QPushButton()
        btn_color.setProperty("role", "color_picker")
        btn_color.setToolTip(tr("Select Point Color"))
        # Only set background color via style, others handled by role="color_picker"
        btn_color.setStyleSheet(f"background-color: {default_color};")
        btn_color.clicked.connect(lambda checked=False, i=ch_idx, b=btn_color: self._pick_channel_color(i, b))
        
        h_row.addWidget(lbl)
        h_row.addWidget(combo_shape)
        h_row.addWidget(btn_color)
        self.channel_settings_layout.addLayout(h_row)
        
        # Push initial values to tool
        self._update_channel_shape(ch_idx, "circle")
        # Color is assumed default from channel unless changed here

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

    def on_count_target_changed(self, index):
        if hasattr(self.main_window, 'count_tool'):
            target_idx = self.combo_count_target.currentData()
            self.main_window.count_tool.target_channel_idx = target_idx

    def set_active_tool(self, tool_action):
        """Switches visible option groups based on the active tool."""
        # Hide all specific groups
        self.wand_group.hide()
        self.count_group.hide()
        
        # Show relevant group
        if tool_action == self.main_window.action_wand:
            self.wand_group.show()
        elif tool_action == self.main_window.action_count:
            self.count_group.show()
            self.update_counts_summary()

    def update_counts_summary(self):
        """Updates the count summary label based on existing point ROIs."""
        if not hasattr(self.main_window, 'session'):
            return
            
        rois = self.main_window.session.roi_manager.get_all_rois()
        point_rois = [r for r in rois if r.label.startswith("Point_")]
        
        total = len(point_rois)
        
        # Breakdown by channel name (extracted from label)
        channel_counts = {}
        for r in point_rois:
            # Label format: Point_{ChannelName}_{Index}
            # We want to extract ChannelName
            if r.label.startswith("Point_"):
                # Remove prefix
                name_part = r.label[6:] 
                # Remove trailing index (last _ part)
                if "_" in name_part:
                    ch_name = name_part.rsplit("_", 1)[0]
                    channel_counts[ch_name] = channel_counts.get(ch_name, 0) + 1
        
        summary_text = tr("Counts: {0} total").format(total)
        if total > 0:
            details = []
            # Sort by count or name? Name is better.
            for ch in sorted(channel_counts.keys()):
                count = channel_counts[ch]
                details.append(f"{ch}: {count}")
            summary_text += " (" + ", ".join(details) + ")"
            
        self.lbl_counts_summary.setText(summary_text)

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
        self.chk_fixed_size.setText(tr("Fixed Shape"))
        self.chk_fixed_size.setToolTip(tr("Lock ROI size to the last drawn shape"))
        
        self.chk_sync_rois.setText(tr("Sync ROIs as Annotations"))
        self.chk_sync_rois.setToolTip(tr("Automatically include ROIs in annotation list and exports"))
        
        self.wand_group.setTitle(tr("Magic Wand Options"))
        self.lbl_wand_tol.setText(tr("Default Tolerance:"))
        self.spin_wand_tol.setToolTip(tr("Initial tolerance when clicking. Drag to adjust."))
        self.lbl_wand_smooth.setText(tr("Smoothing:"))
        self.spin_wand_smooth.setToolTip(tr("Gaussian blur sigma for noise reduction before selection."))
        self.chk_wand_relative.setText(tr("Relative Tolerance (%)"))
        self.chk_wand_relative.setToolTip(tr("If checked, tolerance is a percentage of the clicked pixel value.\nUseful for images with high dynamic range."))
        
        self.count_group.setTitle(tr("Point Counter Options"))
        self.lbl_point_size.setText(tr("Point Size:"))
        self.spin_count_radius.setToolTip(tr("Radius of the point markers."))
        
        if hasattr(self, 'lbl_count_target'):
            self.lbl_count_target.setText(tr("Active Target:"))
        
        if hasattr(self, 'combo_count_target'):
            self.combo_count_target.setItemText(0, tr("Auto (Current View)"))
            self.combo_count_target.setToolTip(tr("When clicking in Merge view, count will be assigned to this channel."))
            
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

    def resizeEvent(self, event):
        # UI OPTIMIZATION: Following the new "Compact Icon-Only" design
        icon_size = 20
        
        # Update all tool buttons in the main tools group
        if hasattr(self, 'tools_group'):
            for btn in self.tools_group.findChildren(QToolButton):
                btn.setIconSize(QSize(icon_size, icon_size))
                btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
                # Only fix size for single-column tools to allow span to work
                if self.tools_group.layout().indexOf(btn) != -1:
                    pos = self.tools_group.layout().getItemPosition(self.tools_group.layout().indexOf(btn))
                    if pos[3] == 1: # col_span == 1
                        btn.setFixedSize(28, 28)
                    else:
                        btn.setMinimumHeight(28)
                
                # Ensure tooltip has text + shortcut if available
                action = btn.defaultAction()
                if action:
                    tip = action.text()
                    if action.shortcut().toString():
                        tip += f" ({action.shortcut().toString()})"
                    btn.setToolTip(tip)

        # Update Analysis Group Buttons
        if hasattr(self, 'analysis_group'):
            for btn in self.analysis_group.findChildren(QToolButton):
                if self.analysis_group.isAncestorOf(btn):
                    btn.setIconSize(QSize(icon_size, icon_size))
                    btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
                    
                    if self.analysis_group.layout().indexOf(btn) != -1:
                        pos = self.analysis_group.layout().getItemPosition(self.analysis_group.layout().indexOf(btn))
                        if pos[3] == 1: # col_span == 1
                            btn.setFixedSize(28, 28)
                        else:
                            btn.setMinimumHeight(28)
                    
                    action = btn.defaultAction()
                    if action:
                        btn.setToolTip(action.text())

        super().resizeEvent(event)
