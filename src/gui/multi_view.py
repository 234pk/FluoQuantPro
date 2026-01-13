import time
import os
from PySide6.QtWidgets import (QWidget, QVBoxLayout, 
                               QSplitter, QLabel, QApplication, QPushButton, QFrame, QMenu,
                               QListWidget, QListWidgetItem)
from PySide6.QtCore import Qt, Signal, QSettings, QRectF, QSize, QPointF, QTimer
from PySide6.QtGui import QPalette
import numpy as np
from typing import Dict

from src.core.data_model import Session
from src.core.renderer import Renderer
from src.core.logger import Logger
from src.gui.canvas_view import CanvasView
from src.gui.sync_manager import SyncManager
from src.gui.icon_manager import get_icon
from src.gui.empty_state import EmptyStateWidget
from src.core.language_manager import tr

class MultiViewWidget(QWidget):
    """
    Manages multiple CanvasView instances in a Grid Layout.
    Handles view synchronization and content rendering.
    """
    channel_file_dropped = Signal(str, int) # file_path, channel_index
    channel_selected = Signal(int) # channel_index
    mouse_moved_on_view = Signal(int, int, int) # x, y, channel_index (-1 for merge)
    tool_cancelled = Signal() # Propagated from CanvasView
    zoom_changed = Signal(float) # Emits current zoom level (scale)
    
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
        self.sync_manager = SyncManager()
        self.settings = QSettings("FluoQuantPro", "Settings")
        
        # Cache for rendered channel images to speed up compositing and targeted updates
        self._channel_images_cache = {}
        self._last_target_shape = None
        self._last_original_shape = None
        
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
        self.empty_state.import_requested.connect(self.import_requested.emit)
        self.empty_state.new_project_requested.connect(self.new_project_requested.emit)
        self.empty_state.open_project_requested.connect(self.open_project_requested.emit)
        self.empty_state.open_recent_requested.connect(self.open_recent_requested.emit)
        self.empty_state.import_folder_requested.connect(self.import_folder_requested.emit)
        self.empty_state.import_merge_requested.connect(self.import_merge_requested.emit)
        
        self.main_layout.addWidget(self.empty_state)
        
        # Loading Overlay (initially hidden)
        self.loading_overlay = QLabel(tr("Loading..."), self)
        self.loading_overlay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.loading_overlay.setProperty("role", "overlay")
        self.loading_overlay.hide()
        
        # Container for views
        self.view_container = QWidget()
        self.main_layout.addWidget(self.view_container)
        
        # Initial State
        self.update_view_state()
        
        # Resize Debounce Timer
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(100) # 100ms debounce
        self._resize_timer.timeout.connect(self._on_resize_finished)

    def show_loading(self, message=None):
        """Shows the loading overlay."""
        if message is None:
            message = tr("Loading...")
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
        # Debounce fit_views to prevent flickering during resize
        self._resize_timer.start()

    def _on_resize_finished(self):
        """Called when resize interaction stops."""
        # Only auto-fit if there are views
        if self.views:
            # USER REQUEST: Do not auto-fit if the user is likely zoomed in.
            # We only auto-fit if the current zoom is close to 1.0 (or whatever the fit scale was)
            # or if it's the first time.
            # For now, let's check if the active view is zoomed.
            active_view = self.get_active_view()
            if active_view:
                # If the transform is not identity, the user might have panned/zoomed.
                # However, fitInView also changes the transform.
                # A better check: only fit if we were already in "fit" mode.
                # But we don't have a "fit mode" flag.
                
                # Let's just skip fit_views on resize if the user is currently using a tool
                # or if the resize was small.
                pass

            # Actually, the best behavior for professional tools is to NOT auto-fit on every resize
            # unless specifically requested or if it's the initial load.
            # However, to keep existing behavior for window maximize/restore, we can check force=False.
            self.fit_views(force=False)

    def update_view_state(self):
        """Updates visibility of empty state vs view container."""
        if not self.session.channels:
            self.empty_state._load_recent_projects() # Refresh recent list when shown
            self.empty_state.show()
            # Relax height constraint - let EmptyStateWidget manage its own internal layout
            self.empty_state.setMaximumHeight(16777215)
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
        # Always create Merge view to ensure availability
        if True:
            merge_view = CanvasView(view_id="Merge", session=self.session)
            merge_view.set_roi_manager(self.session.roi_manager)
            merge_view.set_label("Merge")
            merge_view.active_channel_index = -1 # Explicitly set for tools
            merge_view.mouse_moved.connect(lambda x, y: self.on_mouse_moved(x, y, -1))
            merge_view.view_clicked.connect(self.on_view_clicked) # Add click connection for selection
            merge_view.tool_cancelled.connect(self.tool_cancelled.emit)
            merge_view.scale_bar_moved.connect(self.on_scale_bar_moved)
            merge_view.zoom_changed.connect(self.on_view_zoom_changed)
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
            view.tool_cancelled.connect(self.tool_cancelled.emit)
            view.scale_bar_moved.connect(self.on_scale_bar_moved)
            view.zoom_changed.connect(self.on_view_zoom_changed)
            
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

    def on_view_zoom_changed(self, scale_x, scale_y, anchor):
        """Relay zoom change from a view."""
        # Assuming uniform scaling, use scale_x
        self.zoom_changed.emit(scale_x)

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


    def fit_views(self, force=True):
        """
        Fits all views to their content.
        If force=False, only fits if the view is already close to fit-to-screen scale.
        """
        for view in self.views.values():
            if not force:
                # Check if we are already zoomed in significantly
                # We calculate what the fit-to-screen scale WOULD be
                rect = view.scene().sceneRect()
                if rect.width() <= 0 or rect.height() <= 0:
                    continue
                
                # Get viewport size
                v_rect = view.viewport().rect()
                if v_rect.width() <= 0 or v_rect.height() <= 0:
                    continue
                    
                target_scale = min(v_rect.width() / rect.width(), v_rect.height() / rect.height())
                current_scale = view.transform().m11()
                
                # If current scale is more than 5% different from fit scale, 
                # we assume the user has manually zoomed and we should NOT disrupt them.
                if abs(current_scale - target_scale) / target_scale > 0.05:
                    # print(f"[MultiView] Skipping auto-fit for {view.view_id} (Zoomed: {current_scale:.2f} vs Fit: {target_scale:.2f})")
                    continue
            
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
                 for view in self.views.values():
                      view.update_image(None)
                 self._channel_images_cache.clear()
                 return

            self._last_original_shape = original_shape
            h, w = original_shape
            target_shape = None
            
            # Determine downsampling limit based on user settings
            quality = self.settings.value("display/quality_key", "balanced")
            if quality == "performance":
                 max_dim = 1024 # Standard 1024p
            elif quality == "balanced":
                 max_dim = 2560 # 2.5K Resolution
            elif quality == "high":
                 max_dim = 32768 # System Limit for QPixmap (Effectively Full Res)
            else:
                 # Fallback for old settings
                 quality_text = self.settings.value("display/quality", "Balanced (Recommended)")
                 if "Performance" in quality_text:
                     max_dim = 1024
                 elif "High" in quality_text:
                     max_dim = 32768
                 else:
                     max_dim = 2560
                 
            if preview:
                 # Force smaller preview regardless of setting
                 from src.core.performance_monitor import PerformanceMonitor
                 max_dim = PerformanceMonitor.instance().get_preview_limit(min(max_dim, 1024))
                 
            long_side = max(h, w)
            if long_side > max_dim:
                 scale = float(max_dim) / long_side
                 new_h = int(h * scale)
                 new_w = int(w * scale)
                 target_shape = (new_h, new_w)
            
            self._last_target_shape = target_shape
            
            # 2. Render each channel's display image (Raw -> RGB)
            self._channel_images_cache.clear()
            for i, ch in enumerate(self.session.channels):
                # Always render if we have data, even if hidden (for Merge)
                if ch.raw_data is not None:
                    img = Renderer.render_channel(ch, target_shape=target_shape)
                    self._channel_images_cache[i] = img
            
            # 3. Update Channel Views
            for i, img in self._channel_images_cache.items():
                view_id = f"Ch{i+1}"
                if view_id in self.views:
                    display_img = img
                    if img.dtype == np.float32 and img.max() <= 1.0:
                         display_img = (img * 255).astype(np.uint8)
                    
                    self.views[view_id].update_image(display_img, scene_rect=QRectF(0.0, 0.0, float(w), float(h)))

            # 4. Update Merge View
            self._update_merge_view(w, h, target_shape)

        except Exception as e:
            print(f"Error in render_all: {e}")
            import traceback
            traceback.print_exc()
        
        finally:
            self.sync_manager.set_enabled(True)
            print(f"[MultiView] render_all finished ({time.time() - t_render_start:.4f}s)")

    def render_single_channel(self, channel_index, preview=False):
        """
        Optimized: Renders only one channel and updates Merge view.
        Uses cached images for other channels to save time.
        """
        if not self.session.channels or channel_index < 0 or channel_index >= len(self.session.channels):
            return

        t_start = time.time()
        ch = self.session.channels[channel_index]
        
        # If we don't have baseline info, do a full render
        if self._last_original_shape is None:
            self.render_all(preview=preview)
            return

        h, w = self._last_original_shape
        target_shape = self._last_target_shape
        
        # If preview mode requested but last wasn't preview, we might need to adjust target_shape
        # but usually display adjustments stay in the same mode.
        
        try:
            # 1. Render just this channel
            if ch.raw_data is not None:
                img = Renderer.render_channel(ch, target_shape=target_shape)
                self._channel_images_cache[channel_index] = img
                
                # 2. Update specific view
                view_id = f"Ch{channel_index+1}"
                if view_id in self.views:
                    display_img = img
                    if img.dtype == np.float32 and img.max() <= 1.0:
                         display_img = (img * 255).astype(np.uint8)
                    self.views[view_id].update_image(display_img, scene_rect=QRectF(0.0, 0.0, float(w), float(h)))

            # 3. Update Merge View
            self._update_merge_view(w, h, target_shape)

        except Exception as e:
            print(f"Error in render_single_channel: {e}")
            self.render_all(preview=preview)
        
        finally:
            print(f"[MultiView] render_single_channel({channel_index}) finished ({time.time() - t_start:.4f}s)")

    def _update_merge_view(self, w, h, target_shape):
        """Internal helper to re-composite the merge view from cached channel images."""
        if "Merge" not in self.views:
            return

        if not self._channel_images_cache:
            self.views["Merge"].update_image(None)
            return

        composite = None
        for i, ch in enumerate(self.session.channels):
            is_visible = getattr(ch.display_settings, 'visible', True)
            
            if is_visible and i in self._channel_images_cache:
                img = self._channel_images_cache[i]
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
            th, tw = target_shape if target_shape else (h, w)
            black = np.zeros((th, tw, 3), dtype=np.uint8)
            self.views["Merge"].update_image(black, scene_rect=QRectF(0.0, 0.0, float(w), float(h)))

    def update_view(self, channel_index):
        """
        Updates a specific channel view (and Merge view).
        Used for targeted refreshes (e.g. drag-drop).
        """
        self.render_single_channel(channel_index)

    def fit_to_width(self):
        """Fits all active views to width."""
        for view in self.views.values():
            if view.isVisible() and view.full_res_pixmap:
                view.fit_to_width()

    def fit_to_height(self):
        """Fits all active views to height."""
        for view in self.views.values():
            if view.isVisible() and view.full_res_pixmap:
                view.fit_to_height()

    def setup_layout(self):
        """Updates the grid layout based on number of channels."""
        # 1. Remove and delete existing splitter
        if hasattr(self, 'main_splitter') and self.main_splitter:
            self.main_splitter.hide()
            self.main_splitter.setParent(None)
            self.main_splitter.deleteLater()
            self.main_splitter = None
            
        # 2. Clear current layout of view_container
        if self.view_container.layout():
            layout = self.view_container.layout()
            while layout.count():
                item = layout.takeAt(0)
                widget = item.widget()
                if widget:
                    widget.hide()
                    widget.setParent(None)
                    widget.deleteLater()
        
        # Check Single Channel Mode
        is_single_mode = getattr(self.session, 'is_single_channel_mode', False)
        
        # print(f"[DEBUG] setup_layout: is_single_mode={is_single_mode}")

        if is_single_mode:
            if not self.view_container.layout():
                layout = QVBoxLayout(self.view_container)
                layout.setContentsMargins(0, 0, 0, 0)
            else:
                layout = self.view_container.layout()
            
            target_view = None
            
            # Default to Merge if enabled or no channel found
            target_view = self.views.get("Merge")
            
            # Final Fallback if Merge is missing too
            if target_view is None and self.views:
                target_view = list(self.views.values())[0]
                
            if target_view:
                print(f"[DEBUG] Single Mode: Showing {target_view.view_id}")
                layout.addWidget(target_view)
                target_view.show()
                # Ensure other views are hidden
                for view in self.views.values():
                    if view != target_view:
                        view.hide()
            return
            
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
        
        if num_channels == 1:
            if merge_view:
                # 1 Channel + 1 Merge -> Vertical Stack (Merge on bottom)
                v_splitter.addWidget(channel_views[0])
                v_splitter.addWidget(merge_view)
                channel_views[0].show()
                merge_view.show()
                v_splitter.setStretchFactor(0, 1)
                v_splitter.setStretchFactor(1, 1)
            else:
                # 1 Channel Only
                v_splitter.addWidget(channel_views[0])
                channel_views[0].show()
            
        else:
            # 2+ Channels
            # Prepare ordered list of views
            views_to_layout = list(channel_views)
            
            if merge_view:
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
            else:
                # No Merge view, just layout channels in grid
                pass
            
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
            
    def select_annotation(self, ann_id):
        """Selects the specified annotation in all views."""
        for view in self.views.values():
            view.select_annotation(ann_id)

    def update_all_previews(self):
        """Force update of all views (e.g. during tool usage)."""
        for view in self.views.values():
            view.scene().update()

    def _on_roi_updated(self, roi_or_id):
        """Propagate ROI update to all views."""
        for view in self.views.values():
            view._on_roi_updated(roi_or_id)

    def update_scale_bar(self, settings):
        """Propagate scale bar settings to all views."""
        for view in self.views.values():
            view.update_scale_bar(settings)
