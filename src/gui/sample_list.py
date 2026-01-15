import os
import json
import time
from typing import Optional, List, Dict, Tuple
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QListWidget, QListWidgetItem, 
                               QLabel, QFileDialog, QInputDialog, QMenu, QMessageBox,
                               QSplitter, QAbstractItemView, QTreeWidget, QTreeWidgetItem,
                               QLineEdit, QHBoxLayout, QToolButton, QHeaderView,
                               QSizePolicy, QColorDialog, QApplication, QToolTip,
                               QDialog, QDialogButtonBox, QGridLayout, QComboBox, QRadioButton)
from PySide6.QtCore import Qt, Signal, QSize, QUrl, QSettings, QTimer, QPoint
from PySide6.QtGui import QColor, QDragEnterEvent, QDropEvent, QPixmap, QIcon, QAction, QPalette
from src.gui.icon_manager import get_icon
from src.gui.toggle_switch import ToggleSwitch
from src.core.language_manager import LanguageManager, tr
import tifffile
import qimage2ndarray
import numpy as np
import uuid
from src.core.project_model import ProjectModel, SceneData, ChannelDef
from src.core.channel_config import get_rgb_mapping
from PySide6.QtGui import QUndoCommand
import cv2

class MergeSplitDialog(QDialog):
    def __init__(self, file_path, channel_count, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Multi-Channel Image Detected"))
        self.result_choice = None # 'split', 'keep', 'skip'
        
        layout = QVBoxLayout(self)
        
        msg = tr("The image '{0}' appears to have {1} channels.").format(os.path.basename(file_path), channel_count)
        layout.addWidget(QLabel(msg))
        
        layout.addWidget(QLabel(tr("How would you like to handle it?")))
        
        self.btn_split = QRadioButton(tr("Split into separate channels (Recommended)"))
        self.btn_keep = QRadioButton(tr("Keep as Single Channel (Merge View)"))
        self.btn_skip = QRadioButton(tr("Skip this file"))
        
        self.btn_split.setChecked(True)
        
        layout.addWidget(self.btn_split)
        layout.addWidget(self.btn_keep)
        layout.addWidget(self.btn_skip)
        
        self.row_apply = QHBoxLayout()
        self.lbl_apply = QLabel(tr("Apply to all remaining conflicts"))
        self.apply_to_all = ToggleSwitch()
        self.row_apply.addWidget(self.lbl_apply)
        self.row_apply.addStretch()
        self.row_apply.addWidget(self.apply_to_all)
        layout.addLayout(self.row_apply)
        
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
    def accept(self):
        if self.btn_split.isChecked():
            self.result_choice = 'split'
        elif self.btn_keep.isChecked():
            self.result_choice = 'keep'
        else:
            self.result_choice = 'skip'
        super().accept()

class ConvertFileToSampleCommand(QUndoCommand):
    def __init__(self, model, file_path, color):
        super().__init__(tr("Set as Single Channel Sample"))
        self.model = model
        self.file_path = file_path
        self.color = color
        self.scene_id = str(uuid.uuid4())
        self.scene_name = os.path.splitext(os.path.basename(file_path))[0]
        self.added_scene = None

    def redo(self):
        # Create SceneData
        channel_def = ChannelDef(
            path=self.file_path,
            channel_type="unknown",
            color=self.color
        )
        
        # Ensure unique name
        base_name = self.scene_name
        counter = 1
        while base_name in self.model._scene_map:
            base_name = f"{self.scene_name}_{counter}"
            counter += 1
            
        self.added_scene = SceneData(
            id=base_name, # Use name as ID for consistency with manual creation or uuid? ProjectModel uses name as ID in _add_manual_scene_internal.
            name=base_name,
            channels=[channel_def],
            status="Pending"
        )
        # Use uuid if ProjectModel supports it, but _add_manual_scene_internal uses name.
        # Let's check SceneData definition. ID is string.
        # ProjectModel._add_manual_scene_internal uses name as ID.
        # We should probably stick to that convention or use UUID if we want.
        # But wait, _add_manual_scene_internal: new_scene = SceneData(id=name, name=name)
        
        self.model.scenes.append(self.added_scene)
        self.model._scene_map[self.added_scene.id] = self.added_scene
        self.model.is_dirty = True
        self.model.project_changed.emit()

    def undo(self):
        if self.added_scene:
            self.model._remove_scene_internal(self.added_scene.id)

class PreviewPopup(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedSize(256, 256)
        self.setAlignment(Qt.AlignCenter)
        self.setScaledContents(True)

class FileListWidget(QListWidget):
    """Custom ListWidget that exposes file paths as URLs for Drag & Drop.
       Also supports Quick Look (Preview) on hover.
    """
    delete_pressed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self._preview_popup = PreviewPopup(self)
        self._preview_cache = {} # path -> QPixmap
        self._current_hover_item = None

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Delete:
            self.delete_pressed.emit()
        else:
            super().keyPressEvent(event)
        
    def mimeData(self, items):
        mime = super().mimeData(items)
        urls = []
        valid_exts = ('.tif', '.tiff', '.png', '.jpg', '.jpeg', '.bmp')
        for item in items:
            path = item.data(Qt.ItemDataRole.UserRole)
            if path and os.path.exists(path) and path.lower().endswith(valid_exts):
                urls.append(QUrl.fromLocalFile(path))
        
        if urls:
            mime.setUrls(urls)
        return mime

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        item = self.itemAt(event.position().toPoint())
        
        if item != self._current_hover_item:
            self._current_hover_item = item
            if item:
                self._show_preview(item, event.globalPosition().toPoint())
            else:
                self._preview_popup.hide()
        elif item:
            # Move popup with mouse? Or keep it fixed?
            # Moving it avoids covering the list if user moves down.
            # But let's just update position if it's visible.
            if self._preview_popup.isVisible():
                self._update_popup_pos(event.globalPosition().toPoint())

    def leaveEvent(self, event):
        self._preview_popup.hide()
        self._current_hover_item = None
        super().leaveEvent(event)

    def _update_popup_pos(self, global_pos):
        # Position to the right of the cursor
        x = global_pos.x() + 20
        y = global_pos.y() + 20
        self._preview_popup.move(x, y)

    def _show_preview(self, item, global_pos):
        path = item.data(Qt.ItemDataRole.UserRole)
        if not path or not os.path.exists(path):
            self._preview_popup.hide()
            return

        if path in self._preview_cache:
            pixmap = self._preview_cache[path]
        else:
            pixmap = self._load_thumbnail(path)
            if pixmap:
                self._preview_cache[path] = pixmap
        
        if pixmap:
            self._preview_popup.setPixmap(pixmap)
            self._update_popup_pos(global_pos)
            self._preview_popup.show()
        else:
            self._preview_popup.hide()

    def _load_thumbnail(self, path):
        try:
            valid_exts = ('.tif', '.tiff', '.png', '.jpg', '.jpeg', '.bmp')
            if not path.lower().endswith(valid_exts):
                return None
                
            import cv2
            
            # 1. Try TiffFile for TIFFs (handles scientific data better)
            if path.lower().endswith(('.tif', '.tiff')):
                try:
                    with tifffile.TiffFile(path) as tif:
                        page = tif.pages[0]
                        shape = page.shape
                        
                        # Handle dimensions
                        if len(shape) == 2:
                            h, w = shape
                            is_rgb = False
                        elif len(shape) == 3:
                            h, w, c = shape
                            is_rgb = True
                        else:
                            return None
                            
                        # Subsample
                        subsample = max(1, min(h, w) // 256)
                        data = page.asarray(out='memmap')[::subsample, ::subsample]
                        
                        # RGB handling
                        if is_rgb:
                            if data.shape[-1] > 4:
                                data = np.max(data, axis=2)
                        
                        # Normalize
                        if data.dtype != np.uint8:
                            d_min, d_max = data.min(), data.max()
                            if d_max > d_min:
                                data = ((data - d_min) / (d_max - d_min) * 255).astype(np.uint8)
                            else:
                                data = np.zeros_like(data, dtype=np.uint8)
                                
                        return QPixmap.fromImage(qimage2ndarray.array2qimage(data, normalize=False))
                except Exception:
                    # Fallback to OpenCV if tifffile fails
                    pass

            # 2. Use OpenCV for everything else (or failed TIFFs)
            # img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
            # Fix for Unicode paths:
            img_stream = np.fromfile(path, dtype=np.uint8)
            img = cv2.imdecode(img_stream, cv2.IMREAD_UNCHANGED)
            
            if img is None:
                return None
                
            # Handle dimensions
            if img.ndim == 3:
                # Check for RGB (OpenCV is BGR)
                if img.shape[2] == 3:
                    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                elif img.shape[2] == 4:
                    img = cv2.cvtColor(img, cv2.COLOR_BGRA2RGBA)
            
            # Normalize if needed (e.g. 16-bit PNG)
            if img.dtype != np.uint8:
                d_min, d_max = img.min(), img.max()
                if d_max > d_min:
                    img = ((img - d_min) / (d_max - d_min) * 255).astype(np.uint8)
                else:
                    img = np.zeros_like(img, dtype=np.uint8)

            # Resize for thumbnail
            h, w = img.shape[:2]
            scale = min(256/w, 256/h)
            if scale < 1.0:
                new_w, new_h = int(w*scale), int(h*scale)
                img = cv2.resize(img, (new_w, new_h))
            
            return QPixmap.fromImage(qimage2ndarray.array2qimage(img, normalize=False))

        except Exception as e:
            # Silence errors for preview to avoid console spam
            # print(f"Error loading preview for {path}: {e}") 
            return None

class SampleTreeWidget(QTreeWidget):
    """Subclass to handle key events for deletion."""
    delete_pressed = Signal()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Delete:
            self.delete_pressed.emit()
        else:
            super().keyPressEvent(event)

class SampleListWidget(QWidget):
    """
    Sidebar widget to display the list of Scenes (Samples) and Unassigned Images.
    Allows user to navigate between different fields of view.
    Supports Manual Creation and Drag & Drop with Tree View for Channels.
    """
    scene_selected = Signal(str) # Emits scene_id
    channel_selected = Signal(str, int) # Emits scene_id, channel_index
    scene_renamed = Signal(str, str) # Emits old_id, new_id
    scene_deleted = Signal(str) # Added signal for deletion
    channel_color_changed = Signal(str, int, str) # scene_id, ch_index, new_color
    channel_file_assigned = Signal(str, int, str) # scene_id, ch_index, file_path
    channel_cleared = Signal(str, int) # scene_id, channel_index
    channel_removed = Signal(str, int) # scene_id, channel_index
    scene_structure_changed = Signal(str) # scene_id

    def __init__(self, project_model: ProjectModel, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.project_model = project_model
        self._drag_hint_last_key = None
        
        # Connect to model signals
        self.project_model.project_changed.connect(self.request_tree_refresh)
        
        # Debounced refresh for tree list
        self._tree_refresh_timer = QTimer(self)
        self._tree_refresh_timer.setSingleShot(True)
        self._tree_refresh_timer.setInterval(100) # 100ms debounce
        self._tree_refresh_timer.timeout.connect(self.refresh_list_actual)

        # Debounced refresh for pool list to handle 1200+ files smoothly
        self._pool_refresh_timer = QTimer(self)
        self._pool_refresh_timer.setSingleShot(True)
        self._pool_refresh_timer.setInterval(200) # 200ms debounce
        self._pool_refresh_timer.timeout.connect(self.refresh_pool_list_actual)
        self.project_model.project_changed.connect(self.request_pool_refresh)
        
        # Connect Language Change
        LanguageManager.instance().language_changed.connect(self.retranslate_ui)
        
        # Main Layout
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        
        # Splitter for Sample List (Top) and Pool (Bottom)
        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.layout.addWidget(self.splitter)
        
        # --- Top: Samples Tree ---
        self.top_widget = QWidget()
        top_layout = QVBoxLayout(self.top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(0)
        
        # Header Layout
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(8, 4, 8, 4) # Tighter header margins
        
        self.lbl_title = QLabel(tr("Project Samples") + " (0)")
        self.lbl_title.setProperty("role", "title")
        self.lbl_title.setMinimumWidth(0) # Allow title to shrink
        self.lbl_title.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        header_layout.addWidget(self.lbl_title)
        
        header_layout.addStretch()

        # Sort Button
        self.btn_sort_samples = QToolButton()
        # Use our generated icon (it will fallback to internal generation if png is missing)
        self.btn_sort_samples.setIcon(get_icon("sort"))
        self.btn_sort_samples.setIconSize(QSize(20, 20))
        self.btn_sort_samples.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.btn_sort_samples.setFixedSize(28, 28)
        self.btn_sort_samples.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_sort_samples.setToolTip(tr("Sort Samples A-Z"))
        # self.btn_sort_samples.setAutoRaise(True) # Disabled for consistent global styling
        self.btn_sort_samples.clicked.connect(self.sort_samples)
        header_layout.addWidget(self.btn_sort_samples)

        # Expand/Collapse All Button
        self.btn_expand_all = QToolButton()
        # Use our generated icon for expand
        self.btn_expand_all.setIcon(get_icon("expand")) 
        self.btn_expand_all.setIconSize(QSize(20, 20))
        self.btn_expand_all.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.btn_expand_all.setFixedSize(28, 28)
        self.btn_expand_all.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_expand_all.setToolTip(tr("Expand/Collapse All Channels"))
        # self.btn_expand_all.setAutoRaise(True) # Disabled for consistent global styling
        self.btn_expand_all.setCheckable(True)
        self.btn_expand_all.setChecked(True) # Default expanded
        self.btn_expand_all.toggled.connect(self.toggle_expand_all)
        header_layout.addWidget(self.btn_expand_all)
        
        self.btn_add_sample_header = QToolButton()
        self.btn_add_sample_header.setIcon(get_icon("add", "list-add"))
        self.btn_add_sample_header.setIconSize(QSize(20, 20))
        self.btn_add_sample_header.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.btn_add_sample_header.setFixedSize(28, 28)
        self.btn_add_sample_header.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add_sample_header.setToolTip(tr("Quick Add Blank Sample (Alt+N)"))
        # self.btn_add_sample_header.setAutoRaise(True) # Disabled for consistent global styling
        self.btn_add_sample_header.clicked.connect(self.quick_add_sample)
        header_layout.addWidget(self.btn_add_sample_header)
        
        # Batch Delete Button (next to Add button)
        self.btn_delete_selected = QToolButton()
        self.btn_delete_selected.setIcon(get_icon("delete", "edit-delete"))
        self.btn_delete_selected.setIconSize(QSize(20, 20))
        self.btn_delete_selected.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.btn_delete_selected.setFixedSize(28, 28)
        self.btn_delete_selected.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_delete_selected.setToolTip(tr("Delete Selected Samples"))
        # self.btn_delete_selected.setAutoRaise(True) # Disabled for consistent global styling
        self.btn_delete_selected.clicked.connect(self.on_delete_button_clicked)
        self.btn_delete_selected.setEnabled(False) # Disabled by default
        header_layout.addWidget(self.btn_delete_selected)
        
        top_layout.addLayout(header_layout)
        
        self.tree_widget = SampleTreeWidget()
        self.tree_widget.delete_pressed.connect(self.on_delete_button_clicked)
        self.tree_widget.setHeaderHidden(True)
        self.tree_widget.setAllColumnsShowFocus(True) # Make selection span all columns
        self.tree_widget.setIndentation(15) # Slightly tighter indentation
        # Enable multiple columns for button layout (Column 0: Text, Column 1: Button)
        self.tree_widget.setColumnCount(2)
        self.tree_widget.setMinimumWidth(0)
        self.tree_widget.setMinimumHeight(50) # Reduced from 100
        self.tree_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        header = self.tree_widget.header()
        header.setMinimumSectionSize(10) # Allow columns to be very narrow
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.tree_widget.setColumnWidth(1, 24)
        print("DEBUG: [SampleList] Enabled stretch header and shrinkable tree widget")
        
        self.tree_widget.itemClicked.connect(self.on_item_clicked)
        self.tree_widget.itemChanged.connect(self.on_item_changed)
        self.tree_widget.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree_widget.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.EditKeyPressed)
        self.tree_widget.setAcceptDrops(True)
        self.tree_widget.setDragDropMode(QAbstractItemView.DragDropMode.DropOnly)
        
        # Override events for custom drag-drop logic
        self.tree_widget.dragEnterEvent = self.tree_drag_enter_event
        self.tree_widget.dragMoveEvent = self.tree_drag_move_event
        self.tree_widget.dropEvent = self.tree_drop_event
        
        self.tree_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree_widget.customContextMenuRequested.connect(self.show_sample_context_menu)
        
        top_layout.addWidget(self.tree_widget)
        
        self.splitter.addWidget(self.top_widget)
        
        # Connect selection change to update button state
        self.tree_widget.itemSelectionChanged.connect(self.update_batch_actions_state)
        
        # --- Bottom: Unassigned Pool ---
        self.bottom_widget = QWidget()
        bottom_layout = QVBoxLayout(self.bottom_widget)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        
        # Pool Header Layout
        pool_header = QHBoxLayout()
        pool_header.setContentsMargins(5, 5, 5, 0) # Keep header margin
        self.lbl_pool = QLabel(tr("Unassigned Images") + " (0)")
        self.lbl_pool.setProperty("role", "title")
        self.lbl_pool.setMinimumWidth(0)
        self.lbl_pool.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        pool_header.addWidget(self.lbl_pool)
        pool_header.addStretch()

        # Select All and Create Samples Button
        self.btn_pool_auto_group = QToolButton()
        self.btn_pool_auto_group.setIcon(get_icon("add", "list-add"))
        self.btn_pool_auto_group.setIconSize(QSize(20, 20))
        self.btn_pool_auto_group.setFixedSize(28, 28)
        self.btn_pool_auto_group.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.btn_pool_auto_group.setToolTip(tr("Auto-group selected (or all if none selected) into samples"))
        self.btn_pool_auto_group.clicked.connect(self.auto_group_from_pool)
        pool_header.addWidget(self.btn_pool_auto_group)

        # Batch Delete from Pool Button
        self.btn_pool_delete = QToolButton()
        self.btn_pool_delete.setIcon(get_icon("delete", "edit-delete"))
        self.btn_pool_delete.setIconSize(QSize(20, 20))
        self.btn_pool_delete.setFixedSize(28, 28)
        self.btn_pool_delete.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.btn_pool_delete.setToolTip(tr("Remove selected images from pool"))
        self.btn_pool_delete.clicked.connect(self.remove_selected_from_pool)
        self.btn_pool_delete.setEnabled(False)
        pool_header.addWidget(self.btn_pool_delete)
        
        bottom_layout.addLayout(pool_header)

        # Search Box
        self.search_pool = QLineEdit()
        self.search_pool.setPlaceholderText(tr("Search pool files..."))
        self.search_pool.setClearButtonEnabled(True)
        self.search_pool.textChanged.connect(self.filter_pool_list)
        
        # Add a wrapper with margins for the search box
        search_container = QWidget()
        search_layout = QVBoxLayout(search_container)
        search_layout.setContentsMargins(5, 0, 5, 0)
        search_layout.addWidget(self.search_pool)
        bottom_layout.addWidget(search_container)
        
        self.pool_list = FileListWidget()
        self.pool_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.pool_list.setMinimumWidth(0)
        self.pool_list.setMinimumHeight(50) # Reduced from 100
        self.pool_list.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.pool_list.setDragEnabled(True) # Enable dragging FROM here
        self.pool_list.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self.pool_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.pool_list.customContextMenuRequested.connect(self.show_pool_context_menu)
        self.pool_list.delete_pressed.connect(self.remove_selected_from_pool)
        self.pool_list.itemSelectionChanged.connect(self.update_pool_actions_state)
        
        bottom_layout.addWidget(self.pool_list)
        self.splitter.addWidget(self.bottom_widget)
        
        # Set initial splitter sizes (60/40)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 2)

        # --- Buttons Area ---
        btn_layout = QHBoxLayout() # Changed to horizontal for more compact look
        btn_layout.setContentsMargins(8, 4, 8, 8)
        
        self.btn_auto_group = QToolButton()
        self.btn_auto_group.setIcon(get_icon("add", "list-add"))
        self.btn_auto_group.setIconSize(QSize(20, 20))
        self.btn_auto_group.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.btn_auto_group.setFixedSize(28, 28)
        self.btn_auto_group.setToolTip(tr("Import a folder of images and automatically group them into samples"))
        self.btn_auto_group.setCursor(Qt.CursorShape.PointingHandCursor)
        # self.btn_auto_group.setAutoRaise(True) # Disabled for consistent global styling
        self.btn_auto_group.clicked.connect(self.import_folder_auto)
        btn_layout.addWidget(self.btn_auto_group)
 
        self.btn_load_pool = QToolButton()
        self.btn_load_pool.setIcon(get_icon("folder", "folder-open"))
        self.btn_load_pool.setIconSize(QSize(20, 20))
        self.btn_load_pool.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.btn_load_pool.setFixedSize(28, 28)
        self.btn_load_pool.setToolTip(tr("Import images into the unassigned pool"))
        self.btn_load_pool.setCursor(Qt.CursorShape.PointingHandCursor)
        # self.btn_load_pool.setAutoRaise(True) # Disabled for consistent global styling
        self.btn_load_pool.clicked.connect(self.load_images_to_pool)
        btn_layout.addWidget(self.btn_load_pool)
        
        btn_layout.addStretch()

        # self.btn_new_sample = QPushButton(tr("New Sample (with Channels)"))
        # self.btn_new_sample.clicked.connect(self.create_manual_sample)
        # btn_layout.addWidget(self.btn_new_sample)
        
        self.layout.addLayout(btn_layout)

    def set_active_channel(self, index):
        """Highlights the specified channel for the currently selected scene."""
        selected_items = self.tree_widget.selectedItems()
        if not selected_items:
            return

        # Find the active scene ID from selection
        active_scene_id = None
        for item in selected_items:
            active_scene_id = item.data(0, Qt.ItemDataRole.UserRole)
            if active_scene_id:
                break
        
        if not active_scene_id:
            return

        # Find the scene item and its channel child
        self.tree_widget.blockSignals(True)
        try:
            for i in range(self.tree_widget.topLevelItemCount()):
                scene_item = self.tree_widget.topLevelItem(i)
                if scene_item.data(0, Qt.ItemDataRole.UserRole) == active_scene_id:
                    # If index is -1 (Merge), we select the scene item itself
                    if index == -1:
                        scene_item.setSelected(True)
                        self.tree_widget.setCurrentItem(scene_item)
                    else:
                        # Find the channel child
                        for j in range(scene_item.childCount()):
                            ch_item = scene_item.child(j)
                            if ch_item.data(0, Qt.ItemDataRole.UserRole + 2) == index:
                                ch_item.setSelected(True)
                                self.tree_widget.setCurrentItem(ch_item)
                                break
                    break
        finally:
            self.tree_widget.blockSignals(False)

    def retranslate_ui(self):
        """Update all UI text when language changes."""
        # Top Header
        self.lbl_title.setText(tr("Project Samples ({0})").format(self.project_model.get_scene_count()))
        self.btn_sort_samples.setToolTip(tr("Sort Samples A-Z"))
        self.btn_expand_all.setToolTip(tr("Expand/Collapse All Channels"))
        self.btn_add_sample_header.setToolTip(tr("Quick Add Blank Sample (Alt+N)"))
        self.btn_delete_selected.setToolTip(tr("Delete Selected Samples"))
        
        # Bottom Header
        self.lbl_pool.setText(tr("Unassigned Images ({0})").format(self.project_model.get_pool_count()))
        self.btn_pool_auto_group.setToolTip(tr("Auto-group selected (or all if none selected) into samples"))
        self.btn_pool_delete.setToolTip(tr("Remove selected images from pool"))
        self.search_pool.setPlaceholderText(tr("Search pool files..."))
        
        # Bottom Buttons
        self.btn_auto_group.setToolTip(tr("Import a folder of images and automatically group them into samples"))
        self.btn_load_pool.setToolTip(tr("Import images into the unassigned pool"))
        
        # Refresh the tree to update item tooltips if needed
        self.refresh_list()
        self.refresh_pool_list()

    def quick_add_sample(self):
        """Quickly adds a new sample with default name."""
        # Generate next available ID
        base_name = tr("Sample")
        idx = 1
        while True:
            name = f"{base_name}_{idx}"
            if name not in self.project_model._scene_map:
                break
            idx += 1
            
        # Explicitly fetch template from model to ensure it is passed
        channel_templates = self.project_model.project_channel_template
        print(f"DEBUG: [SampleList] quick_add_sample called. Template in model: {channel_templates}")
        
        # Default fallback if no project template and no previous scenes
        if not channel_templates and not self.project_model.scenes:
            print("DEBUG: [SampleList] No template and no scenes. Using default fallback: DAPI, GFP, RFP")
            channel_templates = ["DAPI", "GFP", "RFP"]
        elif not channel_templates:
            print("DEBUG: [SampleList] No template found, but scenes exist (will try inheritance in model).")
            
        scene_id = self.project_model.add_manual_scene(name, channel_templates)
        print(f"DEBUG: [SampleList] add_manual_scene returned id: {scene_id}")
        self.refresh_list()
        
        # Find and select
        items = self.tree_widget.findItems(name, Qt.MatchFlag.MatchStartsWith | Qt.MatchFlag.MatchRecursive)
        if items:
            self.tree_widget.setCurrentItem(items[0])
            items[0].setExpanded(True)
            self.on_item_clicked(items[0], 0)

    def import_folder_auto(self):
        """
        Imports a folder of images and auto-groups them into samples.
        Checks 'Import Settings' for recursive behavior.
        """
        folder = QFileDialog.getExistingDirectory(self, tr("Select Folder to Import (Auto-Group)"))
        if not folder:
            return
            
        settings = QSettings("FluoQuantPro", "AppSettings")
        recursive = settings.value("import/recursive", False, type=bool)
        
        valid_exts = ('.tif', '.tiff', '.png', '.jpg', '.jpeg', '.bmp', '.gif')
        files = []
        
        if recursive:
            for root, dirs, fnames in os.walk(folder):
                for fname in fnames:
                    if fname.lower().endswith(valid_exts):
                        files.append(os.path.join(root, fname))
        else:
            try:
                for fname in os.listdir(folder):
                    if fname.lower().endswith(valid_exts):
                        files.append(os.path.join(folder, fname))
            except Exception as e:
                print(f"Error listing directory: {e}")
                    
        if not files:
            QMessageBox.information(self, tr("Import"), tr("No images found in folder."))
            return

        valid_files, logs = self._validate_import_files(files, "import_auto_group")
        invalid_count = sum(1 for e in logs if not e.get("ok"))
        if not valid_files:
            QMessageBox.warning(self, tr("Import"), tr("No valid images found."))
            return
        if invalid_count:
            log_path = self._import_log_path()
            if log_path:
                QMessageBox.warning(
                    self,
                    tr("Import"),
                    tr("Skipped {0} invalid files.\nDetails saved to:\n{1}").format(invalid_count, log_path)
                )
            
        count_before = len(self.project_model.scenes)
        self.project_model.add_files(valid_files)
        count_after = len(self.project_model.scenes)
        
        self.refresh_list()
        self.refresh_pool_list()
        
        new_samples = count_after - count_before
        QMessageBox.information(self, tr("Import Complete"), tr("Imported {0} files.\nCreated {1} new samples.").format(len(valid_files), new_samples))

    def filter_pool_list(self, text):
        """Filters the pool list based on search text."""
        text = text.lower()
        for i in range(self.pool_list.count()):
            item = self.pool_list.item(i)
            # Only show unassigned items if they match search? 
            # Or show all items but grey out assigned?
            # Existing logic is to show all and grey out assigned.
            item.setHidden(text not in item.text().lower())

    def auto_group_from_pool(self):
        """Groups selected files from pool into samples. If none selected, groups all unassigned."""
        selected_items = self.pool_list.selectedItems()
        assigned_set = self.project_model.get_assigned_files()
        
        files_to_group = []
        if selected_items:
            for item in selected_items:
                fpath = item.data(Qt.ItemDataRole.UserRole)
                if fpath not in assigned_set:
                    files_to_group.append(fpath)
        else:
            # Group all unassigned
            for fpath in self.project_model.pool_files:
                if fpath not in assigned_set:
                    files_to_group.append(fpath)
                    
        if not files_to_group:
            QMessageBox.information(self, tr("Auto Group"), tr("No unassigned files to group."))
            return
            
        count_before = len(self.project_model.scenes)
        self.project_model.add_files(files_to_group)
        count_after = len(self.project_model.scenes)
        
        self.refresh_list()
        self.refresh_pool_list()
        
        new_samples = count_after - count_before
        QMessageBox.information(self, tr("Auto Group Complete"), tr("Processed {0} files.\nCreated {1} new samples.").format(len(files_to_group), new_samples))

    def on_item_changed(self, item, column):
        """Handle item renaming."""
        item_type = item.data(0, Qt.ItemDataRole.UserRole + 1)
        # Ensure we only process Scene items and only for the Name column (0)
        if item_type != "Scene" or column != 0:
            return

        # QTreeWidget emits itemChanged for ANY change, including setting text programmatically.
        # We need to distinguish user edits from our own refresh_list() updates.
        # We can check if the widget has focus, or use a blocking flag.
        # But refresh_list() clears the tree, so we are usually safe EXCEPT when we setFlags.
        
        # Actually, simpler: check if the new text is different from the stored ID (old name)
        new_name = item.text(0).strip()
        old_id = item.data(0, Qt.ItemDataRole.UserRole)
        
        # If data is None, it might be initial creation, skip
        if old_id is None:
            return

        if not new_name:
            item.setText(0, old_id)
            return

        if new_name == old_id:
            return # No change
            
        # Temporarily block signals to avoid recursion during rename updates
        self.tree_widget.blockSignals(True)
        
        if self.project_model.rename_scene(old_id, new_name):
            # Notify others (e.g. MainWindow)
            self.scene_renamed.emit(old_id, new_name)
            
            # Instead of manually updating the item (which can cause RuntimeError if 
            # other signals trigger a refresh simultaneously), we trigger a full refresh.
            # But we must do it AFTER unblocking signals or it won't work correctly.
            self.tree_widget.blockSignals(False)
            self.refresh_list()
            
            # Re-select the renamed item
            items = self.tree_widget.findItems(new_name, Qt.MatchFlag.MatchExactly | Qt.MatchFlag.MatchRecursive)
            if items:
                self.tree_widget.setCurrentItem(items[0])
        else:
            # Revert if failed (collision)
            QMessageBox.warning(self, tr("Rename Failed"), tr("Name '{0}' already exists.").format(new_name))
            item.setText(0, old_id) 
            self.tree_widget.blockSignals(False)

    def load_images_to_pool(self):
        """
        Loads images into the unassigned pool.
        Checks 'Import Settings' for recursive behavior.
        """
        folder_path = QFileDialog.getExistingDirectory(self, tr("Select Folder with Images"))
        if not folder_path:
            return
            
        settings = QSettings("FluoQuantPro", "AppSettings")
        recursive = settings.value("import/recursive", False, type=bool)
        
        valid_exts = ('.tif', '.tiff', '.png', '.jpg', '.jpeg', '.bmp', '.gif')
        files = self.project_model.scan_folder(folder_path, valid_exts, recursive=recursive)
        
        if not files:
            QMessageBox.information(self, tr("Import"), tr("No images found in folder."))
            return

        valid_files, logs = self._validate_import_files(files, "load_pool")
        invalid_count = sum(1 for e in logs if not e.get("ok"))

        if not valid_files:
            QMessageBox.warning(self, tr("Import"), tr("No valid images found."))
            return

        if invalid_count:
            log_path = self._import_log_path()
            if log_path:
                QMessageBox.warning(
                    self,
                    tr("Import"),
                    tr("Skipped {0} invalid files.\nDetails saved to:\n{1}").format(invalid_count, log_path)
                )

        self.project_model.add_to_pool(valid_files)
        self.refresh_pool_list()

    def sort_samples(self):
        """Sorts the samples in the project model alphabetically by name."""
        self.project_model.scenes.sort(key=lambda s: s.name)
        self.refresh_list()
        self.project_model.project_changed.emit()

    def toggle_expand_all(self, expand: bool):
        """Expands or collapses all top-level items in the tree."""
        if expand:
            self.tree_widget.expandAll()
        else:
            self.tree_widget.collapseAll()

    def request_pool_refresh(self):
        """Requests a debounced refresh of the pool list."""
        self._pool_refresh_timer.start()

    def refresh_pool_list(self):
        """Deprecated: Use request_pool_refresh instead. Kept for signal compatibility if any."""
        self.request_pool_refresh()

    def refresh_pool_list_actual(self):
        """The actual intensive refresh logic, now debounced and performance-optimized."""
        # Save scroll position and current item if any
        scrollbar = self.pool_list.verticalScrollBar()
        scroll_pos = scrollbar.value()
        
        print(f"[SampleList] refresh_pool_list (actual) called. Pool files: {len(self.project_model.pool_files)}")
        
        # Optimization: Block signals and updates during mass insertion
        self.pool_list.blockSignals(True)
        self.pool_list.setUpdatesEnabled(False)
        
        try:
            self.pool_list.clear()
            files = self.project_model.pool_files 
            
            assigned_set = {os.path.normpath(p) for p in self.project_model.get_assigned_files()}

            # User Request: Hide assigned images completely instead of graying them out
            # Only show files that are NOT in the assigned set
            unassigned_files = []
            for f in files:
                if os.path.normpath(f) not in assigned_set:
                    unassigned_files.append(f)

            # Sort alphabetically
            unassigned_files.sort(key=lambda x: os.path.basename(x).lower())

            # Count available files for label
            available_count = len(unassigned_files)
            self.lbl_pool.setText(tr("Unassigned Images ({0})").format(available_count))

            for fpath in unassigned_files:
                fname = os.path.basename(fpath)
                item = QListWidgetItem(fname)
                item.setData(Qt.ItemDataRole.UserRole, fpath)
                item.setToolTip(fpath)
                
                # All visible items are unassigned, so they are selectable and draggable
                item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsDragEnabled)

                self.pool_list.addItem(item)
                
            # Restore scroll position
            scrollbar.setValue(scroll_pos)
            
            # Re-apply search filter
            if self.search_pool.text():
                self.filter_pool_list(self.search_pool.text())
                
            print(f"[SampleList] refresh_pool_list completed. Visible Unassigned: {len(unassigned_files)}")
        finally:
            self.pool_list.setUpdatesEnabled(True)
            self.pool_list.blockSignals(False)

    def request_tree_refresh(self):
        """Requests a debounced refresh of the sample tree."""
        self._tree_refresh_timer.start()

    def refresh_list(self):
        """Compatibility method. Use request_tree_refresh instead."""
        self.request_tree_refresh()

    def refresh_list_actual(self):
        """Rebuilds the sample tree while attempting to preserve scroll position, expansion, and selection."""
        # --- 1. Save current state ---
        scrollbar = self.tree_widget.verticalScrollBar()
        scroll_pos = scrollbar.value()
        
        # Optimization: Disable updates to reduce flicker
        self.tree_widget.setUpdatesEnabled(False)
        
        expanded_ids = set()
        for i in range(self.tree_widget.topLevelItemCount()):
            item = self.tree_widget.topLevelItem(i)
            if item.isExpanded():
                scene_id = item.data(0, Qt.ItemDataRole.UserRole)
                if scene_id:
                    expanded_ids.add(scene_id)
        
        selected_keys = [] # List of (type, scene_id, optional ch_index)
        for item in self.tree_widget.selectedItems():
            item_type = item.data(0, Qt.ItemDataRole.UserRole + 1)
            scene_id = item.data(0, Qt.ItemDataRole.UserRole)
            if item_type == "Scene":
                selected_keys.append(("Scene", scene_id))
            elif item_type == "Channel":
                ch_index = item.data(0, Qt.ItemDataRole.UserRole + 2)
                selected_keys.append(("Channel", scene_id, ch_index))
        
        current_item = self.tree_widget.currentItem()
        current_key = None
        if current_item:
            item_type = current_item.data(0, Qt.ItemDataRole.UserRole + 1)
            scene_id = current_item.data(0, Qt.ItemDataRole.UserRole)
            if item_type == "Scene":
                current_key = ("Scene", scene_id)
            elif item_type == "Channel":
                ch_index = current_item.data(0, Qt.ItemDataRole.UserRole + 2)
                current_key = ("Channel", scene_id, ch_index)

        # --- 2. Rebuild the tree ---
        self.tree_widget.blockSignals(True) # Avoid itemChanged during rebuild
        self.tree_widget.clear()
        self.lbl_title.setText(tr("Samples ({0})").format(len(self.project_model.scenes)))
        
        for scene in self.project_model.scenes:
            # Scene Item
            scene_item = QTreeWidgetItem(self.tree_widget)
            
            # Column 0: Name
            scene_item.setText(0, scene.name)
            scene_item.setFlags(scene_item.flags() | Qt.ItemFlag.ItemIsEditable) # Enable editing
            
            # Column 1: Status
            status_text = tr("Measured") if scene.status == "Measured" else ""
            scene_item.setText(1, status_text)
            if scene.status == "Measured":
                scene_item.setData(1, Qt.ItemDataRole.UserRole + 3, "success")
                palette = QApplication.palette()
                success_color = QColor("#27ae60")
                if palette.color(QPalette.ColorRole.Window).lightness() < 128:
                    success_color = QColor("#2ecc71")
                scene_item.setForeground(1, success_color)
            
            scene_item.setData(0, Qt.ItemDataRole.UserRole, scene.id)
            scene_item.setData(0, Qt.ItemDataRole.UserRole + 1, "Scene")
            
            # Restore expansion
            if scene.id in expanded_ids:
                scene_item.setExpanded(True)
            elif not expanded_ids and self.btn_expand_all.isChecked():
                # Default expansion if no state saved
                scene_item.setExpanded(True)
            
            # Restore selection for Scene
            if ("Scene", scene.id) in selected_keys:
                scene_item.setSelected(True)
            if current_key == ("Scene", scene.id):
                self.tree_widget.setCurrentItem(scene_item)
            
            # Channel Items
            for i, ch in enumerate(scene.channels):
                ch_item = QTreeWidgetItem(scene_item)
                
                # Action buttons in Column 1
                actions_container = QWidget()
                actions_layout = QHBoxLayout(actions_container)
                actions_layout.setContentsMargins(0, 0, 4, 0)
                actions_layout.setSpacing(4)
                
                if ch.path:
                    # Filled
                    fname = os.path.basename(ch.path)
                    ch_item.setText(0, tr("{0}: {1}").format(ch.channel_type, fname))
                    palette = QApplication.palette()
                    ch_item.setForeground(0, palette.color(QPalette.ColorRole.Mid))
                    ch_item.setIcon(0, get_icon("icon", "image-x-generic"))
                    
                    btn_clear = QToolButton()
                    btn_clear.setIcon(get_icon("clear", "edit-clear"))
                    btn_clear.setIconSize(QSize(16, 16))
                    btn_clear.setFixedSize(22, 22)
                    btn_clear.setToolTip(tr("Remove Image from Channel"))
                    btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
                    btn_clear.clicked.connect(lambda _, s_id=scene.id, c_idx=i: self.clear_channel(s_id, c_idx))
                    actions_layout.addWidget(btn_clear)
                
                btn_delete = QToolButton()
                btn_delete.setIcon(get_icon("delete", "edit-delete"))
                btn_delete.setIconSize(QSize(16, 16))
                btn_delete.setFixedSize(22, 22)
                btn_delete.setToolTip(tr("Delete Channel Slot"))
                btn_delete.setCursor(Qt.CursorShape.PointingHandCursor)
                btn_delete.clicked.connect(lambda _, s_id=scene.id, c_idx=i: self.on_remove_channel_clicked(s_id, c_idx))
                actions_layout.addWidget(btn_delete)
                
                actions_layout.addStretch()
                self.tree_widget.setItemWidget(ch_item, 1, actions_container)
                
                pix = QPixmap(16, 16)
                pix.fill(QColor(ch.color))
                ch_item.setIcon(0, QIcon(pix))
                    
                if not ch.path:
                    # Empty Slot
                    ch_item.setText(0, tr("{0}: [{1}]").format(ch.channel_type, tr("Empty")))
                    palette = QApplication.palette()
                    error_color = QColor("#e74c3c")
                    if palette.color(QPalette.ColorRole.Window).lightness() < 128:
                        error_color = QColor("#ff5555")
                    ch_item.setForeground(0, error_color)
                    
                    pix = QPixmap(16, 16)
                    pix.fill(QColor(ch.color))
                    ch_item.setIcon(0, QIcon(pix))
                
                ch_item.setData(0, Qt.ItemDataRole.UserRole, scene.id)
                ch_item.setData(0, Qt.ItemDataRole.UserRole + 1, "Channel")
                ch_item.setData(0, Qt.ItemDataRole.UserRole + 2, i)
                
                # Restore selection for Channel
                if ("Channel", scene.id, i) in selected_keys:
                    ch_item.setSelected(True)
                if current_key == ("Channel", scene.id, i):
                    self.tree_widget.setCurrentItem(ch_item)
            
            # Add [+] Button Item
            add_item = QTreeWidgetItem(scene_item)
            add_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            
            btn_add = QToolButton()
            btn_add.setIcon(get_icon("add", "list-add"))
            btn_add.setIconSize(QSize(14, 14))
            btn_add.setText(tr("Add Channel"))
            btn_add.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            btn_add.setToolTip(tr("Add new empty channel slot"))
            btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_add.setProperty("role", "subtle")
            btn_add.clicked.connect(lambda _, s_id=scene.id: self.on_add_channel_clicked(s_id))
            
            widget_container = QWidget()
            h_layout = QHBoxLayout(widget_container)
            h_layout.setContentsMargins(28, 0, 0, 0) 
            h_layout.setSpacing(0)
            h_layout.addWidget(btn_add)
            h_layout.addStretch()
            
            self.tree_widget.setItemWidget(add_item, 0, widget_container)

        # --- 3. Restore scroll position ---
        self.tree_widget.blockSignals(False)
        self.tree_widget.setUpdatesEnabled(True)
        
        # Use a slightly longer delay to ensure layout is complete before restoring scroll
        QTimer.singleShot(10, lambda: scrollbar.setValue(scroll_pos))

    def on_add_channel_clicked(self, scene_id):
        self.project_model.add_empty_channel(scene_id)
        # Refresh UI and notify other components to update (e.g., Image Display)
        self.refresh_list()
        self.scene_structure_changed.emit(scene_id)

    def on_remove_channel_clicked(self, scene_id, channel_index):
        """Removes a channel slot from a scene."""
        self.project_model.remove_channel(scene_id, channel_index)
        self.channel_removed.emit(scene_id, channel_index)
        # Reload scene if it's the current one
        self.scene_selected.emit(scene_id)

    def clear_channel(self, scene_id, channel_index):
        """Clears the assigned image from a channel slot."""
        self.project_model.update_channel_path(scene_id, channel_index, "")
        self.channel_cleared.emit(scene_id, channel_index)
        # Optionally refresh scene if it's the current one
        self.scene_selected.emit(scene_id) # Reload scene to reflect removal

    def on_item_clicked(self, item, column):
        item_type = item.data(0, Qt.ItemDataRole.UserRole + 1)
        scene_id = item.data(0, Qt.ItemDataRole.UserRole)
        
        if item_type == "Scene":
            self.scene_selected.emit(scene_id)
        elif item_type == "Channel":
            # If clicking a channel, emit only channel info
            # Main window will decide if it needs to reload the whole scene
            ch_index = item.data(0, Qt.ItemDataRole.UserRole + 2)
            self.channel_selected.emit(scene_id, ch_index)

    # --- Drag & Drop Logic (Tree) ---

    def tree_drag_enter_event(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls() or event.source() == self.pool_list:
            event.acceptProposedAction()
        else:
            event.ignore()

    def tree_drag_move_event(self, event):
        if event.mimeData().hasUrls() or event.source() == self.pool_list:
            event.acceptProposedAction()
            pos = event.position().toPoint()
            target_item = self.tree_widget.itemAt(pos)
            
            # Fuzzier hit test: if no item directly under cursor, try a point slightly to the right
            # to account for indentation or empty space in the row.
            if not target_item:
                target_item = self.tree_widget.itemAt(QPoint(50, pos.y()))

            if not target_item:
                if self._drag_hint_last_key is not None:
                    QToolTip.hideText()
                    self._drag_hint_last_key = None
                return

            item_type = target_item.data(0, Qt.ItemDataRole.UserRole + 1)
            scene_id = target_item.data(0, Qt.ItemDataRole.UserRole)

            if item_type == "Channel":
                ch_index = target_item.data(0, Qt.ItemDataRole.UserRole + 2)
                scene = self.project_model.get_scene(scene_id)
                if not scene or not (0 <= ch_index < len(scene.channels)):
                    return
                ch = scene.channels[ch_index]
                key = ("Channel", scene_id, ch_index)
                if key != self._drag_hint_last_key:
                    self._drag_hint_last_key = key
                    hint = tr("Assign to: {0} / {1}").format(scene.name, ch.channel_type)
                    QToolTip.showText(event.globalPosition().toPoint(), hint, self.tree_widget)
            elif item_type == "Scene":
                key = ("Scene", scene_id)
                if key != self._drag_hint_last_key:
                    self._drag_hint_last_key = key
                    scene = self.project_model.get_scene(scene_id)
                    if scene:
                        hint = tr("Auto-assign to sample: {0}").format(scene.name)
                        QToolTip.showText(event.globalPosition().toPoint(), hint, self.tree_widget)
            else:
                if self._drag_hint_last_key is not None:
                    QToolTip.hideText()
                    self._drag_hint_last_key = None

    def _check_image_channels(self, file_path: str, channel_name: Optional[str] = None) -> bool:
        """
        Validates if an image is suitable for single-channel assignment.
        Returns True if grayscale or pseudo-RGB (only one non-zero channel).
        Also returns True if the channel_name has a biological mapping rule.
        Returns False and shows warning if multi-channel and no mapping.
        """
        try:
            # If we have a mapping for this channel, we can handle multi-channel images
            if channel_name and get_rgb_mapping(channel_name) is not None:
                return True

            import numpy as np
            ext = os.path.splitext(file_path)[1].lower()
            if ext in (".tif", ".tiff"):
                data = tifffile.imread(file_path)
            else:
                import cv2
                # data = cv2.imread(file_path, cv2.IMREAD_UNCHANGED)
                # Fix for Unicode paths:
                data_stream = np.fromfile(file_path, dtype=np.uint8)
                data = cv2.imdecode(data_stream, cv2.IMREAD_UNCHANGED)
                
                if data is None:
                    return True
            
            if data.ndim == 2:
                return True
            
            if data.ndim == 3:
                # Check for pseudo-RGB
                # 1. Check active channels (only one channel has data)
                active_channels = []
                is_chw = data.shape[0] < data.shape[2]
                
                num_channels = data.shape[0] if is_chw else data.shape[2]
                
                for i in range(num_channels):
                    if is_chw:
                        ch_data = data[i, :, :]
                    else:
                        ch_data = data[:, :, i]
                        
                    # Use max > threshold instead of > 0 to ignore noise
                    # Threshold: 5 (assuming 8-bit/16-bit low-level noise)
                    if np.max(ch_data) > 5:
                        active_channels.append(ch_data)
                
                if len(active_channels) <= 1:
                    return True
                    
                # 2. Check for Grayscale saved as RGB (R=G=B)
                if len(active_channels) == 3:
                    # Check if all active channels are identical
                    c1 = active_channels[0]
                    c2 = active_channels[1]
                    c3 = active_channels[2]
                    
                    if np.array_equal(c1, c2) and np.array_equal(c2, c3):
                        return True

                # Multi-channel detected
                # Check if it's just noise (e.g. max value is very low in secondary channels)
                # But here we already filtered by max > 0. 
                # Let's assume if we are here, we have multiple significant channels.
                
                QMessageBox.warning(
                        self, 
                        tr("Multi-channel Image Detected"),
                        tr("The image you are trying to assign contains multiple active channels.\n\n"
                           "For single channel assignment, please use a grayscale image or a pseudo-RGB image (only one channel has data).\n\n"
                           "To import multi-channel images correctly, please use the 'Import Merge' function.")
                    )
                return False
            
            return True
        except Exception as e:
            print(f"Error checking image channels: {e}")
            return True

    def tree_drop_event(self, event: QDropEvent):
        QToolTip.hideText()
        self._drag_hint_last_key = None
        file_paths = []
        is_pool_drag = False
        
        if event.source() == self.pool_list:
            is_pool_drag = True
            items = self.pool_list.selectedItems()
            file_paths = [item.data(Qt.ItemDataRole.UserRole) for item in items]
        elif event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            file_paths = [u.toLocalFile() for u in urls if os.path.isfile(u.toLocalFile())]
            
        if not file_paths:
            return

        pos = event.position().toPoint()
        target_item = self.tree_widget.itemAt(pos)
        
        # Fuzzier hit test
        if not target_item:
            target_item = self.tree_widget.itemAt(QPoint(50, pos.y()))
        
        if target_item:
            item_type = target_item.data(0, Qt.ItemDataRole.UserRole + 1)
            scene_id = target_item.data(0, Qt.ItemDataRole.UserRole)
            
            if item_type == "Scene":
                # Dropped on Scene -> Auto Fill
                self.project_model.undo_stack.beginMacro(tr("Assign {0} Images to {1}").format(len(file_paths), scene_id))
                self.handle_drop_on_scene(scene_id, file_paths)
                self.project_model.undo_stack.endMacro()
            elif item_type == "Channel":
                # Dropped on Channel Slot -> Force Fill (First file only)
                ch_index = target_item.data(0, Qt.ItemDataRole.UserRole + 2)
                
                # Get channel name to help with multi-channel validation
                channel_name = None
                if scene_id in self.project_model._scene_map:
                    scene = self.project_model._scene_map[scene_id]
                    if 0 <= ch_index < len(scene.channels):
                        channel_name = scene.channels[ch_index].channel_type
                
                if self._check_image_channels(file_paths[0], channel_name=channel_name):
                    self.project_model.update_channel_path(scene_id, ch_index, file_paths[0])
                    self.refresh_list()
                    self.channel_file_assigned.emit(scene_id, ch_index, file_paths[0])
                    QApplication.processEvents()
                    self.scene_selected.emit(scene_id) # Refresh view
                
            # Remove from pool logic is now just refresh
            # We don't remove from pool_files, just refresh UI to show assigned status
            if is_pool_drag:
                self.refresh_pool_list()
        else:
            # Dropped on empty space -> Create new sample
            reply = QMessageBox.question(self, tr("New Sample"), 
                                       tr("Create new sample for these {0} files?").format(len(file_paths)), 
                                       QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                 first_name = os.path.splitext(os.path.basename(file_paths[0]))[0]
                 
                 self.project_model.undo_stack.beginMacro(tr("Create Sample from {0} files").format(len(file_paths)))
                 
                 # For now, create generic scene, then add files
                 scene_id = self.project_model.add_manual_scene(first_name)
                 
                 # Check if template was used (scene has channels)
                 scene = self.project_model.get_scene(scene_id)
                 if scene and scene.channels:
                      # Template active: Try to fill slots
                      self.handle_drop_on_scene(scene_id, file_paths)
                 else:
                     # No template: Auto-create channels
                     for fpath in file_paths:
                         if not self._check_image_channels(fpath):
                             continue
                             
                         # Guess channel type
                         guess = self.guess_channel(os.path.basename(fpath)) or tr("Other")
                         color = "#FFFFFF" # Simplified
                         self.project_model.add_channel_to_scene(scene_id, fpath, guess, color)
                 
                 self.project_model.undo_stack.endMacro()
                 
                 self.refresh_list()
                 if is_pool_drag:
                    self.refresh_pool_list()
        
        event.acceptProposedAction()

    def _import_log_path(self) -> str:
        try:
            export_dir = self.project_model.get_export_path()
            os.makedirs(export_dir, exist_ok=True)
            return os.path.join(export_dir, "import_log.jsonl")
        except Exception:
            return ""

    def _append_import_logs(self, entries: list):
        log_path = self._import_log_path()
        if not log_path:
            return
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                for entry in entries:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def _validate_import_file(self, file_path: str):
        try:
            if not file_path or not os.path.isfile(file_path):
                return False, "not_a_file", {}
            if os.path.getsize(file_path) <= 0:
                return False, "empty_file", {}

            ext = os.path.splitext(file_path)[1].lower()
            if ext in (".tif", ".tiff"):
                with tifffile.TiffFile(file_path) as tif:
                    page = tif.pages[0]
                    shape = tuple(page.shape) if page.shape is not None else None
                    dtype = str(page.dtype) if page.dtype is not None else None
                if not shape or len(shape) not in (2, 3):
                    return False, "unsupported_shape", {"shape": shape, "dtype": dtype}
                return True, "ok", {"shape": shape, "dtype": dtype}

            if ext in (".png", ".jpg", ".jpeg", ".bmp"):
                import cv2
                # img = cv2.imread(file_path, cv2.IMREAD_UNCHANGED)
                # Fix for Unicode paths:
                img_stream = np.fromfile(file_path, dtype=np.uint8)
                img = cv2.imdecode(img_stream, cv2.IMREAD_UNCHANGED)
                
                if img is None:
                    return False, "decode_failed", {}
                shape = tuple(img.shape)
                dtype = str(img.dtype)
                if img.ndim not in (2, 3):
                    return False, "unsupported_shape", {"shape": shape, "dtype": dtype}
                return True, "ok", {"shape": shape, "dtype": dtype}

            return False, "unsupported_extension", {"ext": ext}
        except Exception as e:
            return False, "exception", {"error": str(e)}

    def _validate_import_files(self, files: list, action: str):
        t = time.strftime("%Y-%m-%d %H:%M:%S")
        valid = []
        logs = []
        for p in files:
            ok, reason, meta = self._validate_import_file(p)
            logs.append({
                "time": t,
                "action": action,
                "file": os.path.normpath(p) if p else p,
                "ok": ok,
                "reason": reason,
                "meta": meta
            })
            if ok:
                valid.append(p)
        self._append_import_logs(logs)
        return valid, logs

    def handle_drop_on_scene(self, scene_id, file_paths):
        """Attempts to match dropped files to empty slots in the scene."""
        scene = self.project_model.get_scene(scene_id)
        if not scene: return
        
        assigned_count = 0
        unmatched_files = []
        
        # Optimization for single channel mode: 
        # If scene has exactly one empty channel, assign the first valid file directly.
        empty_channels = [i for i, ch in enumerate(scene.channels) if not ch.path]
        if len(scene.channels) == 1 and len(empty_channels) == 1 and file_paths:
            fpath = file_paths[0]
            if self._check_image_channels(fpath):
                self.project_model.update_channel_path(scene_id, empty_channels[0], fpath)
                self.channel_file_assigned.emit(scene_id, empty_channels[0], fpath)
                assigned_count = 1
                file_paths = file_paths[1:] # Continue with remaining files if any
                if not file_paths:
                    self.refresh_list()
                    self.scene_structure_changed.emit(scene_id)
                    return

        for fpath in file_paths:
            if not self._check_image_channels(fpath):
                continue
                
            fname = os.path.basename(fpath)
            fname_upper = fname.upper()
            # 1. Try to find an empty slot that matches
            matched = False
            for i, ch in enumerate(scene.channels):
                slot_name = (ch.channel_type or "").strip()
                if not ch.path and slot_name and slot_name.upper() in fname_upper:
                    self.project_model.update_channel_path(scene_id, i, fpath)
                    self.channel_file_assigned.emit(scene_id, i, fpath)
                    matched = True
                    assigned_count += 1
                    break

            if not matched:
                guess = self.guess_channel(fname)
                if guess:
                    guess_upper = guess.upper()
                    expected = self.project_model.channel_patterns.get(guess_upper)
                    expected_type = expected[0].upper() if expected else guess_upper
                    expected_color = (expected[1] if expected else "").lower()

                    for i, ch in enumerate(scene.channels):
                        if ch.path:
                            continue
                        slot_upper = (ch.channel_type or "").strip().upper()
                        if slot_upper in (guess_upper, expected_type) or guess_upper in slot_upper or expected_type in slot_upper:
                            self.project_model.update_channel_path(scene_id, i, fpath)
                            self.channel_file_assigned.emit(scene_id, i, fpath)
                            matched = True
                            assigned_count += 1
                            break

                    if not matched and expected_color:
                        for i, ch in enumerate(scene.channels):
                            if ch.path:
                                continue
                            if (ch.color or "").lower() == expected_color:
                                self.project_model.update_channel_path(scene_id, i, fpath)
                                self.channel_file_assigned.emit(scene_id, i, fpath)
                                matched = True
                                assigned_count += 1
                                break
            
            if not matched:
                unmatched_files.append(fpath)
        
        if unmatched_files:
            # If there are unmatched files, ask user what to do?
            # User request: "Mistaken drag drops to 'other' item" -> implies they don't want auto-creation.
            # So we simply warn and DO NOT create new channels.
            msg = tr("{0} files could not be automatically matched to empty slots.\nPlease drag them to specific channel slots manually.").format(len(unmatched_files))
            QMessageBox.warning(self, tr("Unmatched Files"), msg)

        self.refresh_list()
        self.scene_structure_changed.emit(scene_id)

    def guess_channel(self, filename):
        name_upper = filename.upper()
        for key in ["DAPI", "GFP", "RFP", "CY5", "TRITC", "FITC"]:
            if key in name_upper:
                return key
        return None

    # --- Context Menus ---
    
    def show_pool_context_menu(self, pos):
        menu = QMenu(self)
        
        # Selection count
        selected_items = self.pool_list.selectedItems()
        count = len(selected_items)

        # New Action: Set as Single Channel Sample
        set_single_action = menu.addAction(tr("Set as Single Channel Sample"))
        set_single_action.setEnabled(count > 0)
        
        create_action = menu.addAction(tr("Create Sample from Selection"))
        create_action.setEnabled(count > 0)
        
        menu.addSeparator()
        
        delete_action = menu.addAction(tr("Remove from Pool"))
        delete_action.setIcon(get_icon("delete", "edit-delete"))
        delete_action.setEnabled(count > 0)
        
        action = menu.exec(self.pool_list.mapToGlobal(pos))
        
        if action == create_action:
            self.create_sample_from_pool_selection()
        elif action == delete_action:
            self.remove_selected_from_pool()
        elif action == set_single_action:
            self.convert_pool_items_to_samples()

    def update_pool_actions_state(self):
        """Enable/disable batch actions based on pool selection."""
        count = len(self.pool_list.selectedItems())
        self.btn_pool_delete.setEnabled(count > 0)

    def remove_selected_from_pool(self):
        """Removes selected files from the unassigned pool."""
        items = self.pool_list.selectedItems()
        if not items:
            return
            
        file_paths = [item.data(Qt.ItemDataRole.UserRole) for item in items]
        
        # Confirm deletion
        reply = QMessageBox.question(
            self, 
            tr("Remove from Pool"),
            tr("Are you sure you want to remove {0} selected images from the pool?\nThis only removes them from the project, not from your disk.").format(len(file_paths)),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.project_model.remove_files_from_pool(file_paths)
            # Model signal will trigger refresh

    def _detect_rgb_color(self, file_path: str) -> str:
        try:
            # 1. Read Image
            data = None
            if file_path.lower().endswith(('.tif', '.tiff')):
                try:
                    data = tifffile.imread(file_path)
                except:
                    pass
            
            if data is None:
                # Use cv2 for other formats, handle unicode paths
                stream = np.fromfile(file_path, dtype=np.uint8)
                data = cv2.imdecode(stream, cv2.IMREAD_UNCHANGED)
                if data is not None and data.ndim == 3 and data.shape[2] == 3:
                     data = cv2.cvtColor(data, cv2.COLOR_BGR2RGB)
            
            if data is None:
                return "#FFFFFF"

            # 2. Analyze Dimensions
            if data.ndim == 3:
                # Heuristic: if dim0 is small (3 or 4), it's likely channels.
                if data.shape[0] < data.shape[2] and data.shape[0] <= 4:
                     data = np.transpose(data, (1, 2, 0)) # Convert to HWC
                
                # Subsample for speed
                step = max(1, min(data.shape[0], data.shape[1]) // 100)
                small_data = data[::step, ::step, :]
                
                # Calculate means per channel
                means = np.mean(small_data, axis=(0, 1))
                if len(means) >= 3:
                    r, g, b = means[0], means[1], means[2]
                    
                    # Simple dominance check
                    if r > 1.2 * g and r > 1.2 * b:
                        return "#FF0000" # Red
                    elif g > 1.2 * r and g > 1.2 * b:
                        return "#00FF00" # Green
                    elif b > 1.2 * r and b > 1.2 * g:
                        return "#0000FF" # Blue
                    elif r > 1.2 * b and g > 1.2 * b and abs(r - g) < 0.2 * max(r, g):
                         return "#FFFF00" # Yellow
                    elif r > 1.2 * g and b > 1.2 * g and abs(r - b) < 0.2 * max(r, b):
                         return "#FF00FF" # Magenta
                    elif g > 1.2 * r and b > 1.2 * r and abs(g - b) < 0.2 * max(g, b):
                         return "#00FFFF" # Cyan
            
            return "#FFFFFF"
        except Exception as e:
            print(f"Error detecting color for {file_path}: {e}")
            return "#FFFFFF"

    def _check_multichannel(self, file_path: str) -> tuple[bool, int]:
        """Checks if file has multiple channels and returns count."""
        try:
            # 1. Check TIF/TIFF metadata
            if file_path.lower().endswith(('.tif', '.tiff')):
                try:
                    with tifffile.TiffFile(file_path) as tif:
                        # Check series
                        if len(tif.series) > 0:
                            series = tif.series[0]
                            shape = series.shape
                            ndim = len(shape)
                            
                            # Heuristic for Dimensions
                            # Common: (C, Y, X), (Z, C, Y, X), (T, Z, C, Y, X)
                            # Or (Y, X, C) for RGB
                            
                            # If axes known
                            if hasattr(series, 'axes'):
                                axes = series.axes
                                if 'C' in axes:
                                    idx = axes.find('C')
                                    c = shape[idx]
                                    if c > 1: return True, c
                                if 'S' in axes: # Samples/Channels
                                    idx = axes.find('S')
                                    c = shape[idx]
                                    if c > 1: return True, c

                            # Shape heuristics
                            if ndim == 3:
                                # (C, Y, X) or (Y, X, C) or (Z, Y, X)
                                # Usually Channels are small number (<10)
                                if shape[0] < 10 and shape[0] > 1: return True, shape[0] # C, Y, X
                                if shape[2] < 10 and shape[2] > 1: return True, shape[2] # Y, X, C
                            elif ndim > 3:
                                # Likely 4D/5D
                                return True, 0 # >1 definitely
                except:
                    pass

            # 2. Check content (slow but accurate for RGB png/jpg)
            stream = np.fromfile(file_path, dtype=np.uint8)
            data = cv2.imdecode(stream, cv2.IMREAD_UNCHANGED)
            if data is not None and data.ndim == 3:
                h, w, c = data.shape
                if c > 1:
                    # Check if channels are identical (Grayscale saved as RGB)
                    ch0 = data[:,:,0]
                    is_diff = False
                    for i in range(1, c):
                        if not np.array_equal(ch0, data[:,:,i]):
                            is_diff = True
                            break
                    if is_diff:
                        return True, c
            
            return False, 1
        except Exception:
            return False, 1

    def _split_and_create_sample(self, file_path: str):
        """Splits a multi-channel image and creates a sample."""
        try:
            # 1. Load Data
            data = None
            is_tif = file_path.lower().endswith(('.tif', '.tiff'))
            if is_tif:
                try:
                    data = tifffile.imread(file_path)
                except:
                    pass
            
            if data is None:
                stream = np.fromfile(file_path, dtype=np.uint8)
                data = cv2.imdecode(stream, cv2.IMREAD_UNCHANGED)
                if data is not None and data.ndim == 3:
                    # CV2 is HWC (BGR)
                    data = cv2.cvtColor(data, cv2.COLOR_BGR2RGB) # RGB
            
            if data is None:
                return None
                
            # Normalize to list of (H, W) arrays
            channels_data = []
            
            # Heuristic to detect C dim
            if data.ndim == 3:
                # (C, Y, X) or (Y, X, C)
                # If loaded via TiffFile, it usually respects metadata, but imread returns numpy array.
                # If (3, H, W) -> C=3. If (H, W, 3) -> C=3.
                if data.shape[0] < data.shape[1] and data.shape[0] < data.shape[2] and data.shape[0] <= 10:
                    # CHW
                    for i in range(data.shape[0]):
                        channels_data.append(data[i, :, :])
                else:
                    # HWC
                    for i in range(data.shape[2]):
                        channels_data.append(data[:, :, i])
            elif data.ndim == 4:
                 # (Z, C, Y, X) or (C, Z, Y, X)? 
                 # Too complex for simple split. Just take max projection or fail?
                 # Let's assume user knows what they are doing.
                 # If we split, we probably split into stacks.
                 # Let's skip complex dims for now or just take C if obvious.
                 pass
                 
            if not channels_data:
                return None
                
            # 2. Save split files
            base_dir = os.path.dirname(file_path)
            fname = os.path.splitext(os.path.basename(file_path))[0]
            saved_paths = []
            
            # R, G, B, W
            colors_map = ["#FF0000", "#00FF00", "#0000FF", "#FFFFFF"] 
            
            channel_defs = []
            
            for i, ch_img in enumerate(channels_data):
                new_name = f"{fname}_ch{i+1}.tif"
                new_path = os.path.join(base_dir, new_name)
                
                # Unique name
                counter = 1
                while os.path.exists(new_path):
                     new_name = f"{fname}_ch{i+1}_{counter}.tif"
                     new_path = os.path.join(base_dir, new_name)
                     counter += 1
                     
                tifffile.imwrite(new_path, ch_img)
                
                color = colors_map[i] if i < len(colors_map) else "#FFFFFF"
                ch_type = f"Ch{i+1}"
                
                channel_defs.append({
                    'path': new_path,
                    'type': ch_type,
                    'color': color
                })
                
            # 3. Create Scene
            # We use add_manual_scene to create undoable scene
            scene_id = self.project_model.add_manual_scene(fname)
            
            # Add channels
            for ch_def in channel_defs:
                self.project_model.add_channel_to_scene(scene_id, ch_def['path'], ch_def['type'], ch_def['color'])
                
            return scene_id
            
        except Exception as e:
            print(f"Error splitting file: {e}")
            return None

    def convert_pool_items_to_samples(self):
        items = self.pool_list.selectedItems()
        if not items: return

        self.project_model.undo_stack.beginMacro(tr("Set as Single Channel Samples"))
        
        file_paths_to_remove = []
        apply_to_all_choice = None # 'split' or 'keep'
        
        for item in items:
            file_path = item.data(Qt.ItemDataRole.UserRole)
            if not file_path or not os.path.exists(file_path):
                continue
            
            # 1. Check Multi-channel
            is_multi, count = self._check_multichannel(file_path)
            
            if is_multi:
                choice = apply_to_all_choice
                
                if choice is None:
                    dlg = MergeSplitDialog(file_path, count, self)
                    if dlg.exec():
                        if dlg.apply_to_all.isChecked():
                            apply_to_all_choice = dlg.result_choice
                        choice = dlg.result_choice
                    else:
                        # Cancelled
                        break
                
                if choice == 'split':
                    sid = self._split_and_create_sample(file_path)
                    if sid:
                        file_paths_to_remove.append(file_path)
                    continue
                elif choice == 'skip':
                    continue
                # If keep, proceed to below
                
            # Detect color
            color = self._detect_rgb_color(file_path)
            
            # Create command
            cmd = ConvertFileToSampleCommand(self.project_model, file_path, color)
            self.project_model.undo_stack.push(cmd)
            
            file_paths_to_remove.append(file_path)

        if file_paths_to_remove:
            self.project_model.remove_files_from_pool(file_paths_to_remove)
            
        self.project_model.undo_stack.endMacro()
        self.refresh_pool_list()

    def create_sample_from_pool_selection(self):
        items = self.pool_list.selectedItems()
        if not items: return
        
        file_paths = [item.data(Qt.ItemDataRole.UserRole) for item in items]
        
        # New Dialog
        dialog = NewSampleDialog(self.project_model, self)
        # Pre-fill name?
        first_name = os.path.splitext(os.path.basename(file_paths[0]))[0]
        dialog.name_edit.setText(first_name)
        
        if dialog.exec():
            name, channels = dialog.get_data()
            
            self.project_model.undo_stack.beginMacro(tr("Create Sample '{0}' from Pool").format(name))
            
            scene_id = self.project_model.add_manual_scene(name, channels)
            
            # Now try to auto-fill
            self.handle_drop_on_scene(scene_id, file_paths)
            
            self.project_model.undo_stack.endMacro()
            
            self.refresh_pool_list()

    def show_sample_context_menu(self, pos):
        item = self.tree_widget.itemAt(pos)
        if not item: return
        
        item_type = item.data(0, Qt.ItemDataRole.UserRole + 1)
        scene_id = item.data(0, Qt.ItemDataRole.UserRole)
        
        if item_type == "Scene":
            # Restore User preference: Right click directly triggers rename
            self.tree_widget.editItem(item, 0)
            return
            
        elif item_type == "Channel":
            ch_index = item.data(0, Qt.ItemDataRole.UserRole + 2)
            menu = QMenu(self)
            
            # Rename Channel Action
            action_rename = QAction(tr("Rename Channel..."), self)
            action_rename.setIcon(get_icon("edit", "edit-rename"))
            action_rename.triggered.connect(lambda: self.rename_channel(scene_id, ch_index))
            menu.addAction(action_rename)
            
            menu.addSeparator()

            # Change Color Action
            action_color = QAction(tr("Change Color..."), self)
            action_color.triggered.connect(lambda: self.change_channel_color(scene_id, ch_index))
            menu.addAction(action_color)
            
            # Color Presets (Optional)
            preset_menu = menu.addMenu(tr("Presets"))
            presets = [
                (tr("DAPI Blue"), "#0000FF"),
                (tr("GFP Green"), "#00FF00"),
                (tr("YFP Yellow"), "#FFFF00"),
                (tr("RFP Red"), "#FF0000"),
                (tr("CY5 Magenta"), "#FF00FF")
            ]
            
            for name, hex_code in presets:
                action = QAction(name, self)
                # Show color icon
                pix = QPixmap(16, 16)
                pix.fill(QColor(hex_code))
                action.setIcon(QIcon(pix))
                # Use apply_channel_preset to set both color and name
                action.triggered.connect(lambda _, s=scene_id, i=ch_index, c=hex_code, n=name: self.apply_channel_preset(s, i, c, n))
                preset_menu.addAction(action)
                
            menu.exec(self.tree_widget.mapToGlobal(pos))
            
    def rename_channel(self, scene_id, ch_index):
        """Opens a dialog to rename a channel."""
        scene = self.project_model.get_scene(scene_id)
        if not scene or ch_index >= len(scene.channels): return
        
        current_name = scene.channels[ch_index].channel_type
        
        # Use QInputDialog for simplicity
        new_name, ok = QInputDialog.getText(self, tr("Rename Channel"), 
                                          tr("New Channel Name:"), 
                                          QLineEdit.Normal, 
                                          current_name)
                                          
        if ok and new_name and new_name.strip():
            new_name = new_name.strip()
            if new_name != current_name:
                # Update model
                self.project_model.update_channel_name(scene_id, ch_index, new_name)
                # Refresh UI
                self.refresh_list()
                # Notify others if needed (e.g. if AdjustmentPanel shows channel names)
                self.scene_structure_changed.emit(scene_id)

    def change_channel_color(self, scene_id, ch_index):
        """Opens a color dialog to change the channel color."""
        scene = self.project_model.get_scene(scene_id)
        if not scene or ch_index >= len(scene.channels): return
        
        current_color = scene.channels[ch_index].color
        color = QColorDialog.getColor(QColor(current_color), self, tr("Select Channel Color"))
        
        if color.isValid():
            self.set_channel_color(scene_id, ch_index, color.name())
            
    def set_channel_color(self, scene_id, ch_index, color_hex):
        """Updates the channel color via the model."""
        self.project_model.update_channel_color(scene_id, ch_index, color_hex)
        # Emit signal to notify other parts (e.g. Session/Renderer) for immediate update
        self.channel_color_changed.emit(scene_id, ch_index, color_hex)

    def apply_channel_preset(self, scene_id, ch_index, color_hex, name_prefix):
        """Applies a color preset and updates the channel name."""
        # 1. Update Color
        self.set_channel_color(scene_id, ch_index, color_hex)
        
        # 2. Update Name (Clean "DAPI Blue" to "DAPI")
        # Usually presets are like "DAPI Blue", we might want just "DAPI" or the full name?
        # User said: "directly named what we choose"
        # Let's use the first part of the preset name or the whole name?
        # "DAPI Blue" -> "DAPI" is probably better.
        # But "GFP Green" -> "GFP".
        # "Magenta" -> "Magenta".
        # Let's extract the key part.
        
        new_name = name_prefix.split(" ")[0] # Simple heuristic
        if "/" in name_prefix: # Handle "Cy5 / Far Red"
             new_name = name_prefix.split("/")[0].strip()
             
        self.project_model.update_channel_name(scene_id, ch_index, new_name)
        self.refresh_list()
        self.scene_structure_changed.emit(scene_id)

    def update_batch_actions_state(self):
        """Updates the state of batch operation buttons based on selection."""
        selected_items = self.tree_widget.selectedItems()
        scene_items = [i for i in selected_items if i.data(0, Qt.ItemDataRole.UserRole + 1) == "Scene"]
        
        self.btn_delete_selected.setEnabled(len(scene_items) > 0)
        if len(scene_items) > 0:
            self.btn_delete_selected.setToolTip(tr("Delete {0} Selected Samples").format(len(scene_items)))
        else:
            self.btn_delete_selected.setToolTip(tr("Delete Selected Samples"))

    def on_delete_button_clicked(self):
        """Triggered by the batch delete button below the tree or Delete key."""
        selected_items = self.tree_widget.selectedItems()
        scene_ids = set()
        
        for item in selected_items:
            item_type = item.data(0, Qt.ItemDataRole.UserRole + 1)
            if item_type == "Scene":
                scene_ids.add(item.data(0, Qt.ItemDataRole.UserRole))
            else:
                # If a channel is selected, find its parent scene
                parent = item.parent()
                if parent and parent.data(0, Qt.ItemDataRole.UserRole + 1) == "Scene":
                    scene_ids.add(parent.data(0, Qt.ItemDataRole.UserRole))
        
        if not scene_ids:
            return
            
        if len(scene_ids) == 1:
            self.delete_sample(list(scene_ids)[0])
        else:
            # Create a list of dummy items or just pass IDs to batch_delete
            # Actually, batch_delete_samples expects items. Let's refactor it to accept IDs.
            self.batch_delete_samples_by_id(list(scene_ids))

    def delete_sample(self, scene_id):
        """Deletes a single sample after confirmation."""
        from PySide6.QtWidgets import QMessageBox
        reply = QMessageBox.question(self, tr("Delete Sample"), 
                                   tr("Are you sure you want to delete sample '{0}'?\nAll associated channel mappings and ROI data for this sample will be lost.\n\nNote: This action can be undone using Ctrl+Z.").format(scene_id),
                                   QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        
        if reply == QMessageBox.StandardButton.Yes:
            self.project_model.remove_scene(scene_id)
            self.scene_deleted.emit(scene_id)

    def batch_delete_samples_by_id(self, scene_ids):
        """Deletes multiple samples after a single confirmation."""
        from PySide6.QtWidgets import QMessageBox
        
        reply = QMessageBox.question(self, tr("Delete Multiple Samples"), 
                                   tr("Are you sure you want to delete {0} samples?\nThis will remove all associated channel mappings and ROI data.\n\nNote: This action can be undone using Ctrl+Z.").format(len(scene_ids)),
                                   QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        
        if reply == QMessageBox.StandardButton.Yes:
            if self.project_model.remove_scenes(scene_ids):
                for sid in scene_ids:
                    self.scene_deleted.emit(sid)
    def import_folder(self):
        # Redirect to auto-group import
        self.import_folder_auto()
