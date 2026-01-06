from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                               QGroupBox, QCheckBox, QDoubleSpinBox, QComboBox, 
                               QSpinBox, QColorDialog, QPushButton, QListWidget,
                               QListWidgetItem, QAbstractItemView, QGridLayout, QFrame, QButtonGroup, QSizePolicy, QToolButton)
from PySide6.QtCore import Qt, Signal, QSize, QSettings
from PySide6.QtGui import QColor, QPixmap, QIcon, QAction
from src.core.data_model import Session
from src.core.language_manager import tr, LanguageManager
from src.core.microscope_db import MICROSCOPE_DB, get_recommended_bar_length
from src.gui.icon_manager import get_icon

class AnnotationPanel(QWidget):
    """
    Panel for controlling image overlays like Scale Bar.
    """
    settings_changed = Signal()
    annotation_tool_selected = Signal(str) # 'arrow', 'rect', 'text', 'circle', 'line', 'polygon', 'none'
    clear_annotations_requested = Signal()
    annotation_updated = Signal() # Signal for when an annotation's properties change

    def __init__(self, session: Session, parent=None):
        super().__init__(parent)
        self.session = session
        
        # Default properties for new annotations
        self.default_properties = {
            'color': '#FFFF00', # Yellow
            'thickness': 2,
            'style': 'solid',
            'arrow_head_size': 15.0,
            'export_only': False,
            'dash_length': 10,
            'dash_gap': 5,
            'dot_size': 2,
            'dot_spacing': 3,
            'smooth': True
        }
        
        self.setup_ui()
        LanguageManager.instance().language_changed.connect(self.retranslate_ui)
        self.session.data_changed.connect(self._on_data_changed)

    def setup_ui(self):
        self.setObjectName("card") # Apply global card style
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(10)
        self.setMinimumWidth(0)

        # Initialize Button Group for Tools
        self.tool_group = QButtonGroup(self)
        self.tool_group.setExclusive(True)

        # --- 1. Graphic Annotations Group (Reordered to top as implied by context) ---
        self.grp_annotations = QGroupBox(tr("Graphic Annotations"))
        v_ann = QVBoxLayout()
        v_ann.setSpacing(8)
        v_ann.setContentsMargins(4, 15, 4, 4)
        
        # Visibility Toggle
        self.chk_ann_visible = QCheckBox(tr("Show Annotations"))
        self.chk_ann_visible.setChecked(self.session.show_annotations)
        self.chk_ann_visible.toggled.connect(self._toggle_annotations)
        v_ann.addWidget(self.chk_ann_visible)
        
        # Tool Buttons - Grid Layout
        self.tool_buttons_layout = QGridLayout()
        self.tool_buttons_layout.setSpacing(4)
        self.tool_buttons_layout.setContentsMargins(0, 0, 0, 0)
        
        # Create buttons with Icons
        self.btn_add_arrow = self._create_tool_button("arrow", "arrow")
        self.btn_add_arrow.setToolTip(tr("Arrow Tool"))
        
        self.btn_add_line = self._create_tool_button("line", "line")
        self.btn_add_line.setToolTip(tr("Line Tool"))
        
        self.btn_add_rect = self._create_tool_button("rect", "rect")
        self.btn_add_rect.setToolTip(tr("Rectangle Tool"))
        
        self.btn_add_circle = self._create_tool_button("circle", "circle")
        self.btn_add_circle.setToolTip(tr("Circle Tool"))
        
        self.btn_add_ellipse = self._create_tool_button("ellipse", "ellipse")
        self.btn_add_ellipse.setToolTip(tr("Ellipse Tool"))
        
        self.btn_add_poly = self._create_tool_button("polygon", "polygon")
        self.btn_add_poly.setToolTip(tr("Polygon Tool"))
        
        self.btn_add_text = self._create_tool_button("text", "text")
        self.btn_add_text.setToolTip(tr("Text Tool"))
        
        # Updated Icon for Batch Select
        self.btn_batch_select = self._create_tool_button("batch_select", "batch_select")
        self.btn_batch_select.setToolTip(tr("Batch Select"))
        
        # Grid Placement (4 columns: 0-3)
        # Row 0
        self.tool_buttons_layout.addWidget(self.btn_add_arrow, 0, 0)
        self.tool_buttons_layout.addWidget(self.btn_add_line, 0, 1)
        self.tool_buttons_layout.addWidget(self.btn_add_rect, 0, 2)
        self.tool_buttons_layout.addWidget(self.btn_add_circle, 0, 3)
        # Row 1
        self.tool_buttons_layout.addWidget(self.btn_add_ellipse, 1, 0)
        self.tool_buttons_layout.addWidget(self.btn_add_poly, 1, 1)
        self.tool_buttons_layout.addWidget(self.btn_add_text, 1, 2)
        self.tool_buttons_layout.addWidget(self.btn_batch_select, 1, 3)
        
        # Set column stretch to ensure equal width distribution
        for c in range(4):
            self.tool_buttons_layout.setColumnStretch(c, 1)
            
        v_ann.addLayout(self.tool_buttons_layout)
        
        # Action Layout for managing list
        h_ann_actions = QHBoxLayout()
        h_ann_actions.setContentsMargins(0, 0, 0, 0)
        
        # Clear Button - Changed to Icon Button
        self.btn_clear_ann = QToolButton()
        self.btn_clear_ann.setIcon(get_icon("delete", "edit-clear-all"))
        self.btn_clear_ann.setIconSize(QSize(20, 20))
        self.btn_clear_ann.setToolTip(tr("Clear All Annotations"))
        self.btn_clear_ann.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear_ann.clicked.connect(self.clear_annotations_requested.emit)
        h_ann_actions.addWidget(self.btn_clear_ann)
        
        h_ann_actions.addStretch()
        
        v_ann.addLayout(h_ann_actions)

        # Annotation List
        v_ann.addWidget(QLabel(tr("Manage Annotations:")))
        self.list_ann = QListWidget()
        self.list_ann.setMinimumWidth(0)
        self.list_ann.setMinimumHeight(100) # Minimum readable height
        self.list_ann.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding) # Allow compression/expansion
        self.list_ann.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list_ann.itemSelectionChanged.connect(self._on_selection_changed)
        self.list_ann.itemChanged.connect(self._on_item_changed)
        v_ann.addWidget(self.list_ann)
        
        self.lbl_ann_count = QLabel(tr("Total Annotations: 0"))
        v_ann.addWidget(self.lbl_ann_count)

        self.grp_annotations.setLayout(v_ann)
        layout.addWidget(self.grp_annotations)
        
        # --- 2. Properties Group ---
        self.grp_props = QGroupBox(tr("Properties"))
        
        # Use a main grid layout for properties
        self.grid_props = QGridLayout()
        self.grid_props.setSpacing(4) # Minimal spacing
        self.grid_props.setContentsMargins(4, 12, 4, 4) # Minimal margins
        
        # --- Row 0: Color ---
        self.grid_props.addWidget(QLabel(tr("Color:")), 0, 0)
        self.btn_ann_color = QToolButton()
        self.btn_ann_color.setFixedSize(24, 24) # Smaller fixed size
        self.btn_ann_color.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_ann_color.setToolTip(tr("Click to change color"))
        self.btn_ann_color.setProperty("role", "color_picker")
        self.btn_ann_color.setStyleSheet("background-color: #FFFF00;") 
        self.btn_ann_color.clicked.connect(self._pick_ann_color)
        self.grid_props.addWidget(self.btn_ann_color, 0, 1)
        
        # --- Row 1: Thickness ---
        self.grid_props.addWidget(QLabel(tr("Thick:")), 1, 0) # Shorter text
        self.spin_ann_thickness = QSpinBox()
        self.spin_ann_thickness.setMaximumWidth(65) # Aggressive width reduction
        self.spin_ann_thickness.setRange(1, 50)
        self.spin_ann_thickness.setValue(2)
        self.spin_ann_thickness.setSuffix("px") # No space
        self.spin_ann_thickness.valueChanged.connect(self._update_ann_props)
        self.grid_props.addWidget(self.spin_ann_thickness, 1, 1)
        
        # --- Row 2: Style ---
        self.grid_props.addWidget(QLabel(tr("Style:")), 2, 0)
        self.combo_ann_style = QComboBox()
        self.combo_ann_style.setMaximumWidth(85) # Aggressive width reduction
        self.combo_ann_style.addItems([tr("Solid"), tr("Dashed"), tr("Dotted"), tr("Dash-Dot")])
        self.combo_ann_style.setItemData(0, "solid")
        self.combo_ann_style.setItemData(1, "dashed")
        self.combo_ann_style.setItemData(2, "dotted")
        self.combo_ann_style.setItemData(3, "dash_dot")
        self.combo_ann_style.currentIndexChanged.connect(self._update_ann_props)
        self.grid_props.addWidget(self.combo_ann_style, 2, 1)
        
        # --- Row 3: Size ---
        self.lbl_ann_size = QLabel(tr("Size:"))
        self.grid_props.addWidget(self.lbl_ann_size, 3, 0)
        self.spin_ann_size = QDoubleSpinBox()
        self.spin_ann_size.setMaximumWidth(75) # Aggressive width reduction
        self.spin_ann_size.setRange(1.0, 2000.0)
        self.spin_ann_size.setValue(15.0)
        self.spin_ann_size.setSuffix("px") # No space
        self.spin_ann_size.valueChanged.connect(self._update_ann_props)
        self.grid_props.addWidget(self.spin_ann_size, 3, 1)

        # --- Row 4: Tool-Specific Params (Dynamic visibility) ---
        # We use a container widget for all dynamic params
        self.dynamic_params_container = QWidget()
        self.grid_props.addWidget(self.dynamic_params_container, 4, 0, 1, 2)
        v_dynamic = QVBoxLayout(self.dynamic_params_container)
        v_dynamic.setContentsMargins(0, 0, 0, 0)
        v_dynamic.setSpacing(5)
        
        # Dash Params
        self.widget_dash_params = QWidget()
        h_dash = QHBoxLayout(self.widget_dash_params)
        h_dash.setContentsMargins(0, 0, 0, 0)
        h_dash.addWidget(QLabel(tr("Dash Len:")))
        self.spin_dash_len = QSpinBox()
        self.spin_dash_len.setRange(1, 200)
        self.spin_dash_len.setValue(10)
        self.spin_dash_len.setSuffix(" px")
        self.spin_dash_len.valueChanged.connect(self._update_ann_props)
        h_dash.addWidget(self.spin_dash_len)
        h_dash.addWidget(QLabel(tr("Gap:")))
        self.spin_dash_gap = QSpinBox()
        self.spin_dash_gap.setRange(1, 200)
        self.spin_dash_gap.setValue(5)
        self.spin_dash_gap.setSuffix(" px")
        self.spin_dash_gap.valueChanged.connect(self._update_ann_props)
        h_dash.addWidget(self.spin_dash_gap)
        v_dynamic.addWidget(self.widget_dash_params)
        
        # Dot Params
        self.widget_dot_params = QWidget()
        h_dot = QHBoxLayout(self.widget_dot_params)
        h_dot.setContentsMargins(0, 0, 0, 0)
        h_dot.addWidget(QLabel(tr("Dot Size:")))
        self.spin_dot_size = QSpinBox()
        self.spin_dot_size.setRange(1, 100)
        self.spin_dot_size.setValue(2)
        self.spin_dot_size.setSuffix(" px")
        self.spin_dot_size.valueChanged.connect(self._update_ann_props)
        h_dot.addWidget(self.spin_dot_size)
        h_dot.addWidget(QLabel(tr("Spacing:")))
        self.spin_dot_spacing = QSpinBox()
        self.spin_dot_spacing.setRange(1, 200)
        self.spin_dot_spacing.setValue(3)
        self.spin_dot_spacing.setSuffix(" px")
        self.spin_dot_spacing.valueChanged.connect(self._update_ann_props)
        h_dot.addWidget(self.spin_dot_spacing)
        v_dynamic.addWidget(self.widget_dot_params)
        
        # Text Params
        self.widget_text_params = QWidget()
        h_text = QHBoxLayout(self.widget_text_params)
        h_text.setContentsMargins(0, 0, 0, 0)
        h_text.addWidget(QLabel(tr("Font:")))
        self.combo_font = QComboBox()
        self.combo_font.addItems(["Arial", "Helvetica", "Times New Roman", "Courier New", "Verdana"])
        self.combo_font.currentTextChanged.connect(self._update_ann_props)
        h_text.addWidget(self.combo_font)
        
        self.group_align = QButtonGroup(self)
        self.btn_align_left = QToolButton()
        self.btn_align_left.setIcon(get_icon("align_left"))
        self.btn_align_left.setIconSize(QSize(20, 20))
        self.btn_align_left.setFixedSize(28, 28)
        self.btn_align_left.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.btn_align_left.setCheckable(True)
        self.btn_align_left.setToolTip(tr("Align Left"))
        
        self.btn_align_center = QToolButton()
        self.btn_align_center.setIcon(get_icon("align_center"))
        self.btn_align_center.setIconSize(QSize(20, 20))
        self.btn_align_center.setFixedSize(28, 28)
        self.btn_align_center.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.btn_align_center.setCheckable(True)
        self.btn_align_center.setToolTip(tr("Align Center"))
        
        self.btn_align_right = QToolButton()
        self.btn_align_right.setIcon(get_icon("align_right"))
        self.btn_align_right.setIconSize(QSize(20, 20))
        self.btn_align_right.setFixedSize(28, 28)
        self.btn_align_right.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.btn_align_right.setCheckable(True)
        self.btn_align_right.setToolTip(tr("Align Right"))

        self.group_align.addButton(self.btn_align_left)
        self.group_align.addButton(self.btn_align_center)
        self.group_align.addButton(self.btn_align_right)
        self.group_align.buttonClicked.connect(self._update_ann_props)
        h_text.addWidget(self.btn_align_left)
        h_text.addWidget(self.btn_align_center)
        h_text.addWidget(self.btn_align_right)
        v_dynamic.addWidget(self.widget_text_params)
        
        # Arrow Params
        self.widget_arrow_params = QWidget()
        h_arrow = QHBoxLayout(self.widget_arrow_params)
        h_arrow.setContentsMargins(0, 0, 0, 0)
        h_arrow.addWidget(QLabel(tr("Head Shape:")))
        self.combo_arrow_head = QComboBox()
        self.combo_arrow_head.addItem(tr("V-Shape"), "open")
        self.combo_arrow_head.addItem(tr("Triangle"), "triangle")
        self.combo_arrow_head.addItem(tr("Diamond"), "diamond")
        self.combo_arrow_head.addItem(tr("Circle"), "circle")
        self.combo_arrow_head.currentIndexChanged.connect(self._update_ann_props)
        h_arrow.addWidget(self.combo_arrow_head)
        v_dynamic.addWidget(self.widget_arrow_params)
        
        # Smooth Option (for Polygons)
        self.chk_ann_smooth = QCheckBox(tr("Smooth Curve (Catmull-Rom)"))
        self.chk_ann_smooth.toggled.connect(self._update_ann_props)
        v_dynamic.addWidget(self.chk_ann_smooth)
        
        self.grid_props.addWidget(self.dynamic_params_container, 2, 0, 1, 4)
        
        # Simple Separator
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        self.grid_props.addWidget(line, 4, 0, 1, 4)
        
        self.grp_props.setLayout(self.grid_props)
        layout.addWidget(self.grp_props)
        
        # Initially hide tool-specific params
        self.widget_dash_params.hide()
        self.widget_dot_params.hide()
        self.widget_text_params.hide()
        self.widget_arrow_params.hide()
        self.chk_ann_smooth.hide()
        self.lbl_ann_size.hide()
        self.spin_ann_size.hide()

        # --- 3. Scale Bar Group ---
        self.grp_scale_bar = QGroupBox(tr("Scale Bar"))
        v_scale = QVBoxLayout()
        v_scale.setSpacing(4)
        v_scale.setContentsMargins(4, 12, 4, 4)
        
        # Enable Checkbox
        self.chk_enabled = QCheckBox(tr("Enable"))
        self.chk_enabled.setChecked(self.session.scale_bar_settings.enabled)
        self.chk_enabled.toggled.connect(self._update_settings)
        v_scale.addWidget(self.chk_enabled)
        
        # Use Grid Layout for more compact parameters
        grid_scale = QGridLayout()
        grid_scale.setSpacing(2) # Minimal spacing
        grid_scale.setColumnStretch(0, 0)
        grid_scale.setColumnStretch(1, 1)
        
        # Row 0: Preset Scope
        grid_scale.addWidget(QLabel(tr("Scope:")), 0, 0)
        self.combo_scope = QComboBox()
        self.combo_scope.setMaximumWidth(90) # Reduced
        self.combo_scope.addItem(tr("Custom"), "Custom")
        if "Generic" in MICROSCOPE_DB:
            self.combo_scope.addItem("Generic", "Generic")
        for name in sorted(MICROSCOPE_DB.keys()):
            if name != "Generic":
                self.combo_scope.addItem(name, name)
        self.combo_scope.currentIndexChanged.connect(self._on_scope_changed)
        grid_scale.addWidget(self.combo_scope, 0, 1)
        
        # Row 1: Objective
        grid_scale.addWidget(QLabel(tr("Obj:")), 1, 0)
        self.combo_obj = QComboBox()
        self.combo_obj.setMaximumWidth(90) # Reduced
        self.combo_obj.setEnabled(False)
        self.combo_obj.currentIndexChanged.connect(self._on_objective_changed)
        grid_scale.addWidget(self.combo_obj, 1, 1)
        
        # Row 2: Pixel Size
        grid_scale.addWidget(QLabel(tr("Px:")), 2, 0) # Shorter
        self.spin_pixel = QDoubleSpinBox()
        self.spin_pixel.setMaximumWidth(70) # Reduced
        self.spin_pixel.setRange(0.001, 1000.0)
        self.spin_pixel.setDecimals(4)
        self.spin_pixel.setValue(self.session.scale_bar_settings.pixel_size)
        self.spin_pixel.setSuffix("μm") # Shorter
        self.spin_pixel.valueChanged.connect(self._update_settings)
        grid_scale.addWidget(self.spin_pixel, 2, 1)
        
        # Row 3: Length
        grid_scale.addWidget(QLabel(tr("Len:")), 3, 0) # Shorter
        self.spin_length = QDoubleSpinBox()
        self.spin_length.setMaximumWidth(70) # Reduced
        self.spin_length.setRange(1.0, 10000.0)
        self.spin_length.setValue(self.session.scale_bar_settings.bar_length_um)
        self.spin_length.setSuffix("μm")
        self.spin_length.valueChanged.connect(self._update_settings)
        grid_scale.addWidget(self.spin_length, 3, 1)
        
        # Row 4: Position
        grid_scale.addWidget(QLabel(tr("Pos:")), 4, 0)
        self.combo_pos = QComboBox()
        self.combo_pos.setMaximumWidth(90) # Reduced
        for p in ["Bottom Right", "Bottom Left", "Top Right", "Top Left"]:
            self.combo_pos.addItem(tr(p), p)
        idx = self.combo_pos.findData(self.session.scale_bar_settings.position)
        if idx >= 0: self.combo_pos.setCurrentIndex(idx)
        self.combo_pos.currentIndexChanged.connect(self._update_settings)
        grid_scale.addWidget(self.combo_pos, 4, 1)
        
        # Row 5: Label Checkbox
        self.chk_label = QCheckBox(tr("Show Label"))
        self.chk_label.setChecked(self.session.scale_bar_settings.show_label)
        self.chk_label.toggled.connect(self._update_settings)
        grid_scale.addWidget(self.chk_label, 5, 0, 1, 2)
        
        # Row 6: Color
        grid_scale.addWidget(QLabel(tr("Color:")), 6, 0)
        self.btn_color = QToolButton()
        self.btn_color.setFixedSize(24, 24) # Smaller
        self.btn_color.setProperty("role", "color_picker")
        self.btn_color.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_color.clicked.connect(self._pick_color)
        self._update_color_button()
        grid_scale.addWidget(self.btn_color, 6, 1)
        
        # Row 7: Thickness
        grid_scale.addWidget(QLabel(tr("Thick:")), 7, 0)
        self.spin_thickness = QSpinBox()
        self.spin_thickness.setMaximumWidth(60) # Reduced
        self.spin_thickness.setRange(1, 20)
        self.spin_thickness.setValue(self.session.scale_bar_settings.thickness)
        self.spin_thickness.setSuffix("px")
        self.spin_thickness.valueChanged.connect(self._update_settings)
        grid_scale.addWidget(self.spin_thickness, 7, 1)

        # Row 8: Font Size
        grid_scale.addWidget(QLabel(tr("Font:")), 8, 0)
        self.spin_font = QSpinBox()
        self.spin_font.setMaximumWidth(60) # Reduced
        self.spin_font.setRange(6, 72)
        self.spin_font.setValue(self.session.scale_bar_settings.font_size)
        self.spin_font.setSuffix("pt")
        self.spin_font.valueChanged.connect(self._update_settings)
        grid_scale.addWidget(self.spin_font, 8, 1)
        
        v_scale.addLayout(grid_scale)
        self.grp_scale_bar.setLayout(v_scale)
        layout.addWidget(self.grp_scale_bar)
        
        layout.addStretch()

    def _create_tool_button(self, icon_name, tool_id):
        """Creates a styled toggle QToolButton for annotation tools."""
        btn = QToolButton()
        btn.setIcon(get_icon(icon_name))
        btn.setIconSize(QSize(20, 20))
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        btn.setCheckable(True)
        btn.setFixedSize(28, 28)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setProperty("tool_id", tool_id)
        
        # Connect clicked (for manual toggle logic)
        btn.clicked.connect(lambda checked: self._on_tool_button_clicked(btn, checked))
        self.tool_group.addButton(btn)
        return btn

    def _on_tool_button_clicked(self, btn, checked):
        """Handles mutual exclusivity and toggle-off logic."""
        tool_id = btn.property("tool_id")
        from src.core.logger import Logger
        Logger.info(f"[AnnotationPanel] Tool button clicked: {tool_id}, checked={checked}")
        
        if checked:
            self.annotation_tool_selected.emit(tool_id)
            self._update_tool_specific_controls(tool_id)
        else:
            self.annotation_tool_selected.emit("none")
            self._update_tool_specific_controls("none")

    def clear_tool_selection(self):
        """Unchecks all tool buttons in the annotation panel."""
        self.tool_group.setExclusive(False)
        for button in self.tool_group.buttons():
            button.setChecked(False)
        self.tool_group.setExclusive(True)
        # Emit signal to notify that no tool is selected
        self.annotation_tool_selected.emit('none')
        self._update_tool_specific_controls('none')


    def select_annotation_by_id(self, ann_id):
        """Programmatically select an annotation in the list (e.g. from Canvas click)."""
        if not ann_id:
            self.list_ann.clearSelection()
            return
            
        # Find item with this ID
        # We stored the ID in the label or need to check session
        for i in range(self.list_ann.count()):
            item = self.list_ann.item(i)
            # Match index to session list
            if i < len(self.session.annotations):
                if self.session.annotations[i].id == ann_id:
                    self.list_ann.setCurrentItem(item)
                    item.setSelected(True)
                    return

    def _on_item_changed(self, item):
        idx = self.list_ann.row(item)
        if 0 <= idx < len(self.session.annotations):
            self.session.annotations[idx].visible = (item.checkState() == Qt.CheckState.Checked)
            self.annotation_updated.emit()
            self.settings_changed.emit()

    def _update_style_controls_visibility(self):
        style = self.combo_ann_style.currentData()
        if style in ['dashed', 'dash_dot']:
            self.widget_dash_params.show()
            self.widget_dot_params.hide()
        elif style == 'dotted':
            self.widget_dash_params.hide()
            self.widget_dot_params.show()
        else:
            self.widget_dash_params.hide()
            self.widget_dot_params.hide()

    def _on_selection_changed(self):
        selected_items = self.list_ann.selectedItems()
        # self.grp_props.setEnabled(len(selected_items) > 0) # Removed to allow default setting
        
        widgets_to_block = [
            self.spin_ann_thickness,
            self.combo_ann_style,
            self.spin_ann_size,
            self.spin_dash_len,
            self.spin_dash_gap,
            self.spin_dot_size,
            self.spin_dot_spacing,
            self.combo_font,
            self.combo_arrow_head
        ]

        if len(selected_items) == 1:
            # Load properties of the single selected annotation
            idx = self.list_ann.row(selected_items[0])
            if 0 <= idx < len(self.session.annotations):
                ann = self.session.annotations[idx]
                for w in widgets_to_block:
                    w.blockSignals(True)
                self.spin_ann_thickness.setValue(ann.thickness)
                self._update_ann_color_preview(ann.color)
                
                # Update style combo
                style_idx = self.combo_ann_style.findData(ann.style)
                if style_idx >= 0:
                    self.combo_ann_style.setCurrentIndex(style_idx)
                else:
                    self.combo_ann_style.setCurrentIndex(0) # Default to solid
                
                # Update Advanced Style Params
                self.spin_dash_len.setValue(ann.properties.get('dash_length', 10))
                self.spin_dash_gap.setValue(ann.properties.get('dash_gap', 5))
                self.spin_dot_size.setValue(ann.properties.get('dot_size', 2))
                self.spin_dot_spacing.setValue(ann.properties.get('dot_spacing', 3))
                
                # Update New Params
                font = ann.properties.get('font_family', 'Arial')
                self.combo_font.setCurrentText(font)
                
                self.group_align.blockSignals(True)
                align = ann.properties.get('alignment', 'left')
                if align == 'center': self.btn_align_center.setChecked(True)
                elif align == 'right': self.btn_align_right.setChecked(True)
                else: self.btn_align_left.setChecked(True)
                self.group_align.blockSignals(False)
                
                head = ann.properties.get('arrow_head_shape', 'triangle')
                idx = self.combo_arrow_head.findData(head)
                if idx >= 0: self.combo_arrow_head.setCurrentIndex(idx)
                
                # Update Smooth Checkbox
                self.chk_ann_smooth.blockSignals(True)
                self.chk_ann_smooth.setChecked(ann.properties.get('smooth', True))
                self.chk_ann_smooth.blockSignals(False)
                
                self._update_style_controls_visibility()
                
                # Update Size Spinbox (Arrow Head)
                if ann.type == 'arrow':
                     val = ann.properties.get('arrow_head_size', 15.0)
                     self.spin_ann_size.setValue(float(val))
                elif ann.type == 'text':
                     val = ann.properties.get('font_size', 12.0)
                     self.spin_ann_size.setValue(float(val))
                
                self._update_tool_specific_controls(ann.type)
                
                for w in widgets_to_block:
                    w.blockSignals(False)
        else:
            # If nothing selected (or multiple), should we reset to defaults?
            # Let's reset controls to show current defaults
            for w in widgets_to_block:
                w.blockSignals(True)
            self.spin_ann_thickness.setValue(self.default_properties['thickness'])
            self._update_ann_color_preview(self.default_properties['color'])
            
            style_idx = self.combo_ann_style.findData(self.default_properties['style'])
            if style_idx >= 0:
                self.combo_ann_style.setCurrentIndex(style_idx)
                
            self.spin_dash_len.setValue(self.default_properties['dash_length'])
            self.spin_dash_gap.setValue(self.default_properties['dash_gap'])
            self.spin_dot_size.setValue(self.default_properties['dot_size'])
            self.spin_dot_spacing.setValue(self.default_properties['dot_spacing'])
            
            # Defaults for new params
            self.combo_font.setCurrentText(self.default_properties.get('font_family', 'Arial'))
            
            self.group_align.blockSignals(True)
            align = self.default_properties.get('alignment', 'left')
            if align == 'center': self.btn_align_center.setChecked(True)
            elif align == 'right': self.btn_align_right.setChecked(True)
            else: self.btn_align_left.setChecked(True)
            self.group_align.blockSignals(False)
            
            head = self.default_properties.get('arrow_head_shape', 'triangle')
            idx = self.combo_arrow_head.findData(head)
            if idx >= 0: self.combo_arrow_head.setCurrentIndex(idx)
            
            self._update_style_controls_visibility()
                
            self.spin_ann_size.setValue(self.default_properties['arrow_head_size'])
            
            # Check active tool to decide visibility
            current_tool_btn = self.tool_group.checkedButton()
            if current_tool_btn:
                 tool_id = current_tool_btn.property("tool_id")
                 self._update_tool_specific_controls(tool_id)
            else:
                 self._update_tool_specific_controls('none')
            
            for w in widgets_to_block:
                w.blockSignals(False)

    def _update_ann_color_preview(self, color_hex):
        pix = QPixmap(20, 20)
        pix.fill(QColor(color_hex))
        self.btn_ann_color.setIcon(QIcon(pix))

    def _pick_ann_color(self):
        selected_items = self.list_ann.selectedItems()
        
        # Get initial color
        if selected_items:
            first_idx = self.list_ann.row(selected_items[0])
            initial_color = self.session.annotations[first_idx].color
        else:
            initial_color = self.default_properties['color']
        
        color = QColorDialog.getColor(QColor(initial_color), self, tr("Select Annotation Color"))
        if not color.isValid():
            return

        color_hex = color.name()
        self._update_ann_color_preview(color_hex)
            
        if not selected_items:
            # Update default
            self.default_properties['color'] = color_hex
            return

        # Update selected
        for item in selected_items:
            idx = self.list_ann.row(item)
            ann = self.session.annotations[idx]
            ann.color = color_hex
            
            # USER REQUEST: Sync back to ROI if this is a roi_ref
            if ann.roi_id:
                if hasattr(self.session.roi_manager, 'get_roi'):
                    roi = self.session.roi_manager.get_roi(ann.roi_id)
                else:
                    roi = None
                    for r in self.session.roi_manager.get_all_rois():
                        if r.id == ann.roi_id:
                            roi = r
                            break
                
                if roi:
                    roi.color = color
                    self.session.roi_manager.roi_updated.emit(roi)
        
        self.annotation_updated.emit()
        self.settings_changed.emit()

    def _update_ann_props(self):
        if not hasattr(self, 'list_ann'):
            return
        # Ensure all widgets are initialized before accessing them
        if not hasattr(self, 'spin_ann_thickness') or \
           not hasattr(self, 'combo_ann_style') or \
           not hasattr(self, 'spin_ann_size') or \
           not hasattr(self, 'spin_dash_len') or \
           not hasattr(self, 'spin_dash_gap') or \
           not hasattr(self, 'spin_dot_size') or \
           not hasattr(self, 'spin_dot_spacing') or \
           not hasattr(self, 'combo_font') or \
           not hasattr(self, 'combo_arrow_head'):
            return

        selected_items = self.list_ann.selectedItems()
        
        # Gather current values from UI
        thickness = self.spin_ann_thickness.value()
        style = self.combo_ann_style.currentData()
        arrow_size = self.spin_ann_size.value()
        
        # Advanced Params
        dash_len = self.spin_dash_len.value()
        dash_gap = self.spin_dash_gap.value()
        dot_size = self.spin_dot_size.value()
        dot_spacing = self.spin_dot_spacing.value()
        
        # New Params
        font = self.combo_font.currentText()
        align = "left"
        if self.btn_align_center.isChecked(): align = "center"
        if self.btn_align_right.isChecked(): align = "right"
        head_shape = self.combo_arrow_head.currentData()
        smooth = self.chk_ann_smooth.isChecked()
        
        self._update_style_controls_visibility()
        
        if not selected_items:
            # Update defaults
            self.default_properties['thickness'] = thickness
            if style in ['solid', 'dashed', 'dotted', 'dash_dot']:
                self.default_properties['style'] = style
            self.default_properties['arrow_head_size'] = arrow_size
            self.default_properties['dash_length'] = dash_len
            self.default_properties['dash_gap'] = dash_gap
            self.default_properties['dot_size'] = dot_size
            self.default_properties['dot_spacing'] = dot_spacing
            
            self.default_properties['font_family'] = font
            self.default_properties['alignment'] = align
            self.default_properties['arrow_head_shape'] = head_shape
            self.default_properties['smooth'] = smooth
            return
            
        from src.core.logger import Logger
        for item in selected_items:
            idx = self.list_ann.row(item)
            ann = self.session.annotations[idx]
            
            # Update properties
            ann.thickness = thickness
            
            # Update style
            if style in ['solid', 'dashed', 'dotted', 'dash_dot']:
                ann.style = style
                
            # Update Advanced Params
            ann.properties['dash_length'] = dash_len
            ann.properties['dash_gap'] = dash_gap
            ann.properties['dot_size'] = dot_size
            ann.properties['dot_spacing'] = dot_spacing
                
            # Update arrow size
            if ann.type == 'arrow':
                 ann.properties['arrow_head_size'] = arrow_size
                 ann.properties['arrow_head_shape'] = head_shape
            elif ann.type == 'text':
                 ann.properties['font_size'] = arrow_size
                 ann.properties['font_family'] = font
                 ann.properties['alignment'] = align
            elif ann.type in ['polygon', 'roi_ref']:
                 ann.properties['smooth'] = smooth
            
            # 【核心修复】同步到关联的 ROI
            # 这样 AnnotationGraphicsItem 在渲染时能拿到最新的样式数据
            roi_obj = getattr(ann, 'roi', None)
            if roi_obj:
                if not hasattr(roi_obj, 'display_style'):
                    roi_obj.display_style = {}
                roi_obj.display_style['color'] = ann.color
                roi_obj.display_style['thickness'] = ann.thickness
                # 还可以同步更多属性
                if ann.type == 'arrow':
                    roi_obj.display_style['arrow_head_size'] = arrow_size
                
                # 触发 ROI 更新信号，确保所有视图同步 (包括可能正在显示该 ROI 的其他组件)
                if hasattr(self, 'session') and self.session.roi_manager:
                    self.session.roi_manager.roi_updated.emit(roi_obj.id)
            
            Logger.info(f"Updated annotation {ann.id} properties: thickness={thickness}, smooth={smooth}")
            
        self.annotation_updated.emit()
        self.settings_changed.emit()

    def get_current_properties(self):
        """Returns the current properties (from selection or defaults)."""
        selected_items = self.list_ann.selectedItems()
        if not selected_items:
            return self.default_properties.copy()
            
        props = self.default_properties.copy()
        
        # If selection, we can read from the annotation object
        idx = self.list_ann.row(selected_items[0])
        ann = self.session.annotations[idx]
        props['color'] = ann.color
        props['thickness'] = ann.thickness
        props['style'] = ann.style
        props['arrow_head_size'] = ann.properties.get('arrow_head_size', 15.0)
        props['dash_length'] = ann.properties.get('dash_length', 10)
        props['dash_gap'] = ann.properties.get('dash_gap', 5)
        props['dot_size'] = ann.properties.get('dot_size', 2)
        props['dot_spacing'] = ann.properties.get('dot_spacing', 3)
        
        return props

    def refresh_from_session(self):
        """Sync UI with current session settings."""
        s = self.session.scale_bar_settings
        self.chk_enabled.setChecked(s.enabled)
        self.spin_length.setValue(s.bar_length_um)
        self.spin_thickness.setValue(s.thickness)
        if hasattr(self, 'chk_show_label'):
            self.chk_show_label.setChecked(s.show_label)
        self.combo_pos.setCurrentText(s.position)
        
        self.update_annotation_list()

    def update_annotation_list(self):
        """Refreshes the annotation list widget."""
        self.list_ann.blockSignals(True)
        self.list_ann.clear()
        for ann in self.session.annotations:
            label = f"{ann.type.capitalize()} - {ann.id[:8]}"
            if ann.roi_id:
                label += " (ROI)"
            item = QListWidgetItem(label)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if ann.visible else Qt.Unchecked)
            self.list_ann.addItem(item)
        self.list_ann.blockSignals(False)
        self._update_ann_count()

    def _update_ann_count(self):
        self.lbl_ann_count.setText(tr("Total Annotations: {}").format(len(self.session.annotations)))

    def _update_tool_specific_controls(self, tool_type):
        """Shows/Hides specific controls based on selected tool."""
        # Hide all first
        self.lbl_ann_size.setVisible(False)
        self.spin_ann_size.setVisible(False)
        self.widget_text_params.hide()
        self.widget_arrow_params.hide()
        self.chk_ann_smooth.hide()
        
        if tool_type == 'arrow':
            self.lbl_ann_size.setText(tr("Head Size:"))
            self.lbl_ann_size.setVisible(True)
            self.spin_ann_size.setVisible(True)
            self.widget_arrow_params.show()
        elif tool_type == 'text':
            self.lbl_ann_size.setText(tr("Font Size:"))
            self.lbl_ann_size.setVisible(True)
            self.spin_ann_size.setVisible(True)
            self.widget_text_params.show()
        elif tool_type in ['polygon', 'roi_ref']:
            self.chk_ann_smooth.show()

    def _toggle_annotations(self, visible):
        self.session.show_annotations = visible
        self.settings_changed.emit()

    def _update_color_button(self):
        color = self.session.scale_bar_settings.color
        self.btn_color.setStyleSheet(f"background-color: {color};")

    def _pick_color(self):
        color = QColorDialog.getColor(QColor(self.session.scale_bar_settings.color), self, tr("Select Scale Bar Color"))
        if color.isValid():
            self.session.scale_bar_settings.color = color.name()
            self._update_color_button()
            self._update_settings()

    def _on_scope_changed(self, index):
        scope_name = self.combo_scope.currentData()
        
        self.combo_obj.blockSignals(True)
        self.combo_obj.clear()
        
        if scope_name == "Custom":
            self.combo_obj.setEnabled(False)
            self.spin_pixel.setEnabled(True)
        elif scope_name in MICROSCOPE_DB:
            self.combo_obj.setEnabled(True)
            self.spin_pixel.setEnabled(True) # Allow manual override
            
            # Populate objectives
            objectives = MICROSCOPE_DB[scope_name]
            for obj_name in sorted(objectives.keys(), key=lambda x: int(x.split('x')[0]) if 'x' in x else 0):
                val = objectives[obj_name]
                self.combo_obj.addItem(f"{obj_name} (~{val} um/px)", val)
                
            # Trigger update for first item
            if self.combo_obj.count() > 0:
                self.combo_obj.setCurrentIndex(0)
                self._on_objective_changed(0)
                
        self.combo_obj.blockSignals(False)

    def _on_objective_changed(self, index):
        val = self.combo_obj.currentData()
        if val is not None:
            self.spin_pixel.setValue(float(val))
            
            # Auto-suggest length
            # We need image width. Where to get it?
            # Session has channels.
            if self.session.channels:
                width = self.session.channels[0].shape[1]
                rec_len = get_recommended_bar_length(float(val), width)
                self.spin_length.setValue(rec_len)

    def _update_settings(self):
        s = self.session.scale_bar_settings
        s.enabled = self.chk_enabled.isChecked()
        s.pixel_size = self.spin_pixel.value()
        s.bar_length_um = self.spin_length.value()
        s.position = self.combo_pos.currentData()
        s.thickness = self.spin_thickness.value()
        s.show_label = self.chk_label.isChecked()
        s.font_size = self.spin_font.value()
        
        self.settings_changed.emit()

    def retranslate_ui(self):
        self.grp_scale_bar.setTitle(tr("Scale Bar"))
        self.chk_enabled.setText(tr("Enable Scale Bar"))
        self.lbl_pixel.setText(tr("Px Size:"))
        self.lbl_length.setText(tr("Length:"))
        self.lbl_pos.setText(tr("Pos:"))
        self.lbl_adv_color.setText(tr("Color:"))
        self.chk_label.setText(tr("Label"))
        
        self.grp_annotations.setTitle(tr("Graphic Annotations"))
        self.chk_ann_visible.setText(tr("Show Annotations"))
        
        # Tool buttons - tooltips only (icon-only mode)
        self.btn_add_arrow.setToolTip(tr("Arrow Tool"))
        self.btn_add_line.setToolTip(tr("Line Tool"))
        self.btn_add_rect.setToolTip(tr("Rectangle Tool"))
        self.btn_add_circle.setToolTip(tr("Circle Tool"))
        self.btn_add_ellipse.setToolTip(tr("Ellipse Tool"))
        self.btn_add_poly.setToolTip(tr("Polygon Tool"))
        self.btn_add_text.setToolTip(tr("Text Tool"))
        self.btn_batch_select.setToolTip(tr("Batch Select"))
        
        self.btn_align_left.setToolTip(tr("Align Left"))
        self.btn_align_center.setToolTip(tr("Align Center"))
        self.btn_align_right.setToolTip(tr("Align Right"))
        
        self.btn_clear_ann.setText(tr("Clear All Annotations"))
        self.grp_props.setTitle(tr("Properties"))
        
        # Property labels
        # These are anonymous in grid_props, but we can find them if needed or just re-add labels to class
        # For now, let's just update the ones we have handles for
        self.chk_ann_smooth.setText(tr("Smooth Curve (Catmull-Rom)"))
        
        self.update_annotation_list()
        
        # Update combo items
        current_data = self.combo_pos.currentData()
        self.combo_pos.blockSignals(True)
        self.combo_pos.clear()
        self.combo_pos.addItem(tr("Bottom Right"), "Bottom Right")
        self.combo_pos.addItem(tr("Bottom Left"), "Bottom Left")
        self.combo_pos.addItem(tr("Top Right"), "Top Right")
        self.combo_pos.addItem(tr("Top Left"), "Top Left")
        idx = self.combo_pos.findData(current_data)
        if idx >= 0: self.combo_pos.setCurrentIndex(idx)
        self.combo_pos.blockSignals(False)

        current_style = self.combo_ann_style.currentData()
        self.combo_ann_style.blockSignals(True)
        self.combo_ann_style.clear()
        self.combo_ann_style.addItem(tr("Solid"), "solid")
        self.combo_ann_style.addItem(tr("Dashed"), "dashed")
        self.combo_ann_style.addItem(tr("Dotted"), "dotted")
        self.combo_ann_style.addItem(tr("Dash-Dot"), "dash_dot")
        style_idx = self.combo_ann_style.findData(current_style)
        if style_idx >= 0: self.combo_ann_style.setCurrentIndex(style_idx)
        self.combo_ann_style.blockSignals(False)

        # Update Tool Specific UI (Labels like Head Size / Font Size)
        current_tool_btn = self.tool_group.checkedButton()
        if current_tool_btn:
            self._update_tool_specific_controls(current_tool_btn.property("tool_id"))
        else:
            self._update_tool_specific_controls('none')

    def _on_data_changed(self):
        """Called when session data (e.g. crop) changes."""
        # Auto-adjust scale bar length if it exceeds image bounds
        if self.session.channels:
            # Use first channel as reference
            width_px = self.session.channels[0].shape[1]
            pixel_size = self.session.scale_bar_settings.pixel_size
            current_len = self.session.scale_bar_settings.bar_length_um
            
            width_um = width_px * pixel_size
            
            # If current bar length is wider than the image (or dangerously close)
            # Threshold: > 90% of image width
            if current_len > width_um * 0.9:
                rec_len = get_recommended_bar_length(pixel_size, width_px)
                if rec_len < current_len:
                    print(f"[AnnotationPanel] Auto-shrinking scale bar from {current_len} to {rec_len} um")
                    self.spin_length.setValue(rec_len)
