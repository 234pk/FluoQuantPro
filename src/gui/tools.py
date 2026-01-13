from abc import abstractmethod
from enum import Enum
from typing import Optional, List, Dict, Tuple
from PySide6.QtCore import QPointF, Qt, QObject, Signal, QRectF
from PySide6.QtGui import QPainterPath, QColor, QPen
from PySide6.QtWidgets import QGraphicsPathItem, QGraphicsRectItem, QGraphicsEllipseItem, QGraphicsLineItem
from src.core.algorithms import magic_wand_2d, mask_to_qpath, mask_to_qpaths
from src.core.analysis import calculate_intensity_stats
from src.core.data_model import Session
from src.core.roi_model import ROI, create_smooth_path_from_points
import numpy as np
import time
from src.core.logger import Logger

class ToolContext(Enum):
    ROI = "roi"
    ANNOTATION = "annotation"

class AbstractTool(QObject):
    preview_changed = Signal()
    committed = Signal(str) # Emits a message about the committed action

    def __init__(self, session: Session):
        super().__init__()
        self.session = session
        self.active_channel_idx = -1 # The channel selected in the UI
        self.preview_item = None # Common preview item for all tools
        self.current_view = None # Store the view that started the interaction
        self.cursor_shape = Qt.CursorShape.CrossCursor # Default cursor

    def set_active_channel(self, index: int):
        """Sets the globally active channel from the UI."""
        self.active_channel_idx = index

    def _get_active_view(self):
        """Helper to get the active view from the session."""
        if hasattr(self.session, 'main_window') and self.session.main_window:
             try:
                 mw = self.session.main_window
                 if hasattr(mw, 'multi_view'):
                     return mw.multi_view.get_active_view()
             except:
                 pass
        return None

    def get_channel_color(self, channel_index: int) -> QColor:
        """Returns a color based on the channel index."""
        colors = [
            QColor(0, 191, 255, 200),   # Deep Sky Blue (DAPI)
            QColor(0, 255, 0, 200),     # Green (GFP)
            QColor(255, 165, 0, 200),   # Orange (CY3)
            QColor(255, 0, 255, 200),   # Magenta (CY5)
            QColor(255, 255, 0, 200),   # Yellow
            QColor(0, 255, 255, 200),   # Cyan
            QColor(255, 192, 203, 200), # Pink
        ]
        
        # Use the provided index, or fallback to UI active channel if -1
        idx = channel_index
        if idx < 0:
            idx = self.active_channel_idx
            
        if idx < 0:
            return QColor(255, 255, 0, 200) # Default Yellow fallback
            
        return colors[idx % len(colors)]

    def mouse_press(self, scene_pos: QPointF, channel_index: int, context: dict = None):
        """
        Base implementation for mouse press.
        Sets up the preview item and calls start_preview hook.
        """
        Logger.debug(f"[AbstractTool.mouse_press] ENTER: pos={scene_pos}")
        # 1. Setup Preview Item
        view = context.get('view') if context else None
        if not view:
            view = self._get_active_view()
        
        self.current_view = view
        
        if view and view.scene():
            self.preview_item = QGraphicsPathItem()
            # Default preview style: Dashed Yellow (High Visibility)
            self.preview_item.setPen(QPen(Qt.GlobalColor.yellow, 1, Qt.PenStyle.DashLine))
            self.preview_item.setZValue(9999) # Ensure it's on top of everything
            self.preview_item.setVisible(True)
            
            view.scene().addItem(self.preview_item)
            Logger.debug(f"[AbstractTool.mouse_press] Preview Item added to scene. Scene items count: {len(view.scene().items())}")
        
        # 2. Call hook
        self.start_preview(scene_pos, channel_index, context)
        Logger.debug("[AbstractTool.mouse_press] EXIT")

    def mouse_move(self, scene_pos: QPointF, modifiers=Qt.KeyboardModifier.NoModifier):
        """
        Base implementation for mouse move.
        Updates preview path and calls on_mouse_move hook.
        """
        # 1. Update State (Subclass logic)
        self.on_mouse_move(scene_pos, modifiers)
        
        # 2. Update Preview
        if self.preview_item:
            # Safe Update based on Item Type
            if isinstance(self.preview_item, QGraphicsPathItem):
                path = self.get_preview_path(scene_pos)
                if path:
                    self.preview_item.setPath(path)
            elif isinstance(self.preview_item, QGraphicsRectItem):
                # Handled in subclass on_mouse_move typically, but safe to ignore here if no generic logic
                pass 
            elif isinstance(self.preview_item, QGraphicsEllipseItem):
                pass
            
            # Force update
            view = self.current_view if self.current_view else self._get_active_view()
            if view and view.scene():
                view.scene().update()

    def mouse_release(self, scene_pos: QPointF, modifiers=Qt.KeyboardModifier.NoModifier):
        """
        Base implementation for mouse release.
        Cleans up preview and calls finish_shape hook.
        """
        try:
            self.finish_shape(scene_pos, modifiers)
        finally:
            if self.preview_item:
                if self.preview_item.scene():
                    self.preview_item.scene().removeItem(self.preview_item)
                self.preview_item = None

            self.current_view = None
    
    def mouse_double_click(self, scene_pos: QPointF):
        """Optional hook for double click events."""
        pass
        
    def mouse_right_click(self, scene_pos: QPointF):
        """Optional hook for right click events."""
        pass

    def deactivate(self):
        """
        USER REQUEST: Cleanup logic when tool is switched or cancelled.
        Ensures no preview items or temporary state remains.
        """
        Logger.debug(f"[{self.__class__.__name__}.deactivate] ENTER")
        try:
            if self.preview_item:
                if self.preview_item.scene():
                    self.preview_item.scene().removeItem(self.preview_item)
                self.preview_item = None
            
            # Subclasses can override this to clean up specific state
            self.on_deactivate()
        except Exception as e:
            Logger.error(f"[{self.__class__.__name__}.deactivate] Error: {e}")
        Logger.debug(f"[{self.__class__.__name__}.deactivate] EXIT")

    def on_deactivate(self):
        """Hook for subclasses to perform specific cleanup."""
        pass

    # --- Hooks for Subclasses ---
    def start_preview(self, scene_pos: QPointF, channel_index: int, context: dict = None):
        """Hook called on mouse press. Initialize state here."""
        pass

    def on_mouse_move(self, scene_pos: QPointF, modifiers):
        """Hook called on mouse move. Update state here."""
        pass

    def get_preview_path(self, scene_pos: QPointF) -> QPainterPath:
        """Return the path to be drawn by the preview item."""
        return None

    def finish_shape(self, scene_pos: QPointF, modifiers):
        """Hook called on mouse release. Finalize/Create shape here."""
        pass

class DrawingTool(AbstractTool):
    """
    Intermediate layer for tools that draw geometric shapes (Rect, Ellipse, Line).
    Manages common preview attributes and item creation.
    """
    def __init__(self, session: Session):
        super().__init__(session)
        self.color = Qt.GlobalColor.yellow
        self.line_width = 2
        self.z_value = 9999

    def create_preview_item(self):
        """Factory method to create and configure the preview item."""
        item = self._create_specific_item()
        # Common configuration
        pen = QPen(self.color, self.line_width, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        item.setPen(pen)
        item.setZValue(self.z_value)
        item.setVisible(True) # Ensure visibility
        
        # === 新增：体检日志 ===
        Logger.debug(f"[DrawingTool] Preview Item Created: Type={type(item).__name__}, Color={item.pen().color().name()}, Width={item.pen().width()}, Z={item.zValue()}")
        return item

    @abstractmethod
    def _create_specific_item(self):
        """Abstract method to create the specific QGraphicsItem (Rect, Ellipse, etc)."""
        raise NotImplementedError

    def mouse_press(self, scene_pos: QPointF, channel_index: int, context: dict = None):
        """
        Override AbstractTool.mouse_press to use the factory method.
        """
        Logger.debug(f"[DrawingTool.mouse_press] ENTER: pos={scene_pos}")
        # 1. Setup Preview Item using Factory
        view = context.get('view') if context else None
        if not view:
            view = self._get_active_view()
            
        self.current_view = view
        
        if view and view.scene():
            # Ensure we don't have a stale item (though release usually clears it)
            if self.preview_item:
                if self.preview_item.scene():
                    self.preview_item.scene().removeItem(self.preview_item)
                self.preview_item = None

            self.preview_item = self.create_preview_item()
            Logger.debug(f"[DrawingTool.mouse_press] Created preview item: {type(self.preview_item).__name__} in view {view}")
            
            view.scene().addItem(self.preview_item)
            Logger.debug(f"[DrawingTool.mouse_press] Preview Item added to scene. Scene items count: {len(view.scene().items())}")
        
        # 2. Call hook
        self.start_preview(scene_pos, channel_index, context)
        Logger.debug("[DrawingTool.mouse_press] EXIT")

class MagicWandTool(AbstractTool):
    tolerance_changed = Signal(float) # Signal to update UI feedback

    def __init__(self, session: Session):
        super().__init__(session)
        self.base_tolerance = 100.0 # Default base tolerance
        self.current_tolerance = 100.0
        self.smoothing = 5.0
        self.relative = False
        self.keep_largest = False
        self.split_regions = False
        self.convert_to_polygon = False # New: Convert to polygon on release
        self.contour_smoothing = True # USER REQUEST: Smooth contour output
        
        # State for interactive dragging
        self.is_dragging = False
        self.start_pos = None
        self.seed_pos = None
        self.current_mask = None
        self.current_path = None

    def mouse_press(self, scene_pos: QPointF, channel_index: int, context: dict = None):
        """
        Initial click to start selection.
        """
        Logger.info(f"[MagicWandTool] mouse_press at {scene_pos}, channel_index={channel_index}")
        
        # --- FIX: Ensure Preview Item ---
        view = context.get('view') if context else None
        if not view:
            view = self._get_active_view()
            
        self.current_view = view
        
        if view and view.scene():
             if self.preview_item is None:
                 self.preview_item = QGraphicsPathItem()
                 self.preview_item.setPen(QPen(Qt.GlobalColor.yellow, 1, Qt.PenStyle.DashLine))
                 self.preview_item.setZValue(9999)
                 self.preview_item.setVisible(True)
                 view.scene().addItem(self.preview_item)
        # --------------------------------

        # 1. Determine target channel index
        effective_idx = channel_index
        if effective_idx < 0:
            effective_idx = self.active_channel_idx
            
        # 2. Get the target data and scale
        # If context is provided, we can run on downsampled data for performance
        display_data = context.get('display_data') if context else None
        display_scale = context.get('display_scale', 1.0) if context else 1.0
        
        # 3. Convert coordinates to integer pixel indices
        # FIX: Map scene_pos to image local coordinates to avoid offsets
        image_pos = scene_pos
        if view and hasattr(view, 'get_image_coordinates'):
            image_pos = view.get_image_coordinates(scene_pos)
            Logger.debug(f"[MagicWandTool] Mapped: Scene({scene_pos.x():.1f}, {scene_pos.y():.1f}) -> Image({image_pos.x():.1f}, {image_pos.y():.1f})")

        if display_data is not None:
            # We are running on downsampled data
            # map image_pos (full-res) to display_pos (downsampled)
            x, y = int(image_pos.x() * display_scale), int(image_pos.y() * display_scale)
            work_data = display_data
            Logger.debug(f"[MagicWandTool] Using Downsampled Data ({work_data.shape}) at ({x}, {y})")
        else:
            # Fallback to full-res raw data
            channel = self.session.get_channel(effective_idx)
            if not channel:
                Logger.warning(f"[MagicWandTool] No channel at index {effective_idx}")
                return
            
            if channel.raw_data is None:
                Logger.error(f"[MagicWandTool] Channel {effective_idx} raw_data is None")
                return

            x, y = int(image_pos.x()), int(image_pos.y())
            work_data = channel.raw_data
            Logger.debug(f"[MagicWandTool] Using Raw Data ({work_data.shape}) at ({x}, {y})")
        
        # Boundary check
        h, w = work_data.shape[:2]
        if x < 0 or x >= w or y < 0 or y >= h:
            Logger.warning(f"[MagicWandTool] Click out of bounds ({x}, {y}) for shape ({w}, {h})")
            return

        # Initialize state
        self.is_dragging = True
        self.start_pos = scene_pos # Use original scene_pos for drag delta calculation
        self.seed_pos = (x, y)
        self.tool_active_channel_idx = effective_idx
        self.current_tolerance = self.base_tolerance
        self.display_scale = display_scale # Store for mapping back
        
        # Initial calculation
        ch_name = None
        if effective_idx >= 0:
            channel = self.session.get_channel(effective_idx)
            if channel:
                ch_name = channel.name
        
        self.tool_active_channel_name = ch_name # Cache for move event
        self._update_selection(work_data, channel_name=ch_name)
        self.preview_changed.emit()

    def _apply_polygon_conversion(self, roi, mask):
        """Helper to convert a mask-based ROI to a polygon-based ROI."""
        if mask is None:
            return
            
        from src.core.algorithms import mask_to_qpath
        # Use a reasonable epsilon for polygon conversion to avoid too many points
        # USER REQUEST: Optimize handle point count for performance
        # Increased epsilon from 1.0 to 2.5 for better default performance
        poly_path = mask_to_qpath(mask, simplify_epsilon=2.5, smooth=False)
        
        pts = []
        # Optimization: Limit maximum number of points for converted polygons
        # Reduced max_points from 500 to 150 to significantly improve UI responsiveness
        max_points = 150 
        element_count = poly_path.elementCount()
        
        if element_count > max_points:
            # If too many points, re-simplify with even larger epsilon
            # Increased epsilon from 2.5 to 5.0 for very complex masks
            poly_path = mask_to_qpath(mask, simplify_epsilon=5.0, smooth=False)
            element_count = poly_path.elementCount()
            Logger.debug(f"[MagicWandTool] Re-simplified path: {element_count} points (epsilon 5.0)")

        for i in range(poly_path.elementCount()):
            el = poly_path.elementAt(i)
            pts.append(QPointF(el.x, el.y))
        
        if len(pts) >= 3:
            roi.path = poly_path
            roi.points = pts
            roi.roi_type = "polygon"
            if not roi.label.startswith("Poly"):
                roi.label = f"Poly{roi.label}"

    def mouse_move(self, scene_pos: QPointF, modifiers=Qt.KeyboardModifier.NoModifier):
        """
        Adjusts tolerance based on horizontal drag distance.
        """
        if not self.is_dragging:
            return

        # Calculate horizontal delta to adjust tolerance
        # Right drag = increase tolerance, Left drag = decrease tolerance
        delta_x = (scene_pos.x() - self.start_pos.x()) * self.display_scale # Use display units for delta
        
        if self.relative:
            self.current_tolerance = max(0.1, self.base_tolerance + delta_x * 0.5)
        else:
            self.current_tolerance = max(0.0, self.base_tolerance + delta_x * 2.0)
        
        self.tolerance_changed.emit(self.current_tolerance)
        
        # Re-calculate selection
        # We need the data we started with
        # Actually, let's store work_data in self
        if hasattr(self, 'current_work_data'):
             ch_name = getattr(self, 'tool_active_channel_name', None)
             self._update_selection(self.current_work_data, channel_name=ch_name)
        
        self.preview_changed.emit()
        
        # --- FIX: Update Preview Item ---
        if self.preview_item:
             path = self.get_preview_path()
             self.preview_item.setPath(path)
        # --------------------------------
        
        # Force View Update for real-time feedback
        view = self.current_view if self.current_view else self._get_active_view()
        if view and view.scene():
             view.scene().update()
             view.viewport().update()

    def mouse_release(self, scene_pos: QPointF, modifiers=Qt.KeyboardModifier.NoModifier):
        """
        Commits the ROI.
        """
        Logger.info(f"[MagicWandTool] mouse_release at {scene_pos}")
        if not self.is_dragging or self.current_path is None:
            Logger.debug("[MagicWandTool] No active drag or path to commit")
            self._reset_state()
            return

        try:
            if self.split_regions and hasattr(self, 'current_paths') and self.current_paths:
                base_prefix = "Wand"
                existing = self.session.roi_manager.get_all_rois() if hasattr(self.session, 'roi_manager') else []
                base_count = sum(1 for r in existing if r.label.startswith(base_prefix))
                created = 0
                for i, p in enumerate(self.current_paths):
                    roi = ROI(
                        label=f"{base_prefix}_{base_count + created + 1}",
                        path=p,
                        color=self.get_channel_color(self.tool_active_channel_idx),
                        channel_index=self.tool_active_channel_idx
                    )
                    
                    # USER REQUEST: Convert to polygon if enabled
                    if self.convert_to_polygon:
                        self._apply_polygon_conversion(roi, self.current_masks[i] if hasattr(self, 'current_masks') else None)

                    if self.display_scale < 1.0:
                        roi = roi.get_full_res_roi(self.display_scale)
                    if self.session.channels:
                        stats = calculate_intensity_stats(roi, self.session.channels)
                        roi.stats.update(stats)
                    self.session.roi_manager.add_roi(roi, undoable=True)
                    created += 1
                self.committed.emit(f"Created {created} ROIs")
                Logger.info(f"[MagicWandTool] Created {created} ROIs")
            else:
                roi = ROI(
                    label=f"Wand_{int(np.sum(self.current_mask))}",
                    path=self.current_path,
                    color=self.get_channel_color(self.tool_active_channel_idx),
                    channel_index=self.tool_active_channel_idx
                )
                
                # USER REQUEST: Convert to polygon if enabled
                if self.convert_to_polygon:
                    self._apply_polygon_conversion(roi, self.current_mask)

                if self.display_scale < 1.0:
                    roi = roi.get_full_res_roi(self.display_scale)
                
                if self.session.channels:
                    # Optimization: Use detailed path for stats, but simplified path for display
                    try:
                        from src.core.algorithms import mask_to_qpath
                        detailed_path = mask_to_qpath(self.current_mask, simplify_epsilon=0.5)
                        temp_roi = roi.clone()
                        temp_roi.path = detailed_path
                        # If we are in downsampled mode, we need to scale the detailed path too
                        if self.display_scale < 1.0:
                             temp_roi = temp_roi.get_full_res_roi(self.display_scale)
                        stats = calculate_intensity_stats(temp_roi, self.session.channels)
                        roi.stats.update(stats)
                    except Exception as e:
                        Logger.warning(f"[MagicWand] Detailed stats calculation failed, falling back to simplified: {e}")
                        stats = calculate_intensity_stats(roi, self.session.channels)
                        roi.stats.update(stats)
                self.session.roi_manager.add_roi(roi, undoable=True)
                self.committed.emit(f"Created ROI: {roi.label}")
                Logger.info(f"[MagicWandTool] Successfully created ROI: {roi.label}")

                # USER REQUEST: Restore focus to view after creation to ensure shortcut responsiveness
                # Note: view is defined in the block below, let's move it up or re-find it
                if hasattr(self.session, 'main_window') and self.session.main_window:
                    mw = self.session.main_window
                    if hasattr(mw, 'multi_view'):
                        v = mw.multi_view.get_active_view()
                        if v:
                            v.setFocus(Qt.FocusReason.OtherFocusReason)
        except Exception as e:
            Logger.error(f"[MagicWandTool] Failed to create ROI: {e}", exc_info=True)
        finally:
            # --- FIX: Cleanup Preview Item ---
            if self.preview_item:
                 if self.preview_item.scene():
                     self.preview_item.scene().removeItem(self.preview_item)
                 self.preview_item = None
            # ---------------------------------
            
            self._reset_state()
            self.preview_changed.emit()

        # Reset tool to Hand Mode to allow immediate selection of the new ROI
        if hasattr(self.session, 'main_window') and self.session.main_window:
             mw = self.session.main_window
             # Reset via MultiView's active view
             if hasattr(mw, 'multi_view'):
                 try:
                     view = mw.multi_view.get_active_view()
                     if view:
                         view.set_active_tool(None)
                         # FORCE FOCUS back to the view to ensure keyboard events are captured
                         view.setFocus(Qt.FocusReason.OtherFocusReason)
                         Logger.debug("[MagicWandTool] Auto-switched to Hand Tool after creation and restored focus")
                 except Exception as e:
                     Logger.error(f"[MagicWandTool] Failed to auto-switch to Hand Tool: {e}")

    def _update_selection(self, data: np.ndarray, channel_name: Optional[str] = None):
        """Internal helper to calculate mask and path."""
        self.current_work_data = data # Cache for move event
        self.current_mask = magic_wand_2d(
            data, 
            self.seed_pos, 
            self.current_tolerance,
            smoothing=self.smoothing,
            relative=self.relative,
            channel_name=channel_name
        )
        
        if np.any(self.current_mask):
            # OPTIMIZATION: Dynamic Simplification based on area to reduce lag for large/complex ROIs
            area = np.sum(self.current_mask)
            # Reduced base epsilon from 1.0 to 0.1 for smoother graphics
            # For 100x100 (10k area) -> epsilon ~ 0.3 (was 2.0)
            # For 1000x1000 (1M area) -> epsilon ~ 2.1 (was 11.0)
            dynamic_epsilon = 0.1 + (area ** 0.5) / 500.0
            dynamic_epsilon = max(0.1, min(dynamic_epsilon, 5.0)) # Clamp between 0.1 and 5.0
            
            Logger.debug(f"[MagicWandTool] Area: {area}, Dynamic Epsilon: {dynamic_epsilon:.2f}")

            if self.keep_largest:
                import cv2
                m = self.current_mask.astype(np.uint8)
                nlabels, labels, stats, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
                if nlabels > 1:
                    areas = stats[1:, cv2.CC_STAT_AREA]
                    idx = int(np.argmax(areas)) + 1
                    largest_mask = (labels == idx)
                    self.current_path = mask_to_qpath(largest_mask, simplify_epsilon=dynamic_epsilon, smooth=self.contour_smoothing)
                    self.current_paths = [self.current_path] if self.current_path else []
                else:
                    self.current_path = mask_to_qpath(self.current_mask, simplify_epsilon=dynamic_epsilon, smooth=self.contour_smoothing)
                    self.current_paths = [self.current_path] if self.current_path else []
            elif self.split_regions:
                paths = mask_to_qpaths(self.current_mask, simplify_epsilon=dynamic_epsilon, smooth=self.contour_smoothing)
                self.current_paths = paths
                self.current_path = mask_to_qpath(self.current_mask, simplify_epsilon=dynamic_epsilon, smooth=self.contour_smoothing)
            else:
                self.current_path = mask_to_qpath(self.current_mask, simplify_epsilon=dynamic_epsilon, smooth=self.contour_smoothing)
                self.current_paths = [self.current_path] if self.current_path else []
        else:
            self.current_path = None
            self.current_paths = []

    def _reset_state(self):
        self.is_dragging = False
        self.start_pos = None
        self.seed_pos = None
        self.tool_active_channel_idx = -1
        self.current_mask = None
        self.current_path = None

    def get_preview_path(self) -> QPainterPath:
        """Returns the current path for real-time visualization."""
        return self.current_path or QPainterPath()

class PointCounterTool(AbstractTool):
    """
    Tool for counting spots/points by clicking.
    Creates small circular ROIs and manages counts per channel.
    """
    def __init__(self, session: Session):
        super().__init__(session)
        self.radius = 3.0
        self.current_path = None
        self.target_channel_idx = -1 # -1 means use the channel of the view clicked
        self.channel_settings = {} # {idx: {'color': hex, 'shape': 'circle'}}
        self.active_category = "Puncta" # 将默认分类从 Other 修改为 Puncta

    def set_channel_color_override(self, channel_idx, color_hex):
        if channel_idx not in self.channel_settings:
            self.channel_settings[channel_idx] = {}
        self.channel_settings[channel_idx]['color'] = color_hex

    def set_channel_shape(self, channel_idx, shape):
        if channel_idx not in self.channel_settings:
            self.channel_settings[channel_idx] = {}
        self.channel_settings[channel_idx]['shape'] = shape
        self.preview_changed.emit()

    def set_channel_radius(self, channel_idx, radius):
        if channel_idx not in self.channel_settings:
            self.channel_settings[channel_idx] = {}
        self.channel_settings[channel_idx]['radius'] = radius
        self.preview_changed.emit()

    def _get_channel_config(self, idx):
        """Returns (color, shape, radius) for a given channel index."""
        # 1. 基础默认值
        color = self.get_channel_color(idx)
        shape = 'circle'
        radius = self.radius
        
        # 2. 如果是特定通道，尝试获取该通道在 session 中的默认颜色
        if idx >= 0 and self.session:
            channel = self.session.get_channel(idx)
            if channel:
                color = QColor(channel.display_settings.color)

        # 3. 应用覆盖设置 (来自 UI 的用户修改)
        if idx in self.channel_settings:
            s = self.channel_settings[idx]
            if 'color' in s:
                color = QColor(s['color'])
            if 'shape' in s:
                shape = s['shape']
            if 'radius' in s:
                radius = s['radius']
        
        return color, shape, radius

    def mouse_press(self, scene_pos: QPointF, channel_index: int, context: dict = None):
        """Adds a point ROI at the clicked location."""
        import time
        from src.core.logger import Logger
        start_time = time.perf_counter()
        Logger.debug(f"[PointCounterTool.mouse_press] ENTER - ScenePos: ({scene_pos.x():.2f}, {scene_pos.y():.2f}), Channel: {channel_index}")
        
        self.display_scale = context.get('display_scale', 1.0) if context else 1.0
        # Determine which channel this point belongs to
        # If we are in Merge view (index -1), use UI active channel or override
        effective_channel_idx = channel_index
        if effective_channel_idx < 0:
            effective_channel_idx = self.target_channel_idx if self.target_channel_idx >= 0 else self.active_channel_idx
            
        # 1. Get the target channel for metadata (color, name)
        channel = self.session.get_channel(effective_channel_idx)
        
        # Get Config (Color/Shape/Radius)
        color, shape, radius = self._get_channel_config(effective_channel_idx)
        
        if channel:
            label_prefix = f"Point_{channel.name}"
        else:
            # If still -1 (Merge view and no override), use a generic label
            label_prefix = "Point_Merge"
            color = self.get_channel_color(-1) # Fallback if config failed
            
        # 2. Create path based on shape
        path = self._create_shape_path(scene_pos, radius, shape)
        
        # 3. Create ROI with scientific rigor (Store raw point for full-res mapping)
        # Find current count for this prefix to make label unique
        rois = self.session.roi_manager.get_all_rois()
        existing_count = sum(1 for r in rois if r.label.startswith(label_prefix))
        
        roi = ROI(
            label=f"{label_prefix}_{existing_count + 1}",
            color=color,
            channel_index=effective_channel_idx,
            properties={'shape': shape, 'radius': radius, 'category': self.active_category}
        )
        
        # FIX: Point ROI visual offset issue
        # scene_pos is already in full resolution.
        full_res_pos = scene_pos
        
        view = None
        if hasattr(self.session, 'main_window') and self.session.main_window:
             view = self.session.main_window.multi_view.get_active_view()
             
        if view and hasattr(view, 'get_image_coordinates'):
             full_res_pos = view.get_image_coordinates(scene_pos)
             Logger.debug(f"[PointCounterTool.mouse_press] Mapped: Scene({scene_pos.x():.1f}, {scene_pos.y():.1f}) -> Image({full_res_pos.x():.1f}, {full_res_pos.y():.1f})")
        else:
             Logger.debug("[PointCounterTool.mouse_press] Using Raw Scene coordinates (No View found)")
            
        # Reconstruct using the specific shape logic
        Logger.debug(f"[PointCounterTool.mouse_press] Calling reconstruct_from_points for ROI: {roi.label}")
        roi.reconstruct_from_points([full_res_pos], roi_type="point")
        
        # 4. Add to manager
        Logger.debug(f"[PointCounterTool.mouse_press] Adding ROI to manager: {roi.id}")
        self.session.roi_manager.add_roi(roi, undoable=True)
        
        self.committed.emit(f"Counted {roi.label}")

        # USER REQUEST: Restore focus to view after creation to ensure shortcut responsiveness
        if view:
            view.setFocus(Qt.FocusReason.OtherFocusReason)

        Logger.debug(f"[PointCounterTool.mouse_press] EXIT - Logic took {(time.perf_counter()-start_time)*1000:.2f}ms")
        
    def _create_shape_path(self, center, radius, shape):
        path = QPainterPath()
        x, y = center.x(), center.y()
        r = radius
        if shape == 'square':
            path.addRect(x - r, y - r, 2*r, 2*r)
        elif shape == 'triangle':
            # Upward triangle
            p1 = QPointF(x, y - r)
            p2 = QPointF(x + r, y + r)
            p3 = QPointF(x - r, y + r)
            path.moveTo(p1)
            path.lineTo(p2)
            path.lineTo(p3)
            path.closeSubpath()
        elif shape == 'diamond':
            # Diamond shape
            p1 = QPointF(x, y - r)     # Top
            p2 = QPointF(x + r, y)     # Right
            p3 = QPointF(x, y + r)     # Bottom
            p4 = QPointF(x - r, y)     # Left
            path.moveTo(p1)
            path.lineTo(p2)
            path.lineTo(p3)
            path.lineTo(p4)
            path.closeSubpath()
        elif shape == 'cross':
            # Cross shape (+)
            path.moveTo(x - r, y)
            path.lineTo(x + r, y)
            path.moveTo(x, y - r)
            path.lineTo(x, y + r)
        else: # circle
            path.addEllipse(x - r, y - r, 2*r, 2*r)
        return path

    def mouse_move(self, scene_pos: QPointF, modifiers=Qt.KeyboardModifier.NoModifier):
        """Updates preview of the point to be placed."""
        # Determine shape based on potential target
        target_idx = self.target_channel_idx if self.target_channel_idx >= 0 else self.active_channel_idx
        _, shape, radius = self._get_channel_config(target_idx)
        
        path = self._create_shape_path(scene_pos, radius, shape)
        
        # Add crosshair lines for precision if not already a cross
        if shape != 'cross':
            line_len = radius * 1.5
            path.moveTo(scene_pos.x() - line_len, scene_pos.y())
            path.lineTo(scene_pos.x() + line_len, scene_pos.y())
            path.moveTo(scene_pos.x(), scene_pos.y() - line_len)
            path.lineTo(scene_pos.x(), scene_pos.y() + line_len)
        
        self.current_path = path
        self.preview_changed.emit()

        # --- CRITICAL FIX: Ensure Preview Item Exists & Update ---
        view = self._get_active_view()
        if view and view.scene():
             if self.preview_item is None:
                 self.preview_item = QGraphicsPathItem()
                 self.preview_item.setPen(QPen(Qt.GlobalColor.yellow, 1))
                 self.preview_item.setZValue(9999)
                 view.scene().addItem(self.preview_item)
             
             self.preview_item.setPath(self.current_path)
             view.scene().update()
        # -------------------------------------------------------


    def mouse_release(self, scene_pos: QPointF, modifiers=Qt.KeyboardModifier.NoModifier):
        pass

    def get_preview_path(self) -> QPainterPath:
        return self.current_path or QPainterPath()

# [弃用说明] 注解模式已迁移至 BaseDrawTool/DrawToolFactory。本类仅用于 ROI 专用交互（固定大小/多点预览等）。
class PolygonTool(AbstractTool):
    """
    Polygon Selection Tool (Click-to-Add-Point).
    User clicks to add points, moves to see preview line.
    Double-click OR Right-click to close and commit ROI.
    Supports Freehand (Lasso) drawing via Right-Click toggle.
    """
    def __init__(self, session: Session):
        super().__init__(session)
        self.points = [] # List[QPointF]
        self.current_path = None # QPainterPath for preview
        self.is_active = False
        self.tool_active_channel_idx = -1
        self.is_freehand_mode = False # Toggle state
        self.display_scale = 1.0
        self.is_moving = False
        
        # Fixed Size Mode
        self.fixed_size_mode = False
        self.last_relative_points = None

    def set_fixed_size_mode(self, enabled: bool):
        self.fixed_size_mode = enabled
        Logger.info(f"[PolygonTool] Fixed size mode set to: {enabled}")

    def _update_preview_path(self, mouse_pos: QPointF = None):
        """Updates the QPainterPath used for rendering the preview."""
        if not self.points:
            self.current_path = None
            return

        # Prepare points list for smoothing
        pts = list(self.points)
        
        if mouse_pos and not self.is_freehand_mode and not self.is_moving:
            # Only draw prediction line in point mode, and not moving fixed shape
            pts.append(mouse_pos)
            
        # Use smoothing helper
        # If moving, it's a closed polygon. Otherwise open (preview).
        closed = self.is_moving 
        
        self.current_path = create_smooth_path_from_points(pts, closed=closed)
        
        # Update the visual item
        if self.preview_item:
            self.preview_item.setPath(self.current_path or QPainterPath())
            # Force update
            if self.preview_item.scene():
                self.preview_item.scene().update()

    def mouse_press(self, scene_pos: QPointF, channel_index: int, context: dict = None):
        # Only left click adds points. Right click handled separately.
        view = context.get('view') if context else self._get_active_view()
        self.current_view = view

        if not self.is_active:
            effective_idx = channel_index
            if effective_idx < 0:
                effective_idx = self.active_channel_idx
            self.tool_active_channel_idx = effective_idx
            # --- USER REQUEST: Store scale for reverse mapping ---
            self.display_scale = context.get('display_scale', 1.0) if context else 1.0
            
            # Fixed Size Logic
            if self.fixed_size_mode and self.last_relative_points:
                self.is_active = True
                self.is_moving = True
                # Reconstruct points relative to scene_pos (as start point)
                self.points = [scene_pos + p for p in self.last_relative_points]
                self._update_preview_path()
                return
            
        self.is_active = True
        
        # Ensure preview item exists and is in scene
        if not self.preview_item:
            if view and view.scene():
                self.preview_item = QGraphicsPathItem()
                self.preview_item.setPen(QPen(Qt.GlobalColor.yellow, 2, Qt.PenStyle.DashLine))
                self.preview_item.setZValue(9999)
                view.scene().addItem(self.preview_item)
                Logger.debug(f"[PolygonTool] Preview item added to scene {view.view_id}")

        self.points.append(scene_pos)
        self._update_preview_path(scene_pos) # Init with current pos

    def mouse_move(self, scene_pos: QPointF, modifiers=Qt.KeyboardModifier.NoModifier):
        # Need view for coordinate mapping during move
        # We don't have context here. 
        # But we can store the view from mouse_press?
        # Or look it up.
        
        # For now, let's just use raw scene_pos for preview, but map it when storing?
        # Preview path is drawn in Scene Coordinates.
        # So points should be in Scene Coordinates for drawing?
        # YES. QGraphicsPathItem is in Scene Coords.
        # If we store Image Coordinates in self.points, we must map BACK to Scene for preview.
        
        # Problem: ROI expects Image Coordinates.
        # Preview expects Scene Coordinates.
        
        # Solution: Store points in Image Coordinates. 
        # When updating preview, map Image -> Scene.
        # Or Store Scene Coordinates, and map Scene -> Image only when creating ROI.
        
        # Option 2 is simpler for preview.
        # Let's revert the change above and map at the end (finish_polygon).
        
        if self.is_active:
            if self.is_moving and self.last_relative_points:
                 # Move the entire polygon
                 self.points = [scene_pos + p for p in self.last_relative_points]
                 self._update_preview_path()
                 return

            if self.is_freehand_mode:
                # In Freehand mode, we add points continuously while moving
                # To avoid too many points, maybe check distance?
                if not self.points or (scene_pos - self.points[-1]).manhattanLength() > 2 * self.display_scale:
                     self.points.append(scene_pos)
            
            self._update_preview_path(scene_pos)

        # Force View Update for real-time feedback
        if hasattr(self.session, 'main_window') and self.session.main_window:
             try:
                 mw = self.session.main_window
                 if hasattr(mw, 'multi_view'):
                     view = mw.multi_view.get_active_view()
                     if view and view.scene():
                         view.scene().update()
             except:
                 pass

    def mouse_release(self, scene_pos: QPointF, modifiers=Qt.KeyboardModifier.NoModifier):
        if self.is_moving:
            self.is_moving = False
            self.finish_polygon()

    def mouse_double_click(self, scene_pos: QPointF):
        # Disable double click completion as per user request
        # self.finish_polygon()
        pass

    def mouse_right_click(self, scene_pos: QPointF):
        """
        Right Click Logic:
        1. If not active: Do nothing (or context menu handled by View).
        2. If active:
           a. If we have enough points (>= 2), Close Polygon. (Modified to allow closing "lines" to avoid silent failure)
           b. If we have few points, maybe Toggle Freehand?
           User said: "Right click to change to freehand... then right click to close".
        """
        Logger.debug(f"[PolygonTool] Right Click at {scene_pos}, Active: {self.is_active}, Freehand: {self.is_freehand_mode}, Points: {len(self.points)}")
        if not self.is_active:
             return

        if self.is_freehand_mode:
            # If we are in freehand mode, Right Click closes it.
            self.finish_polygon()
        else:
            # If we are in Point mode
            # If points exist, close it regardless of count to prevent "lost" feeling.
            # finish_polygon will validate count.
            if len(self.points) >= 1:
                last = self.points[-1] if self.points else None
                # Add the final point if it's different from the last one
                if last is None or (scene_pos - last).manhattanLength() > 0:
                    self.points.append(scene_pos)
                self.finish_polygon()
            else:
                self.is_freehand_mode = True
                Logger.info("[PolygonTool] Switched to Freehand Mode")
                if not self.points:
                    self.points.append(scene_pos)

    def finish_polygon(self):
        """Closes the polygon and creates the ROI."""
        if not self.is_active:
            return

        Logger.debug(f"[PolygonTool] finish_polygon called with {len(self.points)} points")

        # Relaxed check: Allow closing even with few points, but ROI creation requires valid shape.
        # If < 3 points, we can't make a polygon area.
        # But we should reset state so user isn't stuck.
        if len(self.points) < 3:
            Logger.warning(f"[PolygonTool] Creation cancelled: Need at least 3 points. (Has {len(self.points)})")
            # If the user tries to close with < 3 points, we should probably just reset
            # But maybe they want to see what happened.
            if hasattr(self.session, 'main_window') and self.session.main_window and hasattr(self.session.main_window, 'lbl_status'):
                 self.session.main_window.lbl_status.setText(f"Cannot close polygon: Need 3+ points (Current: {len(self.points)})")
            # self.points = [] # Don't clear, let them add more?
            # Actually, if they right click to close and fail, they might want to try again.
            return
            
        # Store relative points for fixed size
        p0 = self.points[0]
        self.last_relative_points = [p - p0 for p in self.points]

        # Close the loop (points are in SCENE coordinates)
        path = QPainterPath()
        path.moveTo(self.points[0])
        for pt in self.points[1:]:
            path.lineTo(pt)
        path.closeSubpath()
        
        # Map Points to Image Coordinates for ROI storage
        # We need access to the view to map correctly
        # Try to find active view
        image_points = []
        view = None
        if hasattr(self.session, 'main_window') and self.session.main_window:
             view = self.session.main_window.multi_view.get_active_view()
             
        if view and hasattr(view, 'get_image_coordinates'):
             image_points = [view.get_image_coordinates(p) for p in self.points]
             Logger.debug(f"[PolygonTool] Mapped {len(self.points)} points from Scene -> Image")
        else:
             image_points = self.points # Fallback
             Logger.debug("[PolygonTool] Used Raw Scene coordinates (No View found)")

        # --- ROI Creation (Default) ---
        # Create ROI with scientific rigor (Store raw points for full-res mapping)
        roi = ROI(
            label=f"Polygon_{len(self.session.roi_manager.get_all_rois()) + 1}",
            color=self.get_channel_color(self.tool_active_channel_idx),
            channel_index=self.tool_active_channel_idx
        )
        # Use polygon type
        roi.reconstruct_from_points(image_points, roi_type="polygon")
        
        # Calculate stats immediately
        if self.session.channels:
            stats = calculate_intensity_stats(roi, self.session.channels)
            roi.stats.update(stats)
            Logger.debug(f"[PolygonTool] Closed. Stats: {stats}")
        
        self.session.roi_manager.add_roi(roi, undoable=True)
        self.committed.emit(f"Created ROI: {roi.label}")

        # USER REQUEST: Restore focus to view after creation to ensure shortcut responsiveness
        if view:
            view.setFocus(Qt.FocusReason.OtherFocusReason)

        self._cleanup_polygon()

    def on_deactivate(self):
        """USER REQUEST: Ensure polygon state is cleared on tool switch/ESC."""
        self._cleanup_polygon()

    def _cleanup_polygon(self):
        # Reset
        if self.preview_item:
            if self.preview_item.scene():
                self.preview_item.scene().removeItem(self.preview_item)
            self.preview_item = None
            
        self.points = []
        self.current_path = None
        self.is_active = False
        self.is_freehand_mode = False

# [弃用说明] 注解模式已迁移至 BaseDrawTool/DrawToolFactory。本类仅用于 ROI 专用交互（固定大小等）。
class LineScanTool(DrawingTool):
    """
    Line Scan Tool.
    Drag to draw a line. Real-time updates for colocalization analysis.
    """
    line_updated = Signal(QPointF, QPointF) # Start, End

    def __init__(self, session: Session):
        super().__init__(session)
        self.start_pos = None
        self.end_pos = None
        self.current_path = None
        self.is_dragging = False
        
        # Fixed Size Mode
        self.fixed_size_mode = False
        self.last_vector = None # QPointF (vector from start to end)
        self.is_moving = False # For moving fixed line

    def set_fixed_size_mode(self, enabled: bool):
        self.fixed_size_mode = enabled
        
    def _create_specific_item(self):
        return QGraphicsLineItem()

    def start_preview(self, scene_pos: QPointF, channel_index: int, context: dict = None):
        # --- CRITICAL FIX: Ensure Correct Item Type & Visibility ---
        # Item creation handled by DrawingTool.mouse_press
        # -----------------------------------------------------------

        self.start_pos = scene_pos
        # --- USER REQUEST: Store scale for reverse mapping ---
        self.display_scale = context.get('display_scale', 1.0) if context else 1.0
        
        if self.fixed_size_mode:
            # If we have a stored vector, use it
            if self.last_vector:
                self.end_pos = scene_pos + self.last_vector
                self.is_moving = True
                self.is_dragging = False
            else:
                # Fallback default: 50px horizontal
                self.last_vector = QPointF(50.0, 0.0)
                self.end_pos = scene_pos + self.last_vector
                self.is_moving = True
                self.is_dragging = False
        else:
            # Normal Mode
            self.end_pos = scene_pos
            self.is_dragging = True
            self.is_moving = False

    def on_mouse_move(self, scene_pos: QPointF, modifiers=Qt.KeyboardModifier.NoModifier):
        if self.is_moving and self.last_vector:
            # Move the entire line (maintain vector)
            self.start_pos = scene_pos
            self.end_pos = scene_pos + self.last_vector
            
            # --- USER REQUEST: Emit full-resolution coordinates ---
            self.line_updated.emit(self.start_pos, self.end_pos)
            
        elif self.is_dragging:
            self.end_pos = scene_pos
            
            # --- USER REQUEST: Emit full-resolution coordinates for accurate analysis ---
            self.line_updated.emit(self.start_pos, self.end_pos)
            
        # --- CRITICAL FIX: Update Line Geometry ---
        if self.preview_item and isinstance(self.preview_item, QGraphicsLineItem):
            if self.start_pos and self.end_pos:
                from PySide6.QtCore import QLineF
                self.preview_item.setLine(QLineF(self.start_pos, self.end_pos))
        # ------------------------------------------

    def finish_shape(self, scene_pos: QPointF, modifiers=Qt.KeyboardModifier.NoModifier):
        if self.is_moving:
            self.is_moving = False
            self._create_line_roi()
        elif self.is_dragging:
            self.end_pos = scene_pos
            
            # --- USER REQUEST: Emit full-resolution coordinates for accurate analysis ---
            self.line_updated.emit(self.start_pos, self.end_pos)
            
            # Create a Line ROI for persistence
            self._create_line_roi()
            
            self.is_dragging = False
            
        # Reset
        self.start_pos = None
        self.end_pos = None
        self.current_path = None
        self.is_moving = False
        self.preview_changed.emit()

    def get_preview_path(self, scene_pos: QPointF) -> QPainterPath:
        path = QPainterPath()
        if self.start_pos and self.end_pos:
            path.moveTo(self.start_pos)
            path.lineTo(self.end_pos)
        self.current_path = path
        self.preview_changed.emit()
        return path

    def _update_line(self):
        pass

    def _create_line_roi(self):
        if not self.start_pos or not self.end_pos:
            return
            
        # Line length check
        dx = self.end_pos.x() - self.start_pos.x()
        dy = self.end_pos.y() - self.start_pos.y()
        if (dx*dx + dy*dy) < 4: # Min 2 pixels
            return
            
        # Update last vector for fixed mode
        self.last_vector = self.end_pos - self.start_pos
            
        # FIX: Coordinate Mapping (Scene -> Image)
        image_start = self.start_pos
        image_end = self.end_pos
        
        view = None
        if hasattr(self.session, 'main_window') and self.session.main_window:
             view = self.session.main_window.multi_view.get_active_view()
             
        if view and hasattr(view, 'get_image_coordinates'):
             image_start = view.get_image_coordinates(self.start_pos)
             image_end = view.get_image_coordinates(self.end_pos)
             print(f"DEBUG: LineScan Mapped: Scene({self.start_pos.x():.1f}, {self.start_pos.y():.1f}) -> Image({image_start.x():.1f}, {image_start.y():.1f})")
        else:
             print("DEBUG: LineScan used Raw Scene coordinates (No View found)")
            
        # --- ROI Creation (Default) ---
        path = QPainterPath()
        path.moveTo(image_start)
        path.lineTo(image_end)
        
        roi = ROI(
            label=f"LineScan_{len(self.session.roi_manager.get_all_rois()) + 1}",
            path=path,
            color=QColor(255, 255, 0), # Yellow for line scans
            channel_index=-1, # Global line scan
            roi_type="line_scan",
            measurable=True,
            export_with_image=True
        )
        roi.line_points = (image_start, image_end)
            
        self.session.roi_manager.add_roi(roi, undoable=True)
        self.committed.emit(f"Created Line Scan: {roi.label}")

        # USER REQUEST: Restore focus to view after creation to ensure shortcut responsiveness
        if view:
            view.setFocus(Qt.FocusReason.OtherFocusReason)


class CropTool(AbstractTool):
    """
    Crop Tool.
    Draws a rectangle. Double-click to crop.
    """
    def __init__(self, session: Session):
        super().__init__(session)
        self.start_pos = None
        self.end_pos = None
        self.current_path = None
        
    def start_preview(self, scene_pos: QPointF, channel_index: int, context: dict = None):
        self.start_pos = scene_pos
        self.end_pos = scene_pos
        self.is_dragging = True
        # CropTool uses double click to execute, release just ends drag
        
    def on_mouse_move(self, scene_pos: QPointF, modifiers=Qt.KeyboardModifier.NoModifier):
        if self.start_pos:
            self.end_pos = scene_pos
            
    def finish_shape(self, scene_pos: QPointF, modifiers=Qt.KeyboardModifier.NoModifier):
        # CropTool doesn't commit on release, it waits for double click
        # Just stop dragging
        # But we need to keep the preview visible?
        # AbstractTool clears preview on release.
        # CropTool needs persistent preview until double click.
        # This refactor breaks CropTool unless we persist preview.
        # For now, let's keep CropTool behavior: drag to define, double click to commit.
        # But AbstractTool destroys preview item on release.
        # So CropTool needs its own preview item management or AbstractTool needs to support persistence.
        
        # Workaround: Re-add preview item in finish_shape? Or don't use AbstractTool for CropTool?
        # Actually, CropTool usually clears on release in standard tools, but here it says "Double-click to crop".
        # If it clears on release, user can't see what they selected to double click.
        # So CropTool logic: Drag -> Rect shows -> Release -> Rect stays -> Double Click -> Action.
        
        # We can set self.preview_item to None in finish_shape so AbstractTool doesn't remove it?
        # No, AbstractTool removes it first.
        
        # Let's revert CropTool to NOT use AbstractTool hooks for now, OR:
        # Override mouse_release to NOT call super?
        # But AbstractTool.mouse_release cleans up.
        
        # Let's Override mouse_release in CropTool to bypass cleanup.
        pass

    def mouse_release(self, scene_pos: QPointF, modifiers=Qt.KeyboardModifier.NoModifier):
        # Override to prevent cleanup
        pass

    def mouse_double_click(self, scene_pos: QPointF):
        """
        Double click to execute crop.
        Creates an ROI from the current selection and triggers crop action.
        """
        if not self.start_pos or not self.end_pos:
            return

        # 1. Coordinate Mapping (Scene -> Image)
        # This fixes the "offset" issue on packaged/different resolution screens
        image_start = self.start_pos
        image_end = self.end_pos
        
        view = None
        if hasattr(self.session, 'main_window') and self.session.main_window:
             view = self.session.main_window.multi_view.get_active_view()
             
        if view and hasattr(view, 'get_image_coordinates'):
             image_start = view.get_image_coordinates(self.start_pos)
             image_end = view.get_image_coordinates(self.end_pos)
             Logger.info(f"[CropTool] Mapped Coords: {self.start_pos} -> {image_start}")
        
        # 2. Create ROI
        path = QPainterPath()
        path.addRect(QRectF(image_start, image_end).normalized())
        
        roi = ROI(
            label=f"Crop_{len(self.session.roi_manager.get_all_rois()) + 1}",
            path=path,
            color=QColor(Qt.GlobalColor.white),
            channel_index=-1
        )
        roi.roi_type = "rect" # Treat as rect for crop logic
        
        # 3. Add to Manager (Undoable=False because it's a transient action?)
        # Better to be undoable so user can see what they cropped
        self.session.roi_manager.add_roi(roi, undoable=True)
        
        # USER REQUEST: Restore focus to view after creation to ensure shortcut responsiveness
        if view:
            view.setFocus(Qt.FocusReason.OtherFocusReason)
        
        # 4. Trigger Crop
        if self.session.main_window:
            self.session.main_window.crop_to_selection()
            
        # 5. Cleanup self (AbstractTool deactivate)
        self.deactivate()
        # Also clear the specific tool state
        self.start_pos = None
        self.end_pos = None
        self.current_path = None

    def get_preview_path(self, scene_pos: QPointF) -> QPainterPath:
        path = QPainterPath()
        if self.start_pos and self.end_pos:
            rect = QRectF(self.start_pos, self.end_pos).normalized()
            path.addRect(rect)
        self.current_path = path
        return path

    def _update_rect(self):
        pass


class BatchSelectionTool(AbstractTool):
    """
    Tool for selecting multiple ROIs/Annotations via a drag box.
    """
    selection_made = Signal(QRectF, int)

    def __init__(self, session: Session):
        super().__init__(session)
        self.start_pos = None
        self.current_rect = None
        self.is_dragging = False
        self.tool_channel_index = -1

    def start_preview(self, scene_pos: QPointF, channel_index: int, context: dict = None):
        self.start_pos = scene_pos
        self.is_dragging = True
        self.tool_channel_index = channel_index
        self.current_rect = QRectF(scene_pos, scene_pos)
        
    def on_mouse_move(self, scene_pos: QPointF, modifiers=Qt.KeyboardModifier.NoModifier):
        if not self.is_dragging:
            return
        self.current_rect = QRectF(self.start_pos, scene_pos).normalized()
        
    def finish_shape(self, scene_pos: QPointF, modifiers=Qt.KeyboardModifier.NoModifier):
        if self.is_dragging and self.current_rect:
            self.selection_made.emit(self.current_rect, self.tool_channel_index)
        self.is_dragging = False
        self.current_rect = None
        self.preview_changed.emit()
        
    def get_preview_path(self, scene_pos: QPointF) -> QPainterPath:
        path = QPainterPath()
        if self.current_rect:
            path.addRect(self.current_rect)
        return path

    def _update_preview(self):
        pass


class DrawStyleStrategy:
    def preview_pen(self, shape_type: str, props: dict) -> QPen:
        return QPen(QColor("#FFFF00"), 2, Qt.PenStyle.SolidLine)
    def preview_brush(self, shape_type: str, props: dict):
        return Qt.BrushStyle.NoBrush
    def default_properties(self, shape_type: str) -> dict:
        return {}
    def map_to_model(self, session: Session, points, shape_type: str, color: str, thickness: int, extra: dict):
        return None


class ROIStyleStrategy(DrawStyleStrategy):
    def preview_pen(self, shape_type: str, props: dict) -> QPen:
        # Unified preview style
        pen = QPen(QColor("#FFFF00"), 1, Qt.PenStyle.DashLine)
        if shape_type in ["arrow", "text"]:
             pen = QPen(QColor("#FFFF00"), 2, Qt.PenStyle.SolidLine)
        
        pen.setCosmetic(True)
        return pen
        
    def preview_brush(self, shape_type: str, props: dict):
        if shape_type in ["arrow", "text", "line"]:
            return Qt.BrushStyle.NoBrush
        return Qt.BrushStyle.Dense4Pattern
        
    def default_properties(self, shape_type: str) -> dict:
        props = {"compute_stats": True}
        if shape_type in ["arrow", "text"]:
            props["compute_stats"] = False
        return props
        
    def map_to_model(self, session: Session, points, shape_type: str, color: str, thickness: int, extra: dict):
        roi_type = {
            "rect": "rectangle",
            "ellipse": "ellipse",
            "circle": "ellipse",
            "line": "line",
            "polygon": "polygon",
            "arrow": "arrow",
            "text": "text"
        }.get(shape_type, "polygon")
        
        # Determine if measurable based on type
        measurable = True
        if roi_type in ["arrow", "text"]:
            measurable = False
            
        roi = ROI(
            label=f"{roi_type.capitalize()}_{len(session.roi_manager.get_all_rois()) + 1}", 
            color=QColor(color), 
            channel_index=extra.get("channel_index", -1)
        )
        roi.roi_type = roi_type
        roi.measurable = measurable
        
        # --- EXPORT LOGIC SYNC ---
        # Default to exportable, but if annotation panel exists, follow its default
        export_with_image = True
        if hasattr(session, "main_window") and session.main_window:
            if hasattr(session.main_window, "annotation_panel"):
                # Use current export state from panel defaults if available
                export_with_image = session.main_window.annotation_panel.default_properties.get('export_with_image', True)
        
        roi.export_with_image = export_with_image
        # -------------------------
        
        # Transfer properties
        roi.properties.update(extra.get("properties", {}))
        # Ensure thickness is stored
        roi.properties['thickness'] = thickness
        
        qpoints = []
        for p in points:
            qpoints.append(QPointF(p[0], p[1]))
            
        if shape_type in ["rect", "ellipse", "circle"] and len(qpoints) >= 2:
            roi.reconstruct_from_points(qpoints[:2], roi_type=roi_type)
        elif shape_type in ["line", "arrow"] and len(qpoints) >= 2:
            roi.reconstruct_from_points(qpoints[:2], roi_type=roi_type)
        elif shape_type == "text" and len(qpoints) >= 1:
             roi.reconstruct_from_points(qpoints[:1], roi_type=roi_type)
        else:
            roi.reconstruct_from_points(qpoints, roi_type=roi_type)
            
        if session.channels and measurable and extra.get("compute_stats", True):
            stats = calculate_intensity_stats(roi, session.channels)
            roi.stats.update(stats)
            
        return roi


class BaseDrawTool(AbstractTool):
    def __init__(self, session: Session, shape_type: str, strategy: DrawStyleStrategy):
        super().__init__(session)
        self.shape_type = shape_type
        self.strategy = strategy
        self.start_pos = None
        self.end_pos = None
        self.points = []
        self.is_dragging = False
        self.display_scale = 1.0
        self.tool_channel_index = -1
        self.extra_props = {}
        
        # Fixed Size Mode
        self.fixed_size_mode = False
        self.last_vector = None # Vector from start to end for fixed shapes
        self.is_moving = False  # If moving a fixed shape
        self._press_time = 0.0
        self._drag_threshold = 0.2 # 200ms threshold for short clicks

    def set_fixed_size_mode(self, enabled: bool):
        self.fixed_size_mode = enabled
        Logger.info(f"[BaseDrawTool] {self.shape_type} fixed size mode: {enabled}")

    def set_properties(self, props: dict):
        self.extra_props.update(props)
    def start_preview(self, scene_pos: QPointF, channel_index: int, context: dict = None):
        Logger.debug(f"[BaseDrawTool] start_preview shape={self.shape_type} pos={scene_pos} channel={channel_index}")
        self.start_pos = scene_pos
        self.tool_channel_index = channel_index
        self._press_time = time.time()
        if context:
            self.display_scale = context.get("display_scale", 1.0)
            self.current_view = context.get("view")

        if self.shape_type == "text":
            # Text tool: Show input box immediately on click
            view = self.current_view if self.current_view else self._get_active_view()
            if view and hasattr(view, "show_text_input"):
                initial_text = self.extra_props.get("text", "Text")
                view.show_text_input(scene_pos, initial_text=initial_text, callback=self._on_text_input_finished)
                return

        if self.fixed_size_mode and self.last_vector:
            self.end_pos = self.start_pos + self.last_vector
            self.is_moving = True
            self.is_dragging = False
        else:
            self.end_pos = scene_pos
            self.is_dragging = True
            self.is_moving = False

        self.preview_changed.emit()

    def _on_text_input_finished(self, text: str):
        """Callback from CanvasView when text input is done."""
        if text:
            self.extra_props["text"] = text
            # For text, end_pos is the same as start_pos
            self.end_pos = self.start_pos
            self._commit()
        
        # Reset tool state
        self.start_pos = None
        self.end_pos = None
        self.preview_changed.emit()

    def on_mouse_move(self, scene_pos: QPointF, modifiers=Qt.KeyboardModifier.NoModifier):
        if self.shape_type == "text":
            return # No dragging for text tool in this mode
        if self.is_moving:
            # Moving fixed shape
            self.start_pos = scene_pos
            if self.last_vector:
                self.end_pos = self.start_pos + self.last_vector
            self.preview_changed.emit()
            return

        if not self.is_dragging:
            return
        # Apply constraints for square/circle when Shift is pressed
        if self.shape_type in ["rect", "ellipse", "circle"] and self.start_pos:
            end = scene_pos
            if modifiers & Qt.KeyboardModifier.ShiftModifier:
                dx = end.x() - self.start_pos.x()
                dy = end.y() - self.start_pos.y()
                size = max(abs(dx), abs(dy))
                end = QPointF(self.start_pos.x() + (size if dx >= 0 else -size),
                              self.start_pos.y() + (size if dy >= 0 else -size))
            self.end_pos = end
        else:
            self.end_pos = scene_pos
        self.preview_changed.emit()

    def finish_shape(self, scene_pos: QPointF, modifiers=Qt.KeyboardModifier.NoModifier):
        if self.is_moving:
            self.start_pos = scene_pos
            if self.last_vector:
                self.end_pos = self.start_pos + self.last_vector
            self.is_moving = False
            self._commit()
            self.preview_changed.emit()
            return

        if not self.is_dragging:
            return

        # USER REQUEST: Prevent accidental shape creation from short clicks/drags.
        # Check duration and distance.
        duration = time.time() - self._press_time
        dist = 0.0
        if self.start_pos:
            diff = scene_pos - self.start_pos
            dist = (diff.x()**2 + diff.y()**2)**0.5
            
        if duration < self._drag_threshold and dist < 5.0:
            Logger.info(f"[BaseDrawTool] Click/drag too short (dur={duration:.3f}s, dist={dist:.1f}px). Ignoring shape creation.")
            self.is_dragging = False
            self.start_pos = None
            self.end_pos = None
            self.preview_changed.emit()
            # Cleanup preview item
            if self.preview_item and self.preview_item.scene():
                try:
                    self.preview_item.scene().removeItem(self.preview_item)
                except:
                    pass
            self.preview_item = None
            return

        # Apply final constraints on release
        if self.shape_type in ["rect", "ellipse", "circle"] and self.start_pos:
            end = scene_pos
            if modifiers & Qt.KeyboardModifier.ShiftModifier:
                dx = end.x() - self.start_pos.x()
                dy = end.y() - self.start_pos.y()
                size = max(abs(dx), abs(dy))
                end = QPointF(self.start_pos.x() + (size if dx >= 0 else -size),
                              self.start_pos.y() + (size if dy >= 0 else -size))
            self.end_pos = end
        else:
            self.end_pos = scene_pos
        
        # Store vector for next fixed size use
        if self.start_pos and self.end_pos:
            self.last_vector = self.end_pos - self.start_pos

        self.is_dragging = False
        self._commit()
        self.start_pos = None
        self.end_pos = None
        self.preview_changed.emit()
    def get_preview_path(self, scene_pos: QPointF) -> QPainterPath:
        path = QPainterPath()
        if self.shape_type in ["rect", "ellipse", "circle"] and self.start_pos and self.end_pos:
            rect = QRectF(self.start_pos, self.end_pos).normalized()
            if self.shape_type == "ellipse" or self.shape_type == "circle":
                if self.shape_type == "circle":
                    w = rect.width()
                    h = rect.height()
                    d = max(w, h)
                    rect.setWidth(d)
                    rect.setHeight(d)
                path.addEllipse(rect)
            else:
                path.addRect(rect)
        elif self.shape_type in ["line", "arrow"] and self.start_pos and self.end_pos:
            path.moveTo(self.start_pos)
            path.lineTo(self.end_pos)
            if self.shape_type == "arrow":
                try:
                    import math
                    dx = self.end_pos.x() - self.start_pos.x()
                    dy = self.end_pos.y() - self.start_pos.y()
                    angle = math.atan2(dy, dx)
                    view = self._get_active_view()
                    head_size = float(self.extra_props.get("arrow_head_size", 15.0))
                    if view and hasattr(view, 'display_scale') and view.display_scale > 0:
                        head_size = head_size / view.display_scale
                    arrow_angle = math.pi / 6
                    p1 = QPointF(self.end_pos.x() - head_size * math.cos(angle - arrow_angle),
                                 self.end_pos.y() - head_size * math.sin(angle - arrow_angle))
                    p2 = QPointF(self.end_pos.x() - head_size * math.cos(angle + arrow_angle),
                                 self.end_pos.y() - head_size * math.sin(angle + arrow_angle))
                    path.moveTo(self.end_pos); path.lineTo(p1)
                    path.moveTo(self.end_pos); path.lineTo(p2)
                except Exception as e:
                    Logger.warning(f"[BaseDrawTool] Arrow preview head failed: {e}")
        elif self.shape_type == "polygon":
            if self.start_pos and self.end_pos:
                pts = [self.start_pos, self.end_pos]
                path = create_smooth_path_from_points(pts, closed=False)
        elif self.shape_type == "text" and self.end_pos:
            # User requested no placeholder box for text
            pass
        if self.preview_item:
            pen = self.strategy.preview_pen(self.shape_type, self.extra_props)
            brush = self.strategy.preview_brush(self.shape_type, self.extra_props)
            self.preview_item.setPen(pen)
            self.preview_item.setBrush(brush)
            self.preview_item.setPath(path)
            self.preview_item.setVisible(True)
        return path
    def _get_image_points(self, view, scene_points):
        pts = []
        for p in scene_points:
            if hasattr(view, "get_image_coordinates"):
                ip = view.get_image_coordinates(p)
            else:
                ip = p
            pts.append((ip.x(), ip.y()))
        return pts
    def _commit(self):
        Logger.debug(f"[BaseDrawTool] commit shape={self.shape_type}")
        view = self._get_active_view()
        
        # Determine points based on shape type
        if self.shape_type in ["rect", "ellipse", "circle"]:
            if not (self.start_pos and self.end_pos):
                return
            pts = self._get_image_points(view, [self.start_pos, self.end_pos])
        elif self.shape_type in ["line", "arrow"]:
            if not (self.start_pos and self.end_pos):
                return
            pts = self._get_image_points(view, [self.start_pos, self.end_pos])
        elif self.shape_type == "polygon":
             pts = self._get_image_points(view, [self.start_pos, self.end_pos])
        elif self.shape_type == "text":
            # 支持延迟应用：仅创建占位框，不立即写入文本
            defer_apply = bool(self.extra_props.get("defer_text_apply", False))
            text = self.extra_props.get("text")
            if not defer_apply:
                if not text:
                    try:
                        if hasattr(self.session, "main_window") and hasattr(self.session.main_window, "annotation_panel"):
                            text = self.session.main_window.annotation_panel.get_current_properties().get("text", "")
                    except Exception:
                        text = ""
                if not text:
                    default_text = "Text"
                    try:
                        if hasattr(self.session, "main_window") and hasattr(self.session.main_window, "annotation_panel"):
                            default_text = self.session.main_window.annotation_panel.default_properties.get("text", "Text")
                    except Exception:
                        pass
                    text = default_text
                self.extra_props["text"] = text
            else:
                # 延迟应用：不设置 text，保留空，占位框将显示
                text = ""
            pts = self._get_image_points(view, [self.end_pos])
        else:
            return
            
        color = self.extra_props.get("color", "#FFFF00")
        thickness = int(self.extra_props.get("thickness", 2))
        
        extra = self.strategy.default_properties(self.shape_type)
        extra.update({"channel_index": self.tool_channel_index})
        extra.update({"properties": self.extra_props})
        
        # Always use ROIStyleStrategy (strategy is injected)
        model = self.strategy.map_to_model(self.session, pts, self.shape_type, color, thickness, extra)
        
        if model:
            self.session.roi_manager.add_roi(model, undoable=True)
            self.committed.emit(f"Created ROI: {model.label}")
            
            # USER REQUEST: Restore focus to view after creation to ensure shortcut responsiveness
            if view:
                view.setFocus(Qt.FocusReason.OtherFocusReason)
            
        if self.preview_item and self.preview_item.scene():
            self.preview_item.scene().removeItem(self.preview_item)
        self.preview_item = None


class DrawToolFactory:
    @staticmethod
    def create(session: Session, shape_type: str, module: str = "roi"):
        if shape_type == "polygon":
            return PolygonTool(session)
        # Always return ROI strategy
        strategy = ROIStyleStrategy()
        return BaseDrawTool(session, shape_type, strategy)

# [弃用说明] 注解模式建议使用 BaseDrawTool('arrow')。本类保留箭头预览逻辑以兼容旧流程。
