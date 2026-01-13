from dataclasses import dataclass, field
from typing import List, Optional, Dict
import uuid
from PySide6.QtGui import QPainterPath, QColor, QUndoStack, QUndoCommand
from PySide6.QtCore import QObject, Signal, QPointF, QRectF

def create_smooth_path_from_points(points: List[QPointF], closed: bool = True) -> QPainterPath:
    """
    Generates a smooth QPainterPath from points using Catmull-Rom splines.
    """
    path = QPainterPath()
    if not points:
        return path
    
    path.moveTo(points[0])
    
    if len(points) < 3:
        for p in points[1:]:
            path.lineTo(p)
        if closed:
            path.closeSubpath()
        return path

    n = len(points)
    
    for i in range(n if closed else n - 1):
        if closed:
            p0 = points[(i - 1) % n]
            p1 = points[i]
            p2 = points[(i + 1) % n]
            p3 = points[(i + 2) % n]
        else:
            p0 = points[i - 1] if i > 0 else points[0]
            p1 = points[i]
            p2 = points[i + 1]
            p3 = points[i + 2] if i < n - 2 else points[n - 1]

        # Catmull-Rom to Cubic Bezier conversion
        # Tangent at p1 = 0.5 * (p2 - p0)
        # Tangent at p2 = 0.5 * (p3 - p1)
        
        t1 = (p2 - p0) * 0.5
        t2 = (p3 - p1) * 0.5
        
        c1 = p1 + t1 / 3
        c2 = p2 - t2 / 3
        
        path.cubicTo(c1, c2, p2)
        
    return path

@dataclass
class ROI:
    """
    Vector-based Region of Interest.
    Stores geometry as QPainterPath for resolution-independent rendering.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    label: str = "ROI"
    path: QPainterPath = field(default_factory=QPainterPath)
    color: QColor = field(default_factory=lambda: QColor(255, 255, 0, 200)) # Yellow default
    channel_index: int = -1 # The channel this ROI was primarily drawn on
    visible: bool = True
    selected: bool = False
    roi_type: str = "general" # e.g., "line_scan", "cell", "nucleus"
    line_points: Optional[tuple] = None # (start_qpointf, end_qpointf)
    is_dragging: bool = False # Temporary state for performance optimization
    
    # Unified Model Fields
    measurable: bool = True # Whether this ROI should be included in measurements/statistics
    export_with_image: bool = True # Whether this ROI should be rendered when exporting images
    
    # --- Scientific Rigor: Sub-pixel Accuracy ---
    # Store raw points for resolution-independent reconstruction
    points: List[QPointF] = field(default_factory=list)
    
    # Cache for statistics (to avoid re-calculating on every frame)
    stats: Dict[str, float] = field(default_factory=dict)
    
    # Flexible properties storage (e.g., shape for point counters, custom metadata)
    properties: Dict = field(default_factory=dict)

    def clone(self):
        """Creates a deep copy of the ROI."""
        new_roi = ROI(
            id=self.id,
            label=self.label,
            path=QPainterPath(self.path),
            color=QColor(self.color),
            channel_index=self.channel_index,
            visible=self.visible,
            selected=self.selected,
            roi_type=self.roi_type,
            line_points=self.line_points,
            points=[QPointF(p) for p in self.points],
            stats=self.stats.copy(),
            properties=self.properties.copy()
        )
        new_roi.measurable = self.measurable
        new_roi.export_with_image = self.export_with_image
        return new_roi

    def get_full_res_roi(self, display_scale: float) -> 'ROI':
        """
        Returns a new ROI mapped from display coordinates to full-resolution.
        display_scale = display_size / full_res_size (e.g., 0.2 for 5x downsampling).
        """
        if display_scale <= 0 or display_scale >= 1.0:
            return self.clone()
            
        new_roi = self.clone()
        
        # 1. Map points
        new_points = [QPointF(p.x() / display_scale, p.y() / display_scale) for p in self.points]
        
        # 2. Map path directly for complex shapes (like Magic Wand)
        from PySide6.QtGui import QTransform
        transform = QTransform().scale(1.0 / display_scale, 1.0 / display_scale)
        new_path = transform.map(self.path)
        
        new_roi.points = new_points
        new_roi.path = new_path
        
        # 3. Map line points if present
        if self.line_points:
            p1, p2 = self.line_points
            new_roi.line_points = (
                QPointF(p1.x() / display_scale, p1.y() / display_scale),
                QPointF(p2.x() / display_scale, p2.y() / display_scale)
            )
            
        return new_roi

    def reconstruct_from_points(self, points: List[QPointF], roi_type: str = None):
        """
        Reconstructs the QPainterPath from a list of points.
        This ensures that ROIs can be accurately mapped between coordinate systems.
        """
        import time
        from src.core.logger import Logger
        start_time = time.perf_counter()
        Logger.debug(f"[ROI.reconstruct_from_points] ENTER - ROI: {self.label}, Type: {roi_type or self.roi_type}, Points: {len(points)}")
        
        if roi_type:
            self.roi_type = roi_type
            
        self.points = points
        path = QPainterPath()
        
        if not points:
            self.path = path
            Logger.debug(f"[ROI.reconstruct_from_points] EXIT - Empty points list. Took {(time.perf_counter()-start_time)*1000:.2f}ms")
            return
            
        if self.roi_type in ["line_scan", "line", "arrow"] and len(points) >= 2:
            path.moveTo(points[0])
            path.lineTo(points[1])
            self.line_points = (points[0], points[1])
        elif self.roi_type == "rectangle" and len(points) >= 2:
            # points[0] is top-left, points[1] is bottom-right
            rect = QRectF(points[0], points[1]).normalized()
            path.addRect(rect)
        elif self.roi_type == "ellipse" and len(points) >= 2:
            rect = QRectF(points[0], points[1]).normalized()
            path.addEllipse(rect)
        elif self.roi_type == "polygon" and len(points) >= 3:
            # Use smoothed path for better visual quality
            # Lazy Smoothing: Disable during drag
            if not self.is_dragging:
                self.path = create_smooth_path_from_points(points, closed=True)
            else:
                # Simple polygon during drag
                path = QPainterPath()
                path.moveTo(points[0])
                for p in points[1:]:
                    path.lineTo(p)
                path.closeSubpath()
                self.path = path
            Logger.debug(f"[ROI.reconstruct_from_points] EXIT - Polygon reconstructed. Took {(time.perf_counter()-start_time)*1000:.2f}ms")
            return # Skip default assignment
        elif self.roi_type == "point" and len(points) >= 1:
            # Circular point with radius from properties or default
            r = self.properties.get('radius', 3.0)
            
            # Check for shape property
            shape = self.properties.get('shape', 'circle')
            center = points[0]
            x, y = center.x(), center.y()
            
            Logger.debug(f"[ROI.reconstruct_from_points] Reconstructing POINT: shape={shape}, radius={r}, center=({x:.1f}, {y:.1f})")
            
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
                p1 = QPointF(x, y - r)
                p2 = QPointF(x + r, y)
                p3 = QPointF(x, y + r)
                p4 = QPointF(x - r, y)
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
            else:
                path.addEllipse(center, r, r)
        elif self.roi_type == "text" and len(points) >= 1:
            # Text ROI: Use points[0] as anchor
            # For selection purposes, we create a small rect around the anchor
            # The actual text rendering handles the rest
            anchor = points[0]
            # Create a reasonable hit box for the text anchor
            # If we have font size in properties, use it to estimate
            font_size = self.properties.get('font_size', 12.0)
            text_len = len(self.properties.get('text', 'Text'))
            est_width = text_len * font_size * 0.6
            est_height = font_size * 1.5
            
            rect = QRectF(anchor.x(), anchor.y(), est_width, est_height)
            path.addRect(rect)
        elif self.roi_type == "arrow" and len(points) >= 2:
            # Arrow ROI: Main path is the line
            path.moveTo(points[0])
            path.lineTo(points[1])
            self.line_points = (points[0], points[1])
            # Note: Arrow head is purely visual in UnifiedGraphicsItem
        else:
            # Default fallback (e.g. for wand which generates path directly)
            Logger.debug(f"[ROI.reconstruct_from_points] Using default fallback for type: {self.roi_type}")
            pass
            
        self.path = path
        Logger.debug(f"[ROI.reconstruct_from_points] EXIT - Path assigned. Took {(time.perf_counter()-start_time)*1000:.2f}ms")

    @classmethod
    def from_dict(cls, data):
        """Deserializes ROI from a dictionary (JSON)."""
        from PySide6.QtGui import QPainterPath, QPolygonF, QColor
        from PySide6.QtCore import QPointF, QRectF
        
        roi_type = data.get("roi_type", "general")
        points = [QPointF(pt[0], pt[1]) for pt in data.get("points", [])]
        
        # 1. Reconstruct Path
        path = QPainterPath()
        polygons_data = data.get("polygons", [])
        
        if polygons_data:
            # Restore complex paths (Wand, etc.)
            for poly_pts in polygons_data:
                qpoly = QPolygonF([QPointF(pt[0], pt[1]) for pt in poly_pts])
                path.addPolygon(qpoly)
        elif points:
            # Fallback to points reconstruction
            qpoly = QPolygonF(points)
            path.addPolygon(qpoly)
            if roi_type not in ["line", "line_scan", "arrow"]:
                path.closeSubpath()
        else:
            # Fallback to legacy bounds if nothing else exists
            bounds = data.get("bounds", [0, 0, 10, 10]) # x, y, w, h
            x, y, w, h = bounds
            shape_type = data.get("shape_type", "rect")
            if shape_type == "ellipse":
                path.addEllipse(x, y, w, h)
            else:
                path.addRect(x, y, w, h)
            
        roi = cls(
            id=data.get("id", str(uuid.uuid4())),
            label=data.get("label", "ROI"),
            path=path,
            color=QColor(data.get("color", "#FFFF00")),
            channel_index=data.get("channel_index", -1),
            visible=data.get("visible", True),
            selected=data.get("selected", False),
            roi_type=roi_type,
            points=points,
            stats=data.get("stats", {}),
            properties=data.get("properties", {})
        )
        roi.measurable = data.get("measurable", True)
        roi.export_with_image = data.get("export_with_image", True)
        
        if "line_points" in data:
            lp = data["line_points"]
            roi.line_points = (QPointF(lp[0][0], lp[0][1]), QPointF(lp[1][0], lp[1][1]))
            
        # Final reconstruction for specialized types to ensure geometry consistency
        if roi_type in ["rectangle", "ellipse", "arrow", "line", "line_scan", "point", "text"]:
            roi.reconstruct_from_points(points)
            
        return roi

class AddRoiCommand(QUndoCommand):
    def __init__(self, manager, roi: ROI):
        super().__init__(f"Add ROI {roi.label}")
        self.manager = manager
        self.roi = roi

    def redo(self):
        # Direct call to internal add (avoids recursion)
        self.manager._add_roi_internal(self.roi)

    def undo(self):
        self.manager._remove_roi_internal(self.roi.id)

class RemoveRoiCommand(QUndoCommand):
    def __init__(self, manager, roi: ROI):
        super().__init__(f"Remove ROI {roi.label}")
        self.manager = manager
        self.roi = roi

    def redo(self):
        self.manager._remove_roi_internal(self.roi.id)

    def undo(self):
        self.manager._add_roi_internal(self.roi)

class MoveRoiCommand(QUndoCommand):
    def __init__(self, manager, roi_id, old_path, new_path):
        super().__init__("Move ROI")
        self.manager = manager
        self.roi_id = roi_id
        self.old_path = old_path
        self.new_path = new_path

    def redo(self):
        if self.roi_id in self.manager._rois:
            self.manager._rois[self.roi_id].path = self.new_path
            self.manager.roi_updated.emit(self.manager._rois[self.roi_id])

    def undo(self):
        if self.roi_id in self.manager._rois:
            self.manager._rois[self.roi_id].path = self.old_path
            self.manager.roi_updated.emit(self.manager._rois[self.roi_id])

class ClearRoisCommand(QUndoCommand):
    def __init__(self, manager):
        super().__init__("Clear All ROIs")
        self.manager = manager
        self.rois = list(manager._rois.values())

    def redo(self):
        for roi in self.rois:
            self.manager._remove_roi_internal(roi.id)

    def undo(self):
        for roi in self.rois:
            self.manager._add_roi_internal(roi)

class RoiManager(QObject):
    """
    Manages the collection of ROIs.
    Handles Undo/Redo, Selection, and Updates.
    """
    roi_added = Signal(ROI)
    roi_removed = Signal(str) # ROI ID
    roi_updated = Signal(ROI)
    selection_changed = Signal()

    def __init__(self, undo_stack: Optional[QUndoStack] = None):
        super().__init__()
        self._rois: Dict[str, ROI] = {}
        self._selected_ids: set = set()
        self.undo_stack = undo_stack if undo_stack else QUndoStack(self)

    def get_roi(self, roi_id: str) -> Optional[ROI]:
        """Returns the ROI with the given ID, or None if not found."""
        return self._rois.get(roi_id)

    def add_roi(self, roi: ROI, undoable: bool = False):
        """Adds an ROI. Set undoable=True for user actions."""
        from src.core.logger import Logger
        Logger.debug(f"[RoiManager.add_roi] ENTER - ROI: {roi.label} ({roi.id}), undoable={undoable}")
        if undoable:
            self.undo_stack.push(AddRoiCommand(self, roi))
        else:
            self._add_roi_internal(roi)
        Logger.debug(f"[RoiManager.add_roi] EXIT")

    def _add_roi_internal(self, roi: ROI):
        """Internal method for adding ROI without Undo stack modification."""
        from src.core.logger import Logger
        if roi.id in self._rois:
            Logger.debug(f"[RoiManager._add_roi_internal] ROI {roi.id} already exists, skipping.")
            return
        self._rois[roi.id] = roi
        Logger.debug(f"[RoiManager._add_roi_internal] Emitting roi_added signal for {roi.id}")
        self.roi_added.emit(roi)
        Logger.debug(f"[RoiManager._add_roi_internal] Done")

    def remove_roi(self, roi_id: str, undoable: bool = False):
        """Removes an ROI. Set undoable=True for user actions."""
        if roi_id not in self._rois:
            return
            
        if undoable:
            roi = self._rois[roi_id]
            self.undo_stack.push(RemoveRoiCommand(self, roi))
        else:
            self._remove_roi_internal(roi_id)

    def _remove_roi_internal(self, roi_id: str):
        """Internal method for removing ROI without Undo stack modification."""
        if roi_id in self._rois:
            del self._rois[roi_id]
            if roi_id in self._selected_ids:
                self._selected_ids.remove(roi_id)
            self.roi_removed.emit(roi_id)

    def undo(self):
        self.undo_stack.undo()

    def redo(self):
        self.undo_stack.redo()

    def get_all_rois(self) -> List[ROI]:
        return list(self._rois.values())

    def update_roi_path(self, roi_id: str, new_path: QPainterPath, is_dragging: bool = False):
        """Updates the path of an existing ROI with Undo support."""
        if roi_id in self._rois:
            roi = self._rois[roi_id]
            roi.is_dragging = is_dragging # Set dragging state
            old_path = roi.path
            if old_path != new_path:
                self.undo_stack.push(MoveRoiCommand(self, roi_id, old_path, new_path))

    def get_selected_ids(self) -> List[str]:
        return list(self._selected_ids)

    def clear(self, undoable: bool = False):
        """Clears all ROIs."""
        if not self._rois:
            return
            
        if undoable:
            self.undo_stack.push(ClearRoisCommand(self))
        else:
            to_remove = list(self._rois.keys())
            for rid in to_remove:
                self._remove_roi_internal(rid)
    
    def serialize_rois(self) -> List[dict]:
        """Serializes all ROIs to a list of dicts using full-resolution coordinates."""
        serialized = []
        for roi in self._rois.values():
            # 1. Convert path to subpath polygons to preserve complex shapes (Magic Wand)
            polygons_data = []
            for poly in roi.path.toSubpathPolygons():
                polygons_data.append([[pt.x(), pt.y()] for pt in poly])
            
            # 2. Main points for reconstruction (if available)
            points_data = [[pt.x(), pt.y()] for pt in roi.points]
            
            data = {
                "id": roi.id,
                "label": roi.label,
                "color": roi.color.name(), # Hex
                "roi_type": roi.roi_type,
                "points": points_data,
                "polygons": polygons_data, # Full path data
                "visible": roi.visible,
                "measurable": roi.measurable,
                "export_with_image": roi.export_with_image,
                "properties": roi.properties,
                "stats": roi.stats
            }
            
            if roi.line_points:
                p1, p2 = roi.line_points
                data["line_points"] = [[p1.x(), p1.y()], [p2.x(), p2.y()]]
            
            serialized.append(data)
        return serialized

    def deserialize_rois(self, data_list: List[dict]):
        """Restores ROIs from a list of dicts."""
        self.clear()
        for data in data_list:
            try:
                roi = ROI.from_dict(data)
                self._add_roi_internal(roi)
            except Exception as e:
                from src.core.logger import Logger
                Logger.error(f"Failed to deserialize ROI: {e}")

    def select_all(self):
        """Selects all ROIs."""
        all_ids = list(self._rois.keys())
        self.set_selected_ids(all_ids)

    def set_selection(self, roi_id: str, clear_others: bool = True):
        if clear_others:
            # Iterate over a copy to avoid runtime error if set changes
            for rid in list(self._selected_ids):
                if rid in self._rois:
                    self._rois[rid].selected = False
                    self.roi_updated.emit(self._rois[rid])
            self._selected_ids.clear()
        
        if roi_id in self._rois:
            self._rois[roi_id].selected = True
            self._selected_ids.add(roi_id)
            self.roi_updated.emit(self._rois[roi_id])
        
        self.selection_changed.emit()

    def set_selected_ids(self, ids: List[str]):
        """Sets the selection to the given list of IDs."""
        new_set = set(ids)
        print(f"DEBUG: [RoiManager] set_selected_ids: {len(new_set)} IDs")
        if new_set == self._selected_ids:
            print("DEBUG: [RoiManager] Selection unchanged")
            return
            
        # Update internal state
        # Deselect old ones not in new set
        for rid in list(self._selected_ids):
            if rid not in new_set and rid in self._rois:
                self._rois[rid].selected = False
                # self.roi_updated.emit(self._rois[rid]) # Optional: might be too noisy
        
        # Select new ones
        for rid in new_set:
            if rid in self._rois:
                self._rois[rid].selected = True
                # self.roi_updated.emit(self._rois[rid])

        self._selected_ids = new_set
        self.selection_changed.emit()

    def offset_rois(self, dx: float, dy: float, bounds_rect: tuple):
        """
        Offsets all ROIs by (dx, dy) and filters out those outside bounds_rect.
        bounds_rect: (0, 0, width, height)
        """
        from PySide6.QtCore import QRectF
        
        bound_qrect = QRectF(*bounds_rect)
        to_remove = []
        
        # We need to list keys because we might delete during iteration (if using remove_roi)
        # But here we collect to_remove first.
        for roi_id, roi in self._rois.items():
            # Translate path
            roi.path.translate(dx, dy)
            
            # Check bounds
            if not roi.path.intersects(bound_qrect):
                to_remove.append(roi_id)
            else:
                # Notify update for position change
                self.roi_updated.emit(roi)
                
        # Remove out-of-bounds
        for roi_id in to_remove:
            self._remove_roi_internal(roi_id)

    def set_rois(self, rois):
        """
        Replaces the current ROI collection.
        Input 'rois' can be:
        1. A dict of {roi_id: ROI_Object} (used by Undo/Redo within session)
        2. A list of dicts (serialized data) (used by Project Loading / Scene Switching)
        """
        if isinstance(rois, list):
            # List of Serialized Dicts (Scene Data)
            self.deserialize_rois(rois)
        elif isinstance(rois, dict):
            # Dict of ROI objects (Undo Stack)
            self.clear()
            for roi in rois.values():
                self._add_roi_internal(roi)
        else:
            from src.core.logger import Logger
            Logger.warning(f"[RoiManager.set_rois] Unknown input type: {type(rois)}")
