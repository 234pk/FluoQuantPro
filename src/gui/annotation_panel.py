from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                               QGroupBox, QCheckBox, QDoubleSpinBox, QComboBox, 
                               QSpinBox, QColorDialog, QPushButton, QListWidget,
                               QListWidgetItem, QAbstractItemView, QGridLayout, QFrame, QButtonGroup, QSizePolicy)
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
    annotation_fixed_size_toggled = Signal(bool)

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
            'dot_spacing': 3
        }
        
        self.setup_ui()
        LanguageManager.instance().language_changed.connect(self.retranslate_ui)
        self.session.data_changed.connect(self._on_data_changed)

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(10)
        self.setMinimumWidth(0)

        # Initialize Button Group for Tools
        self.tool_group = QButtonGroup(self)
        self.tool_group.setExclusive(True)

        # --- 1. Graphic Annotations Group (Reordered to top as implied by context) ---
        self.grp_annotations = QGroupBox(tr("Graphic Annotations"))
        # Fluent/Card Style
        self.grp_annotations.setStyleSheet("""
            QGroupBox {
                border: 1px solid #E0E0E0;
                border-radius: 8px;
                margin-top: 1.5em;
                background-color: #FFFFFF;
                font-family: "Segoe UI", sans-serif;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 3px 0 3px;
                color: #4285F4;
                font-weight: bold;
            }
        """)
        v_ann = QVBoxLayout()
        v_ann.setSpacing(8)
        v_ann.setContentsMargins(4, 15, 4, 4)
        
        # Visibility Toggle
        self.chk_ann_visible = QCheckBox(tr("Show Annotations"))
        self.chk_ann_visible.setChecked(self.session.show_annotations)
        self.chk_ann_visible.toggled.connect(self._toggle_annotations)
        self.chk_ann_visible.setStyleSheet("QCheckBox { font-size: 10pt; color: #333; }")
        v_ann.addWidget(self.chk_ann_visible)
        
        # Tool Buttons - Grid Layout
        self.tool_buttons_layout = QGridLayout()
        self.tool_buttons_layout.setSpacing(4)
        self.tool_buttons_layout.setContentsMargins(0, 0, 0, 0)
        
        # Create buttons with Icons (using Unicode for now as placeholders for linear icons)
        # TODO: Replace with QIcon from resources when available
        self.btn_add_arrow = self._create_tool_button("↗", "arrow")
        self.btn_add_arrow.setToolTip(tr("Arrow Tool"))
        
        self.btn_add_line = self._create_tool_button("╱", "line")
        self.btn_add_line.setToolTip(tr("Line Tool"))
        
        self.btn_add_rect = self._create_tool_button("▭", "rect")
        self.btn_add_rect.setToolTip(tr("Rectangle Tool"))
        
        self.btn_add_circle = self._create_tool_button("○", "circle")
        self.btn_add_circle.setToolTip(tr("Circle Tool"))
        
        self.btn_add_ellipse = self._create_tool_button("⬭", "ellipse")
        self.btn_add_ellipse.setToolTip(tr("Ellipse Tool"))
        
        self.btn_add_poly = self._create_tool_button("⬠", "polygon")
        self.btn_add_poly.setToolTip(tr("Polygon Tool"))
        
        self.btn_add_text = self._create_tool_button("T", "text")
        self.btn_add_text.setToolTip(tr("Text Tool"))
        
        # Updated Icon for Batch Select
        self.btn_batch_select = self._create_tool_button("", "batch_select")
        self.btn_batch_select.setIcon(get_icon("batch_select"))
        self.btn_batch_select.setIconSize(QSize(24, 24))
        self.btn_batch_select.setToolTip(tr("Batch Select"))
        self.btn_batch_select.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        
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
        
        # Clear Button
        self.btn_clear_ann = QPushButton(tr("Clear All Annotations"))
        self.btn_clear_ann.setStyleSheet("""
            QPushButton {
                border: 1px solid #CCC;
                border-radius: 4px;
                padding: 6px;
                background-color: #F5F5F5;
                color: #333;
            }
            QPushButton:hover { background-color: #E8E8E8; }
            QPushButton:pressed { background-color: #DDD; }
        """)
        self.btn_clear_ann.clicked.connect(self.clear_annotations_requested.emit)
        v_ann.addWidget(self.btn_clear_ann)
        
        # Sync ROIs
        self.chk_sync_rois = QCheckBox(tr("Sync ROIs as Annotations"))
        
        self.settings = QSettings("FluoQuantPro", "AppSettings")
        sync_default = self.settings.value("interface/sync_rois_as_annotations", True, type=bool)
        self.chk_sync_rois.setChecked(sync_default)
        self.chk_sync_rois.toggled.connect(self._on_sync_rois_toggled)
        
        self.chk_sync_rois.setToolTip(tr("Automatically include ROIs in annotation list and exports"))
        v_ann.addWidget(self.chk_sync_rois)

        # Fixed Size Checkbox (Above List)
        self.chk_ann_fixed_size = QCheckBox(tr("Fixed Size Mode"))
        self.chk_ann_fixed_size.setToolTip(tr("Create new annotations with a fixed size on click"))
        self.chk_ann_fixed_size.toggled.connect(self._update_ann_fixed_size_mode)
        v_ann.addWidget(self.chk_ann_fixed_size)

        # Annotation List
        v_ann.addWidget(QLabel(tr("Manage Annotations:")))
        self.list_ann = QListWidget()
        self.list_ann.setMinimumWidth(0)
        self.list_ann.setMinimumHeight(100) # Minimum readable height
        self.list_ann.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding) # Allow compression/expansion
        self.list_ann.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list_ann.itemSelectionChanged.connect(self._on_selection_changed)
        self.list_ann.itemChanged.connect(self._on_item_changed)
        
        self.list_ann.setStyleSheet("""
            QListWidget {
                border: 1px solid #DDD;
                border-radius: 4px;
                padding: 4px;
                background-color: #FAFAFA;
                font-size: 10pt;
            }
            QListWidget::item {
                padding: 4px;
                border-bottom: 1px solid #EEE;
            }
            QListWidget::item:selected {
                background-color: #E8F0FE;
                color: #1967D2;
                border: 1px solid #D2E3FC;
                border-radius: 4px;
            }
        """)
        v_ann.addWidget(self.list_ann)
        
        self.lbl_ann_count = QLabel(tr("Total Annotations: 0"))
        v_ann.addWidget(self.lbl_ann_count)

        self.grp_annotations.setLayout(v_ann)
        layout.addWidget(self.grp_annotations)
        
        # --- 2. Properties Group ---
        self.grp_props = QGroupBox(tr("Properties"))
        self.grp_props.setStyleSheet("""
            QGroupBox {
                border: 1px solid #E0E0E0;
                border-radius: 8px;
                margin-top: 1.5em;
                background-color: #FFFFFF;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 3px 0 3px;
                color: #4285F4;
                font-weight: bold;
            }
            QLabel { font-size: 9pt; color: #555; }
        """)
        v_props = QVBoxLayout()
        v_props.setSpacing(10)
        v_props.setContentsMargins(10, 15, 10, 10)
        
        # Color & Thickness Row
        h_style = QHBoxLayout()
        
        # Color
        self.btn_ann_color = QPushButton()
        self.btn_ann_color.setMinimumSize(24, 24) # Allow shrinking if needed, but 24 is small enough
        self.btn_ann_color.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.btn_ann_color.setToolTip(tr("Click to change color"))
        self.btn_ann_color.setStyleSheet("border: 1px solid #CCC; border-radius: 4px;")
        self.btn_ann_color.clicked.connect(self._pick_ann_color)
        
        # Thickness
        self.spin_ann_thickness = QSpinBox()
        self.spin_ann_thickness.setRange(1, 20)
        self.spin_ann_thickness.setValue(2)
        # self.spin_ann_thickness.setMinimumWidth(40) 
        self.spin_ann_thickness.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.spin_ann_thickness.setStyleSheet("QSpinBox { padding: 4px; border: 1px solid #DDD; border-radius: 4px; }")
        self.spin_ann_thickness.valueChanged.connect(self._update_ann_props)
        
        self.lbl_ann_color = QLabel(tr("Color:"))
        h_style.addWidget(self.lbl_ann_color)
        h_style.addWidget(self.btn_ann_color)
        h_style.addSpacing(15)
        self.lbl_ann_width = QLabel(tr("Width:"))
        h_style.addWidget(self.lbl_ann_width)
        h_style.addWidget(self.spin_ann_thickness)
        h_style.addStretch()
        v_props.addLayout(h_style)
        
        # Divider
        line1 = QFrame()
        line1.setFrameShape(QFrame.Shape.HLine)
        line1.setFrameShadow(QFrame.Shadow.Plain)
        line1.setStyleSheet("background-color: #EEEEEE;")
        v_props.addWidget(line1)
        
        # Size & Style Row
        h_style2 = QHBoxLayout()
        
        self.spin_ann_size = QDoubleSpinBox()
        self.spin_ann_size.setRange(1.0, 1000.0)
        self.spin_ann_size.setValue(15.0)
        # self.spin_ann_size.setFixedWidth(70)
        # self.spin_ann_size.setStyleSheet("QDoubleSpinBox { padding: 4px; border: 1px solid #DDD; border-radius: 4px; }")
        self.spin_ann_size.valueChanged.connect(self._update_ann_props)
        
        self.combo_ann_style = QComboBox()
        self.combo_ann_style.addItems([tr("Solid"), tr("Dashed"), tr("Dotted")])
        self.combo_ann_style.setItemData(0, "solid")
        self.combo_ann_style.setItemData(1, "dashed")
        self.combo_ann_style.setItemData(2, "dotted")
        self.combo_ann_style.setStyleSheet("QComboBox { padding: 4px; border: 1px solid #DDD; border-radius: 4px; }")
        self.combo_ann_style.currentIndexChanged.connect(self._update_ann_props)
        
        self.lbl_ann_size = QLabel(tr("Size:"))
        h_style2.addWidget(self.lbl_ann_size)
        h_style2.addWidget(self.spin_ann_size)
        h_style2.addSpacing(15)
        self.lbl_ann_style = QLabel(tr("Style:"))
        h_style2.addWidget(self.lbl_ann_style)
        h_style2.addWidget(self.combo_ann_style)
        v_props.addLayout(h_style2)
        
        # Advanced Params (Dash/Dot)
        self.widget_dash_params = QWidget()
        h_dash = QHBoxLayout(self.widget_dash_params)
        h_dash.setContentsMargins(0, 0, 0, 0)
        
        self.spin_dash_len = QSpinBox()
        self.spin_dash_len.setRange(1, 100)
        self.spin_dash_len.setValue(10)
        self.spin_dash_len.setSuffix(" px")
        self.spin_dash_len.setToolTip(tr("Dash Length"))
        self.spin_dash_len.valueChanged.connect(self._update_ann_props)
        
        self.spin_dash_gap = QSpinBox()
        self.spin_dash_gap.setRange(1, 100)
        self.spin_dash_gap.setValue(5)
        self.spin_dash_gap.setSuffix(" px")
        self.spin_dash_gap.setToolTip(tr("Dash Gap"))
        self.spin_dash_gap.valueChanged.connect(self._update_ann_props)
        
        h_dash.addWidget(QLabel(tr("Len:")))
        h_dash.addWidget(self.spin_dash_len)
        h_dash.addWidget(QLabel(tr("Gap:")))
        h_dash.addWidget(self.spin_dash_gap)
        v_props.addWidget(self.widget_dash_params)
        
        self.widget_dot_params = QWidget()
        h_dot = QHBoxLayout(self.widget_dot_params)
        h_dot.setContentsMargins(0, 0, 0, 0)
        
        self.spin_dot_size = QSpinBox()
        self.spin_dot_size.setRange(1, 50)
        self.spin_dot_size.setValue(2)
        self.spin_dot_size.setSuffix(" px")
        self.spin_dot_size.setToolTip(tr("Dot Size (Diameter)"))
        self.spin_dot_size.valueChanged.connect(self._update_ann_props)
        
        self.spin_dot_spacing = QSpinBox()
        self.spin_dot_spacing.setRange(1, 100)
        self.spin_dot_spacing.setValue(3)
        self.spin_dot_spacing.setSuffix(" px")
        self.spin_dot_spacing.setToolTip(tr("Dot Spacing"))
        self.spin_dot_spacing.valueChanged.connect(self._update_ann_props)
        
        h_dot.addWidget(QLabel(tr("Size:")))
        h_dot.addWidget(self.spin_dot_size)
        h_dot.addWidget(QLabel(tr("Space:")))
        h_dot.addWidget(self.spin_dot_spacing)
        v_props.addWidget(self.widget_dot_params)
        
        # Text Params (Font, Alignment)
        self.widget_text_params = QWidget()
        h_text = QHBoxLayout(self.widget_text_params)
        h_text.setContentsMargins(0, 0, 0, 0)
        
        self.combo_font = QComboBox()
        self.combo_font.addItems(["Arial", "Helvetica", "Times New Roman", "Courier New", "Verdana"])
        self.combo_font.setToolTip(tr("Font Family"))
        self.combo_font.currentTextChanged.connect(self._update_ann_props)
        
        self.group_align = QButtonGroup(self)
        self.btn_align_left = QPushButton("L")
        self.btn_align_left.setCheckable(True)
        self.btn_align_left.setMinimumWidth(24)
        self.btn_align_center = QPushButton("C")
        self.btn_align_center.setCheckable(True)
        self.btn_align_center.setMinimumWidth(24)
        self.btn_align_right = QPushButton("R")
        self.btn_align_right.setCheckable(True)
        self.btn_align_right.setMinimumWidth(24)
        self.group_align.addButton(self.btn_align_left)
        self.group_align.addButton(self.btn_align_center)
        self.group_align.addButton(self.btn_align_right)
        self.group_align.buttonClicked.connect(self._update_ann_props)
        
        h_text.addWidget(QLabel(tr("Font:")))
        h_text.addWidget(self.combo_font)
        h_text.addWidget(self.btn_align_left)
        h_text.addWidget(self.btn_align_center)
        h_text.addWidget(self.btn_align_right)
        v_props.addWidget(self.widget_text_params)

        # Arrow Params (Head Shape)
        self.widget_arrow_params = QWidget()
        h_arrow = QHBoxLayout(self.widget_arrow_params)
        h_arrow.setContentsMargins(0, 0, 0, 0)
        
        self.combo_arrow_head = QComboBox()
        self.combo_arrow_head.addItem(tr("V-Shape"), "open")
        self.combo_arrow_head.addItem(tr("Triangle"), "triangle")
        self.combo_arrow_head.addItem(tr("Diamond"), "diamond")
        self.combo_arrow_head.addItem(tr("Circle"), "circle")
        self.combo_arrow_head.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.combo_arrow_head.setMinimumWidth(50)
        self.combo_arrow_head.currentIndexChanged.connect(self._update_ann_props)
        
        h_arrow.addWidget(QLabel(tr("Head:")))
        h_arrow.addWidget(self.combo_arrow_head)
        h_arrow.addStretch()
        v_props.addWidget(self.widget_arrow_params)

        # Initially hide tool-specific params
        self.widget_dash_params.hide()
        self.widget_dot_params.hide()
        self.widget_text_params.hide()
        self.widget_arrow_params.hide()
        
        # Actions Row
        h_prop_actions = QHBoxLayout()
        
        self.chk_ann_export = QCheckBox(tr("Export Only"))
        self.chk_ann_export.setToolTip(tr("If checked, only visible in exported images, not on canvas analysis"))
        self.chk_ann_export.toggled.connect(self._update_ann_props)
        h_prop_actions.addWidget(self.chk_ann_export)
        
        h_prop_actions.addStretch()
        
        self.btn_dup_ann = QPushButton(tr("Duplicate"))
        self.btn_dup_ann.clicked.connect(self._duplicate_selected_ann)
        self.btn_dup_ann.setToolTip(tr("Duplicate selected annotation(s)"))
        h_prop_actions.addWidget(self.btn_dup_ann)
        
        self.btn_del_ann = QPushButton(tr("Delete"))
        self.btn_del_ann.clicked.connect(self._delete_selected_ann)
        h_prop_actions.addWidget(self.btn_del_ann)
        
        v_props.addLayout(h_prop_actions)

        self.grp_props.setLayout(v_props)
        layout.addWidget(self.grp_props)
        
        # --- 3. Scale Bar Group ---
        self.grp_scale_bar = QGroupBox(tr("Scale Bar"))
        self.grp_scale_bar.setStyleSheet("""
            QGroupBox {
                border: 1px solid #E0E0E0;
                border-radius: 8px;
                margin-top: 1.5em;
                background-color: #FDFDFD;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 3px 0 3px;
                color: #555;
                font-weight: bold;
            }
        """)
        v_scale = QVBoxLayout()
        v_scale.setSpacing(8)
        
        # Enable Checkbox
        self.chk_enabled = QCheckBox(tr("Enable Scale Bar"))
        self.chk_enabled.setChecked(self.session.scale_bar_settings.enabled)
        self.chk_enabled.toggled.connect(self._update_settings)
        v_scale.addWidget(self.chk_enabled)
        
        # Preset Row
        h_micro = QHBoxLayout()
        self.combo_scope = QComboBox()
        self.combo_scope.addItem(tr("Custom / Manual"), "Custom")
        if "Generic" in MICROSCOPE_DB:
            self.combo_scope.addItem("Generic", "Generic")
        for name in sorted(MICROSCOPE_DB.keys()):
            if name != "Generic":
                self.combo_scope.addItem(name, name)
        self.combo_scope.currentIndexChanged.connect(self._on_scope_changed)
        
        self.combo_obj = QComboBox()
        self.combo_obj.setEnabled(False)
        self.combo_obj.currentIndexChanged.connect(self._on_objective_changed)
        
        h_micro.addWidget(QLabel(tr("Preset:")))
        h_micro.addWidget(self.combo_scope)
        h_micro.addWidget(self.combo_obj)
        v_scale.addLayout(h_micro)
        
        # Pixel Size & Length
        h_params = QHBoxLayout()
        self.spin_pixel = QDoubleSpinBox()
        self.spin_pixel.setRange(0.001, 1000.0)
        self.spin_pixel.setDecimals(4)
        self.spin_pixel.setValue(self.session.scale_bar_settings.pixel_size)
        self.spin_pixel.valueChanged.connect(self._update_settings)
        
        self.spin_length = QDoubleSpinBox()
        self.spin_length.setRange(1.0, 10000.0)
        self.spin_length.setValue(self.session.scale_bar_settings.bar_length_um)
        self.spin_length.valueChanged.connect(self._update_settings)
        
        self.lbl_pixel = QLabel(tr("Px Size:"))
        h_params.addWidget(self.lbl_pixel)
        h_params.addWidget(self.spin_pixel)
        self.lbl_length = QLabel(tr("Length:"))
        h_params.addWidget(self.lbl_length)
        h_params.addWidget(self.spin_length)
        v_scale.addLayout(h_params)
        
        # Advanced (Color, Pos)
        h_adv = QHBoxLayout()
        self.combo_pos = QComboBox()
        for p in ["Bottom Right", "Bottom Left", "Top Right", "Top Left"]:
            self.combo_pos.addItem(tr(p), p)
        idx = self.combo_pos.findData(self.session.scale_bar_settings.position)
        if idx >= 0: self.combo_pos.setCurrentIndex(idx)
        self.combo_pos.currentIndexChanged.connect(self._update_settings)
        
        # Scale Bar Style (Color, Thickness, Font Size)
        self.btn_color = QPushButton()
        self.btn_color.setMinimumSize(24, 24)
        self.btn_color.clicked.connect(self._pick_color)
        self._update_color_button()
        
        self.spin_thickness = QSpinBox()
        self.spin_thickness.setRange(1, 20)
        self.spin_thickness.setValue(self.session.scale_bar_settings.thickness)
        # self.spin_thickness.setMinimumWidth(50)
        self.spin_thickness.setToolTip(tr("Bar Thickness"))
        self.spin_thickness.valueChanged.connect(self._update_settings)

        self.spin_font = QSpinBox()
        self.spin_font.setRange(6, 72)
        self.spin_font.setValue(self.session.scale_bar_settings.font_size)
        # self.spin_font.setMinimumWidth(50)
        self.spin_font.setToolTip(tr("Font Size"))
        self.spin_font.valueChanged.connect(self._update_settings)
        
        self.chk_label = QCheckBox(tr("Label"))
        self.chk_label.setChecked(self.session.scale_bar_settings.show_label)
        self.chk_label.toggled.connect(self._update_settings)
        
        h_adv.addWidget(QLabel(tr("Pos:")))
        h_adv.addWidget(self.combo_pos)
        h_adv.addWidget(QLabel(tr("Color:")))
        h_adv.addWidget(self.btn_color)
        h_adv.addWidget(self.spin_thickness)
        h_adv.addWidget(self.spin_font)
        h_adv.addWidget(self.chk_label)
        v_scale.addLayout(h_adv)
        
        self.grp_scale_bar.setLayout(v_scale)
        layout.addWidget(self.grp_scale_bar)
        
        layout.addStretch()

        # Apply Global Style for SpinBoxes to ensure text is visible and buttons are reasonable
        spin_style = """
            QSpinBox, QDoubleSpinBox {
                padding: 4px;
                border: 1px solid #CCC;
                border-radius: 4px;
                font-size: 10pt;
            }
            QSpinBox::up-button, QDoubleSpinBox::up-button, 
            QSpinBox::down-button, QDoubleSpinBox::down-button {
                width: 15px;
                border-left: 1px solid #DDD;
                background: #F8F8F8;
                margin: 1px;
            }
            QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
            QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {
                background: #E0E0E0;
            }
        """
        self.setStyleSheet(spin_style)

    def _create_tool_button(self, text, tool_id):
        """Creates a styled toggle button for annotation tools."""
        btn = QPushButton(text)
        btn.setCheckable(True)
        # Restore larger size for usability as requested by user
        # btn.setFixedSize(48, 48) # Removed fixed size to allow compression
        btn.setMinimumSize(32, 32)
        btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed) # Allow expanding/shrinking horizontally
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setProperty("tool_id", tool_id)
        
        # Stylesheet for interaction feedback
        # Increased font size for Unicode icons to match button size
        btn.setStyleSheet("""
            QPushButton {
                border: 1px solid #D0D0D0;
                border-radius: 8px;
                background-color: #FFFFFF;
                color: #333;
                font-size: 16pt; 
                padding: 0px;
            }
            QPushButton:hover {
                background-color: #F0F0F0;
                border-color: #B0B0B0;
                color: #333; 
                background-color: rgba(66, 133, 244, 0.1);
            }
            QPushButton:checked {
                background-color: #E8F0FE; 
                border: 2px solid #4285F4;
                color: #1967D2;
            }
            QPushButton:pressed {
                background-color: #D2E3FC;
                border-style: inset;
                border: 2px solid #3367D6;
            }
        """)
        
        # Connect clicked (for manual toggle logic)
        btn.clicked.connect(lambda checked: self._on_tool_button_clicked(btn, checked))
        self.tool_group.addButton(btn)
        return btn

    def _on_tool_button_clicked(self, btn, checked):
        """Handles mutual exclusivity and toggle-off logic."""
        # If checked, uncheck all others
        if checked:
            self._uncheck_others(btn)
            tool_id = btn.property("tool_id")
            self.annotation_tool_selected.emit(tool_id)
        else:
            # If unchecked (clicked again), it means we want to deselect
            self.annotation_tool_selected.emit("none")

    def _uncheck_others(self, current_btn):
        """Unchecks all tool buttons except the current one."""
        buttons = [
            self.btn_add_arrow, self.btn_add_line, self.btn_add_rect, 
            self.btn_add_circle, self.btn_add_ellipse, self.btn_add_poly, 
            self.btn_add_text, self.btn_batch_select
        ]
        for b in buttons:
            if b != current_btn and b.isChecked():
                b.blockSignals(True) # Prevent recursion
                b.setChecked(False)
                b.blockSignals(False)

    def _on_tool_clicked(self, tool_id, checked):
        # Legacy handler, superseded by _on_tool_button_clicked
        pass

    def clear_tool_selection(self):
        """Unchecks all tool buttons."""
        self.tool_group.setExclusive(False)
        for btn in self.tool_group.buttons():
            btn.setChecked(False)
        self.tool_group.setExclusive(True)
        self._update_tool_specific_controls('none')

    def _update_ann_fixed_size_mode(self, checked):
        # We need to signal the CanvasView about this mode change.
        self.annotation_fixed_size_toggled.emit(checked)

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

    def _on_sync_rois_toggled(self, checked):
        """Persist the sync setting."""
        self.settings.setValue("interface/sync_rois_as_annotations", checked)
        # Trigger immediate sync if enabled?
        # Maybe handled by main window observing this checkbox or signal

    def _update_style_controls_visibility(self):
        style = self.combo_ann_style.currentData()
        if style == 'dashed':
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
            self.chk_ann_export,
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
                self.chk_ann_export.setChecked(ann.export_only)
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
            self.chk_ann_export.setChecked(self.default_properties['export_only'])
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
           not hasattr(self, 'chk_ann_export') or \
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
        export_only = self.chk_ann_export.isChecked()
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
        
        self._update_style_controls_visibility()
        
        if not selected_items:
            # Update defaults
            self.default_properties['thickness'] = thickness
            self.default_properties['export_only'] = export_only
            if style in ['solid', 'dashed', 'dotted']:
                self.default_properties['style'] = style
            self.default_properties['arrow_head_size'] = arrow_size
            self.default_properties['dash_length'] = dash_len
            self.default_properties['dash_gap'] = dash_gap
            self.default_properties['dot_size'] = dot_size
            self.default_properties['dot_spacing'] = dot_spacing
            
            self.default_properties['font_family'] = font
            self.default_properties['alignment'] = align
            self.default_properties['arrow_head_shape'] = head_shape
            return
            
        for item in selected_items:
            idx = self.list_ann.row(item)
            ann = self.session.annotations[idx]
            
            # Update properties
            ann.thickness = thickness
            ann.export_only = export_only
            
            # Update style
            if style in ['solid', 'dashed', 'dotted']:
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
            
            # Note: We don't sync thickness back to ROI as ROIs have fixed dash styles,
            # but we could if ROI model supported it.
            
        self.annotation_updated.emit()
        self.settings_changed.emit()

    def get_current_properties(self):
        """Returns the current properties (from selection or defaults)."""
        selected_items = self.list_ann.selectedItems()
        if not selected_items:
            return self.default_properties.copy()
            
        # If selection exists, return properties of the first selected item
        # But this might be confusing if mixed selection.
        # Actually, if selection exists, the UI reflects the first item.
        # But for CREATING new annotations, we should probably stick to defaults?
        # OR should we use the properties of the selected item as template?
        # Let's use the UI values which reflect the first selected item.
        
        props = self.default_properties.copy()
        props['color'] = self.default_properties['color'] # UI doesn't expose color hex text, need to track it?
        # Wait, color button has icon, but we don't store hex in UI text.
        # We need to rely on what was last set or loaded.
        
        # If selection, we can read from the annotation object
        idx = self.list_ann.row(selected_items[0])
        ann = self.session.annotations[idx]
        props['color'] = ann.color
        props['thickness'] = ann.thickness
        props['style'] = ann.style
        props['export_only'] = ann.export_only
        props['arrow_head_size'] = ann.properties.get('arrow_head_size', 15.0)
        props['dash_length'] = ann.properties.get('dash_length', 10)
        props['dash_gap'] = ann.properties.get('dash_gap', 5)
        props['dot_size'] = ann.properties.get('dot_size', 2)
        props['dot_spacing'] = ann.properties.get('dot_spacing', 3)
        
        return props

    def _delete_selected_ann(self):
        selected_items = self.list_ann.selectedItems()
        if not selected_items:
            return
            
        # Delete from back to front to preserve indices
        rows = sorted([self.list_ann.row(item) for item in selected_items], reverse=True)
        for row in rows:
            self.session.annotations.pop(row)
            
        self.update_annotation_list()
        self.annotation_updated.emit()
        self.settings_changed.emit()

    def _duplicate_selected_ann(self):
        """Duplicates the selected annotations."""
        selected_items = self.list_ann.selectedItems()
        if not selected_items:
            return
            
        new_anns = []
        import uuid
        import copy
        
        for item in selected_items:
            idx = self.list_ann.row(item)
            if 0 <= idx < len(self.session.annotations):
                original = self.session.annotations[idx]
                
                # Create a deep copy
                new_ann = copy.deepcopy(original)
                new_ann.id = str(uuid.uuid4()) # New ID
                new_ann.roi_id = None # Decouple from ROI if it was a ref
                
                # Offset position slightly
                offset_x, offset_y = 20, 20
                if new_ann.points:
                    new_ann.points = [(p[0] + offset_x, p[1] + offset_y) for p in new_ann.points]
                
                new_anns.append(new_ann)
        
        if new_anns:
            self.session.annotations.extend(new_anns)
            self.update_annotation_list()
            self.annotation_updated.emit()
            self.settings_changed.emit()

    def refresh_from_session(self):
        """Sync UI with current session settings."""
        s = self.session.scale_bar_settings
        self.chk_enabled.setChecked(s.enabled)
        self.spin_length.setValue(s.bar_length_um)
        self.spin_thickness.setValue(s.thickness)
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

    def _on_tool_clicked(self, tool_type, checked=False):
        """Handles tool button clicks."""
        print(f"DEBUG: [AnnotationPanel] _on_tool_clicked: {tool_type} (checked={checked})")
        
        if checked:
            # Uncheck others manually
            for btn in self.tool_group.buttons():
                if btn != self.sender() and btn.isChecked():
                    btn.blockSignals(True)
                    btn.setChecked(False)
                    btn.blockSignals(False)
            
            self.annotation_tool_selected.emit(tool_type)
            
            # Update Property UI hints based on tool
            self._update_tool_specific_controls(tool_type)
        else:
            # If unchecked (clicked again), disable tool
            print(f"DEBUG: [AnnotationPanel] Tool {tool_type} toggled OFF.")
            self.annotation_tool_selected.emit('none')
            self._update_tool_specific_controls('none')

    def _update_tool_specific_controls(self, tool_type):
        """Shows/Hides specific controls based on selected tool."""
        # Hide all first
        self.lbl_ann_size.setVisible(False)
        self.spin_ann_size.setVisible(False)
        self.widget_text_params.hide()
        self.widget_arrow_params.hide()
        
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


    def _toggle_annotations(self, visible):
        self.session.show_annotations = visible
        self.settings_changed.emit()

    def _update_ann_count(self):
        self.lbl_ann_count.setText(tr("Total Annotations: {}").format(len(self.session.annotations)))

    def clear_tool_selection(self):
        """Unchecks all annotation tool buttons."""
        buttons = [
            self.btn_add_arrow, self.btn_add_line, self.btn_add_rect, 
            self.btn_add_circle, self.btn_add_ellipse, self.btn_add_poly, 
            self.btn_add_text, self.btn_batch_select
        ]
        for btn in buttons:
            if btn.isChecked():
                btn.blockSignals(True) # Prevent signal loop
                btn.setChecked(False)
                btn.blockSignals(False)

    def _update_color_button(self):
        pix = QPixmap(20, 20)
        pix.fill(QColor(self.session.scale_bar_settings.color))
        self.btn_color.setIcon(QIcon(pix))

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
        if hasattr(self, 'lbl_pixel'):
            self.lbl_pixel.setText(tr("Pixel Size (um/px):"))
        if hasattr(self, 'lbl_length'):
            self.lbl_length.setText(tr("Bar Length (um):"))
        if hasattr(self, 'lbl_pos'):
            self.lbl_pos.setText(tr("Position:"))
        # self.lbl_thickness.setText(tr("Thickness:"))
        self.chk_label.setText(tr("Show Label"))
        
        self.grp_annotations.setTitle(tr("Graphic Annotations"))
        self.chk_ann_visible.setText(tr("Show Annotations"))
        self.chk_ann_fixed_size.setText(tr("Fixed Size Mode"))
        self.btn_add_arrow.setText(tr("Arrow"))
        self.btn_add_line.setText(tr("Line"))
        self.btn_add_rect.setText(tr("Rect"))
        self.btn_add_circle.setText(tr("Circle"))
        self.btn_add_poly.setText(tr("Polygon"))
        self.btn_add_text.setText(tr("Text"))
        self.btn_batch_select.setText(tr("Batch Select"))
        self.btn_clear_ann.setText(tr("Clear All"))
        self.chk_sync_rois.setText(tr("Sync ROIs as Annotations"))
        self.grp_props.setTitle(tr("Properties"))
        
        if hasattr(self, 'lbl_ann_color'):
            self.lbl_ann_color.setText(tr("Color:"))
        if hasattr(self, 'lbl_ann_width'):
            self.lbl_ann_width.setText(tr("Width:"))
        if hasattr(self, 'lbl_ann_size'):
            self.lbl_ann_size.setText(tr("Size:"))
        if hasattr(self, 'lbl_ann_style'):
            self.lbl_ann_style.setText(tr("Style:"))
            
        self.chk_ann_export.setText(tr("Export Only"))
        self.btn_dup_ann.setText(tr("Duplicate"))
        self.btn_del_ann.setText(tr("Delete"))
        
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
        if idx >= 0:
            self.combo_pos.setCurrentIndex(idx)
        self.combo_pos.blockSignals(False)

        current_style = self.combo_ann_style.currentData()
        self.combo_ann_style.blockSignals(True)
        self.combo_ann_style.clear()
        self.combo_ann_style.addItem(tr("Solid"), "solid")
        self.combo_ann_style.addItem(tr("Dashed"), "dashed")
        self.combo_ann_style.addItem(tr("Dotted"), "dotted")
        style_idx = self.combo_ann_style.findData(current_style)
        if style_idx >= 0:
            self.combo_ann_style.setCurrentIndex(style_idx)
        self.combo_ann_style.blockSignals(False)

    def refresh_from_session(self):
        """Update UI components from current session settings."""
        s = self.session.scale_bar_settings
        self.blockSignals(True)
        self.chk_enabled.setChecked(s.enabled)
        self.spin_pixel.setValue(s.pixel_size)
        self.spin_length.setValue(s.bar_length_um)
        
        idx = self.combo_pos.findData(s.position)
        if idx >= 0:
            self.combo_pos.setCurrentIndex(idx)
            
        self.spin_thickness.setValue(s.thickness)
        self.chk_label.setChecked(s.show_label)
        self.spin_font.setValue(s.font_size)
        self._update_color_button()
        self.blockSignals(False)

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
