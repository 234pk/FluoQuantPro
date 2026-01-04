import os
import json
import time
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QListWidget, QListWidgetItem, 
                               QLabel, QFileDialog, QInputDialog, QMenu, QMessageBox,
                               QSplitter, QAbstractItemView, QTreeWidget, QTreeWidgetItem,
                               QLineEdit, QHBoxLayout, QToolButton, QHeaderView,
                               QSizePolicy, QColorDialog, QApplication, QToolTip)
from PySide6.QtCore import Qt, Signal, QSize, QUrl, QSettings
from PySide6.QtGui import QColor, QDragEnterEvent, QDropEvent, QPixmap, QIcon, QAction, QPalette
from src.gui.icon_manager import get_icon
from src.core.language_manager import LanguageManager, tr
import tifffile
import qimage2ndarray
import numpy as np
from src.core.project_model import ProjectModel

class PreviewPopup(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        
        palette = QApplication.palette()
        bg_color = palette.color(QPalette.ColorRole.ToolTipBase).name()
        text_color = palette.color(QPalette.ColorRole.ToolTipText).name()
        border_color = palette.color(QPalette.ColorRole.Mid).name()
        
        self.setStyleSheet(f"border: 1px solid {border_color}; background-color: {bg_color}; color: {text_color};")
        self.setFixedSize(256, 256)
        self.setAlignment(Qt.AlignCenter)
        self.setScaledContents(True)

class FileListWidget(QListWidget):
    """Custom ListWidget that exposes file paths as URLs for Drag & Drop.
       Also supports Quick Look (Preview) on hover.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self._preview_popup = PreviewPopup(self)
        self._preview_cache = {} # path -> QPixmap
        self._current_hover_item = None
        
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

    def __init__(self, project_model: ProjectModel, parent=None):
        super().__init__(parent)
        self.project_model = project_model
        self._drag_hint_last_key = None
        
        # Connect to model signals
        self.project_model.project_changed.connect(self.refresh_list)
        self.project_model.project_changed.connect(self.refresh_pool_list)
        
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
        self.lbl_title.setStyleSheet("font-weight: bold; font-size: 14px;")
        header_layout.addWidget(self.lbl_title)
        
        header_layout.addStretch()

        # Sort Button
        self.btn_sort_samples = QToolButton()
        # Use our generated icon (it will fallback to internal generation if png is missing)
        self.btn_sort_samples.setIcon(get_icon("sort"))
        self.btn_sort_samples.setIconSize(QSize(20, 20))
        self.btn_sort_samples.setFixedSize(28, 28)
        self.btn_sort_samples.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_sort_samples.setToolTip(tr("Sort Samples A-Z"))
        self.btn_sort_samples.setAutoRaise(True)
        self.btn_sort_samples.clicked.connect(self.sort_samples)
        header_layout.addWidget(self.btn_sort_samples)

        # Expand/Collapse All Button
        self.btn_expand_all = QToolButton()
        # Use our generated icon for expand
        self.btn_expand_all.setIcon(get_icon("expand")) 
        self.btn_expand_all.setIconSize(QSize(20, 20))
        self.btn_expand_all.setFixedSize(28, 28)
        self.btn_expand_all.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_expand_all.setToolTip(tr("Expand/Collapse All Channels"))
        self.btn_expand_all.setAutoRaise(True)
        self.btn_expand_all.setCheckable(True)
        self.btn_expand_all.setChecked(True) # Default expanded
        self.btn_expand_all.toggled.connect(self.toggle_expand_all)
        header_layout.addWidget(self.btn_expand_all)
        
        self.btn_add_sample_header = QToolButton()
        self.btn_add_sample_header.setIcon(get_icon("add", "list-add"))
        self.btn_add_sample_header.setIconSize(QSize(20, 20))
        self.btn_add_sample_header.setFixedSize(28, 28)
        self.btn_add_sample_header.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add_sample_header.setToolTip(tr("Quick Add Blank Sample (Alt+N)"))
        self.btn_add_sample_header.setAutoRaise(True)
        self.btn_add_sample_header.clicked.connect(self.quick_add_sample)
        header_layout.addWidget(self.btn_add_sample_header)
        
        # Batch Delete Button (next to Add button)
        self.btn_delete_selected = QToolButton()
        self.btn_delete_selected.setIcon(get_icon("delete", "edit-delete"))
        self.btn_delete_selected.setIconSize(QSize(20, 20))
        self.btn_delete_selected.setFixedSize(28, 28)
        self.btn_delete_selected.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_delete_selected.setToolTip(tr("Delete Selected Samples"))
        self.btn_delete_selected.setAutoRaise(True)
        self.btn_delete_selected.clicked.connect(self.on_delete_button_clicked)
        self.btn_delete_selected.setEnabled(False) # Disabled by default
        self.btn_delete_selected.setStyleSheet("QToolButton:disabled { opacity: 0.3; }")
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
        self.tree_widget.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        header = self.tree_widget.header()
        header.setMinimumSectionSize(10)
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
        palette = QApplication.palette()
        mid_color = palette.color(QPalette.ColorRole.Mid).name()
        self.lbl_pool.setStyleSheet(f"font-weight: bold; font-size: 14px; color: {mid_color};")
        pool_header.addWidget(self.lbl_pool)
        pool_header.addStretch()

        # Select All and Create Samples Button
        self.btn_pool_auto_group = QToolButton()
        self.btn_pool_auto_group.setIcon(get_icon("add", "list-add"))
        self.btn_pool_auto_group.setToolTip(tr("Auto-group selected (or all if none selected) into samples"))
        self.btn_pool_auto_group.clicked.connect(self.auto_group_from_pool)
        pool_header.addWidget(self.btn_pool_auto_group)
        
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
        self.pool_list.setDragEnabled(True) # Enable dragging FROM here
        self.pool_list.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self.pool_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.pool_list.customContextMenuRequested.connect(self.show_pool_context_menu)
        
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
        self.btn_auto_group.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.btn_auto_group.setText(tr("Auto Group Import Folder"))
        self.btn_auto_group.setToolTip(tr("Import a folder of images and automatically group them into samples"))
        self.btn_auto_group.setMinimumHeight(36)
        self.btn_auto_group.setMinimumWidth(0)
        self.btn_auto_group.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_auto_group.setAutoRaise(True)
        self.btn_auto_group.clicked.connect(self.import_folder_auto)
        btn_layout.addWidget(self.btn_auto_group)
 
        self.btn_load_pool = QToolButton()
        self.btn_load_pool.setIcon(get_icon("folder", "folder-open"))
        self.btn_load_pool.setIconSize(QSize(20, 20))
        self.btn_load_pool.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.btn_load_pool.setText(tr("Load Images"))
        self.btn_load_pool.setToolTip(tr("Import images into the unassigned pool"))
        self.btn_load_pool.setMinimumHeight(36)
        self.btn_load_pool.setMinimumWidth(0)
        self.btn_load_pool.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_load_pool.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_load_pool.setAutoRaise(True)
        self.btn_load_pool.clicked.connect(self.load_images_to_pool)
        btn_layout.addWidget(self.btn_load_pool)

        # self.btn_new_sample = QPushButton("New Sample (with Channels)")
        # self.btn_new_sample.clicked.connect(self.create_manual_sample)
        # btn_layout.addWidget(self.btn_new_sample)
        
        self.layout.addLayout(btn_layout)

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
        self.search_pool.setPlaceholderText(tr("Search pool files..."))
        
        # Bottom Buttons
        self.btn_auto_group.setText(tr("Auto Group Import Folder"))
        self.btn_auto_group.setToolTip(tr("Import a folder of images and automatically group them into samples"))
        self.btn_load_pool.setText(tr("Load Images"))
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

    def refresh_pool_list(self):
        # Save scroll position and current item if any
        scrollbar = self.pool_list.verticalScrollBar()
        scroll_pos = scrollbar.value()
        
        print(f"[SampleList] refresh_pool_list called. Pool files: {len(self.project_model.pool_files)}")
        
        # We need to preserve the "visual" position of the dragging item if possible, 
        # but since we are re-sorting, it's tricky.
        # The user request is "keep list at dragging position", which implies 
        # if I just dragged "image1.tif", I want to see where it went (bottom) or 
        # at least not have the list jump to top.
        
        self.pool_list.clear()
        files = self.project_model.pool_files 
        
        assigned_set = self.project_model.get_assigned_files()
        print(f"[SampleList] Assigned files count: {len(assigned_set)}")
        
        # Separate files into unassigned and assigned
        unassigned_files = [f for f in files if f not in assigned_set]
        assigned_files = [f for f in files if f in assigned_set]
        
        # Sort both (optional but keeps it tidy)
        unassigned_files.sort(key=lambda x: os.path.basename(x).lower())
        assigned_files.sort(key=lambda x: os.path.basename(x).lower())
        
        sorted_files = unassigned_files + assigned_files
        
        # Count available files for label
        available_count = len(unassigned_files)
        self.lbl_pool.setText(tr("Unassigned Images ({0})").format(available_count))
        
        last_assigned_item = None
        
        for fpath in sorted_files:
            fname = os.path.basename(fpath)
            item = QListWidgetItem(fname)
            item.setData(Qt.ItemDataRole.UserRole, fpath)
            item.setToolTip(fpath)
            
            if fpath in assigned_set:
                # Use explicit gray color for better visibility of disabled state
                # Force color using QBrush/QColor directly
                item.setForeground(QColor(150, 150, 150)) 
                
                # Disable selection and drag
                item.setFlags(Qt.ItemFlag.NoItemFlags) # Disable everything including Enabled state
                
                # Track the last assigned item added
                last_assigned_item = item
                # print(f"[SampleList] Item '{fname}' marked as assigned (grayed out).")
            else:
                item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsDragEnabled)
                
            self.pool_list.addItem(item)
            
        # Restore scroll position
        # If the list changed significantly (e.g. item moved to bottom), restoring exact pixel value 
        # might be disorienting if the item is no longer there.
        # But generally keeping the scroll bar position is the standard "least surprise" behavior.
        scrollbar.setValue(scroll_pos)
        print(f"[SampleList] refresh_pool_list completed. Unassigned: {len(unassigned_files)}, Assigned: {len(assigned_files)}")

    def refresh_list(self):
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
                palette = QApplication.palette()
                # Use a nice green that works in both themes
                is_dark = palette.color(QPalette.ColorRole.Window).lightness() < 128
                status_color = QColor("#00FF00") if is_dark else QColor("#008000")
                scene_item.setForeground(1, status_color)
            
            scene_item.setData(0, Qt.ItemDataRole.UserRole, scene.id)
            scene_item.setData(0, Qt.ItemDataRole.UserRole + 1, "Scene")
            
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
                    ch_item.setForeground(0, palette.color(QPalette.ColorRole.Mid)) # Greyish for files
                    ch_item.setIcon(0, get_icon("icon", "image-x-generic")) # Try standard icon
                    
                    # Add Clear Button
                    btn_clear = QToolButton()
                    btn_clear.setIcon(get_icon("clear", "edit-clear"))
                    btn_clear.setIconSize(QSize(16, 16))
                    btn_clear.setFixedSize(22, 22)
                    btn_clear.setToolTip(tr("Remove Image from Channel"))
                    btn_clear.setAutoRaise(True)
                    btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
                    btn_clear.clicked.connect(lambda _, s_id=scene.id, c_idx=i: self.clear_channel(s_id, c_idx))
                    actions_layout.addWidget(btn_clear)
                
                # Add Delete Button (always available for channels)
                btn_delete = QToolButton()
                btn_delete.setIcon(get_icon("delete", "edit-delete"))
                btn_delete.setIconSize(QSize(16, 16))
                btn_delete.setFixedSize(22, 22)
                btn_delete.setToolTip(tr("Delete Channel Slot"))
                btn_delete.setAutoRaise(True)
                btn_delete.setCursor(Qt.CursorShape.PointingHandCursor)
                btn_delete.clicked.connect(lambda _, s_id=scene.id, c_idx=i: self.on_remove_channel_clicked(s_id, c_idx))
                actions_layout.addWidget(btn_delete)
                
                actions_layout.addStretch()
                self.tree_widget.setItemWidget(ch_item, 1, actions_container)
                
                # Set color indicator (using a colored square icon)
                pix = QPixmap(16, 16)
                pix.fill(QColor(ch.color))
                ch_item.setIcon(0, QIcon(pix))
                    
                if not ch.path:
                    # Empty Slot
                    ch_item.setText(0, tr("{0}: [{1}]").format(ch.channel_type, tr("Empty")))
                    palette = QApplication.palette()
                    is_dark = palette.color(QPalette.ColorRole.Window).lightness() < 128
                    empty_color = QColor("#FF5555") if is_dark else QColor("#CC0000")
                    ch_item.setForeground(0, empty_color) # Reddish for empty
                    
                    # For empty slots, we might also want to show the color indicator? 
                    # Yes, per user request (DAPI is blue even if empty)
                    pix = QPixmap(16, 16)
                    pix.fill(QColor(ch.color))
                    ch_item.setIcon(0, QIcon(pix))
                
                ch_item.setData(0, Qt.ItemDataRole.UserRole, scene.id)
                ch_item.setData(0, Qt.ItemDataRole.UserRole + 1, "Channel")
                ch_item.setData(0, Qt.ItemDataRole.UserRole + 2, i) # Index
            
            # Add [+] Button Item
            add_item = QTreeWidgetItem(scene_item)
            add_item.setFlags(Qt.ItemFlag.ItemIsEnabled) # Not selectable/dragable
            
            btn_add = QToolButton()
            btn_add.setIcon(get_icon("add", "list-add"))
            btn_add.setIconSize(QSize(14, 14))
            btn_add.setText(tr("Add Channel"))
            btn_add.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            btn_add.setToolTip(tr("Add new empty channel slot"))
            btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
            
            # Professional, integrated style with theme-aware hover
            palette = QApplication.palette()
            mid_color = palette.color(QPalette.ColorRole.Mid).name()
            btn_add.setStyleSheet(f"""
                QToolButton {{
                    border: none;
                    background: transparent;
                    color: {mid_color};
                    font-size: 11px;
                    padding: 2px 5px;
                    border-radius: 4px;
                }}
                QToolButton:hover {{
                    background-color: rgba(128, 128, 128, 0.2);
                    color: palette(window-text);
                }}
            """)
            btn_add.clicked.connect(lambda _, s_id=scene.id: self.on_add_channel_clicked(s_id))
            
            widget_container = QWidget()
            h_layout = QHBoxLayout(widget_container)
            # Indent to match channel text (icon is ~16px, spacing ~5px, so ~21-25px)
            h_layout.setContentsMargins(28, 0, 0, 0) 
            h_layout.setSpacing(0)
            h_layout.addWidget(btn_add)
            h_layout.addStretch()
            
            self.tree_widget.setItemWidget(add_item, 0, widget_container)

            # Respect the expand/collapse all button state
            scene_item.setExpanded(self.btn_expand_all.isChecked())

    def on_add_channel_clicked(self, scene_id):
        self.project_model.add_empty_channel(scene_id)

    def on_remove_channel_clicked(self, scene_id, channel_index):
        """Removes a channel slot from a scene."""
        self.project_model.remove_channel(scene_id, channel_index)
        self.refresh_list()
        self.refresh_pool_list()
        self.channel_removed.emit(scene_id, channel_index)
        # Reload scene if it's the current one
        self.scene_selected.emit(scene_id)

    def clear_channel(self, scene_id, channel_index):
        """Clears the assigned image from a channel slot."""
        self.project_model.update_channel_path(scene_id, channel_index, "")
        self.refresh_list()
        self.refresh_pool_list()
        self.channel_cleared.emit(scene_id, channel_index)
        # Optionally refresh scene if it's the current one
        # But we don't have direct access to main window here easily without signal
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
            target_item = self.tree_widget.itemAt(event.position().toPoint())
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

    def _check_image_channels(self, file_path: str) -> bool:
        """
        Validates if an image is suitable for single-channel assignment.
        Returns True if grayscale or pseudo-RGB (only one non-zero channel).
        Returns False and shows warning if multi-channel.
        """
        try:
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

        target_item = self.tree_widget.itemAt(event.position().toPoint())
        
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
                if self._check_image_channels(file_paths[0]):
                    ch_index = target_item.data(0, Qt.ItemDataRole.UserRole + 2)
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
        self.scene_selected.emit(scene_id)

    def guess_channel(self, filename):
        name_upper = filename.upper()
        for key in ["DAPI", "GFP", "RFP", "CY5", "TRITC", "FITC"]:
            if key in name_upper:
                return key
        return None

    # --- Context Menus ---
    
    def show_pool_context_menu(self, pos):
        menu = QMenu(self)
        create_action = menu.addAction(tr("Create Sample from Selection"))
        action = menu.exec(self.pool_list.mapToGlobal(pos))
        
        if action == create_action:
            self.create_sample_from_pool_selection()

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
                (tr("DAPI Blue"), "#0000ff"),
                (tr("GFP Green"), "#009E73"),
                (tr("YFP Gold"), "#F0E442"),
                (tr("RFP Red"), "#D55E00"),
                (tr("Magenta"), "#CC79A7"),
                (tr("Cy5 / Far Red"), "#A2142F")
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
                self.scene_selected.emit(scene_id)

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
        self.scene_selected.emit(scene_id)

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
