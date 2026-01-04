from abc import abstractmethod
from PySide6.QtCore import QPointF, Qt, QObject, Signal, QRectF
from PySide6.QtGui import QPainterPath, QColor
from src.core.algorithms import magic_wand_2d, mask_to_qpath
from src.core.analysis import calculate_intensity_stats
from src.core.data_model import Session
from src.core.roi_model import ROI
import numpy as np
from src.core.logger import Logger

class AbstractTool(QObject):
    preview_changed = Signal()
    committed = Signal(str) # Emits a message about the committed action

    def __init__(self, session: Session):
        super().__init__()
        self.session = session
        self.active_channel_idx = -1 # The channel selected in the UI

    def set_active_channel(self, index: int):
        """Sets the globally active channel from the UI."""
        self.active_channel_idx = index

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

    @abstractmethod
    def mouse_press(self, scene_pos: QPointF, channel_index: int, context: dict = None):
        pass

    @abstractmethod
    def mouse_move(self, scene_pos: QPointF, modifiers=Qt.KeyboardModifier.NoModifier):
        pass

    @abstractmethod
    def mouse_release(self, scene_pos: QPointF, modifiers=Qt.KeyboardModifier.NoModifier):
        pass
    
    def mouse_double_click(self, scene_pos: QPointF):
        """Optional hook for double click events."""
        pass
        
    def mouse_right_click(self, scene_pos: QPointF):
        """Optional hook for right click events."""
        pass

class MagicWandTool(AbstractTool):
    tolerance_changed = Signal(float) # Signal to update UI feedback

    def __init__(self, session: Session):
        super().__init__(session)
        self.base_tolerance = 100.0 # Default base tolerance
        self.current_tolerance = 100.0
        self.smoothing = 1.0
        self.relative = False
        
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
        # 1. Determine target channel index
        effective_idx = channel_index
        if effective_idx < 0:
            effective_idx = self.active_channel_idx
            
        # 2. Get the target data and scale
        # If context is provided, we can run on downsampled data for performance
        display_data = context.get('display_data') if context else None
        display_scale = context.get('display_scale', 1.0) if context else 1.0
        
        # 3. Convert coordinates to integer pixel indices
        if display_data is not None:
            # We are running on downsampled data
            # map scene_pos (full-res) to display_pos (downsampled)
            x, y = int(scene_pos.x() * display_scale), int(scene_pos.y() * display_scale)
            work_data = display_data
            print(f"MagicWand: Using Downsampled Data ({work_data.shape}) at ({x}, {y})")
        else:
            # Fallback to full-res raw data
            channel = self.session.get_channel(effective_idx)
            if not channel:
                print(f"MagicWand: No channel at index {effective_idx}")
                return
            x, y = int(scene_pos.x()), int(scene_pos.y())
            work_data = channel.raw_data
            print(f"MagicWand: Using Raw Data ({work_data.shape}) at ({x}, {y})")
        
        # Boundary check
        h, w = work_data.shape[:2]
        if x < 0 or x >= w or y < 0 or y >= h:
            print(f"MagicWand: Click out of bounds ({x}, {y})")
            return

        # Initialize state
        self.is_dragging = True
        self.start_pos = scene_pos
        self.seed_pos = (x, y)
        self.tool_active_channel_idx = effective_idx
        self.current_tolerance = self.base_tolerance
        self.display_scale = display_scale # Store for mapping back
        
        # Initial calculation
        self._update_selection(work_data)
        self.preview_changed.emit()

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
             self._update_selection(self.current_work_data)
        
        self.preview_changed.emit()

    def mouse_release(self, scene_pos: QPointF, modifiers=Qt.KeyboardModifier.NoModifier):
        """
        Commits the ROI.
        """
        if not self.is_dragging or self.current_path is None:
            self._reset_state()
            return

        # Create the ROI
        roi = ROI(
            label=f"Wand_{int(np.sum(self.current_mask))}",
            path=self.current_path,
            color=self.get_channel_color(self.tool_active_channel_idx),
            channel_index=self.tool_active_channel_idx
        )
        
        # --- USER REQUEST: Reverse Mapping to Full Resolution ---
        if self.display_scale < 1.0:
            roi = roi.get_full_res_roi(self.display_scale)
            print(f"MagicWand: Mapped to Full Resolution (Scale: {self.display_scale:.4f})")
        
        # Calculate stats on full-res data
        if self.session.channels:
            stats = calculate_intensity_stats(roi, self.session.channels)
            roi.stats.update(stats)
        
        self.session.roi_manager.add_roi(roi)
        self.committed.emit(f"Created ROI: {roi.label}")
        self._reset_state()
        self.preview_changed.emit()

    def _update_selection(self, data: np.ndarray):
        """Internal helper to calculate mask and path."""
        self.current_work_data = data # Cache for move event
        self.current_mask = magic_wand_2d(
            data, 
            self.seed_pos, 
            self.current_tolerance,
            smoothing=self.smoothing,
            relative=self.relative
        )
        
        if np.any(self.current_mask):
            self.current_path = mask_to_qpath(self.current_mask, simplify_epsilon=0.5)
        else:
            self.current_path = None

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

    def set_channel_color_override(self, channel_idx, color_hex):
        if channel_idx not in self.channel_settings:
            self.channel_settings[channel_idx] = {}
        self.channel_settings[channel_idx]['color'] = color_hex

    def set_channel_shape(self, channel_idx, shape):
        if channel_idx not in self.channel_settings:
            self.channel_settings[channel_idx] = {}
        self.channel_settings[channel_idx]['shape'] = shape

    def _get_channel_config(self, idx):
        """Returns (color, shape) for a given channel index."""
        # Default
        color = self.get_channel_color(idx)
        shape = 'circle'
        
        # Override
        if idx in self.channel_settings:
            s = self.channel_settings[idx]
            if 'color' in s:
                color = QColor(s['color'])
            if 'shape' in s:
                shape = s['shape']
        
        # Handle Merge (idx = -1) - check if we have settings for -1?
        # Actually Merge usually uses target_channel_idx, so we should look that up first.
        return color, shape

    def mouse_press(self, scene_pos: QPointF, channel_index: int, context: dict = None):
        """Adds a point ROI at the clicked location."""
        self.display_scale = context.get('display_scale', 1.0) if context else 1.0
        # Determine which channel this point belongs to
        # If we are in Merge view (index -1), use UI active channel or override
        effective_channel_idx = channel_index
        if effective_channel_idx < 0:
            effective_channel_idx = self.target_channel_idx if self.target_channel_idx >= 0 else self.active_channel_idx
            
        # 1. Get the target channel for metadata (color, name)
        channel = self.session.get_channel(effective_channel_idx)
        
        # Get Config (Color/Shape)
        color, shape = self._get_channel_config(effective_channel_idx)
        
        if channel:
            label_prefix = f"Point_{channel.name}"
        else:
            # If still -1 (Merge view and no override), use a generic label
            label_prefix = "Point_Merge"
            color = self.get_channel_color(-1) # Fallback if config failed
            
        # 2. Create path based on shape
        path = self._create_shape_path(scene_pos, self.radius, shape)
        
        # 3. Create ROI with scientific rigor (Store raw point for full-res mapping)
        # Find current count for this prefix to make label unique
        existing_count = sum(1 for r in self.session.roi_manager.get_all_rois() 
                           if r.label.startswith(label_prefix))
        
        roi = ROI(
            label=f"{label_prefix}_{existing_count + 1}",
            color=color,
            channel_index=effective_channel_idx,
            properties={'shape': shape}
        )
        
        # FIX: Point ROI visual offset issue
        # scene_pos is already in full resolution.
        full_res_pos = scene_pos
        
        view = None
        if hasattr(self.session, 'main_window') and self.session.main_window:
             view = self.session.main_window.multi_view.get_active_view()
             
        if view and hasattr(view, 'get_image_coordinates'):
             full_res_pos = view.get_image_coordinates(scene_pos)
             print(f"DEBUG: PointCounter Mapped: Scene({scene_pos.x():.1f}, {scene_pos.y():.1f}) -> Image({full_res_pos.x():.1f}, {full_res_pos.y():.1f})")
        else:
             print("DEBUG: PointCounter used Raw Scene coordinates (No View found)")
            
        # Reconstruct using the specific shape logic
        roi.reconstruct_from_points([full_res_pos], roi_type="point")
        
        # We don't need to manually set path anymore as reconstruct_from_points handles it now
        # based on properties['shape']
        
        # 4. Add to manager
        self.session.roi_manager.add_roi(roi, undoable=True)
        self.committed.emit(f"Counted {roi.label}")
        
    def _create_shape_path(self, center, radius, shape):
        path = QPainterPath()
        x, y = center.x(), center.y()
        r = radius
        if shape == 'square':
            path.addRect(x - r, y - r, 2*r, 2*r)
        elif shape == 'triangle':
            # Upward triangle
            # Top
            p1 = QPointF(x, y - r)
            # Bottom Right
            p2 = QPointF(x + r, y + r)
            # Bottom Left
            p3 = QPointF(x - r, y + r)
            path.moveTo(p1)
            path.lineTo(p2)
            path.lineTo(p3)
            path.closeSubpath()
        else: # circle
            path.addEllipse(x - r, y - r, 2*r, 2*r)
        return path

    def mouse_move(self, scene_pos: QPointF, modifiers=Qt.KeyboardModifier.NoModifier):
        """Updates preview of the point to be placed."""
        # Determine shape based on potential target
        # This is tricky because we don't know the channel until click (for Merge).
        # But we can guess based on target_channel_idx.
        target_idx = self.target_channel_idx if self.target_channel_idx >= 0 else self.active_channel_idx
        _, shape = self._get_channel_config(target_idx)
        
        path = self._create_shape_path(scene_pos, self.radius, shape)
        
        # Add crosshair lines (optional, maybe distracting with shapes?)
        # Let's keep them but make them subtle or just rely on shape.
        # User asked for shapes, let's keep crosshair for precision.
        line_len = self.radius * 2
        path.moveTo(scene_pos.x() - line_len, scene_pos.y())
        path.lineTo(scene_pos.x() + line_len, scene_pos.y())
        path.moveTo(scene_pos.x(), scene_pos.y() - line_len)
        path.lineTo(scene_pos.x(), scene_pos.y() + line_len)
        
        self.current_path = path
        self.preview_changed.emit()

    def mouse_release(self, scene_pos: QPointF, modifiers=Qt.KeyboardModifier.NoModifier):
        pass

    def get_preview_path(self) -> QPainterPath:
        return self.current_path or QPainterPath()

class PolygonSelectionTool(AbstractTool):
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
        
        # Fixed Size Mode
        self.fixed_size_mode = False
        self.last_relative_points = None # List[QPointF] relative to points[0]
        self.is_moving = False

    def set_fixed_size_mode(self, enabled: bool):
        self.fixed_size_mode = enabled

    def _update_preview_path(self, mouse_pos: QPointF = None):
        """Updates the QPainterPath used for rendering the preview."""
        if not self.points:
            self.current_path = None
            return

        path = QPainterPath()
        path.moveTo(self.points[0])
        
        for pt in self.points[1:]:
            path.lineTo(pt)
            
        if mouse_pos and not self.is_freehand_mode and not self.is_moving:
            # Only draw prediction line in point mode, and not moving fixed shape
            path.lineTo(mouse_pos)
        elif self.is_moving:
             # Close the path for preview if moving fixed shape
             path.closeSubpath()
            
        self.current_path = path

    def mouse_press(self, scene_pos: QPointF, channel_index: int, context: dict = None):
        # Only left click adds points. Right click handled separately.
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
        
        # If in freehand mode, we don't add points on click, we wait for drag?
        # Actually, user requested Right Click to Toggle.
        # So Left Click is always add point (or start freehand segment?)
        self.points.append(scene_pos)
        print(f"DEBUG: Polygon Point Added. Total: {len(self.points)}")
        Logger.debug(f"[PolygonTool] Point added: ({scene_pos.x():.1f}, {scene_pos.y():.1f}), total={len(self.points)}")
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
        print(f"DEBUG: Polygon Right Click at {scene_pos}, Active: {self.is_active}, Freehand: {self.is_freehand_mode}, Points: {len(self.points)}")
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
                print("Switched to Freehand Mode")
                if not self.points:
                    self.points.append(scene_pos)

    def finish_polygon(self):
        """Closes the polygon and creates the ROI."""
        if not self.is_active:
            return

        print(f"DEBUG: finish_polygon called with {len(self.points)} points")

        # Relaxed check: Allow closing even with few points, but ROI creation requires valid shape.
        # If < 3 points, we can't make a polygon area.
        # But we should reset state so user isn't stuck.
        if len(self.points) < 3:
            print(f"Polygon creation cancelled: Need at least 3 points. (Has {len(self.points)})")
            # If the user tries to close with < 3 points, we should probably just reset
            # But maybe they want to see what happened.
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
             print(f"DEBUG: Polygon Mapped {len(self.points)} points from Scene -> Image")
        else:
             image_points = self.points # Fallback
             print("DEBUG: Polygon used Raw Scene coordinates (No View found)")

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
            print(f"Polygon Closed. Stats: {stats}")
        
        self.session.roi_manager.add_roi(roi, undoable=True)
        self.committed.emit(f"Created ROI: {roi.label}")

        # Reset
        self.points = []
        self.current_path = None
        self.is_active = False
        self.is_freehand_mode = False

class RectangleSelectionTool(AbstractTool):
    """
    Rectangle Selection Tool.
    Drag to draw a rectangle. Release to create ROI.
    """
    def __init__(self, session: Session):
        super().__init__(session)
        self.start_pos = None
        self.end_pos = None
        self.current_path = None
        self.is_dragging = False
        self.active_channel_idx = -1
        
        # Fixed Size Mode
        self.fixed_size_mode = False
        self.last_size = None # QSizeF
        self.is_moving = False # For moving fixed rect
        
    def set_fixed_size_mode(self, enabled: bool):
        self.fixed_size_mode = enabled
        
    def mouse_press(self, scene_pos: QPointF, channel_index: int, context: dict = None):
        print(f"DEBUG: RectTool.mouse_press at {scene_pos}, channel={channel_index}")
        effective_idx = channel_index
        if effective_idx < 0:
            effective_idx = self.active_channel_idx
        self.tool_active_channel_idx = effective_idx
        
        # --- USER REQUEST: Store scale for reverse mapping ---
        self.display_scale = context.get('display_scale', 1.0) if context else 1.0
        print(f"DEBUG: RectTool.mouse_press display_scale={self.display_scale}")
        
        if self.fixed_size_mode and self.last_size:
            # Fixed Mode: Place rect centered at click (or top-left?)
            # Let's do top-left for consistency with visual start
            self.start_pos = scene_pos
            self.end_pos = scene_pos + QPointF(self.last_size.width(), self.last_size.height())
            self.is_moving = True
            self._update_rect()
        else:
            # Normal Mode
            self.start_pos = scene_pos
            self.end_pos = scene_pos
            self.is_dragging = True
            self._update_rect()
        
    def mouse_move(self, scene_pos: QPointF, modifiers=Qt.KeyboardModifier.NoModifier):
        if self.is_moving and self.last_size:
            # Move the entire rect
            self.start_pos = scene_pos
            self.end_pos = scene_pos + QPointF(self.last_size.width(), self.last_size.height())
            self._update_rect()
        elif self.is_dragging and self.start_pos:
            # Resize
            self.end_pos = scene_pos
            
            # Handle Square constraint (Shift Key)
            if modifiers & Qt.KeyboardModifier.ShiftModifier:
                width = self.end_pos.x() - self.start_pos.x()
                height = self.end_pos.y() - self.start_pos.y()
                
                # Determine max dimension and sign
                size = max(abs(width), abs(height))
                new_w = size if width >= 0 else -size
                new_h = size if height >= 0 else -size
                
                self.end_pos = QPointF(self.start_pos.x() + new_w, self.start_pos.y() + new_h)
            
            self._update_rect()
            
    def mouse_release(self, scene_pos: QPointF, modifiers=Qt.KeyboardModifier.NoModifier):
        print(f"DEBUG: RectTool.mouse_release at {scene_pos}")
        if self.is_moving:
            self.is_moving = False
            self._create_roi()
        elif self.is_dragging and self.start_pos:
            self.end_pos = scene_pos
            
            # Handle Square constraint (Shift Key) - Re-apply on release to ensure precision
            if modifiers & Qt.KeyboardModifier.ShiftModifier:
                width = self.end_pos.x() - self.start_pos.x()
                height = self.end_pos.y() - self.start_pos.y()
                size = max(abs(width), abs(height))
                new_w = size if width >= 0 else -size
                new_h = size if height >= 0 else -size
                self.end_pos = QPointF(self.start_pos.x() + new_w, self.start_pos.y() + new_h)
                
            self._create_roi()
            
        # Reset
        self.start_pos = None
        self.end_pos = None
        self.current_path = None
        self.is_dragging = False
        self.is_moving = False
        self.preview_changed.emit()
            
    def _update_rect(self):
        path = QPainterPath()
        if self.start_pos and self.end_pos:
            rect = QRectF(self.start_pos, self.end_pos).normalized()
            path.addRect(rect)
        self.current_path = path
        self.preview_changed.emit()

    def _create_roi(self):
        print("DEBUG: RectTool._create_roi start")
        if not self.start_pos or not self.end_pos:
            print("DEBUG: RectTool._create_roi aborted: start_pos or end_pos missing")
            return
            
        rect = QRectF(self.start_pos, self.end_pos).normalized()
        
        # Minimum size check
        if rect.width() < 2 or rect.height() < 2:
            print("DEBUG: RectTool._create_roi aborted: too small")
            return
        
        # Update last size for fixed mode
        self.last_size = rect.size()
        
        # FIX: Coordinate Mapping (Scene -> Image)
        image_start = self.start_pos
        image_end = self.end_pos
        
        view = None
        try:
            if hasattr(self.session, 'main_window') and self.session.main_window:
                 view = self.session.main_window.multi_view.get_active_view()
                 print(f"DEBUG: RectTool got active view: {view}")
                 
            if view and hasattr(view, 'get_image_coordinates'):
                 image_start = view.get_image_coordinates(self.start_pos)
                 image_end = view.get_image_coordinates(self.end_pos)
                 print(f"DEBUG: Rectangle Mapped: Scene({self.start_pos.x():.1f}, {self.start_pos.y():.1f}) -> Image({image_start.x():.1f}, {image_start.y():.1f})")
            else:
                 print("DEBUG: Rectangle used Raw Scene coordinates (No View found)")
            
            # Create ROI with scientific rigor (Store raw points for full-res mapping)
            print("DEBUG: Creating ROI object...")
            roi = ROI(
                label=f"Rectangle_{len(self.session.roi_manager.get_all_rois()) + 1}",
                color=self.get_channel_color(self.tool_active_channel_idx),
                channel_index=self.tool_active_channel_idx
            )
            print("DEBUG: Reconstructing ROI from points...")
            roi.reconstruct_from_points([image_start, image_end], roi_type="rectangle")
            
            # Calculate stats
            if self.session.channels:
                print("DEBUG: Calculating stats...")
                stats = calculate_intensity_stats(roi, self.session.channels)
                roi.stats.update(stats)
                print(f"DEBUG: Stats calculated: {stats.keys()}")
                
            print("DEBUG: Adding ROI to manager...")
            self.session.roi_manager.add_roi(roi, undoable=True)
            self.committed.emit(f"Created ROI: {roi.label}")
            print("DEBUG: RectTool._create_roi success")
            
        except Exception as e:
            print(f"ERROR: Crash in RectTool._create_roi: {e}")
            import traceback
            traceback.print_exc()

class TextTool(AbstractTool):
    """
    Tool for creating text annotations.
    """
    def __init__(self, session: Session):
        super().__init__(session)
        self.start_pos = None
        self.end_pos = None
        self.current_path = None
        self.is_dragging = False
        self.color = "#FFFF00"
        self.font_size = 12
        
    def set_color(self, hex_color: str):
        self.color = hex_color
        
    def mouse_press(self, scene_pos: QPointF, channel_index: int, context: dict = None):
        self.start_pos = scene_pos
        self.end_pos = scene_pos
        self.is_dragging = True
        self.display_scale = context.get('display_scale', 1.0) if context else 1.0
        self._update_path()
        
    def mouse_move(self, scene_pos: QPointF, modifiers=Qt.KeyboardModifier.NoModifier):
        if self.is_dragging:
            self.end_pos = scene_pos
            self._update_path()
            self.preview_changed.emit()
            
    def mouse_release(self, scene_pos: QPointF, modifiers=Qt.KeyboardModifier.NoModifier):
        if self.is_dragging:
            self.end_pos = scene_pos
            self._create_annotation()
            
        self.is_dragging = False
        self.start_pos = None
        self.end_pos = None
        self.current_path = None
        self.preview_changed.emit()
        
    def _update_path(self):
        path = QPainterPath()
        if self.start_pos and self.end_pos:
            path.moveTo(self.start_pos)
            path.lineTo(self.end_pos) # Just a line to show where text starts
        self.current_path = path
        
    def _create_annotation(self):
        if not self.start_pos or not self.end_pos:
            return
            
        import uuid
        from src.core.data_model import GraphicAnnotation
        from PySide6.QtWidgets import QInputDialog
        
        # Ask for text
        text, ok = QInputDialog.getText(None, "Annotation Text", "Enter text:")
        if not ok or not text:
            return
            
        # Points are in scene coordinates (full resolution)
        pts = [(self.start_pos.x(), self.start_pos.y()), 
               (self.end_pos.x(), self.end_pos.y())]
               
        ann = GraphicAnnotation(
            id=str(uuid.uuid4()),
            type='text',
            points=pts,
            color=self.color,
            thickness=1,
            visible=True
        )
        ann.text = text
        ann.properties['font_size'] = self.font_size
        
        self.session.annotations.append(ann)
        self.committed.emit(f"Added text annotation")
        
    def get_preview_path(self) -> QPainterPath:
        return self.current_path or QPainterPath()


class EllipseSelectionTool(AbstractTool):
    """
    Ellipse Selection Tool.
    Drag to draw an ellipse. Release to create ROI.
    """
    def __init__(self, session: Session):
        super().__init__(session)
        self.start_pos = None
        self.end_pos = None
        self.current_path = None
        self.is_dragging = False
        self.tool_active_channel_idx = -1
        
        # Fixed Size Mode
        self.fixed_size_mode = False
        self.last_size = None # QSizeF
        self.is_moving = False # For moving fixed shape
        
    def set_fixed_size_mode(self, enabled: bool):
        self.fixed_size_mode = enabled
        
    def mouse_press(self, scene_pos: QPointF, channel_index: int, context: dict = None):
        effective_idx = channel_index
        if effective_idx < 0:
            effective_idx = self.active_channel_idx
        self.tool_active_channel_idx = effective_idx
        
        # --- USER REQUEST: Store scale for reverse mapping ---
        self.display_scale = context.get('display_scale', 1.0) if context else 1.0
        
        if self.fixed_size_mode and self.last_size:
            # Fixed Mode
            self.start_pos = scene_pos
            self.end_pos = scene_pos + QPointF(self.last_size.width(), self.last_size.height())
            self.is_moving = True
            self._update_ellipse()
        else:
            # Normal Mode
            self.start_pos = scene_pos
            self.end_pos = scene_pos
            self.is_dragging = True
            self._update_ellipse()
        
    def mouse_move(self, scene_pos: QPointF, modifiers=Qt.KeyboardModifier.NoModifier):
        if self.is_moving and self.last_size:
            # Move the entire shape
            self.start_pos = scene_pos
            self.end_pos = scene_pos + QPointF(self.last_size.width(), self.last_size.height())
            self._update_ellipse()
        elif self.is_dragging and self.start_pos:
            self.end_pos = scene_pos
            
            # Handle Circle constraint (Shift Key)
            if modifiers & Qt.KeyboardModifier.ShiftModifier:
                width = self.end_pos.x() - self.start_pos.x()
                height = self.end_pos.y() - self.start_pos.y()
                
                # Determine max dimension and sign
                size = max(abs(width), abs(height))
                new_w = size if width >= 0 else -size
                new_h = size if height >= 0 else -size
                
                self.end_pos = QPointF(self.start_pos.x() + new_w, self.start_pos.y() + new_h)
            
            self._update_ellipse()
            
    def mouse_release(self, scene_pos: QPointF, modifiers=Qt.KeyboardModifier.NoModifier):
        if self.is_moving:
            self.is_moving = False
            self._create_roi()
        elif self.is_dragging and self.start_pos:
            self.end_pos = scene_pos
            
            # Handle Circle constraint (Shift Key) - Re-apply on release to ensure precision
            if modifiers & Qt.KeyboardModifier.ShiftModifier:
                width = self.end_pos.x() - self.start_pos.x()
                height = self.end_pos.y() - self.start_pos.y()
                size = max(abs(width), abs(height))
                new_w = size if width >= 0 else -size
                new_h = size if height >= 0 else -size
                self.end_pos = QPointF(self.start_pos.x() + new_w, self.start_pos.y() + new_h)
                
            self._create_roi()
            
        # Reset
        self.start_pos = None
        self.end_pos = None
        self.current_path = None
        self.is_dragging = False
        self.is_moving = False
        self.preview_changed.emit()
            
    def _update_ellipse(self):
        path = QPainterPath()
        if self.start_pos and self.end_pos:
            rect = QRectF(self.start_pos, self.end_pos).normalized()
            path.addEllipse(rect)
        self.current_path = path
        self.preview_changed.emit()

    def _create_roi(self):
        if not self.start_pos or not self.end_pos:
            return
            
        rect = QRectF(self.start_pos, self.end_pos).normalized()
        
        # Minimum size check
        if rect.width() < 2 or rect.height() < 2:
            return
            
        # Update last size for fixed mode
        self.last_size = rect.size()
        
        # FIX: Coordinate Mapping (Scene -> Image)
        image_start = self.start_pos
        image_end = self.end_pos
        
        view = None
        if hasattr(self.session, 'main_window') and self.session.main_window:
             view = self.session.main_window.multi_view.get_active_view()
             
        if view and hasattr(view, 'get_image_coordinates'):
             image_start = view.get_image_coordinates(self.start_pos)
             image_end = view.get_image_coordinates(self.end_pos)
             print(f"DEBUG: Ellipse Mapped: Scene({self.start_pos.x():.1f}, {self.start_pos.y():.1f}) -> Image({image_start.x():.1f}, {image_start.y():.1f})")
        else:
             print("DEBUG: Ellipse used Raw Scene coordinates (No View found)")
            
        # Create ROI with scientific rigor (Store raw points for full-res mapping)
        roi = ROI(
            label=f"Ellipse_{len(self.session.roi_manager.get_all_rois()) + 1}",
            color=self.get_channel_color(self.tool_active_channel_idx),
            channel_index=self.tool_active_channel_idx
        )
        roi.reconstruct_from_points([image_start, image_end], roi_type="ellipse")
        
        # Calculate stats
        if self.session.channels:
            stats = calculate_intensity_stats(roi, self.session.channels)
            roi.stats.update(stats)
            
        self.session.roi_manager.add_roi(roi, undoable=True)
        self.committed.emit(f"Created ROI: {roi.label}")


class LineScanTool(AbstractTool):
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

    def mouse_press(self, scene_pos: QPointF, channel_index: int, context: dict = None):
        self.start_pos = scene_pos
        # --- USER REQUEST: Store scale for reverse mapping ---
        self.display_scale = context.get('display_scale', 1.0) if context else 1.0
        
        if self.fixed_size_mode:
            # If we have a stored vector, use it
            if self.last_vector:
                self.end_pos = scene_pos + self.last_vector
                self.is_moving = True
                self.is_dragging = False
                self._update_line()
            else:
                # Fallback default: 50px horizontal
                self.last_vector = QPointF(50.0, 0.0)
                self.end_pos = scene_pos + self.last_vector
                self.is_moving = True
                self.is_dragging = False
                self._update_line()
        else:
            # Normal Mode
            self.end_pos = scene_pos
            self.is_dragging = True
            self.is_moving = False
            self._update_line()

    def mouse_move(self, scene_pos: QPointF, modifiers=Qt.KeyboardModifier.NoModifier):
        if self.is_moving and self.last_vector:
            # Move the entire line (maintain vector)
            self.start_pos = scene_pos
            self.end_pos = scene_pos + self.last_vector
            self._update_line()
            
            # --- USER REQUEST: Emit full-resolution coordinates ---
            self.line_updated.emit(self.start_pos, self.end_pos)
            
        elif self.is_dragging:
            self.end_pos = scene_pos
            self._update_line()
            
            # --- USER REQUEST: Emit full-resolution coordinates for accurate analysis ---
            self.line_updated.emit(self.start_pos, self.end_pos)

    def mouse_release(self, scene_pos: QPointF, modifiers=Qt.KeyboardModifier.NoModifier):
        if self.is_moving:
            self.is_moving = False
            self._create_line_roi()
        elif self.is_dragging:
            self.end_pos = scene_pos
            self._update_line()
            
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

    def get_preview_path(self) -> QPainterPath:
        return self.current_path or QPainterPath()

    def _update_line(self):
        path = QPainterPath()
        if self.start_pos and self.end_pos:
            path.moveTo(self.start_pos)
            path.lineTo(self.end_pos)
        self.current_path = path
        self.preview_changed.emit()

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
            
        path = QPainterPath()
        path.moveTo(image_start)
        path.lineTo(image_end)
        
        roi = ROI(
            label=f"LineScan_{len(self.session.roi_manager.get_all_rois()) + 1}",
            path=path,
            color=QColor(255, 255, 0), # Yellow for line scans
            channel_index=-1 # Global line scan
        )
        # Mark as line scan for filtering
        roi.roi_type = "line_scan"
        roi.line_points = (image_start, image_end)
            
        self.session.roi_manager.add_roi(roi, undoable=True)
        self.committed.emit(f"Created Line Scan: {roi.label}")


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
        
    def mouse_press(self, scene_pos: QPointF, channel_index: int):
        self.start_pos = scene_pos
        self.end_pos = scene_pos
        self._update_rect()
        
    def mouse_move(self, scene_pos: QPointF, modifiers=Qt.KeyboardModifier.NoModifier):
        if self.start_pos:
            self.end_pos = scene_pos
            self._update_rect()
            
    def mouse_release(self, scene_pos: QPointF, modifiers=Qt.KeyboardModifier.NoModifier):
        pass
        
    def mouse_double_click(self, scene_pos: QPointF):
        # Execute Crop
        if self.start_pos and self.end_pos:
            rect = QRectF(self.start_pos, self.end_pos).normalized()
            
            # Minimum size check
            if rect.width() < 5 or rect.height() < 5:
                print("Crop area too small.")
                return
                
            r_tuple = (rect.x(), rect.y(), rect.width(), rect.height())
            
            from src.core.commands import CropCommand
            cmd = CropCommand(self.session, r_tuple)
            self.session.roi_manager.undo_stack.push(cmd)
            
            # Reset
            self.start_pos = None
            self.end_pos = None
            self.current_path = None
            self.preview_changed.emit()
            
    def _update_rect(self):
        path = QPainterPath()
        if self.start_pos and self.end_pos:
            rect = QRectF(self.start_pos, self.end_pos).normalized()
            path.addRect(rect)
        self.current_path = path
        self.preview_changed.emit()


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

    def mouse_press(self, scene_pos: QPointF, channel_index: int, context: dict = None):
        self.start_pos = scene_pos
        self.is_dragging = True
        self.tool_channel_index = channel_index
        self.current_rect = QRectF(scene_pos, scene_pos)
        self._update_preview()

    def mouse_move(self, scene_pos: QPointF, modifiers=Qt.KeyboardModifier.NoModifier):
        if not self.is_dragging:
            return
        self.current_rect = QRectF(self.start_pos, scene_pos).normalized()
        self._update_preview()

    def mouse_release(self, scene_pos: QPointF, modifiers=Qt.KeyboardModifier.NoModifier):
        if self.is_dragging and self.current_rect:
            self.selection_made.emit(self.current_rect, self.tool_channel_index)
        self.is_dragging = False
        self.current_rect = None
        self.preview_changed.emit()

    def _update_preview(self):
        self.preview_changed.emit()

    def get_preview_path(self) -> QPainterPath:
        path = QPainterPath()
        if self.current_rect:
            path.addRect(self.current_rect)
        return path
