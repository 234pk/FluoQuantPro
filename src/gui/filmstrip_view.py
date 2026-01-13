import time
from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QScrollArea, 
                                QLabel, QFrame, QSizePolicy, QSplitter)
from PySide6.QtCore import Qt, Signal, QRectF, QPointF
import numpy as np
from typing import Dict, List

from src.core.data_model import Session
from src.core.renderer import Renderer
from src.gui.canvas_view import CanvasView
from src.gui.sync_manager import SyncManager
from src.gui.empty_state import EmptyStateWidget
from src.core.language_manager import tr

class FilmstripWidget(QWidget):
    """
    Displays images in a filmstrip layout: 
    A large main view on top, and a horizontal scrollable thumbnail bar at the bottom.
    """
    channel_selected = Signal(int) # channel_index (-1 for merge)
    channel_file_dropped = Signal(str, int)
    mouse_moved_on_view = Signal(int, int, int) # x, y, channel_index
    tool_cancelled = Signal()
    zoom_changed = Signal(float)
    
    # Relay import signals from EmptyState
    import_requested = Signal()
    new_project_requested = Signal()
    open_project_requested = Signal()
    open_recent_requested = Signal(str)
    import_folder_requested = Signal()
    import_merge_requested = Signal()

    def __init__(self, session: Session, parent=None):
        super().__init__(parent)
        self.session = session
        self.views: Dict[str, CanvasView] = {}
        self.main_view = None
        self.sync_manager = SyncManager()
        self._channel_images_cache = {}
        self._last_original_shape = None
        self._last_target_shape = None
        self.active_channel_id = "Merge" # Default view in main view
        self.current_tool = None
        self.annotation_mode = 'none'

        self.init_ui()

    def init_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # Empty State Widget
        self.empty_state = EmptyStateWidget(self)
        self.empty_state.import_requested.connect(self.import_requested.emit)
        self.empty_state.new_project_requested.connect(self.new_project_requested.emit)
        self.empty_state.open_project_requested.connect(self.open_project_requested.emit)
        self.empty_state.open_recent_requested.connect(self.open_recent_requested.emit)
        self.empty_state.import_folder_requested.connect(self.import_folder_requested.emit)
        self.empty_state.import_merge_requested.connect(self.import_merge_requested.emit)
        self.main_layout.addWidget(self.empty_state)

        # Use a Splitter for movable divider
        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: #333;
                height: 2px;
            }
            QSplitter::handle:hover {
                background-color: #007acc;
            }
        """)
        
        # 1. Main View (Top)
        self.main_view = CanvasView(view_id="Main", session=self.session)
        self.main_view.set_roi_manager(self.session.roi_manager)
        self.main_view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.main_view.set_label(tr("Merge"))
        self.main_view.active_channel_index = -1
        # Connect signals from main view to propagate to MainWindow
        self.main_view.zoom_changed.connect(self.on_main_zoom_changed)
        self.main_view.mouse_moved.connect(self._on_main_mouse_moved)
        self.main_view.tool_cancelled.connect(self.tool_cancelled.emit)
        self.main_view.file_dropped.connect(lambda f, idx: self.channel_file_dropped.emit(f, self.main_view.active_channel_index))
        
        self.splitter.addWidget(self.main_view)

        # 2. Thumbnail Bar (Bottom scroll area)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignCenter) # Center content
        self.scroll_area.setMinimumHeight(100)
        self.scroll_area.setMaximumHeight(400) # Reasonable max height for thumb bar

        self.container = QWidget()
        self.container.setObjectName("filmstrip_container")
        self.container.setStyleSheet("""
            QWidget#filmstrip_container {
                background-color: #0f0f0f;
                border-top: 1px solid #222;
            }
        """)
        self.filmstrip_layout = QHBoxLayout(self.container)
        self.filmstrip_layout.setContentsMargins(15, 8, 15, 8)
        self.filmstrip_layout.setSpacing(15)
        self.filmstrip_layout.setAlignment(Qt.AlignmentFlag.AlignCenter) # USER REQUEST: Center thumbnails

        # Drop hint overlay
        self.drop_hint_label = QLabel(tr("Drop images here to add channels"), self.container)
        self.drop_hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.drop_hint_label.setStyleSheet("""
            color: #444;
            font-style: italic;
            font-size: 11px;
            background: transparent;
        """)
        self.drop_hint_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        
        self.scroll_area.setWidget(self.container)
        self.splitter.addWidget(self.scroll_area)
        
        # Connect splitter move signal to update thumbnail sizes
        self.splitter.splitterMoved.connect(lambda: self.update_thumbnail_sizes())
        
        # Initial splitter sizes
        self.splitter.setSizes([800, 180])
        
        self.main_layout.addWidget(self.splitter)
        
        # Initial State
        self.update_view_state()

    def update_view_state(self):
        """Updates visibility of empty state vs view container."""
        if not self.session.channels:
            self.empty_state._load_recent_projects() # Refresh recent list when shown
            self.empty_state.show()
            self.splitter.hide()
        else:
            self.empty_state.hide()
            self.splitter.show()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_thumbnail_sizes()
        # Position drop hint in the middle of the container
        if hasattr(self, 'drop_hint_label'):
            self.drop_hint_label.setGeometry(self.container.rect())

    def update_thumbnail_sizes(self):
        """Adjusts thumbnail sizes to fit the current scroll area height while staying square."""
        if not self.views:
            # Show drop hint if empty
            if hasattr(self, 'drop_hint_label'):
                self.drop_hint_label.show()
            return
            
        # Hide drop hint if we have content
        if hasattr(self, 'drop_hint_label'):
            self.drop_hint_label.hide()
            
        # Get available height in scroll area (minus margins)
        # We use a slightly smaller value than the scroll area height to avoid vertical scrollbars
        h = self.scroll_area.viewport().height() - 20 
        if h < 60: h = 60 # Minimum reasonable size
        
        for thumb in self.views.values():
            thumb.setFixedSize(h, h)

    def wheelEvent(self, event):
        """
        USER REQUEST: Handle mouse wheel for both horizontal scrolling and selection switching.
        - Non-image area (background): Scroll the thumbnail bar horizontally.
        - Over a thumbnail: Switch to the previous/next channel.
        """
        # Map to the container where thumbnails are located
        pos_in_container = self.container.mapFrom(self, event.position().toPoint())
        
        # Check if the event is within the scroll area's visible viewport
        viewport_rect = self.scroll_area.viewport().rect()
        pos_in_viewport = self.scroll_area.viewport().mapFrom(self, event.position().toPoint())
        
        if viewport_rect.contains(pos_in_viewport):
            delta = event.angleDelta().y()
            if delta == 0:
                delta = event.angleDelta().x()
                
            # Check if mouse is over a thumbnail (CanvasView)
            child = self.container.childAt(pos_in_container)
            # Traverse up to find if we are over a CanvasView or its viewport
            is_over_thumbnail = False
            target_thumb = None
            while child:
                if isinstance(child, CanvasView):
                    target_thumb = child
                    is_over_thumbnail = True
                    break
                if hasattr(child, 'parentWidget'):
                    child = child.parentWidget()
                else:
                    break
            
            if is_over_thumbnail and target_thumb:
                # 1. Over a thumbnail: Switch channel selection
                all_ids = list(self.views.keys())
                if self.active_channel_id in all_ids:
                    curr_pos = all_ids.index(self.active_channel_id)
                    if delta > 0: # Scroll up -> Previous
                        new_pos = max(0, curr_pos - 1)
                    else: # Scroll down -> Next
                        new_pos = min(len(all_ids) - 1, curr_pos + 1)
                    
                    if new_pos != curr_pos:
                        target_id = all_ids[new_pos]
                        thumb = self.views[target_id]
                        # Directly call select_channel to update UI and state
                        self.on_thumbnail_clicked(target_id, thumb.active_channel_index)
                
                event.accept()
                return
            else:
                # 2. In non-image area: Scroll the bar horizontally
                bar = self.scroll_area.horizontalScrollBar()
                if bar:
                    # Standard scroll speed adjustment
                    bar.setValue(bar.value() - delta)
                    event.accept()
                    return
        
        super().wheelEvent(event)

    def initialize_views(self):
        """Creates and adds thumbnails for all channels and merge."""
        # Clear existing thumbnails
        for view in self.views.values():
            self.filmstrip_layout.removeWidget(view)
            view.deleteLater()
        self.views.clear()
        
        # Reset sync manager - Only sync the main view (to propagate signals to MainWindow)
        # Note: We don't add thumbnails to sync_manager anymore to keep them at full-view
        self.sync_manager = SyncManager()
        self.sync_manager.add_view(self.main_view)

        if not self.session.channels:
            return

        # 1. Create Channel Thumbnails
        for i, ch in enumerate(self.session.channels):
            view_id = f"Ch{i+1}"
            thumb = self._create_thumbnail(view_id, ch.name, i)
            self.views[view_id] = thumb
            self.filmstrip_layout.addWidget(thumb)

        # 2. Create Merge Thumbnail (Skip if single channel mode)
        if not getattr(self.session, 'is_single_channel_mode', False):
            merge_thumb = self._create_thumbnail("Merge", tr("Merge"), -1)
            self.views["Merge"] = merge_thumb
            self.filmstrip_layout.addWidget(merge_thumb)
        else:
            # If single channel mode, ensure active channel is the first one if it was Merge
            if self.active_channel_id == "Merge":
                self.active_channel_id = "Ch1"

        # Connect synchronization
        self.sync_manager.set_enabled(True)
        
        # --- USER REQUEST: Restore active tool and annotation mode to new views ---
        if self.current_tool:
            self.main_view.set_active_tool(self.current_tool)
            for thumb in self.views.values():
                thumb.set_active_tool(self.current_tool)
        
        if self.annotation_mode != 'none':
            self.main_view.set_annotation_mode(self.annotation_mode)
            for thumb in self.views.values():
                thumb.set_annotation_mode(self.annotation_mode)

        # Update main view state
        self.select_channel(-1 if self.active_channel_id == "Merge" else int(self.active_channel_id[2:])-1)
        
        # Ensure sizes are correct
        from PySide6.QtCore import QTimer
        QTimer.singleShot(50, self.update_thumbnail_sizes)

        # Update visibility of empty state
        self.update_view_state()

    def _create_thumbnail(self, view_id: str, label: str, channel_index: int) -> CanvasView:
        view = CanvasView(view_id=view_id, session=self.session)
        view.set_roi_manager(self.session.roi_manager)
        view._wheel_enabled = False # USER REQUEST: Disable zoom on thumbnails to allow filmstrip scrolling
        view.set_label(label)
        view.active_channel_index = channel_index
        
        # Policy: Follow height, keep square if possible
        view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        # Aggressively remove border and background for a cleaner look
        view.setFrameShape(QFrame.Shape.NoFrame)
        view.setLineWidth(0)
        view.setStyleSheet("background-color: transparent; border: none;")
        
        # Disable scrollbars for thumbnails to keep it clean
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        # Connect signals
        view.view_clicked.connect(self.on_thumbnail_clicked)
        view.tool_cancelled.connect(self.tool_cancelled.emit)
        view.file_dropped.connect(self.channel_file_dropped.emit)
        
        return view

    def on_thumbnail_clicked(self, view_id: str, channel_index: int):
        self.select_channel(channel_index)
        self.channel_selected.emit(channel_index)

    def on_main_zoom_changed(self, scale_x, scale_y, focus_pos):
        self.zoom_changed.emit(scale_x)

    def _on_main_mouse_moved(self, x, y):
        # Determine channel index for status bar
        idx = -1 if self.active_channel_id == "Merge" else int(self.active_channel_id[2:])-1
        self.mouse_moved_on_view.emit(x, y, idx)

    def select_channel(self, index: int):
        """Visually selects the thumbnail and updates the main view content reference."""
        view_id = "Merge" if index == -1 else f"Ch{index+1}"
        
        # USER REQUEST: Avoid redundant updates to prevent excessive redrawing
        if self.active_channel_id == view_id:
            return
            
        self.active_channel_id = view_id
        
        # Update selection highlight in thumbnails
        for vid, thumb in self.views.items():
            is_active = (vid == view_id)
            thumb.set_selected(is_active)
            if is_active:
                thumb.setStyleSheet("background-color: rgba(0, 122, 204, 0.15); border: 2px solid #007acc; border-radius: 4px;")
            else:
                thumb.setStyleSheet("background-color: transparent; border: none;")
        
        # Update main view properties to reflect current channel
        self.main_view.active_channel_index = index
        self.main_view.set_label(tr("Merge") if index == -1 else self.session.channels[index].name)
        
        # Trigger re-render of main view with correct channel
        self.render_main_view()
        
        # Scroll to ensure the selected thumbnail is visible
        if view_id in self.views:
            thumb = self.views[view_id]
            self.scroll_area.ensureWidgetVisible(thumb)

    def render_all(self, preview=False):
        """Renders all thumbnails and the main view."""
        if not self.session.channels:
            return

        # Get target shape from the first valid channel
        h, w = 0, 0
        for ch in self.session.channels:
            if ch.raw_data is not None:
                h, w = ch.raw_data.shape[:2]
                break
        
        if h == 0 or w == 0:
            return

        self._last_original_shape = (h, w)
        
        # Determine render quality for thumbnails (small)
        thumb_target_shape = (256, 256) # Small enough for thumbnails
        
        # Determine render quality for main view (large)
        max_dim = 2048 
        long_side = max(h, w)
        if long_side > max_dim:
            scale = float(max_dim) / long_side
            main_target_shape = (int(h * scale), int(w * scale))
        else:
            main_target_shape = (h, w)
        
        self._last_target_shape = main_target_shape
        self._channel_images_cache.clear()

        # 1. Render thumbnails and cache images
        for i, ch in enumerate(self.session.channels):
            if ch.raw_data is not None:
                # Render for thumbnail
                thumb_img = Renderer.render_channel(ch, target_shape=thumb_target_shape)
                
                view_id = f"Ch{i+1}"
                if view_id in self.views:
                    display_img = thumb_img
                    if thumb_img.dtype == np.float32 and thumb_img.max() <= 1.0:
                        display_img = (thumb_img * 255).astype(np.uint8)
                    view = self.views[view_id]
                    view.update_image(display_img, scene_rect=QRectF(0.0, 0.0, float(w), float(h)))
                    # Ensure thumbnail shows full image
                    view.fitInView(view.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
                
                # Render for main view (higher res) and cache for merge
                main_img = Renderer.render_channel(ch, target_shape=main_target_shape)
                self._channel_images_cache[i] = main_img

        # 2. Update Merge Thumbnail
        self._update_merge_thumbnail(w, h, thumb_target_shape)
        
        # 3. Update Main View
        self.render_main_view()

    def render_main_view(self):
        """Updates the image in the main view based on current active_channel_id."""
        if not self.main_view or not self._last_original_shape:
            return
            
        h, w = self._last_original_shape
        
        if self.active_channel_id == "Merge":
            # Composite from cache
            composite = None
            for i, ch in enumerate(self.session.channels):
                if getattr(ch.display_settings, 'visible', True) and i in self._channel_images_cache:
                    img = self._channel_images_cache[i]
                    if composite is None:
                        composite = img.astype(np.float32)
                    else:
                        composite += img.astype(np.float32)
            
            if composite is not None:
                np.clip(composite, 0.0, 1.0, out=composite)
                composite = (composite * 255).astype(np.uint8)
                self.main_view.update_image(composite, scene_rect=QRectF(0, 0, w, h))
            else:
                th, tw = self._last_target_shape if self._last_target_shape else (h, w)
                black = np.zeros((th, tw, 3), dtype=np.uint8)
                self.main_view.update_image(black, scene_rect=QRectF(0, 0, w, h))
        else:
            # Single channel
            try:
                ch_idx = int(self.active_channel_id[2:]) - 1
                if ch_idx in self._channel_images_cache:
                    img = self._channel_images_cache[ch_idx]
                    display_img = img
                    if img.dtype == np.float32 and img.max() <= 1.0:
                        display_img = (img * 255).astype(np.uint8)
                    self.main_view.update_image(display_img, scene_rect=QRectF(0, 0, w, h))
            except (ValueError, IndexError):
                pass

    def flash_channel(self, channel_index: int, duration_ms: int = 250):
        """Flashes the corresponding thumbnail for visual feedback."""
        if channel_index is None or channel_index < 0:
            # If it's merge (-1), flash the merge thumbnail
            view_id = "Merge"
        else:
            view_id = f"Ch{channel_index+1}"
            
        thumb = self.views.get(view_id)
        if thumb and hasattr(thumb, "start_flash"):
            thumb.start_flash(duration_ms)

    def fit_to_width(self):
        """Fits the main view and thumbnails to width."""
        if self.main_view:
            self.main_view.fit_to_width()
        for thumb in self.views.values():
            thumb.fit_to_width()

    def fit_to_height(self):
        """Fits the main view and thumbnails to height."""
        if self.main_view:
            self.main_view.fit_to_height()
        for thumb in self.views.values():
            thumb.fit_to_height()

    def update_view(self, channel_index: int):
        """Updates a specific channel thumbnail and the main view if it's showing that channel."""
        # For Filmstrip, we just re-render everything as it's easier and usually fast enough
        # since thumbnails are small and cached.
        self.render_all()

    def show_loading(self, message=None):
        """Shows a loading message (placeholder for consistent interface)."""
        # Filmstrip doesn't have a loading overlay yet, but we provide the method for consistency
        # In the future, we could implement a similar overlay as MultiViewWidget
        pass

    def hide_loading(self):
        """Hides the loading message."""
        pass

    def fit_views(self, force=True):
        """Fits the main view to its viewport."""
        if self.main_view:
            self.main_view.fitInView(self.main_view.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        # Thumbnails are already fitted by Renderer.render_channel and CanvasView.update_image with scene_rect
        for thumb in self.views.values():
            thumb.fitInView(thumb.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def update_scale_bar(self, settings):
        """Updates scale bar on all views."""
        if self.main_view:
            self.main_view.update_scale_bar(settings)
        for view in self.views.values():
            view.update_scale_bar(settings)

    def update_overlays(self):
        """Forces an overlay update on all views."""
        if self.main_view:
            self.main_view.update()
        for view in self.views.values():
            view.update()

    def set_tool(self, tool):
        """Sets the active interactive tool on the main view."""
        self.current_tool = tool
        if self.main_view:
            self.main_view.set_active_tool(tool)
        # We also propagate to thumbnails so they show the same cursor/state
        for thumb in self.views.values():
            thumb.set_active_tool(tool)

    def set_annotation_mode(self, mode):
        """Sets the annotation drawing mode on the main view."""
        self.annotation_mode = mode
        if self.main_view:
            self.main_view.set_annotation_mode(mode)
        # thumbnails don't usually need drawing mode, but keeping it consistent
        for thumb in self.views.values():
            thumb.set_annotation_mode(mode)

    def update_all_previews(self):
        """Force update of all views (e.g. during tool usage)."""
        if self.main_view:
            self.main_view.scene().update()
        for thumb in self.views.values():
            thumb.scene().update()

    def _on_roi_updated(self, roi_or_id):
        """Propagate ROI update to all views."""
        if self.main_view:
            self.main_view._on_roi_updated(roi_or_id)
        for thumb in self.views.values():
            thumb._on_roi_updated(roi_or_id)

    def _update_merge_thumbnail(self, w, h, target_shape):
        if "Merge" not in self.views:
            return

        # Simple merge for thumbnail (could be optimized)
        composite = None
        for i, ch in enumerate(self.session.channels):
            if getattr(ch.display_settings, 'visible', True) and ch.raw_data is not None:
                # Re-render at thumbnail size for the merge thumb
                img = Renderer.render_channel(ch, target_shape=target_shape)
                if composite is None:
                    composite = img.astype(np.float32)
                else:
                    composite += img.astype(np.float32)
        
        if composite is not None:
            np.clip(composite, 0.0, 1.0, out=composite)
            composite = (composite * 255).astype(np.uint8)
            view = self.views["Merge"]
            view.update_image(composite, scene_rect=QRectF(0.0, 0.0, float(w), float(h)))
            view.fitInView(view.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        else:
            black = np.zeros((target_shape[0], target_shape[1], 3), dtype=np.uint8)
            view = self.views["Merge"]
            view.update_image(black, scene_rect=QRectF(0.0, 0.0, float(w), float(h)))
            view.fitInView(view.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def select_annotation(self, ann_id):
        """Selects the specified annotation in all views."""
        self.main_view.select_annotation(ann_id)
        for thumb in self.views.values():
            thumb.select_annotation(ann_id)

    def get_active_view(self):
        return self.main_view
