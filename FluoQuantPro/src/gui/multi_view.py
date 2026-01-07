import time
import os
from PySide6.QtWidgets import (QWidget, QVBoxLayout, 
                               QSplitter, QLabel, QApplication, QPushButton, QFrame, QMenu,
                               QListWidget, QListWidgetItem)
from PySide6.QtCore import Qt, Signal, QSettings, QRectF, QSize, QPointF
from PySide6.QtGui import QPalette
import numpy as np
from typing import Dict

from src.core.data_model import Session
from src.core.renderer import Renderer
from src.core.logger import Logger
from src.gui.canvas_view import CanvasView
from src.gui.sync_manager import SyncManager
from src.gui.icon_manager import get_icon
from src.core.language_manager import tr

class EmptyStateWidget(QWidget):
    """
    Widget displayed when no images are loaded.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(20)
        
        # Icon
        icon_label = QLabel()
        icon = get_icon("import", "document-import")
        pixmap = icon.pixmap(128, 128)
        icon_label.setPixmap(pixmap)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_label)
        
        # Title
        title = QLabel(tr("No Sample Selected"))
        title.setProperty("role", "title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        
        # Subtitle
        subtitle = QLabel(tr("Start by creating a new project or opening an existing one."))
        subtitle.setProperty("role", "subtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)
        
        # Action Buttons Container
        btn_container = QWidget()
        btn_layout = QVBoxLayout(btn_container)
        btn_layout.setSpacing(10)
        layout.addWidget(btn_container)
        
        # New Project
        self.btn_new = QPushButton(tr("New Project"))
        self.btn_new.setIcon(get_icon("new", "document-new"))
        self.btn_new.setIconSize(QSize(24, 24))
        self.btn_new.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_new.setProperty("role", "hero")
        btn_layout.addWidget(self.btn_new)

        # Open Project
        self.btn_open = QPushButton(tr("Open Project"))
        self.btn_open.setIcon(get_icon("open", "document-open"))
        self.btn_open.setIconSize(QSize(24, 24))
        self.btn_open.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_open.setProperty("role", "hero")
        btn_layout.addWidget(self.btn_open)

        # Import Images (Secondary)
        self.btn_import = QPushButton(tr("Import Images"))
        self.btn_import.setIcon(get_icon("import", "document-import")) # Changed icon key to match action
        self.btn_import.setIconSize(QSize(24, 24))
        self.btn_import.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_import.setProperty("role", "hero")
        btn_layout.addWidget(self.btn_import)
        
        # Import Folder
        self.btn_import_folder = QPushButton(tr("Import Folder"))
        self.btn_import_folder.setIcon(get_icon("folder", "folder-open"))
        self.btn_import_folder.setIconSize(QSize(24, 24))
        self.btn_import_folder.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_import_folder.setProperty("role", "hero")
        btn_layout.addWidget(self.btn_import_folder)
        
        # Import Merge
        self.btn_import_merge = QPushButton(tr("Import Merge (RGB Split)"))
        self.btn_import_merge.setIcon(get_icon("import", "document-import"))
        self.btn_import_merge.setIconSize(QSize(24, 24))
        self.btn_import_merge.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_import_merge.setProperty("role", "hero")
        btn_layout.addWidget(self.btn_import_merge)
        
        # Recent Projects Button
        self.btn_recent = QPushButton(tr("Recent Projects"))
        self.btn_recent.setIcon(get_icon("open", "document-open-recent"))
        self.btn_recent.setIconSize(QSize(24, 24))
        self.btn_recent.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_recent.setProperty("role", "hero")
        btn_layout.addWidget(self.btn_recent)
        
        # Recent Projects List Section (Keep for quick access)
        self.lbl_recent = QLabel(tr("Recent Projects:"))
        self.lbl_recent.setProperty("role", "title")
        self.lbl_recent.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_recent.hide() # Hidden by default
        btn_layout.addWidget(self.lbl_recent)
        
        self.list_recent = QListWidget()
        self.list_recent.setProperty("role", "recent")
        self.list_recent.setFixedHeight(150)
        self.list_recent.hide()
        # Connected in MultiViewWidget instead
        btn_layout.addWidget(self.list_recent)
        
        self._load_recent_projects()
        
        # Connect button to show menu
        self.btn_recent.clicked.connect(self._show_recent_menu)
        
    def _show_recent_menu(self):
        """Shows the recent projects menu at the button location."""
        menu = QMenu(self)
        
        settings = QSettings("FluoQuantPro", "AppSettings")
        recent = settings.value("recentProjects", [])
        if not isinstance(recent, list):
            recent = [recent] if recent else []
            
        if not recent:
            action = menu.addAction(tr("No Recent Projects"))
            action.setEnabled(False)
        else:
            for path in recent:
                if os.path.exists(path):
                    action = menu.addAction(os.path.basename(path))
                    action.setData(path)
                    action.setToolTip(path)
                    # Correctly emit the signal via parent (MultiViewWidget)
                    action.triggered.connect(lambda checked=False, p=path: self.parent().open_recent_requested.emit(p))
            
            menu.addSeparator()
            clear_action = menu.addAction(tr("Clear Recent Projects"))
            clear_action.triggered.connect(self._clear_recent)
            
        # Show menu below the button
        menu.exec(self.btn_recent.mapToGlobal(self.btn_recent.rect().bottomLeft()))

    def _clear_recent(self):
        """Clears recent projects list and refreshes UI."""
        settings = QSettings("FluoQuantPro", "AppSettings")
        settings.setValue("recentProjects", [])
        self._load_recent_projects()
        # Also notify main window to update its menu if possible
        # But for now, just refreshing local state is enough

    def _load_recent_projects(self):
        settings = QSettings("FluoQuantPro", "AppSettings")
        # Load as list of strings
        recent = settings.value("recentProjects", [])
        # Ensure it's a list (QSettings can return single string if only one item)
        if not isinstance(recent, list):
            recent = [recent] if recent else []
            
        if recent:
            self.lbl_recent.show()
            self.list_recent.show()
            self.list_recent.clear()
            for path in recent:
                if path and isinstance(path, str) and os.path.exists(path):
                    item = QListWidgetItem(path)
                    item.setToolTip(path)
                    self.list_recent.addItem(item)
        else:
            self.lbl_recent.hide()
            self.list_recent.hide()

class MultiViewWidget(QWidget):
    """
    Manages multiple CanvasView instances in a Grid Layout.
    Handles view synchronization and content rendering.
    """
    channel_file_dropped = Signal(str, int) # file_path, channel_index
    channel_selected = Signal(int) # channel_index
    mouse_moved_on_view = Signal(int, int, int) # x, y, channel_index (-1 for merge)
    annotation_created = Signal(object) # GraphicAnnotation
    annotation_modified = Signal(object) # GraphicAnnotation or dict update
    tool_cancelled = Signal() # Propagated from CanvasView
    
    # Relay import signal
    import_requested = Signal()
    new_project_requested = Signal()
    open_project_requested = Signal()
    open_recent_requested = Signal(str) # New signal for recent projects
    import_folder_requested = Signal()
    import_merge_requested = Signal()

    def __init__(self, session: Session, parent=None):
        super().__init__(parent)
        self.session = session
        self.sync_manager = SyncManager()
        self.settings = QSettings("FluoQuantPro", "Settings")
        
        # Store views: "Merge", "Ch1", "Ch2", ...
        self.views: Dict[str, CanvasView] = {}
        self.active_channel_id = "Merge" 
        self.annotation_mode = 'none'
        self.current_tool = None
        
        # Main Layout
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Empty State Widget
        self.empty_state = EmptyStateWidget(self)
        self.empty_state.btn_import.clicked.connect(self.import_requested.emit)
        self.empty_state.btn_new.clicked.connect(self.new_project_requested.emit)
        self.empty_state.btn_open.clicked.connect(self.open_project_requested.emit)
        self.empty_state.btn_import_folder.clicked.connect(self.import_folder_requested.emit)
        self.empty_state.btn_import_merge.clicked.connect(self.import_merge_requested.emit)
        
        # Connect recent list click
        self.empty_state.list_recent.itemClicked.connect(lambda item: self.open_recent_requested.emit(item.text()))
        
        self.main_layout.addWidget(self.empty_state)
        
        # Loading Overlay (initially hidden)
        self.loading_overlay = QLabel("Loading...", self)
        self.loading_overlay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.loading_overlay.setProperty("role", "overlay")
        self.loading_overlay.hide()
        
        # Container for views
        self.view_container = QWidget()
        self.main_layout.addWidget(self.view_container)
        
        # Initial State
        self.update_view_state()

    def show_loading(self, message="Loading..."):
        """Shows the loading overlay."""
        self.loading_overlay.setText(message)
        self.loading_overlay.raise_() # Ensure on top
        self.loading_overlay.resize(self.size())
        self.loading_overlay.show()
        # print(f"[{time.strftime('%H:%M:%S')}] UI: Showing Loading Overlay: {message}")
        
    def hide_loading(self):
        """Hides the loading overlay."""
        self.loading_overlay.hide()
        # print(f"[{time.strftime('%H:%M:%S')}] UI: Hiding Loading Overlay")
        
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.loading_overlay.resize(self.size())
        
    def update_view_state(self):
        """Updates visibility of empty state vs view container."""
        if not self.session.channels:
            self.empty_state._load_recent_projects() # Refresh recent list when shown
            self.empty_state.show()
            self.view_container.hide()
        else:
            self.empty_state.hide()
            self.view_container.show()

    def initialize_views(self):
        """Creates CanvasView instances for Merge and each Channel."""
        # Clear existing
        self.views.clear()
        self.sync_manager = SyncManager() # Reset sync
        
        # 1. Merge View
        merge_view = CanvasView(view_id="Merge", session=self.session)
        merge_view.set_roi_manager(self.session.roi_manager)
        merge_view.set_label("Merge")
        merge_view.active_channel_index = -1 # Explicitly set for tools
        merge_view.mouse_moved.connect(lambda x, y: self.on_mouse_moved(x, y, -1))
        merge_view.view_clicked.connect(self.on_view_clicked) # Add click connection for selection
        merge_view.annotation_created.connect(self.annotation_created.emit)
        merge_view.annotation_modified.connect(self.annotation_modified.emit)
        merge_view.tool_cancelled.connect(self.tool_cancelled.emit)
        merge_view.scale_bar_moved.connect(self.on_scale_bar_moved)
        self.views["Merge"] = merge_view
        self.sync_manager.add_view(merge_view)
        
        # 2. Channel Views
        for i, ch in enumerate(self.session.channels):
            # Use channel name or index as ID
            view_id = f"Ch{i+1}"
            view = CanvasView(view_id=view_id, session=self.session)
            view.set_roi_manager(self.session.roi_manager)
            view.set_label(ch.name)  # Display Channel Name
            view.active_channel_index = i # For tool operations
            view.file_dropped.connect(self.on_view_file_dropped)
            view.view_clicked.connect(self.on_view_clicked)
            view.annotation_created.connect(self.annotation_created.emit)
            view.annotation_modified.connect(self.annotation_modified.emit)
            view.tool_cancelled.connect(self.tool_cancelled.emit)
            view.scale_bar_moved.connect(self.on_scale_bar_moved)
            
            # Connect mouse move for status bar
            # We need to capture i for the lambda
            view.mouse_moved.connect(lambda x, y, idx=i: self.on_mouse_moved(x, y, idx))
            self.views[view_id] = view
            self.sync_manager.add_view(view)
            
        # Set Default Layout
        self.setup_layout()

        # --- USER REQUEST: Restore active tool and annotation mode to new views ---
        if self.current_tool:
            for view in self.views.values():
                view.set_active_tool(self.current_tool)
        
        if self.annotation_mode != 'none':
            for view in self.views.values():
                view.set_annotation_mode(self.annotation_mode)
                
        # Initial Render
        self.render_all()
        
        # Update State
        self.update_view_state()

    def flash_channel(self, channel_index: int, duration_ms: int = 250):
        if channel_index is None or channel_index < 0:
            return
        view_id = f"Ch{channel_index+1}"
        view = self.views.get(view_id)
        if view and hasattr(view, "start_flash"):
            view.start_flash(duration_ms)

    def on_view_file_dropped(self, file_path: str, channel_index: int):
        """Relay signal to main window."""
        self.channel_file_dropped.emit(file_path, channel_index)

    def on_view_clicked(self, view_id: str, channel_index: int):
        """Relay selection signal and update visual state."""
        if self.active_channel_id == view_id:
            # Already selected, skip redundant updates to prevent excessive redrawing
            return

        self.active_channel_id = view_id
        
        # Update Visuals only if changed
        for vid, view in self.views.items():
            view.set_selected(vid == view_id)
            
        # Relay selection signal
        if channel_index >= 0:
            self.channel_selected.emit(channel_index)
        elif view_id == "Merge":
            self.channel_selected.emit(-1)

    def on_mouse_moved(self, x: int, y: int, channel_index: int):
        """Relay mouse movement from a view."""
        self.mouse_moved_on_view.emit(x, y, channel_index)

    def on_scale_bar_moved(self, pos: QPointF):
        """Sync scale bar position across all views."""
        # Update session settings (so it persists for new views)
        self.session.scale_bar_settings.custom_pos = (pos.x(), pos.y())
        self.session.scale_bar_settings.position = "Custom"
        
        # Propagate to all views
        for view in self.views.values():
            # Avoid re-emitting if the view is the sender (optional, but view handles it)
            view.update_ruler_position(pos)

    def get_active_view(self):
        """Returns the currently active CanvasView instance."""
        return self.views.get(self.active_channel_id)

    def select_channel(self, index: int):
        """Programmatically select a channel view."""
        if index < 0:
            target_id = "Merge"
        else:
            target_id = f"Ch{index+1}"
            
        if target_id in self.views:
            self.on_view_clicked(target_id, index)


    def fit_views(self):
        """Fits all views to their content."""
        for view in self.views.values():
            view.fitInView(view.scene().sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def render_all(self, preview=False):
        """Renders content for all views. If preview=True, downsamples for performance."""
        t_render_start = time.time()
        
        # Disable sync during bulk update to prevent coordinate jumping
        self.sync_manager.set_enabled(False)
        
        try:
            # 1. Determine Original Shape (for Scene Rect)
            original_shape = None
            for ch in self.session.channels:
                 if not getattr(ch, 'is_placeholder', False) and ch.raw_data is not None:
                      original_shape = ch.shape # (H, W)
                      break
            
            if original_shape is None:
                 # No valid data to render
                 # print("[Timing] MultiView: No original_shape found.")
                 for view in self.views.values():
                      view.update_image(None)
                 return

            h, w = original_shape
            target_shape = None
            
            # Determine downsampling limit based on user settings
            quality = self.settings.value("display/quality", "Balanced (Recommended)")
            if quality == "Performance (Downsampled)":
                 max_dim = 1024
            elif quality == "Balanced (Recommended)":
                 max_dim = 2048
            else: # High Quality (Full Resolution)
                 max_dim = 8192 # High but safe limit for QPixmap
                 
            if preview:
                 # Force smaller preview regardless of setting
                 max_dim = min(max_dim, 1024)
                 
            long_side = max(h, w)
            if long_side > max_dim:
                 # print(f"[Performance] Downsampling image {w}x{h} to max {max_dim}px based on quality setting: {quality}")
                 scale = float(max_dim) / long_side
                 new_h = int(h * scale)
                 new_w = int(w * scale)
                 target_shape = (new_h, new_w)
            
            # 2. Render each channel's display image (Raw -> RGB)
            # We use the Renderer class which might be static or instance
            # For now, let's assume we do it per-channel here or via Session helpers
            
            # Optimization: If we have many channels, we could thread this.
            # But for 3-4 channels, serial is fine if Renderer is fast (LUT).
            
            channel_images = {}
            for i, ch in enumerate(self.session.channels):
                # Always render if we have data, even if hidden (for Merge)
                if ch.raw_data is not None:
                    # Render returns (H, W, 3) or (H, W, 4) uint8
                    # Pass target_shape for resizing during render
                    img = Renderer.render_channel(ch, target_shape=target_shape)
                    channel_images[i] = img
            
            # 3. Update Channel Views
            for i, img in channel_images.items():
                view_id = f"Ch{i+1}"
                if view_id in self.views:
                    # Update scene rect to match ORIGINAL shape, but display scaled image
                    # The CanvasView handles the scaling logic (display_scale)
                    
                    # Convert to uint8 0-255 for display if needed
                    display_img = img
                    if img.dtype == np.float32 and img.max() <= 1.0:
                         display_img = (img * 255).astype(np.uint8)
                    
                    self.views[view_id].update_image(display_img, scene_rect=QRectF(0.0, 0.0, float(w), float(h)))

            # 4. Update Merge View
            if "Merge" in self.views:
                # Composite
                # Simple additive blending for now
                if not channel_images:
                    self.views["Merge"].update_image(None)
                else:
                    # Start with black
                    if target_shape:
                        th, tw = target_shape
                    else:
                        th, tw = h, w
                        
                    composite = None
                    
                    for i, ch in enumerate(self.session.channels):
                        # ch is an ImageChannel object.
                        # It should have a visible property if it's an ImageChannel.
                        # However, session.channels stores ImageChannel objects which definitely have 'visible'.
                        # But wait, session.channels might contain ChannelDef objects if not fully initialized?
                        # No, session.channels is List[ImageChannel].
                        # The error says 'ImageChannel' object has no attribute 'visible'.
                        # Let's check ImageChannel definition in src/core/data_model.py or use display_settings.visible.
                        
                        is_visible = True
                        if hasattr(ch, 'display_settings'):
                            is_visible = ch.display_settings.visible
                        elif hasattr(ch, 'visible'):
                             is_visible = ch.visible
                        
                        if is_visible and i in channel_images:
                            img = channel_images[i]
                            if composite is None:
                                composite = img.astype(np.float32)
                            else:
                                composite += img.astype(np.float32)
                    
                    if composite is not None:
                        np.clip(composite, 0.0, 1.0, out=composite)
                        composite = (composite * 255).astype(np.uint8)
                        self.views["Merge"].update_image(composite, scene_rect=QRectF(0.0, 0.0, float(w), float(h)))
                    else:
                         # Black if all hidden
                        black = np.zeros((th, tw, 3), dtype=np.uint8)
                        self.views["Merge"].update_image(black, scene_rect=QRectF(0.0, 0.0, float(w), float(h)))


        except Exception as e:
            print(f"Error in render_all: {e}")
            import traceback
            traceback.print_exc()
        
        finally:
            self.sync_manager.set_enabled(True)
            print(f"[14:33:26] MultiView: render_all finished ({time.time() - t_render_start:.4f}s)")

    def update_view(self, channel_index):
        """
        Updates a specific channel view (and Merge view).
        Used for targeted refreshes (e.g. drag-drop).
        """
        # Find view ID
        view_id = f"Ch{channel_index+1}"
        if view_id in self.views:
            # Render just this channel
            ch = self.session.channels[channel_index]
            if ch.raw_data is not None:
                img = Renderer.render_channel(ch)
                
                # Get dimensions from image itself, not session which might be mixed
                h, w = img.shape[:2] if img.ndim > 1 else (0, 0)
                
                display_img = img
                if img.dtype == np.float32 and img.max() <= 1.0:
                     display_img = (img * 255).astype(np.uint8)
                
                self.views[view_id].update_image(display_img, scene_rect=QRectF(0.0, 0.0, float(w), float(h)))
                
        # Always refresh merge
        # This is a bit inefficient to re-render all for merge, but safe
        self.render_all()

    def setup_layout(self):
        """Updates the grid layout based on number of channels."""
        # 1. Remove existing splitter
        if hasattr(self, 'main_splitter'):
            self.main_splitter.setParent(None)
            
        # 2. Clear current layout of view_container
        if self.view_container.layout():
            old_layout = self.view_container.layout()
            while old_layout.count():
                item = old_layout.takeAt(0)
                if item.widget():
                    item.widget().setParent(None)
            dummy = QWidget()
            dummy.setLayout(old_layout)
        
        if not self.view_container.layout():
            self.view_container.setLayout(QVBoxLayout())
            self.view_container.layout().setContentsMargins(0, 0, 0, 0)
        
        container_layout = self.view_container.layout()
        
        # 3. Create Custom Layout based on channel count
        merge_view = self.views.get("Merge")
        channel_views = [v for k, v in self.views.items() if k != "Merge"]
        num_channels = len(channel_views)

        if not merge_view and not channel_views:
            return

        # Main Vertical Splitter
        v_splitter = QSplitter(Qt.Orientation.Vertical)
        v_splitter.setHandleWidth(4)
        
        # --- NEW LAYOUT LOGIC (2-Column Grid with special Merge handling) ---
        # Rule: 
        # N=1: Ch1 / Merge (Vertical)
        # N>1: 2-Column Grid
        #   - If total views (N+1) is odd (e.g. N=2 -> 3 views): Last item (Merge) is centered.
        #   - If total views (N+1) is even (e.g. N=3 -> 4 views): Last row has 2 items.
        #     User wants Merge at "Left Bottom".
        #     So for N=3: [1, 2], [Merge, 3] (Swap Merge and Last Channel)
        
        if num_channels == 1 and merge_view:
            # 1 Channel + 1 Merge -> Vertical Stack (Merge on bottom)
            v_splitter.addWidget(channel_views[0])
            v_splitter.addWidget(merge_view)
            channel_views[0].show()
            merge_view.show()
            v_splitter.setStretchFactor(0, 1)
            v_splitter.setStretchFactor(1, 1)
            
        else:
            # 2+ Channels
            # Prepare ordered list of views
            views_to_layout = list(channel_views)
            
            total_views = len(views_to_layout) + 1 # +1 for Merge
            is_odd_total = (total_views % 2 != 0)
            
            # If total views is even (e.g. N=3, Total 4), swap Merge to be before the last channel
            # to achieve "Left Bottom" placement for Merge.
            # Example N=3: [1, 2, 3] + [M]. Total 4.
            # Grid 2x2. Row 2: [3, M].
            # User wants: [M, 3].
            # So list should be: 1, 2, M, 3.
            
            if not is_odd_total:
                # Insert Merge before the last channel
                views_to_layout.insert(-1, merge_view)
            else:
                # Total is odd (e.g. N=2 -> 3 views). Merge is last.
                # Grid: [1, 2], [M].
                views_to_layout.append(merge_view)
            
            # Build 2-column grid using nested Splitters
            cols = 2
            rows = (len(views_to_layout) + cols - 1) // cols
            
            for r in range(rows):
                h_splitter = QSplitter(Qt.Orientation.Horizontal)
                h_splitter.setHandleWidth(4)
                
                # Check if this is the last row and it has only 1 item (Center case)
                items_in_row = min(cols, len(views_to_layout) - r * cols)
                
                if r == rows - 1 and items_in_row == 1:
                    # Centered Single Item
                    # We can simulate centering by adding spacers
                    # [Spacer 1*] [Item 2*] [Spacer 1*]
                    idx = r * cols
                    view = views_to_layout[idx]
                    
                    spacer_l = QWidget()
                    spacer_r = QWidget()
                    # Make spacers transparent/invisible but take space
                    spacer_l.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
                    spacer_r.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
                    
                    h_splitter.addWidget(spacer_l)
                    h_splitter.addWidget(view)
                    h_splitter.addWidget(spacer_r)
                    view.show()
                    
                    # Set stretch factors to center (1:2:1 ratio usually works well for visual centering)
                    # Use setSizes to enforce the ratio initially
                    h_splitter.setStretchFactor(0, 1)
                    h_splitter.setStretchFactor(1, 2) # Give view more space
                    h_splitter.setStretchFactor(2, 1)
                    
                    # Enforce initial size ratio
                    h_splitter.setSizes([100, 200, 100])
                    
                    # Disable collapsing for spacers to prevent weird behavior
                    h_splitter.setCollapsible(0, False)
                    h_splitter.setCollapsible(2, False)
                    
                else:
                    # Normal Row
                    for c in range(cols):
                        idx = r * cols + c
                        if idx < len(views_to_layout):
                            view = views_to_layout[idx]
                            h_splitter.addWidget(view)
                            view.show()
                        else:
                            # Should not happen if logic is correct for 2 cols
                            pass
                    
                    # Even stretch
                    for i in range(h_splitter.count()):
                        h_splitter.setStretchFactor(i, 1)
                
                v_splitter.addWidget(h_splitter)
                v_splitter.setStretchFactor(r, 1) # Even vertical stretch
        
        container_layout.addWidget(v_splitter)
        self.main_splitter = v_splitter 

    def set_tool(self, tool):
        """Propagate tool to all views."""
        # Clear annotation mode when a tool is selected
        for view in self.views.values():
            view.set_annotation_mode('none')

        # Disconnect previous tool if exists
        if hasattr(self, 'current_tool') and self.current_tool:
            try:
                # Use context safety for disconnection
                self.current_tool.preview_changed.disconnect(self.update_all_previews)
            except (RuntimeError, Exception):
                pass
                
        self.current_tool = tool # Store for state persistence (e.g., when reloading samples)
        
        # Propagate to views
        for view in self.views.values():
            view.set_active_tool(tool)
            
        if tool:
            # If a tool is active, connect its preview signal
            # Use UniqueConnection to prevent duplicates
            try:
                self.current_tool.preview_changed.connect(self.update_all_previews, Qt.ConnectionType.UniqueConnection)
            except Exception as e:
                # print(f"Error connecting tool preview: {e}")
                pass

    def set_annotation_mode(self, mode):
        """Sets the annotation mode for all views."""
        self.annotation_mode = mode
        for view in self.views.values():
            view.set_annotation_mode(mode)
            
    def update_all_previews(self):
        """Force update of all views (e.g. during tool usage)."""
        for view in self.views.values():
            view.scene().update()

    def update_scale_bar(self, settings):
        """Propagate scale bar settings to all views."""
        for view in self.views.values():
            view.update_scale_bar(settings)

    def set_annotations(self, annotations):
        """Propagate annotations to all views."""
        for view in self.views.values():
            view.set_annotations(annotations)
            
            # Note: We do NOT disconnect annotation_modified here because it breaks 
            # the connection established in connect_signals. 
            # set_annotations just updates the visual items, the view's signal 
            # should remain connected to the main window.

    def sync_annotation(self, annotation):
        """Updates a single annotation across all views with batch rendering optimization."""
        t_start = time.time()
        # Update all views without immediate repaint
        for view in self.views.values():
            view.update_single_annotation(annotation, repaint=False)
        
        # Trigger a single update for each view after all processing is done
        for view in self.views.values():
            view.scene().update()
        
        dt = time.time() - t_start
        if getattr(annotation, 'is_dragging', False):
            Logger.debug(f"[Performance] Multi-channel sync for {annotation.id} took {dt*1000:.2f}ms (Batch Rendered)")

    def connect_signals(self, main_window):
        """Connect view signals to main window slots."""
        for view in self.views.values():
             view.file_dropped.connect(main_window.import_file)
             view.view_clicked.connect(main_window.set_active_channel)
             view.annotation_created.connect(main_window.on_annotation_created)
             view.annotation_modified.connect(main_window.on_annotation_modified)
