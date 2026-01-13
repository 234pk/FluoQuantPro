from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                               QGroupBox, QDoubleSpinBox, QComboBox, 
                               QSpinBox, QColorDialog, QPushButton, QListWidget,
                               QListWidgetItem, QAbstractItemView, QGridLayout, QFrame, QButtonGroup, QSizePolicy, QToolButton, QLineEdit, QSpacerItem)
from src.gui.toggle_switch import ToggleSwitch
from PySide6.QtCore import Qt, Signal, QSize, QSettings
from PySide6.QtGui import QColor, QPixmap, QIcon, QAction
from src.core.data_model import Session
from src.core.language_manager import tr, LanguageManager
from src.core.microscope_db import MICROSCOPE_DB, get_recommended_bar_length
from src.gui.icon_manager import get_icon
from src.gui.theme_manager import ThemeManager
from src.core.roi_model import ROI

class AnnotationPanel(QWidget):
    """
    Panel for managing ROIs (annotations) and Scale Bar.
    Unified ROI/Annotation management.
    """
    settings_changed = Signal()
    annotation_tool_selected = Signal(str) # 'arrow', 'rect', 'text', 'circle', 'line', 'polygon', 'none'
    clear_annotations_requested = Signal()
    annotation_updated = Signal() # Signal for when an annotation's properties change
    annotation_selected = Signal(str) # Signal for when an annotation is selected in the list (Forward Sync)

    def __init__(self, session: Session, parent=None):
        super().__init__(parent)
        self.session = session
        self._updating_from_canvas = False # Flag to prevent signal loops
        self._updating_ui = False # Flag to prevent UI changes triggering model updates
        
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
            'smooth': True,
            'font_family': 'Arial',
            'font_size': 12.0,
            'text': 'Text',
            'alignment': 'left',
            'arrow_head_shape': 'triangle',
            'measurable': False, # Default for visual annotations
            'export_with_image': True
        }
        
        self.setup_ui()
        LanguageManager.instance().language_changed.connect(self.retranslate_ui)
        ThemeManager.instance().theme_changed.connect(self.refresh_icons)
        
        # Connect to ROI Manager signals
        if self.session.roi_manager:
            self.session.roi_manager.roi_added.connect(self._on_roi_added)
            self.session.roi_manager.roi_removed.connect(self._on_roi_removed)
            self.session.roi_manager.roi_updated.connect(self._on_roi_updated)
            self.session.roi_manager.selection_changed.connect(self._on_manager_selection_changed)
            
        self.session.project_changed.connect(self.update_annotation_list)

    def setup_ui(self):
        self.setObjectName("card") # Apply global card style
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(10)
        self.setMinimumWidth(0)

        # Initialize Button Group for Tools
        self.tool_group = QButtonGroup(self)
        self.tool_group.setExclusive(True)

        # --- 1. Graphic Annotations Group ---
        self.grp_annotations = QGroupBox(tr("Graphic Annotations"))
        self.grp_annotations.setObjectName("grp_annotations")
        self.grp_annotations.setProperty("full_title", tr("Graphic Annotations"))
        v_ann = QVBoxLayout()
        v_ann.setSpacing(8)
        v_ann.setContentsMargins(4, 15, 4, 4)
        
        # Visibility Toggle
        self.row_ann_visible = QHBoxLayout()
        self.lbl_ann_visible = QLabel(tr("Show Annotations"))
        self.chk_ann_visible = ToggleSwitch()
        #self.chk_ann_visible.setChecked(self.session.show_annotations)
        self.chk_ann_visible.toggled.connect(self._toggle_annotations)
        self.row_ann_visible.addWidget(self.lbl_ann_visible)
        self.row_ann_visible.addStretch()
        self.row_ann_visible.addWidget(self.chk_ann_visible)
        v_ann.addLayout(self.row_ann_visible)
        
        # Tool Buttons - Grid Layout (Will be populated after props are ready)
        self.tool_buttons_layout = QGridLayout()
        self.tool_buttons_layout.setSpacing(4)
        self.tool_buttons_layout.setContentsMargins(0, 0, 0, 0)
        for c in range(4):
            self.tool_buttons_layout.setColumnStretch(c, 1)
        v_ann.addLayout(self.tool_buttons_layout)
        
        # Action Layout for managing list
        h_ann_actions = QHBoxLayout()
        h_ann_actions.setContentsMargins(0, 0, 0, 0)
        
        # Clear Button
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
        self.list_ann.setMinimumHeight(100)
        self.list_ann.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.list_ann.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list_ann.itemSelectionChanged.connect(self._on_list_selection_changed)
        self.list_ann.itemChanged.connect(self._on_item_changed)
        v_ann.addWidget(self.list_ann)
        
        self.lbl_ann_count = QLabel(tr("Total Annotations: 0"))
        v_ann.addWidget(self.lbl_ann_count)

        self.grp_annotations.setLayout(v_ann)
        layout.addWidget(self.grp_annotations)
        
        # --- 2. Properties Group ---
        self.grp_props = QGroupBox(tr("Properties"))
        self.grp_props.setObjectName("grp_props")
        self.grp_props.setProperty("full_title", tr("Properties"))
        
        self.grid_props = QGridLayout()
        self.grid_props.setSpacing(4)
        self.grid_props.setContentsMargins(4, 12, 4, 4)
        
        # --- Row 0: Color ---
        self.grid_props.addWidget(QLabel(tr("Color:")), 0, 0)
        self.btn_ann_color = QToolButton()
        self.btn_ann_color.setFixedSize(24, 24)
        self.btn_ann_color.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_ann_color.setProperty("role", "color_picker")
        self.btn_ann_color.setStyleSheet("background-color: #FFFF00;") 
        self.btn_ann_color.clicked.connect(self._pick_ann_color)
        self.grid_props.addWidget(self.btn_ann_color, 0, 1)
        
        # --- Row 1: Thickness ---
        self.grid_props.addWidget(QLabel(tr("Thick:")), 1, 0)
        self.spin_ann_thickness = QSpinBox()
        self.spin_ann_thickness.setMaximumWidth(65)
        self.spin_ann_thickness.setRange(1, 50)
        self.spin_ann_thickness.setValue(2)
        self.spin_ann_thickness.setSuffix("px")
        self.spin_ann_thickness.valueChanged.connect(self._update_ann_props)
        self.grid_props.addWidget(self.spin_ann_thickness, 1, 1)
        
        # --- Row 2: Style ---
        self.lbl_ann_style = QLabel(tr("Style:"))
        self.grid_props.addWidget(self.lbl_ann_style, 2, 0)
        self.combo_ann_style = QComboBox()
        self.combo_ann_style.setMaximumWidth(85)
        self.combo_ann_style.addItems([tr("Solid"), tr("Dashed")])
        self.combo_ann_style.setItemData(0, "solid")
        self.combo_ann_style.setItemData(1, "dashed")
        self.combo_ann_style.currentIndexChanged.connect(self._update_ann_props)
        self.grid_props.addWidget(self.combo_ann_style, 2, 1)
        
        # --- Row 3: Size ---
        self.lbl_ann_size = QLabel(tr("Size:"))
        self.grid_props.addWidget(self.lbl_ann_size, 3, 0)
        self.spin_ann_size = QDoubleSpinBox()
        self.spin_ann_size.setMaximumWidth(75)
        self.spin_ann_size.setRange(1.0, 2000.0)
        self.spin_ann_size.setValue(15.0)
        self.spin_ann_size.setSuffix("px")
        self.spin_ann_size.valueChanged.connect(self._update_ann_props)
        self.grid_props.addWidget(self.spin_ann_size, 3, 1)

        # --- Row 4 & 5: Internal Properties ---
        self.lbl_ann_measurable = QLabel(tr("Measurable:"))
        self.grid_props.addWidget(self.lbl_ann_measurable, 4, 0)
        self.chk_measurable = ToggleSwitch()
        self.chk_measurable.toggled.connect(self._update_ann_props)
        self.grid_props.addWidget(self.chk_measurable, 4, 1)
        
        self.lbl_ann_export = QLabel(tr("Export:"))
        self.grid_props.addWidget(self.lbl_ann_export, 5, 0)
        self.chk_export = ToggleSwitch()
        self.chk_export.toggled.connect(self._update_ann_props)
        self.grid_props.addWidget(self.chk_export, 5, 1)

        # --- Dynamic Params ---
        self.dynamic_params_container = QWidget()
        self.grid_props.addWidget(self.dynamic_params_container, 6, 0, 1, 2)
        v_dynamic = QVBoxLayout(self.dynamic_params_container)
        v_dynamic.setContentsMargins(0, 0, 0, 0)
        v_dynamic.setSpacing(5)
        
        # Dash Params
        self.widget_dash_params = QWidget()
        h_dash = QHBoxLayout(self.widget_dash_params)
        h_dash.setContentsMargins(0, 0, 0, 0)
        h_dash.setSpacing(4)
        
        h_dash.addWidget(QLabel(tr("Dash:")))
        self.spin_dash_len = QSpinBox()
        self.spin_dash_len.setRange(1, 200)
        self.spin_dash_len.setValue(10)
        self.spin_dash_len.setToolTip(tr("Dash Length"))
        self.spin_dash_len.valueChanged.connect(self._update_ann_props)
        h_dash.addWidget(self.spin_dash_len)
        
        h_dash.addWidget(QLabel(tr("Gap:")))
        self.spin_dash_gap = QSpinBox()
        self.spin_dash_gap.setRange(1, 200)
        self.spin_dash_gap.setValue(5)
        self.spin_dash_gap.setToolTip(tr("Gap Length"))
        self.spin_dash_gap.valueChanged.connect(self._update_ann_props)
        h_dash.addWidget(self.spin_dash_gap)
        
        v_dynamic.addWidget(self.widget_dash_params)
        
        # Text Params
        self.widget_text_params = QWidget()
        v_text = QVBoxLayout(self.widget_text_params)
        v_text.setContentsMargins(0, 0, 0, 0)
        h_row1 = QHBoxLayout()
        h_row1.setContentsMargins(0, 0, 0, 0)
        h_row1.addWidget(QLabel(tr("Text:")))
        self.edit_text = QLineEdit()
        self.edit_text.setPlaceholderText(tr("Enter text"))
        self.edit_text.textChanged.connect(self._update_ann_props)
        h_row1.addWidget(self.edit_text)
        # Apply button row
        h_row2 = QHBoxLayout()
        h_row2.setContentsMargins(0, 0, 0, 0)
        from PySide6.QtWidgets import QPushButton
        self.btn_apply_text = QPushButton(tr("Apply"))
        self.btn_apply_text.setToolTip(tr("Apply text to selected annotation"))
        self.btn_apply_text.clicked.connect(self.apply_text_to_selection)
        h_row2.addWidget(self.btn_apply_text)
        v_text.addLayout(h_row1)
        v_text.addLayout(h_row2)
        h_row2 = QHBoxLayout()
        h_row2.setContentsMargins(0, 0, 0, 0)
        h_row2.addWidget(QLabel(tr("Font:")))
        self.combo_font = QComboBox()
        self.combo_font.addItems(["Arial", "Helvetica", "Times New Roman", "Courier New", "Verdana"])
        self.combo_font.currentTextChanged.connect(self._update_ann_props)
        h_row2.addWidget(self.combo_font)
        v_text.addLayout(h_row2)
        
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
        h_row3 = QHBoxLayout()
        h_row3.setContentsMargins(0, 0, 0, 0)
        h_row3.addWidget(self.btn_align_left)
        h_row3.addWidget(self.btn_align_center)
        h_row3.addWidget(self.btn_align_right)
        v_text.addLayout(h_row3)
        v_dynamic.addWidget(self.widget_text_params)
        
        # Arrow Params (Deprecated - moved to standard Size control)
        self.widget_arrow_params = QWidget()
        self.widget_arrow_params.hide()
        
        # Smooth Option (for Polygons)
        self.row_smooth = QHBoxLayout()
        self.lbl_ann_smooth = QLabel(tr("Smooth Curve (Catmull-Rom)"))
        self.chk_ann_smooth = ToggleSwitch()
        self.chk_ann_smooth.toggled.connect(self._update_ann_props)
        self.row_smooth.addWidget(self.lbl_ann_smooth)
        self.row_smooth.addStretch()
        self.row_smooth.addWidget(self.chk_ann_smooth)
        v_dynamic.addLayout(self.row_smooth)
        
        self.grp_props.setLayout(self.grid_props)
        layout.addWidget(self.grp_props)
        
        # Now create tool buttons after all property widgets are initialized
        self.btn_add_arrow = self._create_tool_button("arrow", "arrow")
        self.btn_add_arrow.setToolTip(tr("Arrow Tool"))
        self.btn_add_text = self._create_tool_button("text", "text")
        self.btn_add_text.setToolTip(tr("Text Tool"))
        self.tool_buttons_layout.addWidget(self.btn_add_arrow, 0, 0)
        self.tool_buttons_layout.addWidget(self.btn_add_text, 0, 1)

        # Initially hide tool-specific params
        self.widget_dash_params.hide()
        self.widget_text_params.hide()
        self.widget_arrow_params.hide()
        self.chk_ann_smooth.hide()
        self.lbl_ann_size.hide()
        self.spin_ann_size.hide()

        # --- 3. Scale Bar Group ---
        self.grp_scale_bar = QGroupBox(tr("Scale Bar"))
        self.grp_scale_bar.setObjectName("grp_scale_bar")
        self.grp_scale_bar.setProperty("full_title", tr("Scale Bar"))
        v_scale = QVBoxLayout()
        v_scale.setSpacing(4)
        v_scale.setContentsMargins(4, 12, 4, 4)
        
        # Enable Checkbox
        self.row_enabled = QHBoxLayout()
        self.lbl_enabled = QLabel(tr("Enable"))
        self.chk_enabled = ToggleSwitch()
        self.chk_enabled.setChecked(self.session.scale_bar_settings.enabled)
        self.chk_enabled.toggled.connect(self._update_settings)
        self.row_enabled.addWidget(self.lbl_enabled)
        self.row_enabled.addStretch()
        self.row_enabled.addWidget(self.chk_enabled)
        v_scale.addLayout(self.row_enabled)
        
        # Use Grid Layout for more compact parameters
        grid_scale = QGridLayout()
        grid_scale.setSpacing(2)
        grid_scale.setColumnStretch(0, 0)
        grid_scale.setColumnStretch(1, 1)
        
        # Row 0: Preset Scope
        grid_scale.addWidget(QLabel(tr("Scope:")), 0, 0)
        self.combo_scope = QComboBox()
        self.combo_scope.setMaximumWidth(90)
        self.combo_scope.addItem(tr("Custom"), "Custom")
        if "Generic" in MICROSCOPE_DB:
            self.combo_scope.addItem(tr("Generic"), "Generic")
        for name in sorted(MICROSCOPE_DB.keys()):
            if name != "Generic":
                self.combo_scope.addItem(name, name)
        self.combo_scope.currentIndexChanged.connect(self._on_scope_changed)
        grid_scale.addWidget(self.combo_scope, 0, 1)
        
        # Row 1: Objective
        grid_scale.addWidget(QLabel(tr("Obj:")), 1, 0)
        self.combo_obj = QComboBox()
        self.combo_obj.setMaximumWidth(90)
        self.combo_obj.setEnabled(False)
        self.combo_obj.currentIndexChanged.connect(self._on_objective_changed)
        grid_scale.addWidget(self.combo_obj, 1, 1)
        
        # Row 2: Pixel Size
        grid_scale.addWidget(QLabel(tr("Px:")), 2, 0)
        self.spin_pixel = QDoubleSpinBox()
        self.spin_pixel.setMaximumWidth(70)
        self.spin_pixel.setRange(0.001, 1000.0)
        self.spin_pixel.setDecimals(4)
        self.spin_pixel.setValue(self.session.scale_bar_settings.pixel_size)
        self.spin_pixel.setSuffix("μm")
        self.spin_pixel.valueChanged.connect(self._update_settings)
        grid_scale.addWidget(self.spin_pixel, 2, 1)
        
        # Row 3: Length
        grid_scale.addWidget(QLabel(tr("Len:")), 3, 0)
        self.spin_length = QDoubleSpinBox()
        self.spin_length.setMaximumWidth(70)
        self.spin_length.setRange(1.0, 10000.0)
        self.spin_length.setValue(self.session.scale_bar_settings.bar_length_um)
        self.spin_length.setSuffix("μm")
        self.spin_length.valueChanged.connect(self._update_settings)
        grid_scale.addWidget(self.spin_length, 3, 1)
        
        # Row 4: Position
        grid_scale.addWidget(QLabel(tr("Pos:")), 4, 0)
        self.combo_pos = QComboBox()
        self.combo_pos.setMaximumWidth(90)
        for p in ["Bottom Right", "Bottom Left", "Top Right", "Top Left"]:
            self.combo_pos.addItem(tr(p), p)
        idx = self.combo_pos.findData(self.session.scale_bar_settings.position)
        if idx >= 0: self.combo_pos.setCurrentIndex(idx)
        self.combo_pos.currentIndexChanged.connect(self._update_settings)
        grid_scale.addWidget(self.combo_pos, 4, 1)
        
        # Row 5: Label Checkbox
        grid_scale.addWidget(QLabel(tr("Show Label")), 5, 0)
        self.chk_label = ToggleSwitch()
        self.chk_label.setChecked(self.session.scale_bar_settings.show_label)
        self.chk_label.toggled.connect(self._update_settings)
        grid_scale.addWidget(self.chk_label, 5, 1)
        
        # Row 6: Color
        grid_scale.addWidget(QLabel(tr("Color:")), 6, 0)
        self.btn_color = QToolButton()
        self.btn_color.setFixedSize(24, 24)
        self.btn_color.setProperty("role", "color_picker")
        self.btn_color.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_color.clicked.connect(self._pick_color)
        self._update_color_button()
        grid_scale.addWidget(self.btn_color, 6, 1)
        
        # Row 7: Thickness
        grid_scale.addWidget(QLabel(tr("Thick:")), 7, 0)
        self.spin_thickness = QSpinBox()
        self.spin_thickness.setMaximumWidth(60)
        self.spin_thickness.setRange(1, 20)
        self.spin_thickness.setValue(self.session.scale_bar_settings.thickness)
        self.spin_thickness.setSuffix("px")
        self.spin_thickness.valueChanged.connect(self._update_settings)
        grid_scale.addWidget(self.spin_thickness, 7, 1)

        # Row 8: Font Size
        grid_scale.addWidget(QLabel(tr("Font:")), 8, 0)
        self.spin_font = QSpinBox()
        self.spin_font.setMaximumWidth(60)
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
        btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        btn.setMinimumSize(28, 28)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setProperty("tool_id", tool_id)
        
        btn.clicked.connect(lambda checked: self._on_tool_button_clicked(btn, checked))
        self.tool_group.addButton(btn)
        
        # Store for icon refresh
        if not hasattr(self, '_tool_buttons'):
            self._tool_buttons = {}
        self._tool_buttons[tool_id] = (btn, icon_name)
        
        return btn

    def refresh_icons(self):
        """Refresh all icons in the panel to match the current theme."""
        # 1. Main annotation tool buttons
        if hasattr(self, '_tool_buttons'):
            for btn, icon_name in self._tool_buttons.values():
                btn.setIcon(get_icon(icon_name))
        
        # 2. Action buttons
        if hasattr(self, 'btn_clear_ann'):
            self.btn_clear_ann.setIcon(get_icon("delete", "edit-clear-all"))
            
        # 3. Alignment buttons
        if hasattr(self, 'btn_align_left'):
            self.btn_align_left.setIcon(get_icon("align_left"))
        if hasattr(self, 'btn_align_center'):
            self.btn_align_center.setIcon(get_icon("align_center"))
        if hasattr(self, 'btn_align_right'):
            self.btn_align_right.setIcon(get_icon("align_right"))

    def _on_tool_button_clicked(self, btn, checked):
        tool_id = btn.property("tool_id")
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
        self.annotation_tool_selected.emit('none')
        self._update_tool_specific_controls('none')

    def select_annotation_by_id(self, ann_id):
        """Select an annotation in the list (triggered from Canvas)."""
        self._updating_from_canvas = True
        try:
            if not ann_id:
                self.list_ann.clearSelection()
                return
                
            for i in range(self.list_ann.count()):
                item = self.list_ann.item(i)
                if item.data(Qt.UserRole) == ann_id:
                    self.list_ann.setCurrentItem(item)
                    item.setSelected(True)
                    self.list_ann.scrollToItem(item)
                    return
        finally:
            self._updating_from_canvas = False

    def _on_item_changed(self, item):
        """Handle visibility checkbox toggle."""
        roi_id = item.data(Qt.UserRole)
        if roi_id and self.session.roi_manager:
            roi = self.session.roi_manager.get_roi(roi_id)
            if roi:
                new_visible = (item.checkState() == Qt.CheckState.Checked)
                if roi.visible != new_visible:
                    roi.visible = new_visible
                    
                    # SYNC: If visibility is changed via the list checkbox, 
                    # we usually want the export status to follow.
                    roi.export_with_image = new_visible
                    
                    # Notify manager and refresh property UI if selected
                    self.session.roi_manager.roi_updated.emit(roi)
                    
                    # If this is the currently selected item, update the checkbox in the property panel
                    selected_items = self.list_ann.selectedItems()
                    if len(selected_items) == 1 and selected_items[0] == item:
                        self._updating_ui = True
                        self.chk_export.setChecked(new_visible)
                        self._updating_ui = False

    def _on_list_selection_changed(self):
        """Handle selection from List -> Manager."""
        if self._updating_from_canvas:
            return
            
        selected_items = self.list_ann.selectedItems()
        selected_ids = [item.data(Qt.UserRole) for item in selected_items]
        
        # Sync to Manager
        if self.session.roi_manager:
            self.session.roi_manager.set_selected_ids(selected_ids)
            
        # Update UI props
        self._load_props_from_selection()

    def _on_manager_selection_changed(self):
        """Handle selection from Manager -> List."""
        if self.session.roi_manager:
            selected_ids = set(self.session.roi_manager.get_selected_ids())
            
            self._updating_from_canvas = True
            self.list_ann.blockSignals(True)
            try:
                for i in range(self.list_ann.count()):
                    item = self.list_ann.item(i)
                    rid = item.data(Qt.UserRole)
                    item.setSelected(rid in selected_ids)
            finally:
                self.list_ann.blockSignals(False)
                self._updating_from_canvas = False
            
            self._load_props_from_selection()

    def _load_props_from_selection(self):
        """Updates property widgets based on current selection."""
        selected_items = self.list_ann.selectedItems()
        
        self._updating_ui = True # Block signals
        try:
            if len(selected_items) == 1:
                rid = selected_items[0].data(Qt.UserRole)
                roi = self.session.roi_manager.get_roi(rid)
                if roi:
                    # Common
                    self.spin_ann_thickness.setValue(roi.properties.get('thickness', 2))
                    self._update_ann_color_preview(roi.color.name())
                    
                    style = roi.properties.get('style', 'solid')
                    idx = self.combo_ann_style.findData(style)
                    self.combo_ann_style.setCurrentIndex(idx if idx >= 0 else 0)
                    
                    self.chk_measurable.setChecked(roi.measurable)
                    self.chk_export.setChecked(roi.export_with_image)
                    
                    # Tool specific
                    self.spin_dash_len.setValue(roi.properties.get('dash_length', 10))
                    self.spin_dash_gap.setValue(roi.properties.get('dash_gap', 5))
                    
                    # Arrow / Text
                    if roi.roi_type == 'arrow':
                        self.spin_ann_size.setValue(roi.properties.get('arrow_head_size', 15.0))
                        
                    elif roi.roi_type == 'text':
                         self.spin_ann_size.setValue(roi.properties.get('font_size', 12.0))
                         self.edit_text.setText(roi.properties.get('text', 'Text'))
                         self.combo_font.setCurrentText(roi.properties.get('font_family', 'Arial'))
                         
                         align = roi.properties.get('alignment', 'left')
                         if align == 'center': self.btn_align_center.setChecked(True)
                         elif align == 'right': self.btn_align_right.setChecked(True)
                         else: self.btn_align_left.setChecked(True)
                    
                    self._update_tool_specific_controls(roi.roi_type)
                    
            elif not selected_items:
                # Update controls based on active tool even if no ROI selected
                active_tool = self.session.active_tool if hasattr(self.session, 'active_tool') else 'none'
                self._update_tool_specific_controls(active_tool)
                
                # Defaults or mixed
                self.chk_measurable.setChecked(self.default_properties['measurable'])
                self.chk_export.setChecked(self.default_properties['export_with_image'])
                # ... reset others ...
                
        finally:
            self._updating_ui = False

    def _update_ann_props(self, *args):
        """Called when UI widgets change."""
        if self._updating_ui:
            return

        # Get values
        thickness = self.spin_ann_thickness.value()
        style = self.combo_ann_style.currentData()
        size = self.spin_ann_size.value()
        measurable = self.chk_measurable.isChecked()
        export = self.chk_export.isChecked()
        
        # Update visibility of dash length based on style immediately
        tool_id = 'none'
        selected_items = self.list_ann.selectedItems()
        if selected_items:
            rid = selected_items[0].data(Qt.UserRole)
            roi = self.session.roi_manager.get_roi(rid)
            if roi: tool_id = roi.roi_type
        else:
            tool_id = self.session.active_tool if hasattr(self.session, 'active_tool') else 'none'
            
        if style == 'dashed' and tool_id not in ['text', 'line_scan']:
            self.widget_dash_params.show()
        else:
            self.widget_dash_params.hide()

        # Advanced
        dash_len = self.spin_dash_len.value()
        dash_gap = self.spin_dash_gap.value()
        text_content = self.edit_text.text()
        font = self.combo_font.currentText()
        align = "left"
        if self.btn_align_center.isChecked(): align = "center"
        if self.btn_align_right.isChecked(): align = "right"
        head_shape = "triangle" # Defaulting as requested
        arrow_head_size = size # Reuse standard size control
        smooth = self.chk_ann_smooth.isChecked()

        # Update Selection
        selected_items = self.list_ann.selectedItems()
        if selected_items:
            for item in selected_items:
                rid = item.data(Qt.UserRole)
                roi = self.session.roi_manager.get_roi(rid)
                if roi:
                    roi.measurable = measurable
                    roi.export_with_image = export
                    
                    # Update properties dict
                    roi.properties['thickness'] = thickness
                    roi.properties['style'] = style
                    roi.properties['dash_length'] = dash_len
                    roi.properties['dash_gap'] = dash_gap
                    roi.properties['smooth'] = smooth
                    
                    if roi.roi_type == 'arrow':
                        roi.properties['arrow_head_size'] = arrow_head_size
                        roi.properties['arrow_head_shape'] = head_shape
                    elif roi.roi_type == 'text':
                        roi.properties['font_size'] = size
                        roi.properties['text'] = text_content
                        roi.properties['font_family'] = font
                        roi.properties['alignment'] = align
                    
                    # Notify update
                    self.session.roi_manager.roi_updated.emit(roi)
            
            # Also notify tool settings change for real-time preview
            self.settings_changed.emit()
        else:
            # Update Defaults
            self.default_properties['thickness'] = thickness
            self.default_properties['style'] = style
            self.default_properties['dash_length'] = dash_len
            self.default_properties['dash_gap'] = dash_gap
            self.default_properties['arrow_head_size'] = arrow_head_size
            self.default_properties['measurable'] = measurable
            self.default_properties['export_with_image'] = export
            
            # For defaults, also notify settings change
            self.settings_changed.emit()

    def _pick_ann_color(self):
        color = QColorDialog.getColor(QColor(self.default_properties['color']), self, tr("Select Color"))
        if not color.isValid():
            return
            
        self._update_ann_color_preview(color.name())
        
        selected_items = self.list_ann.selectedItems()
        if selected_items:
            for item in selected_items:
                rid = item.data(Qt.UserRole)
                roi = self.session.roi_manager.get_roi(rid)
                if roi:
                    roi.color = color
                    self.session.roi_manager.roi_updated.emit(roi)
        else:
            self.default_properties['color'] = color.name()

    def _update_ann_color_preview(self, color_hex):
        pix = QPixmap(20, 20)
        pix.fill(QColor(color_hex))
        self.btn_ann_color.setIcon(QIcon(pix))

    def update_annotation_list(self):
        """Refreshes the list from RoiManager."""
        self.list_ann.blockSignals(True)
        self.list_ann.clear()
        
        if self.session.roi_manager:
            for roi in self.session.roi_manager.get_all_rois():
                label = f"{roi.label} ({roi.roi_type})"
                item = QListWidgetItem(label)
                item.setData(Qt.UserRole, roi.id)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.Checked if roi.visible else Qt.Unchecked)
                self.list_ann.addItem(item)
                
        self.list_ann.blockSignals(False)
        self._update_ann_count()
        
        # Restore selection if needed?
        self._on_manager_selection_changed()

    def _on_roi_added(self, roi):
        self.update_annotation_list()

    def _on_roi_removed(self, roi_id):
        self.update_annotation_list()

    def _on_roi_updated(self, roi):
        # Optional: Update label if name changed
        # For now just ensure list item exists
        pass

    def _update_ann_count(self):
        count = self.list_ann.count()
        self.lbl_ann_count.setText(tr("Total Annotations: {0}").format(count))

    def _update_tool_specific_controls(self, tool_id):
        """Shows/hides controls based on selected tool or annotation type."""
        self.lbl_ann_size.setVisible(False)
        self.spin_ann_size.setVisible(False)
        self.widget_text_params.hide()
        self.widget_arrow_params.hide()
        self.chk_ann_smooth.hide()
        self.widget_dash_params.hide()
        
        # Reset common controls
        self.lbl_ann_style.show()
        self.combo_ann_style.show()
        self.spin_ann_thickness.show()
        self.lbl_ann_measurable.show()
        self.chk_measurable.show()
        self.lbl_ann_export.show()
        self.chk_export.show()
        
        self.lbl_ann_size.setText(tr("Size:"))
        
        if tool_id == 'arrow':
            # Arrow uses the standard Size control for Head Size
            self.lbl_ann_size.setText(tr("Head Size:"))
            self.lbl_ann_size.setVisible(True)
            self.spin_ann_size.setVisible(True)
            self.lbl_ann_style.show() # Restore style (solid/dashed)
            self.combo_ann_style.show()
            self.lbl_ann_measurable.hide()
            self.chk_measurable.hide()
        elif tool_id == 'text':
            self.lbl_ann_size.setText(tr("Font Size:"))
            self.lbl_ann_size.setVisible(True)
            self.spin_ann_size.setVisible(True)
            self.widget_text_params.show()
            self.lbl_ann_style.hide()
            self.combo_ann_style.hide()
            self.lbl_ann_measurable.hide()
            self.chk_measurable.hide()
        elif tool_id == 'polygon':
            self.chk_ann_smooth.show()
        elif tool_id == 'line_scan':
            # LineScan doesn't need style/size controls usually
            self.lbl_ann_style.hide()
            self.combo_ann_style.hide()
            self.lbl_ann_size.hide()
            self.spin_ann_size.hide()
            self.lbl_ann_measurable.show() # Should be measurable
            self.lbl_ann_export.show() # Should be exportable
            
        style = self.combo_ann_style.currentData()
        if style == 'dashed' and tool_id not in ['text', 'line_scan']:
            self.widget_dash_params.show()

    def _toggle_annotations(self, visible):
        """Toggles visibility of all ROIs."""
        if not self.session.roi_manager:
            return
            
        # Batch update visibility
        for roi in self.session.roi_manager.get_all_rois():
            roi.visible = visible
            # We don't emit individual signals to avoid storm
            
        # Force full view update
        # We need a way to tell views to refresh ROI items from model
        # But UnifiedGraphicsItem listens to roi_updated? No, CanvasView connects signals.
        # CanvasView._on_roi_updated calls item.update_from_model
        
        # We can emit a special signal or just iterate views
        # For now, let's just trigger a repaint which might not be enough if items are not updated
        # Ideally, we emit a 'batch_updated' signal from manager
        self.session.roi_manager.project_changed.emit() # This triggers a reload in some places?

    # --- Scale Bar Methods (Preserved) ---
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
            self.spin_pixel.setEnabled(True)
            objectives = MICROSCOPE_DB[scope_name]
            for obj_name in sorted(objectives.keys(), key=lambda x: int(x.split('x')[0]) if 'x' in x else 0):
                val = objectives[obj_name]
                self.combo_obj.addItem(f"{obj_name} (~{val} um/px)", val)
            if self.combo_obj.count() > 0:
                self.combo_obj.setCurrentIndex(0)
                self._on_objective_changed(0)
        self.combo_obj.blockSignals(False)

    def _on_objective_changed(self, index):
        val = self.combo_obj.currentData()
        if val is not None:
            self.spin_pixel.setValue(float(val))
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

    def refresh_from_session(self):
        """Sync UI with current session settings."""
        s = self.session.scale_bar_settings
        self.chk_enabled.setChecked(s.enabled)
        self.spin_length.setValue(s.bar_length_um)
        self.spin_thickness.setValue(s.thickness)
        self.chk_label.setChecked(s.show_label)
        self.combo_pos.setCurrentText(s.position)
        self.update_annotation_list()

    def get_current_properties(self):
        """Returns the current properties (from selection or defaults)."""
        # If selection, return its props?
        # Or just return defaults?
        # Tools usually ask for defaults to start with.
        return self.default_properties.copy()
        
    def apply_text_to_selection(self):
        selected_items = self.list_ann.selectedItems()
        text_content = self.edit_text.text()
        for item in selected_items:
             rid = item.data(Qt.UserRole)
             roi = self.session.roi_manager.get_roi(rid)
             if roi and roi.roi_type == 'text':
                 roi.properties['text'] = text_content
                 self.session.roi_manager.roi_updated.emit(roi)

    def retranslate_ui(self):
        self.grp_scale_bar.setTitle(tr("Scale Bar"))
        self.lbl_enabled.setText(tr("Enable"))
        self.grp_annotations.setTitle(tr("Graphic Annotations"))
        self.lbl_ann_visible.setText(tr("Show Annotations"))
        self.btn_add_arrow.setToolTip(tr("Arrow Tool"))
        self.btn_add_text.setToolTip(tr("Text Tool"))
        self.btn_clear_ann.setToolTip(tr("Clear All Annotations"))
        self.grp_props.setTitle(tr("Properties"))
        self.lbl_ann_measurable.setText(tr("Measurable:"))
        self.lbl_ann_export.setText(tr("Export:"))
        self.lbl_ann_smooth.setText(tr("Smooth Curve (Catmull-Rom)"))
        
        # Dash Params
        if hasattr(self, 'spin_dash_len'):
            self.spin_dash_len.setToolTip(tr("Dash Length"))
        if hasattr(self, 'spin_dash_gap'):
            self.spin_dash_gap.setToolTip(tr("Gap Length"))
            
        self.update_annotation_list()
