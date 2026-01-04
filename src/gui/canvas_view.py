from PySide6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QGraphicsPathItem, QLabel, QGraphicsItem, QApplication, QGraphicsRectItem, QGraphicsObject, QGraphicsLineItem
from PySide6.QtGui import QPixmap, QPainter, QPen, QColor, QBrush, QPainterPath, QFont, QTransform, QPalette, QPainterPathStroker, QKeySequence
from PySide6.QtCore import Qt, Signal, QRectF, QPoint, QPointF, QTimer, QObject
from PySide6.QtOpenGLWidgets import QOpenGLWidget
import numpy as np
import qimage2ndarray
import cv2
import time
from src.core.language_manager import tr
from src.core.logger import Logger
from src.core.roi_model import ROI
from src.core.data_model import GraphicAnnotation
from src.gui.tools import RectangleSelectionTool, PolygonSelectionTool, EllipseSelectionTool, LineScanTool
from src.gui.rendering.qt_engine import QtRenderEngine
from src.gui.rendering.engine import StyleConfigCenter

class RoiHandleItem(QGraphicsRectItem):
    """Handle for resizing/manipulating ROIs."""
    def __init__(self, parent, position_flag, size=10):
        # position_flag: 'top-left', 'top-right', 'bottom-left', 'bottom-right', 'top', 'bottom', 'left', 'right'
        super().__init__(-size/2, -size/2, size, size, parent)
        self.position_flag = position_flag
        self.setBrush(QBrush(QColor("white")))
        self.setPen(QPen(QColor("black"), 1))
        self.setZValue(10) # Ensure handles are above parent items
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False) 
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True) # Keep constant size on screen
        self.setAcceptHoverEvents(True)
        self.setCursor(self._get_cursor())
        self.setVisible(False) # Hidden by default until parent is selected

    def _get_cursor(self):
        if self.position_flag in ['top-left', 'bottom-right', 'start', 'end']:
            return Qt.CursorShape.SizeFDiagCursor
        elif self.position_flag in ['top-right', 'bottom-left']:
            return Qt.CursorShape.SizeBDiagCursor
        elif self.position_flag in ['top', 'bottom']:
            return Qt.CursorShape.SizeVerCursor
        elif self.position_flag in ['left', 'right']:
            return Qt.CursorShape.SizeHorCursor
        elif self.position_flag == 'rotate':
            return Qt.CursorShape.PointingHandCursor # Or custom rotate cursor if available
        return Qt.CursorShape.ArrowCursor

    def paint(self, painter, option, widget):
        if self.position_flag == 'rotate':
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            
            # Draw black circle with white border
            # Size is already set via __init__ (should be larger)
            pen = QPen(QColor("white"), 1.5) # 1.5x thickness
            painter.setPen(pen)
            painter.setBrush(QBrush(QColor("black")))
            rect = self.rect()
            painter.drawEllipse(rect)
            
            # Draw Circular Arrow (White)
            # ↻ (U+21BB)
            font = QFont("Arial", int(rect.height() * 0.9)) # Slightly smaller to fit
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(QPen(QColor("white")))
            
            # Center the text
            painter.drawText(rect.adjusted(0, -2, 0, 0), Qt.AlignmentFlag.AlignCenter, "↻")
        else:
            super().paint(painter, option, widget)

    def shape(self):
        # Fat Finger Logic for interaction (10px tolerance)
        # QGraphicsRectItem uses rect(), not path()
        path = QPainterPath()
        path.addRect(self.rect())
        if path.isEmpty(): return path
        
        # Create a wider stroke for hit testing
        stroker = QPainterPathStroker()
        stroker.setWidth(4) # Reduced from 10 to 4 to prevent overlapping
        stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
        stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        stroke_path = stroker.createStroke(path)
        
        # Combine with original path (so fill area is also clickable)
        return stroke_path + path

    def mousePressEvent(self, event):
        # Consume event to prevent parent from getting it (which would be move)
        self.start_pos = event.scenePos()
        self.parentItem().handle_press(self.position_flag, event.scenePos())
        event.accept()

    def mouseMoveEvent(self, event):
        self.parentItem().handle_move(self.position_flag, event.scenePos())
        event.accept()

    def mouseReleaseEvent(self, event):
        self.parentItem().handle_release(self.position_flag, event.scenePos())
        event.accept()

class RoiGraphicsItem(QGraphicsPathItem):
    """Custom GraphicsItem for ROI to handle interactions and sync."""
    def __init__(self, roi: ROI, parent=None, display_scale=1.0):
        # We need to scale the path if the scene is downsampled but ROI is full res
        self.display_scale = display_scale
        scaled_path = self._scale_path(roi.path, display_scale)
        super().__init__(scaled_path, parent)
        self.roi_id = roi.id
        self.roi_color = roi.color # Store the base color
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True) # Allow moving by default
        self.setAcceptHoverEvents(True)
        self._is_hovered = False
        
        # Rendering Engine
        self.engine = QtRenderEngine()
        self.style_center = StyleConfigCenter()
        
        # Resizing Handles
        self.handles = {}
        self._create_handles()
        
        # State for resizing
        self._is_resizing = False
        self._start_resize_rect = None
        self._start_resize_path = None
        
        # Apply visual style immediately
        self.update_appearance()
        
        # Sync Throttling
        self._last_sync_time = 0

    def shape(self):
        """Override shape to increase hit area for easier selection."""
        path = self.path()
        stroker = QPainterPathStroker()
        stroker.setWidth(4) # Reduced from 10 to 4 to prevent overlapping
        return stroker.createStroke(path) + path # Stroke + Fill

    def _create_handles(self):
        flags = ['top-left', 'top-right', 'bottom-left', 'bottom-right', 'top', 'bottom', 'left', 'right', 'rotate']
        for flag in flags:
            size = 12 if flag == 'rotate' else 10 # 20% larger for rotate handle
            handle = RoiHandleItem(self, flag, size=size)
            # Style override for rotate handle
            if flag == 'rotate':
                # Style handled in paint()
                pass
            self.handles[flag] = handle
            
        # Initialize Reference Lines (Smart Guides)
        # External: Dashed #888888
        pen_ext = QPen(QColor("#888888"), 1, Qt.PenStyle.DashLine)
        self.guide_ext_h = QGraphicsLineItem(self)
        self.guide_ext_h.setPen(pen_ext)
        self.guide_ext_h.hide()
        self.guide_ext_v = QGraphicsLineItem(self)
        self.guide_ext_v.setPen(pen_ext)
        self.guide_ext_v.hide()
        
        # Internal: Solid #CCCCCC
        pen_int = QPen(QColor("#CCCCCC"), 1, Qt.PenStyle.SolidLine)
        self.guide_int_h = QGraphicsLineItem(self)
        self.guide_int_h.setPen(pen_int)
        self.guide_int_h.hide()
        self.guide_int_v = QGraphicsLineItem(self)
        self.guide_int_v.setPen(pen_int)
        self.guide_int_v.hide()

    def _update_handles_pos(self):
        rect = self.path().boundingRect()
        self.handles['top-left'].setPos(rect.topLeft())
        self.handles['top-right'].setPos(rect.topRight())
        self.handles['bottom-left'].setPos(rect.bottomLeft())
        self.handles['bottom-right'].setPos(rect.bottomRight())
        self.handles['top'].setPos(QPointF(rect.center().x(), rect.top()))
        self.handles['bottom'].setPos(QPointF(rect.center().x(), rect.bottom()))
        self.handles['left'].setPos(QPointF(rect.left(), rect.center().y()))
        self.handles['right'].setPos(QPointF(rect.right(), rect.center().y()))
        
        # Rotate handle: placed above top handle
        self.handles['rotate'].setPos(QPointF(rect.center().x(), rect.top() - 20))

    def handle_press(self, flag, scene_pos):
        self._is_resizing = True
        self._start_resize_rect = self.path().boundingRect()
        self._start_resize_path = self.path()
        self._start_mouse_pos = scene_pos
        self._resize_flag = flag
        self._start_rotation = self.rotation()
        
        # Estimate initial angle for Internal Guides
        self._initial_angle = 0.0
        path = self.path()
        if path.elementCount() in [4, 5]: # Rectangle (5 points if closed)
            p0 = path.elementAt(0)
            p1 = path.elementAt(1)
            # Check if it's a MoveTo/LineTo sequence
            import math
            dx = p1.x - p0.x
            dy = p1.y - p0.y
            self._initial_angle = math.degrees(math.atan2(dy, dx))
            
        # Initialize Guides Visibility (Fade In logic can be added here)
        self.guide_ext_h.setVisible(True)
        self.guide_ext_v.setVisible(True)
        self.guide_int_h.setVisible(True)
        self.guide_int_v.setVisible(True)
        
        # Set opacity for "Fade In" effect
        # Simple implementation: Instant show
        for item in [self.guide_ext_h, self.guide_ext_v, self.guide_int_h, self.guide_int_v]:
            item.setOpacity(0.0)
            # Animate opacity to 1.0? 
            # We don't have a QObject for property animation.
            # Just set to 0.8
            item.setOpacity(0.8)

    def handle_move(self, flag, scene_pos):
        if not self._is_resizing:
            return
            
        import math
        
        # Update Guides
        rect = self.path().boundingRect()
        center = rect.center()
        
        # External Guides (Global Axis)
        # Large length
        L = 100000
        self.guide_ext_h.setLine(center.x() - L, center.y(), center.x() + L, center.y())
        self.guide_ext_v.setLine(center.x(), center.y() - L, center.x(), center.y() + L)
        
        current_angle = self._initial_angle
        
        if flag == 'rotate':
            # Calculate rotation angle
            # Center of rotation is the CENTER of the bounding rect at start
            rect_start = self._start_resize_rect
            center_start = rect_start.center()
            
            # Vector from center to mouse
            current_pos_local = self.mapFromScene(scene_pos)
            
            # Angle of mouse relative to center
            angle_mouse = math.degrees(math.atan2(current_pos_local.y() - center_start.y(), current_pos_local.x() - center_start.x()))
            # Angle of start pos relative to center
            start_pos_local = self.mapFromScene(self._start_mouse_pos)
            angle_start = math.degrees(math.atan2(start_pos_local.y() - center_start.y(), start_pos_local.x() - center_start.x()))
            
            delta_angle = angle_mouse - angle_start
            current_angle = self._initial_angle + delta_angle
            
            # Apply rotation to original path
            transform = QTransform()
            transform.translate(center_start.x(), center_start.y())
            transform.rotate(delta_angle)
            transform.translate(-center_start.x(), -center_start.y())
            
            new_path = transform.map(self._start_resize_path)
            self.prepareGeometryChange()
            self.setPath(new_path)
            self._update_handles_pos()
            
            # Update Internal Guides
            # Rotate lines around center
            # Horizontal Guide (Local X)
            t_int = QTransform()
            t_int.translate(center_start.x(), center_start.y()) # Use start center as pivot (or current center? They are same for rotation)
            t_int.rotate(current_angle)
            t_int.translate(-center_start.x(), -center_start.y())
            
            p1_h = t_int.map(QPointF(center_start.x() - L, center_start.y()))
            p2_h = t_int.map(QPointF(center_start.x() + L, center_start.y()))
            self.guide_int_h.setLine(p1_h.x(), p1_h.y(), p2_h.x(), p2_h.y())
            
            p1_v = t_int.map(QPointF(center_start.x(), center_start.y() - L))
            p2_v = t_int.map(QPointF(center_start.x(), center_start.y() + L))
            self.guide_int_v.setLine(p1_v.x(), p1_v.y(), p2_v.x(), p2_v.y())
            
            # Real-time sync for rotation
            # Note: self.pos() is offset. self.path() is local.
            # Scene Path = self.sceneTransform().map(self.path())
            new_path_scene = self.sceneTransform().map(self.path())
            self._notify_roi_moved(new_path_scene)
            
            return

        # Resize Logic
        # Calculate new bounding rect based on handle movement
        # Use Local Coordinate System (Unrotate -> Resize -> Rotate) to support "Internal Crop"
        
        rect_start = self._start_resize_rect
        center_start = rect_start.center()
        
        # 1. Unrotate path to align with axes
        t_unrotate = QTransform()
        t_unrotate.translate(center_start.x(), center_start.y())
        t_unrotate.rotate(-self._initial_angle)
        t_unrotate.translate(-center_start.x(), -center_start.y())
        
        path_unrotated = t_unrotate.map(self._start_resize_path)
        rect_unrotated = path_unrotated.boundingRect()
        
        # 2. Project mouse delta onto local axes
        current_pos_local = self.mapFromScene(scene_pos)
        start_pos_local = self.mapFromScene(self._start_mouse_pos)
        delta_local = current_pos_local - start_pos_local
        
        rad = math.radians(-self._initial_angle)
        dx_local = delta_local.x() * math.cos(rad) - delta_local.y() * math.sin(rad)
        dy_local = delta_local.x() * math.sin(rad) + delta_local.y() * math.cos(rad)
        
        # 3. Resize unrotated rect
        new_rect_unrotated = QRectF(rect_unrotated)
        
        if 'left' in flag:
            new_rect_unrotated.setLeft(rect_unrotated.left() + dx_local)
        if 'right' in flag:
            new_rect_unrotated.setRight(rect_unrotated.right() + dx_local)
        if 'top' in flag:
            new_rect_unrotated.setTop(rect_unrotated.top() + dy_local)
        if 'bottom' in flag:
            new_rect_unrotated.setBottom(rect_unrotated.bottom() + dy_local)
            
        # Avoid negative size
        if new_rect_unrotated.width() < 1: new_rect_unrotated.setWidth(1)
        if new_rect_unrotated.height() < 1: new_rect_unrotated.setHeight(1)
        
        # 4. Scale Transform (on unrotated rect)
        sx = new_rect_unrotated.width() / rect_unrotated.width() if rect_unrotated.width() > 0 else 1
        sy = new_rect_unrotated.height() / rect_unrotated.height() if rect_unrotated.height() > 0 else 1
        
        t_scale = QTransform()
        t_scale.translate(rect_unrotated.x(), rect_unrotated.y())
        t_scale.scale(sx, sy)
        t_scale.translate(-rect_unrotated.x(), -rect_unrotated.y())
        
        # Apply scaling to unrotated path (handles translation of edges too)
        # Note: We map the path, not just rect, to preserve shape details if any
        # But we assume the unrotated path is roughly the unrotated rect
        
        # 5. Handle Translation implied by resizing (e.g. dragging Top moves the Top edge)
        # The t_scale above scales around the center of rect_unrotated? No, rect_unrotated.x()/y() is TopLeft.
        # So it scales around TopLeft.
        # If we drag Right, TopLeft is fixed. Scale around TL works.
        # If we drag Left, TopLeft moves.
        # We need to map the new rect to the old rect logic properly.
        # Actually, simpler: just map unrotated rect to new unrotated rect.
        
        t_final_unrotated = QTransform()
        t_final_unrotated.translate(new_rect_unrotated.left(), new_rect_unrotated.top())
        t_final_unrotated.scale(sx, sy)
        t_final_unrotated.translate(-rect_unrotated.left(), -rect_unrotated.top())
        
        path_scaled_unrotated = t_final_unrotated.map(path_unrotated)
        
        # 6. Rotate back
        t_rotate = QTransform()
        t_rotate.translate(center_start.x(), center_start.y())
        t_rotate.rotate(self._initial_angle)
        t_rotate.translate(-center_start.x(), -center_start.y())
        
        new_path = t_rotate.map(path_scaled_unrotated)
        
        self.prepareGeometryChange()
        self.setPath(new_path)
        self._update_handles_pos()
        
        # Update Internal Guides for Resize (maintain initial angle)
        # Center has likely moved
        center_new = self.path().boundingRect().center() 
        t_int = QTransform()
        t_int.translate(center_new.x(), center_new.y())
        t_int.rotate(self._initial_angle)
        t_int.translate(-center_new.x(), -center_new.y())
        
        p1_h = t_int.map(QPointF(center_new.x() - L, center_new.y()))
        p2_h = t_int.map(QPointF(center_new.x() + L, center_new.y()))
        self.guide_int_h.setLine(p1_h.x(), p1_h.y(), p2_h.x(), p2_h.y())
        
        p1_v = t_int.map(QPointF(center_new.x(), center_new.y() - L))
        p2_v = t_int.map(QPointF(center_new.x(), center_new.y() + L))
        self.guide_int_v.setLine(p1_v.x(), p1_v.y(), p2_v.x(), p2_v.y())

        # Real-time sync for resize
        new_path_scene = self.sceneTransform().map(self.path())
        self._notify_roi_moved(new_path_scene)

    def handle_release(self, flag, scene_pos):
        self._is_resizing = False
        
        # Hide Guides
        self.guide_ext_h.setVisible(False)
        self.guide_ext_v.setVisible(False)
        self.guide_int_h.setVisible(False)
        self.guide_int_v.setVisible(False)
        
        # Commit change
        new_path_scene = self.sceneTransform().map(self.path())
        # Reset local pos if any (though we modified path in place, pos should still be 0,0)
        self.setPos(0, 0)
        QTimer.singleShot(0, lambda: self._notify_roi_moved(new_path_scene, force=True))

    def _scale_path(self, path, scale):
        if scale >= 1.0:
            return path
        transform = QTransform()
        transform.scale(scale, scale)
        return transform.map(path)

    def shape(self):
        """
        Custom shape to make selection easier (wider hit area).
        Especially important for thin lines like Arrows.
        """
        path = super().shape()
        
        # If it's a thin path (Arrow/Line/Polygon), widen it for hit testing
        # Rect/Ellipse usually have area, but if unfilled, we still want to select the border easily.
        # But QGraphicsPathItem.shape() returns the fill + stroke.
        
        # Use QPainterPathStroker to create a "fat" path
        stroker = QPainterPathStroker()
        stroker.setWidth(10.0) # 10px tolerance (5px each side)
        stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
        stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        
        wide_path = stroker.createStroke(self.path())
        
        # Merge with original path (in case it has fill)
        return path + wide_path

    def update_appearance(self, is_selected=None):
        try:
            if is_selected is None:
                is_selected = self.isSelected()
                
            pen = self.pen()
            # Ensure pen is cosmetic so it doesn't scale with zoom
            pen.setCosmetic(True) 
            
            if is_selected:
                pen.setColor(QColor("#FF0000")) # Red for selected
                pen.setStyle(Qt.PenStyle.SolidLine)
                pen.setWidth(2)
                # Show handles
                self._update_handles_pos()
                for h in self.handles.values():
                    h.setVisible(True)
            elif self._is_hovered:
                pen.setColor(QColor("#00FFFF")) # Cyan for hover
                pen.setStyle(Qt.PenStyle.SolidLine)
                pen.setWidth(4) # Thicker for hover
                # Optional: Add shadow effect or glow?
                # For now, just thicker line is good.
                for h in self.handles.values():
                    h.setVisible(False)
            else:
                # Use the ROI's assigned color for normal state
                pen.setColor(self.roi_color)
                pen.setStyle(Qt.PenStyle.DashLine)
                pen.setDashPattern([3.0, 2.5]) # 6px dash, 5px gap (with 2px width)
                pen.setWidth(2)
                for h in self.handles.values():
                    h.setVisible(False)
            self.setPen(pen)
        except Exception:
            pass

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedChange:
            self.update_appearance(is_selected=bool(value))
        
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged and self.scene():
            # Sync Logic for Dragging
            # Check if this change is due to user interaction (selected + moving)
            # AND NOT due to internal update (to prevent loops)
            if self.isSelected() and not getattr(self, '_is_resizing', False) and not getattr(self, '_is_updating', False):
                 # Bake current transform (pos) into path for sync
                 # Note: self.pos() is the offset. self.path() is local.
                 # Scene Path = self.sceneTransform().map(self.path())
                 new_path_scene = self.sceneTransform().map(self.path())
                 self._notify_roi_moved(new_path_scene)
                     
        return super().itemChange(change, value)

    @property
    def is_dragging(self):
        """Returns True if the item is currently being dragged by the user."""
        return getattr(self, '_is_actually_dragging', False) or getattr(self, '_is_resizing', False)

    def mousePressEvent(self, event):
        if self._is_resizing:
            return

        # 1. Record State
        self._drag_start_pos = event.pos() 
        self._drag_start_scene_pos = event.scenePos()
        self._last_scene_pos = event.scenePos()
        self._drag_start_time = time.time() * 1000 # ms
        self._is_actually_dragging = False
        self._pending_deselect = False
        self._copied_in_drag = False # Reset copy flag
        
        # 2. Exclusive Selection Logic (Fix for ROI Selection Anomaly)
        # Use QApplication.keyboardModifiers() for reliability across platforms
        modifiers = QApplication.keyboardModifiers()
        is_ctrl = bool(modifiers & Qt.KeyboardModifier.ControlModifier)
        is_shift = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)
        
        # Debug Log for ROI Selection
        print(f"ROI Click: Modifiers={modifiers}, Ctrl={is_ctrl}, Shift={is_shift}, Current Selected={self.isSelected()}")

        if is_ctrl:
            # Multi-selection Mode with Support for Dragging Selected Items
            
            # If item is ALREADY selected, we might want to Drag it (Move) OR Deselect it (Toggle).
            # We cannot decide on Press. So we defer deselect to Release if no drag happened.
            if self.isSelected():
                self._pending_deselect = True
                print(f"DEBUG: Ctrl Click on Selected Item. Deferring deselect to Release to allow Drag.")
                event.accept()
                # We do NOT call super() yet? No, we need to allow Drag.
                # If we return here, drag won't start?
                # QGraphicsItem drag logic starts in mouseMoveEvent.
                # So we must NOT return?
                # Actually, standard QGraphicsItem handles selection internally.
                # We are overriding it.
                
                # To allow drag, we must accept event and let mouseMoveEvent happen.
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
                return 

            # If not selected, standard Smart Stack Logic
            scene_items = self.scene().items(event.scenePos()) if self.scene() else []
            # Filter for ROI/Annotation items
            target_items = [i for i in scene_items if type(i).__name__ in ['RoiGraphicsItem', 'AnnotationGraphicsItem']]
            
            if target_items:
                # Check if any is unselected
                any_unselected = any(not item.isSelected() for item in target_items)
                
                if any_unselected:
                    print(f"DEBUG: Ctrl Click on stack of {len(target_items)}. Adding unselected items.")
                    for item in target_items:
                        if not item.isSelected():
                            item.setSelected(True)
                else:
                    # All selected. We are clicking one of them.
                    # This case should be handled by the "if self.isSelected()" block above if we are the top one.
                    # But if we are clicking a stack, maybe we want to deselect the specific one we clicked?
                    # Or defer deselect for ALL?
                    pass 
            else:
                 # Should not happen if we clicked self, but fallback
                 self.setSelected(not self.isSelected())
                
        elif is_shift:
             # Additive Mode
             self.setSelected(True)
        else:
             # Standard Click: Exclusive Selection
             # If we are NOT already selected, clear others.
             # Note: This implementation clears others immediately on press, which simplifies single selection.
             if self.scene():
                 # Block signals to prevent excessive updates during clearance
                 self.scene().blockSignals(True)
                 for item in self.scene().selectedItems():
                     if item != self:
                         item.setSelected(False)
                 self.scene().blockSignals(False)
             self.setSelected(True)
        
        # 4. Accept (Grab Mouse to prevent View Pan)
        event.accept()
        
        # 5. Cursor
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        
        # We handle selection manually, so we don't call super().mousePressEvent(event)
        # This prevents default QGraphicsItem selection logic from interfering.
        # super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._is_resizing:
            return
            
        if not self._drag_start_scene_pos:
            return

        # 1. Anti-jitter / Intent Recognition
        if not self._is_actually_dragging:
            delta = (event.scenePos() - self._drag_start_scene_pos).manhattanLength()
            # Threshold: 3px (Anti-jitter)
            if delta > 3:
                self._is_actually_dragging = True
            else:
                return # Ignore small movements

        # --- Copy on Drag Logic (Alt Key) ---
        # Use event modifiers for reliability instead of global state
        # Fix: Check BOTH event modifiers and global modifiers to prevent sticky key issues
        # or incorrect event flags.
        is_alt_event = bool(event.modifiers() & Qt.KeyboardModifier.AltModifier)
        is_alt_global = bool(QApplication.keyboardModifiers() & Qt.KeyboardModifier.AltModifier)
        # Strict check: Alt must be pressed according to Event
        is_alt = is_alt_event
        
        # Debug drag copy state
        # if is_alt:
        #    print(f"DEBUG: Alt Drag detected. Event={is_alt_event}, Global={is_alt_global}")

        # Check if we are currently dragging (using is_dragging property) to prevent accidental copy
        if is_alt and not self._copied_in_drag and self.roi_manager and self._is_actually_dragging:
            # Create a copy at the ORIGINAL position (where we started)
            # and continue dragging THIS item (which becomes the "moved copy").
            # Effectively, we leave a clone behind.
            
            try:
                original_roi = self.roi_manager.get_roi(self.roi_id)
                if original_roi:
                    import uuid
                    # Clone the ROI model
                    new_roi = original_roi.clone()
                    new_roi.id = str(uuid.uuid4())
                    new_roi.selected = False # The copy left behind is not selected
                    
                    # Add to manager -> This creates a new Item at the original position
                    # (since we haven't committed the move of THIS item yet, 
                    #  and the original_roi path is still at start pos)
                    self.roi_manager.add_roi(new_roi)
                    
                    self._copied_in_drag = True
                    Logger.debug(f"[RoiGraphicsItem] Alt-Drag: Created copy {new_roi.id} at original position. Alt={is_alt}")
            except Exception as e:
                Logger.error(f"[RoiGraphicsItem] Failed to copy ROI: {e}")
        elif not is_alt and self._copied_in_drag:
             # If user releases Alt during drag, we could potentially remove the copy?
             # But standard behavior usually keeps it. 
             pass
        elif self._is_actually_dragging and not self._copied_in_drag:
             # Just debugging to confirm why copy happens if it does
             # Logger.debug(f"Dragging without copy. Alt={is_alt} Modifiers={event.modifiers()}")
             pass

        # 2. Boundary Checks (Viewport Collision)
        # Prevent dragging completely off-screen if desired, 
        # but standard canvas behavior usually allows it. 
        # User spec: "Establish viewport boundary collision detection algorithm"
        # We'll clamp the position to be at least partially visible or within scene rect.
        
        current_scene_pos = event.scenePos()
        
        # Calculate proposed new position
        diff = current_scene_pos - self._last_scene_pos
        
        if self.scene():
             # Constraint: At least 10px must remain inside scene
             # We check if the translation would move it too far
             
             # Current rect in scene (approximate using bounding rect)
             current_rect = self.mapToScene(self.path().boundingRect()).boundingRect()
             # Proposed rect
             proposed_rect = current_rect.translated(diff.x(), diff.y())
             
             scene_rect = self.scene().sceneRect()
             margin = 10
             
             # Check X
             if proposed_rect.right() < scene_rect.left() + margin:
                 diff.setX(scene_rect.left() + margin - current_rect.right())
             elif proposed_rect.left() > scene_rect.right() - margin:
                 diff.setX(scene_rect.right() - margin - current_rect.left())
                 
             # Check Y
             if proposed_rect.bottom() < scene_rect.top() + margin:
                 diff.setY(scene_rect.top() + margin - current_rect.bottom())
             elif proposed_rect.top() > scene_rect.bottom() - margin:
                 diff.setY(scene_rect.bottom() - margin - current_rect.top())
        
        new_pos = self.pos() + diff
        
        # 3. Dragging (1:1 Mapping, Sub-pixel precision)
        # We use scenePos to ensure 1:1 mapping with mouse regardless of zoom/DPI
        self._last_scene_pos = current_scene_pos
        
        # 4. Update Position
        # setPos takes QPointF, supporting sub-pixel precision
        self.setPos(new_pos)

    def mouseReleaseEvent(self, event):
        if self._is_resizing:
            super().mouseReleaseEvent(event)
            return

        # Handle pending deselect for Ctrl-Click (if no drag occurred)
        if getattr(self, '_pending_deselect', False):
            if not self._is_actually_dragging:
                print(f"DEBUG: Ctrl Click (No Drag) -> Deselecting item.")
                self.setSelected(False)
            else:
                print(f"DEBUG: Ctrl Drag detected -> Keeping item selected.")
            self._pending_deselect = False

        self._is_actually_dragging = False
        self._drag_start_scene_pos = None
        self.setCursor(Qt.CursorShape.ArrowCursor)
        
        # Commit change if moved
        if self.pos() != QPointF(0, 0):
            # Bake transformation into path
            new_path_scene = self.sceneTransform().map(self.path())
            self.prepareGeometryChange()
            self.setPath(new_path_scene)
            self.setPos(0, 0)
            self._update_handles_pos()
            
            # Notify
            QTimer.singleShot(0, lambda: self._notify_roi_moved(new_path_scene, force=True))
            
        super().mouseReleaseEvent(event)

    def hoverEnterEvent(self, event):
        self._is_hovered = True
        self.update_appearance()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self._is_hovered = False
        self.update_appearance()
        super().hoverLeaveEvent(event)

    def paint(self, painter, option, widget):
        # High Performance Visuals via Unified Rendering Engine
        
        # Determine state and get style
        if self.isSelected():
            style = self.style_center.get_style('selected')
        elif self._is_hovered:
            style = self.style_center.get_style('hover').copy()
            style['pen_width'] = 4.0 # Thicker for better visibility
            style['pen_color'] = "#00FFFF" # Cyan
        else:
            # Custom ROI style (preserving per-ROI color)
            style = self.style_center.get_style('roi_default').copy()
            style['pen_color'] = self.roi_color.name()
            
        # Set context and draw
        self.engine.set_context(painter, 1.0)
        
        # Check if we need to draw special shapes (Arrow/Line)
        # This allows RoiGraphicsItem to handle "Annotation" visuals.
        # We need access to the ROI model or infer from path?
        # Ideally, ROI model should be accessible.
        drawn = False
        if hasattr(self, 'roi_manager') and self.roi_manager:
            try:
                roi = self.roi_manager.get_roi(self.roi_id)
                # Check for 'arrow' type (or similar annotation properties)
                if roi and getattr(roi, 'roi_type', '') == 'arrow':
                    # Manually draw arrow using the path (assuming path is the shaft/line)
                    # We need to construct the arrow head.
                    # This logic duplicates AnnotationGraphicsItem logic but ensures visual consistency.
                    
                    path = self.path()
                    if path.elementCount() >= 2:
                        p1 = path.elementAt(0)
                        p2 = path.elementAt(1)
                        # Rebuild arrow parts (Shaft + Head)
                        # We use the same helper as AnnotationGraphicsItem if available, or duplicate it.
                        # Since we are in CanvasView, maybe we can access a static helper?
                        # Or just reimplement simple arrow head.
                        
                        start_point = QPointF(p1.x, p1.y)
                        end_point = QPointF(p2.x, p2.y)
                        
                        # Draw Shaft
                        self.engine.draw_path(path, style)
                        
                        # Draw Head
                        # Vector math
                        line_vec = end_point - start_point
                        length = math.sqrt(line_vec.x()**2 + line_vec.y()**2)
                        if length > 0:
                            unit_vec = line_vec / length
                            # Normal
                            normal_vec = QPointF(-unit_vec.y(), unit_vec.x())
                            
                            arrow_len = 15.0 # Fixed size or scale?
                            arrow_width = 8.0
                            
                            p_base = end_point - unit_vec * arrow_len
                            p_left = p_base + normal_vec * arrow_width
                            p_right = p_base - normal_vec * arrow_width
                            
                            head_path = QPainterPath()
                            head_path.moveTo(end_point)
                            head_path.lineTo(p_left)
                            head_path.lineTo(p_right)
                            head_path.closeSubpath()
                            
                            # Draw Head with Fill
                            style_head = style.copy()
                            style_head['brush_color'] = style['pen_color']
                            style_head['brush_alpha'] = 255
                            self.engine.draw_path(head_path, style_head)
                            
                        drawn = True
            except Exception as e:
                # Fallback
                pass

        if not drawn:
            self.engine.draw_path(self.path(), style)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange and self.scene():
            pass
        
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged and self.scene():
            # Sync Logic for Dragging
            # Check if this change is due to user interaction (selected + moving)
            if self.isSelected() and not getattr(self, '_is_resizing', False):
                 # Bake current transform (pos) into path for sync
                 # Note: self.pos() is the offset. self.path() is local.
                 # Scene Path = self.sceneTransform().map(self.path())
                 new_path_scene = self.sceneTransform().map(self.path())
                 self._notify_roi_moved(new_path_scene)
                     
        return super().itemChange(change, value)

    def _notify_roi_moved(self, new_path, force=False):
        # Throttling to prevent UI freeze during fast drag
        current_time = time.time()
        if not force and (current_time - getattr(self, '_last_sync_time', 0) < 0.03): # Limit to ~30 FPS
            return
        self._last_sync_time = current_time

        if self.scene():
            # Iterate ALL views sharing this scene (or managed by same session)
            # Actually, standard QGraphicsScene shares items across views if they view the SAME scene.
            # But here we have Separate Scenes for Separate Views (Ch1, Ch2, Merge).
            # We need to notify the ROI Manager, which then updates ALL other views.
            
            # The issue is that _notify_roi_moved calls view.on_roi_moved only for the CURRENT view's window?
            # No, self.scene().views() returns views attached to THIS scene.
            # But other channels have DIFFERENT scenes.
            
            # So we MUST go through the ROI Manager.
            if hasattr(self, 'roi_manager') and self.roi_manager:
                 # Update the model (Single Source of Truth)
                 self.roi_manager.update_roi_path(self.roi_id, new_path)

    def on_roi_moved(self, roi_id, new_path):
        """Called when ROI is moved/resized via handles."""
        # This is a callback for the VIEW to update its visual item if the model changed.
        # But wait, if we are the one dragging, we don't want to be updated again (loop/jitter).
        
        if roi_id in self._roi_items:
            item = self._roi_items[roi_id]
            # Only update if the item is NOT currently being dragged by user
            # We can check item.isSelected() or a specific flag
            
            # If the new path is significantly different (e.g. from another view), update it.
            # But during drag, we are generating the new path.
            
            # If item is selected, we assume it *might* be the source of change.
            # But "Sync" means other views need to update.
            # The current view (source) already has the path.
            
            # Optimization: Check if path is already same
            if item.path() == new_path:
                return
                
            # If item is selected and has focus, maybe we are dragging it?
            # We need a way to know if this update came from THIS item.
            
            # Simple check: If we are dragging THIS item, ignore external updates for it.
            # But 'item' here is the wrapper.
            # We can check if QGraphicsView is in DragMode?
            pass # The update logic is actually in _on_roi_updated via signal.
            
        if self.roi_manager:
            # self.roi_manager.update_roi_path(roi_id, new_path) 
            # NO! This creates a loop. This method is likely intended as a "Slot" for external updates?
            # No, looking at previous code, it was calling manager.update_roi_path.
            # So it was an "Emitter" helper.
            pass
class ScaleBarItem(QGraphicsObject):
    """Movable GraphicsItem for Scale Bar."""
    moved = Signal(QPointF)

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setZValue(200) # Above everything
        self._last_preset_pos = None
        self.update_settings(settings)

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        self.moved.emit(self.pos())

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        self.moved.emit(self.pos())
        # Update settings to reflect custom position
        self.settings.custom_pos = (self.pos().x(), self.pos().y())
        self.settings.position = "Custom"

    def update_settings(self, settings):
        old_pos_preset = self.settings.position if hasattr(self, 'settings') else None
        self.settings = settings
        self.prepareGeometryChange()
        self.setVisible(settings.enabled)
        
        # Position calculation
        image_rect = None
        if self.scene():
            # Try to find the pixmap item in the scene to use as a reference for positioning
            # This is more accurate than sceneRect() which includes large padding
            for item in self.scene().items():
                if isinstance(item, QGraphicsPixmapItem):
                    image_rect = item.mapRectToScene(item.boundingRect())
                    break
        
        # If no image found, fallback to scene rect or just skip positioning
        if image_rect is None and self.scene():
            image_rect = self.scene().sceneRect()

        if image_rect:
            pix_size = self.settings.pixel_size if self.settings.pixel_size > 0 else 1.0
            length_px = self.settings.bar_length_um / pix_size
            padding = 50
            
            # If position preset changed, or first time
            if old_pos_preset != settings.position or self._last_preset_pos is None:
                if settings.position == "Bottom Right":
                    new_pos = QPointF(image_rect.right() - length_px - padding, image_rect.bottom() - padding)
                elif settings.position == "Bottom Left":
                    new_pos = QPointF(image_rect.left() + padding, image_rect.bottom() - padding)
                elif settings.position == "Top Right":
                    new_pos = QPointF(image_rect.right() - length_px - padding, image_rect.top() + padding)
                elif settings.position == "Top Left":
                    new_pos = QPointF(image_rect.left() + padding, image_rect.top() + padding)
                else:
                    new_pos = self.pos()
                
                self.setPos(new_pos)
                self._last_preset_pos = settings.position
                
        self.update()

    def boundingRect(self):
        if not self.settings.enabled:
            return QRectF()
        
        # Estimate size based on settings
        pix_size = self.settings.pixel_size if self.settings.pixel_size > 0 else 1.0
        length_px = self.settings.bar_length_um / pix_size
        width = length_px
        height = self.settings.thickness + (self.settings.font_size + 10 if self.settings.show_label else 0)
        return QRectF(0, 0, width, height)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedChange:
            # print(f"DEBUG: Annotation {self.ann_id} selection changed to {bool(value)}")
            self.update_appearance(is_selected=bool(value))
        return super().itemChange(change, value)

    def paint(self, painter, option, widget):
        if not self.settings.enabled:
            return

        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Calculate length in pixels
        pix_size = self.settings.pixel_size if self.settings.pixel_size > 0 else 1.0
        length_px = self.settings.bar_length_um / pix_size
        color = QColor(self.settings.color)
        
        # Draw Bar
        pen = QPen(color, self.settings.thickness)
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        painter.setPen(pen)
        painter.drawLine(0, self.settings.thickness/2, length_px, self.settings.thickness/2)
        
        # Draw Label
        if self.settings.show_label:
            font_size = self.settings.font_size if self.settings.font_size > 0 else 1
            font = QFont("Arial", font_size)
            painter.setFont(font)
            painter.setPen(color)
            label = f"{self.settings.bar_length_um} \u00B5m"
            text_rect = QRectF(0, self.settings.thickness + 5, length_px, font_size + 5)
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, label)

class AnnotationGraphicsItem(QGraphicsPathItem, QObject):
    """GraphicsItem for persistent annotations."""
    modified = Signal(object) # Emits self when modified

    def __init__(self, ann: GraphicAnnotation, parent=None):
        QGraphicsPathItem.__init__(self, parent)
        QObject.__init__(self) # Initialize QObject
        path = QPainterPath()
        self.setPath(path)
        self.ann_id = ann.id
        self.ann_type = ann.type
        self.display_scale = 1.0 # Default display scale for rendering context
        self._pattern_cache = {}
        self._path_version = 0
        self._is_hovered = False
        self.handles = {}
        
        # Rendering Engine
        self.engine = QtRenderEngine()
        self.style_center = StyleConfigCenter()
        # Connect to style updates
        self.style_center.style_changed.connect(self.update)
        
        self.update_from_model(ann)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setAcceptHoverEvents(True)
        
        # Dynamic Z-Value for selection priority
        if self.ann_type in ['text', 'arrow', 'line']:
            self.setZValue(150) # Higher priority
        else:
            self.setZValue(110) # Lower priority than text
        
        self._is_hovered = False
        
        # Resizing Handles
        self._create_handles()
        self.update_appearance()
        
        # State for resizing
        self._is_resizing = False
        self._start_resize_rect = None
        self._start_resize_path = None
        self._start_mouse_pos = None
        self._resize_flag = None

    @property
    def is_dragging(self):
        """Returns True if the item is currently being dragged by the user."""
        return getattr(self, '_is_actually_dragging', False) or getattr(self, '_is_resizing', False)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        # Check if we moved
        if self.pos() != QPointF(0, 0):
             # We moved!
             # We do NOT bake the position into the path here because
             # on_annotation_modified_item will handle the mapping to scene.
             # Actually, baking it is cleaner, but CanvasView expects to read path.
             # If we bake it, path changes.
             # If we don't bake it, pos changes.
             # on_annotation_modified_item needs to handle both.
             
             # Emit signal
             self.modified.emit(self)

    def _invalidate_pattern_cache(self):
        self._pattern_cache = {}

    def _painter_scale(self, painter) -> float:
        t = painter.worldTransform()
        sx = (t.m11() * t.m11() + t.m12() * t.m12()) ** 0.5
        sy = (t.m21() * t.m21() + t.m22() * t.m22()) ** 0.5
        s = (sx + sy) * 0.5
        if s <= 1e-6:
            return 1.0
        return float(s)

    def _get_scale_mode(self) -> str:
        try:
            mode = self.ann_props.get('scale_mode', 'screen')
        except Exception:
            mode = 'screen'
        return mode if mode in ('screen', 'physical') else 'screen'

    def _effective_length(self, value: float, painter_scale: float) -> float:
        mode = self._get_scale_mode()
        if mode == 'screen':
            return float(value) / float(painter_scale)
        return float(value)

    def _get_style_pattern(self):
        style = getattr(self, 'ann_style', None)
        if style is None:
            style = 'solid'
        pattern = None
        try:
            pattern = self.ann_props.get('pattern')
        except Exception:
            pattern = None
        return style, pattern

    def shape(self):
        """Override shape to increase hit area for easier selection."""
        path = self.path()
        stroker = QPainterPathStroker()
        stroker.setWidth(4) # Reduced from 10 to 4 to prevent overlapping selection issues
        # Apply stroker to ALL shapes to ensure boundary is clickable even if not filled
        # For filled shapes, we want the interior + thick border
        stroke_path = stroker.createStroke(path)
        return stroke_path + path # Combine thickened stroke + interior

    def boundingRect(self):
        """
        Override boundingRect to ensure it covers the item even with cosmetic pens 
        and high zoom levels.
        """
        # Get the base path bounding rect
        rect = self.path().boundingRect()
        
        # Add a generous margin to account for:
        # 1. Cosmetic pen width (which can be relatively large in scene coords when zoomed out, 
        #    but we care about clipping)
        # 2. Arrow heads or other decorations that might slightly exceed the path
        # 3. Selection glow (which adds ~6px)
        
        margin = 1000.0 # Increased from 20.0 to 1000.0 to handle extreme zooms safely
        
        return rect.adjusted(-margin, -margin, margin, margin)

    def _create_handles(self):
        # Create appropriate handles based on type
        flags = []
        if self.ann_type in ['arrow', 'line']:
            flags = ['start', 'end']
        elif self.ann_type in ['rect', 'ellipse', 'circle']:
            flags = ['top-left', 'top-right', 'bottom-left', 'bottom-right', 'top', 'bottom', 'left', 'right', 'rotate']
        elif self.ann_type == 'polygon':
             flags = ['top-left', 'top-right', 'bottom-left', 'bottom-right', 'rotate']
        elif self.ann_type == 'text':
             flags = ['rotate'] # Text mainly rotates? Or maybe resize font? For now rotate.
        
        for flag in flags:
            handle = RoiHandleItem(self, flag)
            # Style override for rotate handle
            if flag == 'rotate':
                handle.setBrush(QBrush(QColor("white")))
                handle.setPen(QPen(QColor("black"), 1))
            self.handles[flag] = handle

    def _update_handles_pos(self):
        path = self.path()
        if path.elementCount() == 0:
            return
            
        if self.ann_type in ['arrow', 'line']:
             # ... (existing logic)
             start = path.elementAt(0)
             end = path.elementAt(1)
             
             if 'start' in self.handles:
                 self.handles['start'].setPos(QPointF(start.x, start.y))
             if 'end' in self.handles:
                 self.handles['end'].setPos(QPointF(end.x, end.y))
                 
        else:
             # Use bounding box for shapes
             rect = path.boundingRect()
             if 'top-left' in self.handles: self.handles['top-left'].setPos(rect.topLeft())
             if 'top-right' in self.handles: self.handles['top-right'].setPos(rect.topRight())
             if 'bottom-left' in self.handles: self.handles['bottom-left'].setPos(rect.bottomLeft())
             if 'bottom-right' in self.handles: self.handles['bottom-right'].setPos(rect.bottomRight())
             
             if 'top' in self.handles: self.handles['top'].setPos(QPointF(rect.center().x(), rect.top()))
             if 'bottom' in self.handles: self.handles['bottom'].setPos(QPointF(rect.center().x(), rect.bottom()))
             if 'left' in self.handles: self.handles['left'].setPos(QPointF(rect.left(), rect.center().y()))
             if 'right' in self.handles: self.handles['right'].setPos(QPointF(rect.right(), rect.center().y()))
             
             if 'rotate' in self.handles:
                 # Place rotate handle above top
                 self.handles['rotate'].setPos(QPointF(rect.center().x(), rect.top() - 20))

    def handle_press(self, flag, scene_pos):
        self._is_resizing = True
        self._start_resize_rect = self.path().boundingRect()
        self._start_resize_path = self.path()
        self._start_mouse_pos = scene_pos
        self._resize_flag = flag
        
    def handle_move(self, flag, scene_pos):
        if not self._is_resizing:
            return

        if self.ann_type in ['arrow', 'line']:
            # Direct endpoint manipulation
            current_pos_local = self.mapFromScene(scene_pos)
            
            # Reconstruct path
            path = self.path()
            # For Arrow/Line, first 2 elements are start/end of shaft
            start = QPointF(path.elementAt(0).x, path.elementAt(0).y)
            end = QPointF(path.elementAt(1).x, path.elementAt(1).y)
            
            if flag == 'start':
                start = current_pos_local
            elif flag == 'end':
                end = current_pos_local
            
            new_path = QPainterPath()
            if self.ann_type == 'arrow':
                 self.shaft_path, self.head_path = self._build_arrow_paths(start, end)
                 new_path = QPainterPath()
                 new_path.addPath(self.shaft_path)
                 new_path.addPath(self.head_path)
            else:
                 new_path.moveTo(start)
                 new_path.lineTo(end)
            
            self.prepareGeometryChange()
            self.setPath(new_path)
            self._update_handles_pos()
            
        else:
            if flag == 'rotate':
                # Calculate rotation angle
                rect = self._start_resize_rect
                center = rect.center()
                
                # Current approach: Modifying Path using transform
                current_pos_local = self.mapFromScene(scene_pos)
                
                import math
                # Angle of mouse relative to center
                angle_mouse = math.degrees(math.atan2(current_pos_local.y() - center.y(), current_pos_local.x() - center.x()))
                # Angle of start pos relative to center
                start_pos_local = self.mapFromScene(self._start_mouse_pos)
                angle_start = math.degrees(math.atan2(start_pos_local.y() - center.y(), start_pos_local.x() - center.x()))
                
                delta_angle = angle_mouse - angle_start
                
                # Apply rotation using QGraphicsItem rotation (Standard Approach)
                # This ensures we preserve the original shape geometry in the path
                # and only modify the transformation.
                
                # Ensure pivot is center
                self.setTransformOriginPoint(center)
                
                # Get current rotation (might not be 0 if previously rotated)
                current_rotation = self.rotation()
                new_rotation = current_rotation + delta_angle
                
                self.setRotation(new_rotation)
                
                # Update handles to reflect rotation?
                # Handles are children, so they rotate with parent automatically!
                # But we might need to adjust their "unrotated" positions if we were modifying path before.
                # Since we are NOT modifying path, handles stay at bounding box corners.
                # Just need to update _start_mouse_pos for continuous drag?
                # Actually, delta is relative to start of drag.
                # If we use setRotation, we are changing the local coordinate system?
                # No, setRotation rotates the item in the parent's coordinate system.
                # Local coordinates stay same.
                # So mapFromScene(scene_pos) will change because the item rotated!
                # This makes incremental calculation tricky.
                
                # Better approach for incremental drag:
                # Calculate absolute angle of mouse vs center (in scene coords).
                # Then set rotation based on difference from initial click.
                
                # Center in Scene Coords
                center_scene = self.mapToScene(center)
                
                # Mouse Angle in Scene
                angle_mouse_scene = math.degrees(math.atan2(scene_pos.y() - center_scene.y(), scene_pos.x() - center_scene.x()))
                
                # Start Mouse Angle in Scene
                start_mouse_scene = self._start_mouse_pos
                if start_mouse_scene:
                     angle_start_scene = math.degrees(math.atan2(start_mouse_scene.y() - center_scene.y(), start_mouse_scene.x() - center_scene.x()))
                else:
                     angle_start_scene = angle_mouse_scene
                
                # Initial Rotation of Item
                # We need to store this on press
                if not hasattr(self, '_start_rotation'):
                    self._start_rotation = self.rotation()
                    
                # Delta
                delta = angle_mouse_scene - angle_start_scene
                self.setRotation(self._start_rotation + delta)
                
                # Store rotation in properties for persistence
                if not isinstance(self.ann_props, dict):
                    self.ann_props = {}
                self.ann_props['rotation'] = self.rotation()
                
                # Update handles? They rotate with item.
                # But if we have a "rotate" handle that stays at top, it rotates too. Correct.
                
                # Trigger sync
                self._notify_modified()
                return

            # Box resizing logic (Shared with ROI)
            rect = self._start_resize_rect
            # ... (Logic from ROI)
            # Simplification: Just calculate new rect
            current_pos_local = self.mapFromScene(scene_pos)
            start_pos_local = self.mapFromScene(self._start_mouse_pos)
            delta_local = current_pos_local - start_pos_local
            
            new_rect = QRectF(rect)
            if 'left' in flag: new_rect.setLeft(rect.left() + delta_local.x())
            if 'right' in flag: new_rect.setRight(rect.right() + delta_local.x())
            if 'top' in flag: new_rect.setTop(rect.top() + delta_local.y())
            if 'bottom' in flag: new_rect.setBottom(rect.bottom() + delta_local.y())
            
            if new_rect.width() < 1: new_rect.setWidth(1)
            if new_rect.height() < 1: new_rect.setHeight(1)
            
            sx = new_rect.width() / rect.width() if rect.width() > 0 else 1
            sy = new_rect.height() / rect.height() if rect.height() > 0 else 1
            
            transform = QTransform()
            transform.translate(new_rect.left(), new_rect.top())
            transform.scale(sx, sy)
            transform.translate(-rect.left(), -rect.top())
            
            new_path = transform.map(self._start_resize_path)
            self.prepareGeometryChange()
            self.setPath(new_path)
            self._update_handles_pos()

    def handle_release(self, flag, scene_pos):
        self._is_resizing = False
        self._notify_modified()

    def mousePressEvent(self, event):
        if self._is_resizing:
            return

        # 1. Record State for Dragging
        self._drag_start_pos = event.pos() 
        self._drag_start_scene_pos = event.scenePos()
        self._last_scene_pos = event.scenePos()
        self._drag_start_time = time.time() * 1000 # ms
        self._is_actually_dragging = False

        # 2. Exclusive Selection Logic
        modifiers = QApplication.keyboardModifiers()
        is_ctrl = bool(modifiers & Qt.KeyboardModifier.ControlModifier)
        is_shift = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)

        if is_ctrl:
            # Multi-selection Mode: Toggle state
            
            # --- FIX: Overlapping Multi-selection ---
            scene_items = self.scene().items(event.scenePos()) if self.scene() else []
            # Filter for ROI/Annotation items
            # RoiGraphicsItem is defined before this class, so we can use it. 
            # AnnotationGraphicsItem is this class.
            target_items = [i for i in scene_items if type(i).__name__ in ['RoiGraphicsItem', 'AnnotationGraphicsItem']]
            
            if len(target_items) > 1:
                print(f"DEBUG: Ctrl Click on stack of {len(target_items)} items. Toggling all.")
                # Toggle all items in the stack
                for item in target_items:
                    item.setSelected(not item.isSelected())
            else:
                self.setSelected(not self.isSelected())
                
        elif is_shift:
             self.setSelected(True)
        else:
             # Single selection
             if self.scene():
                 self.scene().blockSignals(True)
                 for item in self.scene().selectedItems():
                     if item != self:
                         item.setSelected(False)
                 self.scene().blockSignals(False)
             self.setSelected(True)

        # 3. Accept (Grab Mouse)
        event.accept()
        
        # 4. Cursor (if movable)
        if self.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable:
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        
        # NOTE: We do NOT call super().mousePressEvent(event) here because
        # we implement our own dragging logic below, and we want to avoid
        # QGraphicsItem's default behavior conflicting with our selection logic.

    def mouseMoveEvent(self, event):
        if self._is_resizing:
            return
            
        if not getattr(self, '_drag_start_scene_pos', None):
            return

        # 1. Anti-jitter / Intent Recognition
        if not self._is_actually_dragging:
            delta = (event.scenePos() - self._drag_start_scene_pos).manhattanLength()
            if delta > 3:
                self._is_actually_dragging = True
            else:
                return # Ignore small movements

        current_scene_pos = event.scenePos()
        
        # Calculate proposed new position
        diff = current_scene_pos - self._last_scene_pos
        
        if self.scene():
             # Constraint: At least 10px must remain inside scene
             current_rect = self.mapToScene(self.path().boundingRect()).boundingRect()
             proposed_rect = current_rect.translated(diff.x(), diff.y())
             scene_rect = self.scene().sceneRect()
             margin = 10
             
             # Check X
             if proposed_rect.right() < scene_rect.left() + margin:
                 diff.setX(scene_rect.left() + margin - current_rect.right())
             elif proposed_rect.left() > scene_rect.right() - margin:
                 diff.setX(scene_rect.right() - margin - current_rect.left())
                 
             # Check Y
             if proposed_rect.bottom() < scene_rect.top() + margin:
                 diff.setY(scene_rect.top() + margin - current_rect.bottom())
             elif proposed_rect.top() > scene_rect.bottom() - margin:
                 diff.setY(scene_rect.bottom() - margin - current_rect.top())
        
        new_pos = self.pos() + diff
        
        # Update Position
        self._last_scene_pos = current_scene_pos
        self.setPos(new_pos)
        
        # Force immediate repaint
        if self.scene():
            self.scene().update()
        
        # Notify modification for real-time sync (Fix for Terminal#503-1007)
        self._notify_modified()
        
        # Debug Log
        Logger.debug(f"Annotation Dragging - Pos: {new_pos}")

    def mouseReleaseEvent(self, event):
        # Restore cursor
        self._is_actually_dragging = False
        self._drag_start_scene_pos = None
        self.setCursor(Qt.CursorShape.ArrowCursor)

        if self.pos() != QPointF(0, 0):
            try:
                    # Apply movement to path
                    self.prepareGeometryChange()
                    
                    # FIX for Ghosting/Detach:
                    # Instead of mapping the whole path (which might corrupt composite paths like Arrows),
                    # we reconstruct the path from mapped Control Points.
                    if self.ann_type in ['arrow', 'line']:
                        # 1. Get current local points
                        # Assuming element 0 and 1 are always Start/End for Arrow/Line in local coords
                        p1 = self.path().elementAt(0)
                        p2 = self.path().elementAt(1)
                        
                        # 2. Map to Scene (apply the translation we just did)
                        # We used to use self.sceneTransform() which includes rotation.
                        # But since we separate rotation now (via setRotation), we ONLY want translation.
                        # New Scene Point = Local Point + Item Position (Offset)
                        offset = self.pos()
                        p1_scene = QPointF(p1.x + offset.x(), p1.y + offset.y())
                        p2_scene = QPointF(p2.x + offset.x(), p2.y + offset.y())
                        
                        # 3. Rebuild Path from scratch
                        # This ensures the structure (Shaft + Head) is generated cleanly
                        # and matches what _update_handles_pos expects.
                        if self.ann_type == 'arrow':
                            self.shaft_path, self.head_path = self._build_arrow_paths(p1_scene, p2_scene)
                            new_path = QPainterPath()
                            new_path.addPath(self.shaft_path)
                            new_path.addPath(self.head_path)
                        else:
                            new_path = QPainterPath()
                            new_path.moveTo(p1_scene)
                            new_path.lineTo(p2_scene)
                            
                        self.setPath(new_path)
                    
                    else:
                        # For simple shapes, mapping the path is usually safe
                        # But again, only apply translation!
                        offset = self.pos()
                        transform = QTransform()
                        transform.translate(offset.x(), offset.y())
                        self.setPath(transform.map(self.path()))
                    
                    self.setPos(0, 0)
                    self._update_handles_pos()
                    self._notify_modified()
            except Exception as e:
                print(f"ERROR: Annotation Drag Release failed: {e}")
                
        super().mouseReleaseEvent(event)

    def hoverEnterEvent(self, event):
        self._is_hovered = True
        self.update_appearance()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self._is_hovered = False
        self.update_appearance()
        super().hoverLeaveEvent(event)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedChange:
            self.update_appearance(is_selected=bool(value))
        elif change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            # Trigger repaint on position change
            self.update()
            if self.scene():
                self.scene().update()
            print(f"DEBUG: Annotation Position Updated: {value}")
        return super().itemChange(change, value)

    def _notify_modified(self):
        # Notify view to update model
        if self.scene():
            for view in self.scene().views():
                if hasattr(view, 'on_annotation_modified_item'):
                    Logger.debug(f"Annotation {self.ann_id} modified, notifying view.")
                    view.on_annotation_modified_item(self)
                    break

    def update_appearance(self, is_selected=None):
        try:
            if is_selected is None:
                is_selected = self.isSelected()
            
            # Handle visibility of handles only. Styling is done in paint() via engine.
            if is_selected:
                self._update_handles_pos()
                for h in self.handles.values():
                    h.setVisible(True)
            else:
                for h in self.handles.values():
                    h.setVisible(False)
            
            # Force update to trigger paint
            self.update()
        except Exception:
            pass

    def paint(self, painter, option, widget):
        # High Performance Visuals via Unified Rendering Engine
        
        # Check if we should render in "Annotation Style" (No fill, special thickness)
        # We assume Pending Mode ROIs have high alpha color (255) vs standard ROI (200)
        # Or we can check if this ROI has a linked annotation?
        # But accessing session is slow.
        
        base_color = self.roi_color
        
        # If selected, override
        if self.isSelected():
            style = self.style_center.get_style('selected')
        elif self._is_hovered:
            style = self.style_center.get_style('hover').copy()
            style['pen_width'] = 4.0 # Thicker for better visibility
            style['pen_color'] = "#00FFFF" # Cyan
        else:
            # Normal State
            # We construct style based on ROI properties
            
            # Determine if we should fill
            # Standard ROI color usually has Alpha ~200.
            # Annotation color usually has Alpha 255 (Opaque).
            # If Alpha is 255, we treat it as "Annotation Style" (No Fill).
            
            brush_color = None
            if base_color.alpha() < 250:
                 # Standard ROI: Use weak fill (e.g. 40 alpha)
                 brush_color = QColor(base_color.red(), base_color.green(), base_color.blue(), 40).name(QColor.NameFormat.HexArgb)
            else:
                 # Opaque Color (Annotation): No Fill
                 brush_color = None # Transparent
            
            style = {
                'pen_color': base_color.name(),
                'pen_width': 2.0, # Default ROI width
                'pen_style': 'solid',
                'brush_color': brush_color,
                'antialiasing': True
            }
            
        # Set context and draw
        self.engine.set_context(painter, self.display_scale)
        self.engine.draw_path(self.path(), style)

    def _build_arrow_paths(self, start, end):
        """Helper to construct shaft and head paths for arrows."""
        # --- REFACTOR: Create a single continuous path for the whole arrow ---
        # This prevents detachment and ensures consistent stroking.
        
        path = QPainterPath()
        
        # 1. Shaft
        path.moveTo(start)
        path.lineTo(end)
        
        # 2. Head
        # Get properties
        head_shape = self.ann_props.get('arrow_head_shape', 'open')
        arrow_len = float(self.ann_props.get('arrow_head_size', 15.0))
        
        import math
        angle = math.atan2(end.y() - start.y(), end.x() - start.x())
        
        # Note: We append the head path to the shaft path.
        # For 'open' shape, we just draw lines.
        # For filled shapes (triangle/diamond), we might want to close them subpaths.
        
        if head_shape == 'open':
            arrow_angle = math.pi / 6
            p1 = end - QPointF(arrow_len * math.cos(angle - arrow_angle), arrow_len * math.sin(angle - arrow_angle))
            p2 = end - QPointF(arrow_len * math.cos(angle + arrow_angle), arrow_len * math.sin(angle + arrow_angle))
            
            # Draw one wing, then back to tip, then other wing
            path.moveTo(end)
            path.lineTo(p1)
            path.moveTo(end)
            path.lineTo(p2)
            
        elif head_shape == 'triangle':
            arrow_angle = math.pi / 6
            p1 = end - QPointF(arrow_len * math.cos(angle - arrow_angle), arrow_len * math.sin(angle - arrow_angle))
            p2 = end - QPointF(arrow_len * math.cos(angle + arrow_angle), arrow_len * math.sin(angle + arrow_angle))
            
            # Add polygon as subpath
            path.moveTo(end)
            path.lineTo(p1)
            path.lineTo(p2)
            path.lineTo(end)
            path.closeSubpath() # Ensure closed for filling
            
        elif head_shape == 'diamond':
            # Kite shape
            w = arrow_len * 0.5
            p_back = end - QPointF(arrow_len * math.cos(angle), arrow_len * math.sin(angle))
            p_mid = (end + p_back) / 2
            perp_angle = angle + math.pi/2
            width_vec = QPointF(w * math.cos(perp_angle), w * math.sin(perp_angle))
            p_left = p_mid + width_vec
            p_right = p_mid - width_vec
            
            path.moveTo(end)
            path.lineTo(p_left)
            path.lineTo(p_back)
            path.lineTo(p_right)
            path.lineTo(end)
            path.closeSubpath() # Ensure closed for filling
            
        elif head_shape == 'circle':
            radius = arrow_len / 2
            path.addEllipse(end.x() - radius, end.y() - radius, radius*2, radius*2)
            
        # Return same path for both to satisfy legacy call signature or just return one?
        # The caller expects (shaft, head). 
        # But we want to return a Unified Path.
        # Let's modify the caller too. But wait, `update_from_model` calls this.
        # We should update `update_from_model` to just use one path.
        # But for minimal impact, let's return (path, empty_path) or split it if really needed?
        # Actually, if we return (path, QPainterPath()), and caller does path.addPath(), it works.
        
        return path, QPainterPath()

    def update_from_model(self, ann: GraphicAnnotation):
        self.setVisible(ann.visible)
        self.ann_color = ann.color # Store for appearance reset
        self.ann_props = ann.properties # Store for resizing
        self.ann_style = getattr(ann, 'style', 'solid')
        
        # Update selectable flag from model
        is_selectable = getattr(ann, 'selectable', True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, is_selectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False) # Handled manually
        
        if not ann.visible:
            return

        path = QPainterPath()
        pts = [QPointF(p[0], p[1]) for p in ann.points]
        if not pts:
            return
            
        self.shaft_path = None
        self.head_path = None

        if ann.type == 'arrow':
            if len(pts) >= 2:
                start, end = pts[0], pts[1]
                self.shaft_path, self.head_path = self._build_arrow_paths(start, end)
                # Use addPath instead of + (union) to combine open paths correctly
                path = QPainterPath()
                path.addPath(self.shaft_path)
                path.addPath(self.head_path)
        elif ann.type == 'line':
            if len(pts) >= 2:
                path.moveTo(pts[0])
                path.lineTo(pts[1])
        elif ann.type == 'rect':
            if len(pts) >= 2:
                path.addRect(QRectF(pts[0], pts[1]).normalized())
        elif ann.type == 'circle':
            if len(pts) >= 2:
                # Use bounding box logic consistent with creation
                rect = QRectF(pts[0], pts[1]).normalized()
                center = rect.center()
                radius = min(rect.width(), rect.height()) / 2.0
                path.addEllipse(center, radius, radius)
        elif ann.type == 'ellipse':
            if len(pts) >= 2:
                path.addEllipse(QRectF(pts[0], pts[1]).normalized())
        elif ann.type == 'polygon' or ann.type == 'roi_ref':
            if len(pts) >= 1:
                path.moveTo(pts[0])
                for p in pts[1:]:
                    path.lineTo(p)
                if len(pts) > 2:
                    path.closeSubpath()

        self.setPath(path)
        
        # Apply Rotation (if present)
        # Note: Rotation is applied around the center of the bounding rect
        rotation = ann.properties.get('rotation', 0.0)
        self.setRotation(rotation)
        if rotation != 0:
            # Ensure pivot is correct (center of unrotated shape)
            self.setTransformOriginPoint(path.boundingRect().center())
        else:
             # Reset pivot just in case
             self.setTransformOriginPoint(path.boundingRect().center())

        self._path_version += 1
        self._invalidate_pattern_cache()
        self.update_appearance() # Refresh appearance (pen style)
        pen = QPen(QColor(ann.color), ann.thickness)
        scale_mode = ann.properties.get('scale_mode', 'screen') if isinstance(ann.properties, dict) else 'screen'
        pen.setCosmetic(False if scale_mode == 'physical' else True)
        pen.setStyle(Qt.PenStyle.SolidLine)
        self.setPen(pen)
        
        # Handle Text
        if hasattr(self, 'text_item'):
            if self.scene():
                self.scene().removeItem(self.text_item)
            self.text_item = None
            
        if ann.type == 'text' and ann.text:
            from PySide6.QtWidgets import QGraphicsSimpleTextItem
            self.text_item = QGraphicsSimpleTextItem(ann.text, self)
            self.text_item.setBrush(QBrush(QColor(ann.color)))
            # Font size
            font_size = ann.properties.get('font_size', 12.0)
            try:
                font_size_value = float(font_size)
            except Exception:
                font_size_value = 12.0
            if font_size_value <= 0:
                font_size_value = 1.0
            font = QFont("Arial", int(font_size_value))
            self.text_item.setFont(font)
            # Position at first point
            if pts:
                self.text_item.setPos(pts[0])
                
            # If selected, maybe show box? handled by parent selection usually.
            
    def paint(self, painter, option, widget):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        # Ensure high quality
        # HighQualityAntialiasing is sometimes just an alias or ignored, but explicit AA is key.
        
        style, pattern = self._get_style_pattern()
        painter_scale = self._painter_scale(painter)

        base_pen = QPen(self.pen())
        
        # Override color if selected (Fix for missing selection visual feedback)
        if self.isSelected():
            base_pen.setColor(QColor("#FF0000"))
            
        color = base_pen.color()
        thickness = max(0.1, float(base_pen.widthF() if base_pen.widthF() > 0 else base_pen.width()))

        scale_mode = self._get_scale_mode()
        # Force high quality settings matching ROI
        base_pen.setCosmetic(False if scale_mode == 'physical' else True)
        base_pen.setStyle(Qt.PenStyle.SolidLine)
        base_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        base_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        
        # Ensure width is sufficient for AA to look good
        if base_pen.isCosmetic() and thickness < 1.5:
            thickness = 1.5
            base_pen.setWidthF(thickness)

        # Custom Arrow Painting
        if self.ann_type == 'arrow' and getattr(self, 'shaft_path', None) is not None and getattr(self, 'head_path', None) is not None:
             # Draw Shaft
             if style == 'dashed':
                 dash_len = float(self.ann_props.get('dashLength', 10.0)) if isinstance(self.ann_props, dict) else 10.0
                 dash_gap = float(self.ann_props.get('dashGap', 5.0)) if isinstance(self.ann_props, dict) else 5.0
                 dash_len = max(0.1, dash_len)
                 dash_gap = max(0.1, dash_gap)
                 base_pen.setDashPattern([self._effective_length(dash_len, painter_scale), self._effective_length(dash_gap, painter_scale)])
                 painter.setPen(base_pen)
                 painter.setBrush(Qt.BrushStyle.NoBrush)
                 painter.drawPath(self.shaft_path)
             elif style == 'dotted':
                 # Fallback to solid shaft for dotted for now, or implement dot logic on shaft
                 # Implementing simplified dot logic for shaft
                 dot_size = float(self.ann_props.get('dotSize', 2.0)) if isinstance(self.ann_props, dict) else 2.0
                 dot_spacing = float(self.ann_props.get('dotSpacing', 3.0)) if isinstance(self.ann_props, dict) else 3.0
                 dot_size = max(0.1, dot_size)
                 dot_spacing = max(0.1, dot_spacing)
                 r = self._effective_length(dot_size * 0.5, painter_scale)
                 step = self._effective_length(dot_spacing, painter_scale)
                 
                 # Draw dots along shaft
                 # Use cached pattern if possible?
                 # For simplicity, just draw dashed for dotted arrow shaft for now to avoid complexity,
                 # or stick to solid if user selected dotted.
                 # Let's use dashed approximation or solid.
                 base_pen.setStyle(Qt.PenStyle.DotLine) # Use Qt standard dot line
                 painter.setPen(base_pen)
                 painter.setBrush(Qt.BrushStyle.NoBrush)
                 painter.drawPath(self.shaft_path)
             else:
                 painter.setPen(base_pen)
                 painter.setBrush(Qt.BrushStyle.NoBrush)
                 painter.drawPath(self.shaft_path)
             
             # Draw Head
             head_shape = self.ann_props.get('arrow_head_shape', 'open')
             head_pen = QPen(base_pen)
             head_pen.setStyle(Qt.PenStyle.SolidLine)
             head_pen.setDashPattern([]) # Clear dashes
             
             painter.setPen(head_pen)
             
             if head_shape == 'open':
                 painter.setBrush(Qt.BrushStyle.NoBrush)
             else:
                 painter.setBrush(QBrush(color))
             
             painter.drawPath(self.head_path)
             
             # Text handling
             if hasattr(self, 'text_item') and self.text_item:
                if self.isSelected():
                    self.text_item.setBrush(QBrush(QColor("#FF0000")))
                else:
                    self.text_item.setBrush(QBrush(QColor(self.ann_color)))
             return

        if style == 'dashed':
            dash_len = float(self.ann_props.get('dashLength', 10.0)) if isinstance(self.ann_props, dict) else 10.0
            dash_gap = float(self.ann_props.get('dashGap', 5.0)) if isinstance(self.ann_props, dict) else 5.0
            dash_len = max(0.1, dash_len)
            dash_gap = max(0.1, dash_gap)
            base_pen.setDashPattern([self._effective_length(dash_len, painter_scale), self._effective_length(dash_gap, painter_scale)])
            painter.setPen(base_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(self.path())
        elif style == 'dotted':
            dot_size = float(self.ann_props.get('dotSize', 2.0)) if isinstance(self.ann_props, dict) else 2.0
            dot_spacing = float(self.ann_props.get('dotSpacing', 3.0)) if isinstance(self.ann_props, dict) else 3.0
            dot_size = max(0.1, dot_size)
            dot_spacing = max(0.1, dot_spacing)
            r = self._effective_length(dot_size * 0.5, painter_scale)
            step = self._effective_length(dot_spacing, painter_scale)

            path = self.path()
            try:
                length = float(path.length())
            except Exception:
                length = 0.0

            cache_key = (self._path_version, round(painter_scale, 2), round(dot_size, 2), round(dot_spacing, 2), scale_mode)
            dots = self._pattern_cache.get('dots') if self._pattern_cache.get('key') == cache_key else None
            if dots is None:
                dots = []
                if length > 0 and step > 0:
                    d = 0.0
                    while d <= length:
                        try:
                            p = path.pointAtPercent(path.percentAtLength(d))
                        except Exception:
                            break
                        dots.append(p)
                        d += step
                self._pattern_cache = {'key': cache_key, 'dots': dots}

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(color))
            for p in dots:
                painter.drawEllipse(QPointF(p), r, r)
        elif style == 'dash_dot':
            dash_len = float(self.ann_props.get('dashLength', 10.0)) if isinstance(self.ann_props, dict) else 10.0
            dash_gap = float(self.ann_props.get('dashGap', 5.0)) if isinstance(self.ann_props, dict) else 5.0
            dot_size = float(self.ann_props.get('dotSize', 2.0)) if isinstance(self.ann_props, dict) else 2.0
            dot_spacing = float(self.ann_props.get('dotSpacing', 3.0)) if isinstance(self.ann_props, dict) else 3.0
            dash_len = max(0.1, dash_len)
            dash_gap = max(0.1, dash_gap)
            dot_size = max(0.1, dot_size)
            dot_spacing = max(0.1, dot_spacing)

            dash_cycle = dash_len + dash_gap + dot_spacing + dash_gap
            base_pen.setDashPattern([self._effective_length(dash_len, painter_scale), self._effective_length(dash_cycle - dash_len, painter_scale)])
            painter.setPen(base_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(self.path())

            r = self._effective_length(dot_size * 0.5, painter_scale)
            offset = dash_len + dash_gap
            step = dash_cycle

            path = self.path()
            try:
                length = float(path.length())
            except Exception:
                length = 0.0

            cache_key = (self._path_version, round(painter_scale, 2), round(dash_len, 2), round(dash_gap, 2), round(dot_size, 2), round(dot_spacing, 2), scale_mode)
            dots = self._pattern_cache.get('dash_dot_dots') if self._pattern_cache.get('dash_dot_key') == cache_key else None
            if dots is None:
                dots = []
                if length > 0 and step > 0:
                    d = float(offset)
                    while d <= length:
                        try:
                            p = path.pointAtPercent(path.percentAtLength(d))
                        except Exception:
                            break
                        dots.append(p)
                        d += float(step)
                self._pattern_cache['dash_dot_key'] = cache_key
                self._pattern_cache['dash_dot_dots'] = dots

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(color))
            for p in dots:
                painter.drawEllipse(QPointF(p), r, r)
        else:
            painter.setPen(base_pen)
            painter.setBrush(self.brush())
            painter.drawPath(self.path())

        if hasattr(self, 'text_item') and self.text_item:
            # If parent is selected, maybe make text red?
            if self.isSelected():
                self.text_item.setBrush(QBrush(QColor("#FF0000")))
            else:
                self.text_item.setBrush(QBrush(QColor(self.ann_color)))

class CanvasView(QGraphicsView):
    """
    The main viewport for displaying the multi-channel image.
    Supports zooming and panning.
    Handles ROI rendering via QGraphicsPathItem.
    """
    zoom_changed = Signal(float, float, QPointF) # scale_x, scale_y, focus_scene_pos
    file_dropped = Signal(str, int) # file_path, channel_index
    view_clicked = Signal(str, int) # view_id, channel_index (For channel selection)
    mouse_moved = Signal(int, int) # scene_x, scene_y
    annotation_created = Signal(object) # GraphicAnnotation object
    annotation_modified = Signal(object) # GraphicAnnotation object (updated)
    tool_cancelled = Signal() # Emitted when ESC is pressed
    scale_bar_moved = Signal(QPointF) # Emitted when scale bar is moved

    def __init__(self, parent=None, view_id="canvas", session=None):
        super().__init__(parent)
        self.view_id = view_id
        self.session = session
        
        # --- GPU Acceleration: Enable OpenGL Viewport ---
        self.setViewport(QOpenGLWidget())
        
        self.setAcceptDrops(True) # Enable Drag & Drop
        self.setMouseTracking(True) # Enable Mouse Tracking for status bar info
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus) # Enable Keyboard Events
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.scene.selectionChanged.connect(self.on_scene_selection_changed)
        
        # Quicklook Preview Label (Hidden by default)
        self.preview_label = QLabel(self)
        self.preview_label.setWindowFlags(Qt.WindowType.ToolTip)
        self.preview_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.preview_label.hide()
        
        palette = QApplication.palette()
        accent_color = palette.color(QPalette.ColorRole.Highlight).name()
        self.preview_label.setStyleSheet(f"border: 2px solid {accent_color}; background-color: black;")
        
        # Image Item (Z-value 0)
        self.pixmap_item = QGraphicsPixmapItem()
        self.pixmap_item.setZValue(0)
        self.scene.addItem(self.pixmap_item)
        
        # Temp Path Item (For Lasso/Wand Preview)
        self.temp_path_item = QGraphicsPathItem()
        self.temp_path_item.setZValue(100) # Topmost
        pen = QPen(QColor("#00FFFF"), 2) # Cyan for high visibility
        pen.setStyle(Qt.PenStyle.SolidLine)
        pen.setCosmetic(True)
        self.temp_path_item.setPen(pen)
        
        # Add a semi-transparent fill for the preview
        fill_color = QColor("#00FFFF")
        fill_color.setAlpha(60) # Light blue fill
        self.temp_path_item.setBrush(QBrush(fill_color))
        
        self.scene.addItem(self.temp_path_item)
        
        # View settings
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True) # AA for ROIs
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        
        # Black background for better fluorescence visibility
        self.setBackgroundBrush(QBrush(Qt.GlobalColor.black))

        # State
        self._zoom_level = 1.0
        self.roi_manager = None
        self.active_tool = None
        self.active_channel_index = 0
        
        # Map ROI ID -> GraphicsItem
        self._roi_items = {}
        self._is_updating_from_manager = False
        
        self.label_text = None
        self.is_selected = False
        self.flash_active = False # Visual feedback for updates
        self._is_hand_panning = False
        self._hand_pan_last_pos = None
        
        # --- Scientific Rigor: Data/Display Mapping ---
        self.last_display_array = None # The (H,W,3) array currently shown
        self.display_scale = 1.0 # display_size / full_res_size

        # --- Graphic Annotations State ---
        self.annotation_mode = 'none' # 'arrow', 'rect', 'text', 'circle', 'line', 'polygon', 'none'
        self.annotation_fixed_size_mode = False # If true, create with fixed size on click
        self.last_ann_size = {
            'arrow': 50.0,
            'line': 50.0,
            'rect': (50.0, 50.0),
            'ellipse': (50.0, 50.0),
            'circle': 50.0
        }
        self.current_ann_points = []
        self.sync_rois_as_annotations = True # User request integration
        self.preview_ann_item = QGraphicsPathItem()
        self.preview_ann_item.setZValue(150)
        self.scene.addItem(self.preview_ann_item)

        # --- Scale Bar ---
        from src.core.data_model import ScaleBarSettings
        if self.session:
            self.scale_bar_item = ScaleBarItem(self.session.scale_bar_settings)
        else:
            self.scale_bar_item = ScaleBarItem(ScaleBarSettings())
        self.scale_bar_item.moved.connect(self.scale_bar_moved.emit)
        self.scene.addItem(self.scale_bar_item)
        
        # Map Annotation ID -> GraphicsItem
        self._ann_items = {}

        # Smooth Zoom State
        self._target_zoom = 1.0
        self._current_zoom = 1.0 # Tracks the logical zoom level (not necessarily current transform scale)
        self._zoom_velocity = 0.0
        self._zoom_anchor_scene = QPointF()
        self._zoom_anchor_viewport = QPoint()
        self._zoom_timer = QTimer(self)
        self._zoom_timer.setInterval(16) # ~60 FPS
        self._zoom_timer.timeout.connect(self._process_zoom_animation)
        self._is_zooming_smoothly = False
        
        # Constants
        self.ZOOM_MIN = 0.1
        self.ZOOM_MAX = 50.0
        self.ZOOM_DAMPING = 0.85
        self.ZOOM_SPRING = 0.2

    def mousePressEvent(self, event):
        # Force focus to receive key events immediately on click
        self.setFocus()
        click_pos = event.position().toPoint()
        if event.button() == Qt.MouseButton.LeftButton:
            try:
                self.view_clicked.emit(self.view_id, self.active_channel_index)
                print(f"DEBUG: CanvasView({self.view_id}) view_clicked channel_index={self.active_channel_index}")
            except Exception as e:
                print(f"WARNING: CanvasView({self.view_id}) view_clicked emit failed: {e}")

        # 1. ROI Tools (Priority)
        # Note: If Control is held, we prioritize Multi-Select over Tool usage unless dragging
        modifiers = QApplication.keyboardModifiers()
        is_ctrl = bool(modifiers & Qt.KeyboardModifier.ControlModifier)
        # Also check Space key (which usually means temporary Pan)
        # But we can't check pressed keys easily via QApplication without a global tracker or event loop check.
        # However, keyPressEvent handles Space by setting DragMode.
        # If DragMode is ScrollHandDrag, we should bypass tool?
        is_hand_mode = self.dragMode() == QGraphicsView.DragMode.ScrollHandDrag

        # Force bypass if Ctrl or Space (Hand Mode) is active
        # This overrides any tool logic.
        if is_ctrl or is_hand_mode:
             # Logic for "Hand Tool" override
             # If we click on an item, we select/move it.
             # If we click on background, we Pan.
             # In both cases, we must NOT trigger the active tool (e.g. Rect/Polygon).
             self._bypass_active_tool_events = True
             
             # Also check if we are clicking on an interactable item to ensure we don't just Pan
             # But super().mousePressEvent handles that distinction (Item vs Background)
             pass

        if self.annotation_mode != 'none':
            # Check for existing items to allow interaction (Selection/Move)
            # Use a small tolerance rect for better hit testing
            items_under = self.items(QRectF(click_pos.x() - 5, click_pos.y() - 5, 10, 10).toRect())
            has_interactable = False
            for item in items_under:
                 if isinstance(item, (RoiGraphicsItem, AnnotationGraphicsItem, RoiHandleItem)):
                     has_interactable = True
                     break
            
            if has_interactable or is_ctrl or is_hand_mode:
                  # Let QGraphicsView handle interaction (selection/move)
                  # This prevents "Drawing" logic from hijacking the click on an existing item
                  # CRITICAL FIX: Explicitly bypass active tool events for subsequent move/release
                  self._bypass_active_tool_events = True
                  super().mousePressEvent(event)
                  return

             # If we have an active tool (e.g. for rect/polygon annotation), allow fall-through
            if self.active_tool:
                 pass
            else:
                 scene_pos = self.mapToScene(click_pos)
                 if event.button() == Qt.MouseButton.LeftButton:
                     self._handle_annotation_click(scene_pos)
                 elif event.button() == Qt.MouseButton.RightButton:
                     if self.annotation_mode == 'polygon':
                         Logger.debug("[CanvasView] Annotation polygon right-click: finish polygon")
                         self._finish_annotation()
                     else:
                         self._finish_annotation()
                 event.accept()
                 return

        if self.active_tool and event.button() == Qt.MouseButton.LeftButton:
            # Strictly prioritize Active Tool over ROI/Annotation Selection
            # We DO NOT bypass the tool even if an item is under the cursor.
            # This ensures only "Hand Tool" (No Active Tool) can select/drag items.
            
            # EXCEPT if Ctrl or Space is held (Hand Mode Override)
            if is_ctrl or is_hand_mode:
                 self._bypass_active_tool_events = True
            else:
                 self._bypass_active_tool_events = False
        
        if self.active_tool and (event.button() == Qt.MouseButton.RightButton or not is_ctrl):
            bypass = False # Never bypass for Left/Right click if tool is active

            # Additional Bypass for Ctrl (Pan Mode) - allow panning if background clicked
            if is_ctrl or is_hand_mode: 
                 bypass = True # Always bypass tool if Ctrl is held (prioritize Pan/Select)

            if bypass:
                self._bypass_active_tool_events = True
                # Force Movable Flag just in case
                item = self.itemAt(click_pos)
                if item:
                    item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
                    item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
                Logger.debug(f"[CanvasView] Bypass tool press due to interactable under cursor or Ctrl: {type(self.active_tool).__name__}")
            else:
                self._bypass_active_tool_events = False
                scene_pos = self.mapToScene(click_pos)

                if event.button() == Qt.MouseButton.RightButton:
                    print(f"DEBUG: CanvasView Right Click dispatch to {self.active_tool}")
                    self.active_tool.mouse_right_click(scene_pos)
                    self._update_preview()
                    event.accept()
                    return

                if event.button() == Qt.MouseButton.LeftButton:
                    self.active_tool.mouse_press(
                        scene_pos,
                        self.active_channel_index,
                        context={'display_scale': self.display_scale, 'display_data': self.last_display_array, 'view': self},
                    )
                    event.accept()
                    return

        # 3. Smart Pan & Interaction Logic (Fat Finger Detection)
        # Use a tolerance area for clicking to handle cosmetic lines when zoomed out
        # "Fat finger" logic: 10x10 pixel box centered on click
        items_in_rect = self.items(QRectF(click_pos.x() - 5, click_pos.y() - 5, 10, 10).toRect())
        
        # Walk up hierarchy to find interactable parent
        interactable = None
        
        # Prioritize items that are ON TOP (first in list)
        for item in items_in_rect:
            # Check up hierarchy for this item
            temp_item = item
            while temp_item:
                if isinstance(temp_item, (RoiGraphicsItem, AnnotationGraphicsItem, RoiHandleItem, ScaleBarItem)):
                    interactable = temp_item
                    break
                if (temp_item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable) or \
                   (temp_item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable):
                    interactable = temp_item
                    break
                temp_item = temp_item.parentItem()
            
            if interactable:
                break # Found the top-most interactable item
        
        if interactable:
            # print(f"DEBUG: Smart Pan triggered for item: {interactable}")
            
            # Manual interaction dispatch to ensure reliability even if Scene hit-test fails (e.g. cosmetic lines)
            # This is crucial for fixing "Control key multi-select" issues on thin lines
            if isinstance(interactable, (RoiGraphicsItem, AnnotationGraphicsItem)):
                # Logic: If we rely on super(), Scene calls itemAt(). If itemAt() fails (strict check), background click -> deselect.
                # So we MUST ensure the item gets selected if our Fat Finger logic found it.
                
                modifiers = QApplication.keyboardModifiers()
                is_ctrl = bool(modifiers & Qt.KeyboardModifier.ControlModifier)
                is_shift = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)
                
                # Check if Scene actually hits it (Strict check)
                scene_hit = self.itemAt(click_pos) == interactable
                
                if scene_hit:
                    # Scene sees it. We can rely on standard propagation.
                    # We just need to ensure DragMode is off so the Item receives the event instead of the View panning.
                    Logger.debug(f"[CanvasView] Smart Pan hit confirmed by Scene. Dispatching to super() for drag. Ctrl={is_ctrl}")
                    
                    # Temporarily disable View's Hand Drag if active, to allow Item Drag
                    if self.dragMode() != QGraphicsView.DragMode.NoDrag:
                        self._temp_drag_restore = self.dragMode()
                        self.setDragMode(QGraphicsView.DragMode.NoDrag)
                        self._temp_drag_mode = True
                    
                    super().mousePressEvent(event)
                    return

                # If Scene MISSED it (Fat Finger case), we must handle selection manually.
                # Note: We must also manually forward the press event to the item to initialize drag state,
                # and grab mouse to ensure it receives move events.
                try:
                    # Helper to simulate QGraphicsSceneMouseEvent
                    scene_pos = self.mapToScene(click_pos)
                    
                    def forward_press_event(target_item):
                        local_pos = target_item.mapFromScene(scene_pos)
                        
                        class MockEvent:
                            def __init__(self, p, sp, mods):
                                self._p = p
                                self._sp = sp
                                self._mods = mods
                            def pos(self): return self._p
                            def scenePos(self): return self._sp
                            def modifiers(self): return self._mods
                            def accept(self): pass
                            def ignore(self): pass
                            
                        mock_event = MockEvent(local_pos, scene_pos, event.modifiers())
                        target_item.mousePressEvent(mock_event)
                        target_item.grabMouse()

                    # Force Movable/Selectable Flags for safety
                    interactable.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
                    interactable.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
 
                    if is_ctrl:
                         # Smart Stack Selection Logic:
                         # ... (Stack logic same as before) ...
                         
                         print(f"ROI Click: Modifiers={modifiers}, Ctrl={is_ctrl}, Shift={is_shift}, Current Selected={interactable.isSelected()}")
                         print(f"DEBUG: [Canvas] Smart Stack Trace Initiated for {interactable}")
                         
                         # Check items in stack
                         valid_stack = []
                         for it in items_in_rect:
                             temp = it
                             while temp:
                                 if isinstance(temp, (RoiGraphicsItem, AnnotationGraphicsItem)):
                                     if temp not in valid_stack:
                                         valid_stack.append(temp)
                                     break
                                 temp = temp.parentItem()
                         
                         first_unselected = None
                         for item in valid_stack:
                             if not item.isSelected():
                                 first_unselected = item
                                 break
                         
                         if first_unselected:
                             print(f"Selecting underlying item: {first_unselected} (ID: {id(first_unselected)})")
                             first_unselected.setSelected(True)
                             forward_press_event(first_unselected)
                         else:
                             print(f"Deselecting top item: {interactable} (ID: {id(interactable)})")
                             interactable.setSelected(False)
                             # No drag if deselecting
                             
                         event.accept() 
                         return 
                         
                    elif is_shift:
                         interactable.setSelected(True)
                         forward_press_event(interactable)
                         event.accept()
                         return
                    else:
                         # Exclusive selection
                         # We must manually clear others because if Scene misses this item, super() would clear all.
                         if self.scene:
                             self.scene.blockSignals(True)
                             for item in self.scene.selectedItems():
                                 if item != interactable:
                                     item.setSelected(False)
                             self.scene.blockSignals(False)
                         
                         interactable.setSelected(True)
                         forward_press_event(interactable)
                         
                         event.accept()
                         return
                except Exception as e:
                    print(f"ERROR: Selection logic failed: {e}")
                    import traceback
                    traceback.print_exc()
                
                # We handled selection. But we still need super() for dragging if applicable.
                # If we call super(), and Scene misses it, super() might try to clear selection.
                # But since we already selected it, maybe super() sees it as selected?
                # No, super() logic is: Click on point -> Nothing -> Clear Selection.
                
                # To prevent super() from clearing selection, we can't easily interfere.
                # BUT, if we are in Hand mode, we disable drag anyway.
                
                # If we are in Pointer mode, and we click a thin line.
                # We selected it manually.
                # super() runs. Scene says "Nothing".
                # super() clears selection.
                # Result: Selection lost.
                
                # FIX: If we manually handled selection, DO NOT call super().
                # BUT then dragging won't work.
                
                # Compromise: If modifiers are pressed (Multi-select), we prioritize Selection over Dragging.
                # if is_ctrl or is_shift:
                
                # ALWAYS prioritize dispatch to super() if we hit an item manually, 
                # because otherwise Dragging will NEVER work if Scene.itemAt() failed (which is why we are here).
                # The only case to stop is if we want to BLOCK dragging (e.g. shift-click usually just selects).
                # But Ctrl-click might want to drag multiple items.
                
                # Temporarily disable View's Hand Drag if active, to allow Item Drag
                if self.dragMode() != QGraphicsView.DragMode.NoDrag:
                    self._temp_drag_restore = self.dragMode()
                    self.setDragMode(QGraphicsView.DragMode.NoDrag)
                    self._temp_drag_mode = True
                
                # We MUST call super().mousePressEvent(event) to let QGraphicsView initiate the drag.
                # But we need to make sure QGraphicsView sees the item.
                # Since we are here because Scene might have missed it (Fat Finger), 
                # calling super() might just click background and deselect everything.
                
                # TRICK: We don't call super() if we think Scene will miss it.
                # Instead, we manually initiate a drag? No, too complex.
                
                # Observation: If we manually set Selected, and then call super(), 
                # super() might deselect it if it thinks we clicked background.
                
                # If is_ctrl is False, we already cleared selection (Exclusive).
                # So if super() deselects, it's fine? No, we just selected 'interactable'.
                
                # Let's try calling super() anyway. If it deselects, we are screwed.
                # But if we DON'T call super(), drag never starts.
                
                # Solution: Check if itemAt matches.
                hit = self.itemAt(click_pos)
                if hit != interactable:
                     # Scene missed it. We rely on our manual selection.
                     # We CANNOT drag this item because QGraphicsView doesn't know it's under the mouse.
                     # User has to click precisely to drag.
                     Logger.debug(f"[CanvasView] Smart Pan hit {interactable}, but Scene sees {hit}. Selection updated, but drag might fail.")
                     return
                else:
                     # Scene sees it. Safe to call super() to start drag.
                     Logger.debug(f"[CanvasView] Smart Pan hit confirmed by Scene. Dispatching to super() for drag.")
                     super().mousePressEvent(event)
                     return

            # Temporarily disable drag to allow item interaction

            # Temporarily disable drag to allow item interaction
            if self.dragMode() != QGraphicsView.DragMode.NoDrag:
                self._temp_drag_restore = self.dragMode()
                self.setDragMode(QGraphicsView.DragMode.NoDrag)
                self._temp_drag_mode = True
                
            super().mousePressEvent(event)
            return
        else:
             # print("DEBUG: Smart Pan ignored (background or non-interactive)")
             pass

        if self.active_tool is None and self.annotation_mode == 'none' and event.button() == Qt.MouseButton.LeftButton:
             # Just ensure we fall through to super() for standard Hand Drag
             # But first check if we need to clear selection (if not clicking item)
             # Wait, if we are here, we passed Smart Pan logic, so we are clicking background (or non-interactable).
             modifiers = QApplication.keyboardModifiers()
             is_ctrl = bool(modifiers & Qt.KeyboardModifier.ControlModifier)
             is_shift = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)
             
             if not is_ctrl and not is_shift and self.scene:
                 # Standard behavior: clicking background clears selection
                 # But in Hand Mode, clicking background pans. Does it clear selection?
                 # Usually yes.
                 self.scene.clearSelection()
                 
             # Fall through to super() to handle DragMode.ScrollHandDrag
             pass


        super().mousePressEvent(event)


    def update_ruler_position(self, pos: QPointF):
        """Updates the ruler position from external sync."""
        if hasattr(self, 'scale_bar_item') and self.scale_bar_item:
            self.scale_bar_item.setPos(pos)

    def _emit_annotation_selected(self, ann_id):
        """Helper to find MainWindow and emit selection change for Property Panel sync."""
        window = self.window()
        if hasattr(window, 'on_annotation_selected_on_canvas'):
            window.on_annotation_selected_on_canvas(ann_id)

    def _on_roi_added(self, roi):
        """Called when a new ROI is added to the manager."""
        # Create item with current display scale
        # Fixed: Always use 1.0 because Scene is Full Resolution
        item = RoiGraphicsItem(roi, display_scale=1.0)
        item.roi_manager = self.roi_manager # Inject manager for sync
        self.scene.addItem(item)
        self._roi_items[roi.id] = item

    def _on_roi_removed(self, roi_id):
        if roi_id in self._roi_items:
            item = self._roi_items.pop(roi_id)
            self.scene.removeItem(item)

    def _on_roi_updated(self, roi):
        if roi.id in self._roi_items:
            item = self._roi_items[roi.id]
            
            # Prevent update loop if this item is currently being manipulated by the user
            # This prevents the "rebound" effect and double-translation during drag
            if getattr(item, 'is_dragging', False):
                return

            # Update path with scaling
            # Fixed: Always use 1.0 because Scene is Full Resolution
            scaled_path = item._scale_path(roi.path, 1.0)
            
            # Use flag to prevent itemChange from triggering a feedback loop
            item._is_updating = True
            try:
                item.setPath(scaled_path)
                
                # Reset position because the new path is "baked" in scene coordinates
                # This ensures we don't have residual offsets from previous local moves
                item.setPos(0, 0)
                
                item.roi_color = roi.color
                item.update_appearance()
            finally:
                item._is_updating = False
    
    def set_roi_manager(self, manager):
        """Connects to the ROI manager signals."""
        if self.roi_manager:
            try:
                self.roi_manager.roi_added.disconnect(self._on_roi_added)
                self.roi_manager.roi_removed.disconnect(self._on_roi_removed)
                self.roi_manager.roi_updated.disconnect(self._on_roi_updated)
                self.scene.selectionChanged.disconnect(self.on_scene_selection_changed)
            except:
                pass
        
        self.roi_manager = manager
        if manager:
            manager.roi_added.connect(self._on_roi_added)
            manager.roi_removed.connect(self._on_roi_removed)
            manager.roi_updated.connect(self._on_roi_updated)
            self.scene.selectionChanged.connect(self.on_scene_selection_changed)
            
            # Load existing
            self._sync_rois()

    def _sync_rois(self):
        # Clear
        for item in self._roi_items.values():
            self.scene.removeItem(item)
        self._roi_items.clear()
        
        if self.roi_manager:
            for roi in self.roi_manager.get_all_rois():
                self._on_roi_added(roi)

    def set_active_tool(self, tool):
        """Sets the active tool (ROI tool)."""
        self.setFocus() # Ensure focus for keyboard shortcuts (e.g. Space for Pan)
        self.active_tool = tool
        self._update_preview()

        if tool:
            # If tool is set, ensure annotation mode is none (though handled by controller)
            self.annotation_mode = 'none'
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            self._update_annotation_preview()
            
            # Set Cursor based on tool type
            tool_name = type(tool).__name__.lower()
            if "pointcounter" in tool_name or "count" in tool_name:
                self.setCursor(Qt.CursorShape.CrossCursor)
            elif "rect" in tool_name or "ellipse" in tool_name or "polygon" in tool_name:
                self.setCursor(Qt.CursorShape.CrossCursor)
            elif "annotation" in tool_name:
                 self.setCursor(Qt.CursorShape.CrossCursor)
            elif "linescan" in tool_name or "line" in tool_name:
                 self.setCursor(Qt.CursorShape.CrossCursor)
            elif "wand" in tool_name:
                self.setCursor(Qt.CursorShape.PointingHandCursor)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)

        elif self.annotation_mode == 'none':
             self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
             self.setCursor(Qt.CursorShape.OpenHandCursor)
             
             # Re-enable item movement in Hand mode
             for item in self._roi_items.values():
                 item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
                 item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
             for item in self._ann_items.values():
                 item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
                 item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)

    def _has_interactable_at(self, click_pos):
        try:
            items_in_rect = self.items(QRectF(click_pos.x() - 5, click_pos.y() - 5, 10, 10).toRect())
        except Exception:
            return False

        for item in items_in_rect:
            temp_item = item
            while temp_item:
                if isinstance(temp_item, (RoiGraphicsItem, AnnotationGraphicsItem, RoiHandleItem, ScaleBarItem)):
                    return True
                if (temp_item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable) or \
                   (temp_item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable):
                    return True
                temp_item = temp_item.parentItem()

        return False

    def set_annotation_mode(self, mode: str):
        """Sets the annotation drawing mode."""
        self.annotation_mode = mode
        self.current_ann_points = []
        self.preview_ann_item.setPath(QPainterPath())
        
        # New Logic: Use Tools for supported modes to unify drawing interaction
        if mode == 'rect':
             self.set_active_tool(RectangleSelectionTool(self.session))
        elif mode == 'ellipse':
             self.set_active_tool(EllipseSelectionTool(self.session))
        elif mode == 'polygon':
             self.set_active_tool(PolygonSelectionTool(self.session))
        elif mode == 'line':
             self.set_active_tool(LineScanTool(self.session))
        elif mode != 'none':
            # Fallback for unsupported modes (e.g. arrow, text)
            self.active_tool = None 
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            self.setCursor(Qt.CursorShape.CrossCursor)
        elif not self.active_tool:
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def update_scale_bar(self, settings):
        """Updates the scale bar settings."""
        if hasattr(self, 'scale_bar_item'):
            self.scale_bar_item.update_settings(settings)
            self.scene.update() # Force redraw

    def set_annotations(self, annotations):
        """Syncs the view with the annotation list."""
        # 0. Capture Selection State
        selected_ids = []
        for ann_id, item in self._ann_items.items():
            if item.isSelected():
                selected_ids.append(ann_id)
        
        # Track IDs to keep
        current_ids = {ann.id for ann in annotations}
        
        # 1. Remove stale items
        to_remove = [ann_id for ann_id in self._ann_items if ann_id not in current_ids]
        for ann_id in to_remove:
            item = self._ann_items.pop(ann_id)
            self.scene.removeItem(item)
            
        # 2. Update or Create
        for ann in annotations:
             # Skip if ROI-linked (Smart Merge)
             if ann.roi_id and self.roi_manager and self.roi_manager.get_roi(ann.roi_id):
                 if ann.id in self._ann_items:
                     item = self._ann_items.pop(ann.id)
                     self.scene.removeItem(item)
                 continue

             if ann.id in self._ann_items:
                 # Update existing
                 item = self._ann_items[ann.id]
                 # Skip update if dragging to prevent loop/lag
                 if not getattr(item, 'is_dragging', False):
                     item.update_from_model(ann)
             else:
                 # Create new
                 item = AnnotationGraphicsItem(ann)
                 item.modified.connect(self.on_annotation_modified_item)
                 self.scene.addItem(item)
                 self._ann_items[ann.id] = item
                 
                 # Restore Selection for new items if they were selected? 
                 # IDs persist, so yes.
                 if ann.id in selected_ids:
                     item.setSelected(True)
        
        # Force redraw
        self.scene.update()

    def update_single_annotation(self, ann):
        """Updates a single annotation item without full reset."""
        if ann.id in self._ann_items:
            item = self._ann_items[ann.id]
            # If this item is currently being dragged, don't update it from external source
            # to avoid conflict/lag.
            if getattr(item, 'is_dragging', False) or getattr(item, '_is_actually_dragging', False):
                return

            item.update_from_model(ann)
            # Force update
            item.update()

    def on_annotation_modified_item(self, item):
        """Called when an annotation item is modified via handles or drag."""
        Logger.debug(f"View received modification for item {item.ann_id}")
        path = item.path()
        ann_type = item.ann_type
        
        new_points = []
        
        # Helper to map local point to scene (handling item position ONLY, ignoring rotation)
        # We want the "Unrotated Scene Points" which define the shape geometry.
        # Rotation is stored separately.
        def map_pt(p):
            # item.pos() is the translation offset
            # We assume 'p' is in local coords (unrotated)
            # Handle QPainterPath.Element (x, y properties) vs QPointF (x(), y() methods)
            if hasattr(p, 'x') and not callable(p.x):
                 px = p.x
                 py = p.y
            else:
                 px = p.x()
                 py = p.y()
            return QPointF(px + item.pos().x(), py + item.pos().y())

        if ann_type in ['arrow', 'line']:
            # Expecting 2 points
            if path.elementCount() >= 2:
                p1 = path.elementAt(0)
                p2 = path.elementAt(1)
                
                p1_mapped = map_pt(p1)
                p2_mapped = map_pt(p2)
                
                new_points = [(p1_mapped.x(), p1_mapped.y()), (p2_mapped.x(), p2_mapped.y())]
                
        elif ann_type in ['rect', 'ellipse', 'circle']:
             # Use bounding rect
             # Note: We use the unrotated bounding rect corners mapped to scene (translated)
             rect = path.boundingRect()
             tl_scene = map_pt(rect.topLeft())
             br_scene = map_pt(rect.bottomRight())
             new_points = [(tl_scene.x(), tl_scene.y()), (br_scene.x(), br_scene.y())]
             
        elif ann_type == 'polygon':
             # Extract all vertices
             for i in range(path.elementCount()):
                 e = path.elementAt(i)
                 if e.isMoveTo() or e.isLineTo():
                     pt = map_pt(e)
                     new_points.append((pt.x(), pt.y()))
        
        # Fallback for roi_ref or other types (treat as polygon/path)
        if not new_points and path.elementCount() > 0:
             for i in range(path.elementCount()):
                 e = path.elementAt(i)
                 if e.isMoveTo() or e.isLineTo():
                     pt = map_pt(e)
                     new_points.append((pt.x(), pt.y()))
        
        if new_points:
            update_data = {
                'id': item.ann_id,
                'points': new_points,
                'properties': {'rotation': item.rotation()} # Save rotation
            }
            # Merge existing properties if possible?
            # The signal receiver should handle merge.
            # But here we emit a partial dict?
            # Usually we update the Annotation object directly?
            # CanvasView emits signal, Main updates session.
            # We should probably include 'rotation' in properties.
            # But wait, 'properties' is a dict in GraphicAnnotation.
            # We are sending a dict with 'properties' key.
            # The receiver (MainWindow) likely does: ann.points = data['points']; ann.properties.update(data['properties'])
            
            self.annotation_modified.emit(update_data)
            item.update()
             

    def contextMenuEvent(self, event):
        """Handle Context Menu events (Right Click)."""
        # If we have an active tool, it might handle right click (e.g. Polygon finish)
        if self.active_tool:
             # We already handled Right Button in mousePressEvent for immediate response,
             # but Qt might still trigger contextMenuEvent.
             # We should consume it to prevent default menu if the tool is active.
             event.accept()
             return

        # If we are in annotation mode, we also handle right click to finish
        if self.annotation_mode != 'none':
             event.accept()
             return
             
        # Otherwise show standard context menu (if any)
        super().contextMenuEvent(event)

    def mouseMoveEvent(self, event):
        scene_pos = self.mapToScene(event.position().toPoint())
        self.mouse_moved.emit(int(scene_pos.x()), int(scene_pos.y()))
        
        # 1. ROI Tools
        # Handle Bypass FIRST
        if getattr(self, '_bypass_active_tool_events', False):
             # Logger.debug(f"[CanvasView] Bypassing tool move (Bypass Flag True)") 
             super().mouseMoveEvent(event)
             return

        if self.active_tool:
            self._update_preview()
            try:
                self.active_tool.mouse_move(scene_pos, event.modifiers())
            except Exception as e:
                Logger.error(f"[CanvasView] Tool mouse_move failed: {e}")
            return
            
        # 2. Annotation Tools
        if self.annotation_mode != 'none':
            # Only handle annotation move if we are actively drawing (have points)
            if self.current_ann_points:
                self._handle_annotation_move(scene_pos)
                return
            # If not drawing, fall through to super() to allow item dragging

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        # Restore drag mode if we were moving an item
        if hasattr(self, '_temp_drag_restore'):
            self.setDragMode(self._temp_drag_restore)
            del self._temp_drag_restore
            
        if getattr(self, '_temp_drag_mode', False):
            self._temp_drag_mode = False
            
        scene_pos = self.mapToScene(event.position().toPoint())
        
        # 1. ROI Tools
        # Handle Bypass FIRST
        if getattr(self, '_bypass_active_tool_events', False):
             Logger.debug(f"[CanvasView] Bypass tool release due to item interaction (Active Tool: {self.active_tool})")
             self._bypass_active_tool_events = False
             super().mouseReleaseEvent(event)
             return

        if self.active_tool:
            self.active_tool.mouse_release(scene_pos, event.modifiers())
            self._update_preview()
            return

        # 2. Annotation Tools (Legacy / Fallback)
        # (Usually handled in click/move, but maybe for drag-to-draw rects?)
        # For now, we use click-click for lines/polys, maybe drag for rect/circle?
        # Let's support drag for Rect/Circle/Ellipse
        if self.annotation_mode in ['rect', 'circle', 'ellipse', 'arrow', 'line'] and len(self.current_ann_points) > 0:
             # If we were dragging to create, finish on release
             if len(self.current_ann_points) == 2:
                 self._finish_annotation()
        
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        """Handle keyboard events (Delete/Backspace to remove items, Space for Pan, [ ] for size)."""
        # print(f"DEBUG: [CanvasView] KeyPress: {event.key()} Modifiers: {event.modifiers()}")
        
        if event.isAutoRepeat():
            super().keyPressEvent(event)
            return

        # Ctrl: Switch to Hand Tool (Pan) + Multi-Select Mode (Only while held)
        if event.key() == Qt.Key.Key_Control:
            if not getattr(self, '_is_ctrl_pan_active', False):
                self._is_ctrl_pan_active = True
                
                # Store state
                self._prev_tool_ctrl = self.active_tool
                self._prev_ann_mode_ctrl = self.annotation_mode
                self._prev_drag_mode_ctrl = self.dragMode()
                self._prev_cursor_ctrl = self.viewport().cursor()
                
                # Switch to Pan Mode (ScrollHandDrag)
                # This fulfills the requirement: "Hold Ctrl to switch to Hand Tool"
                self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
                self.setCursor(Qt.CursorShape.OpenHandCursor)
                
                # Re-enable item movement/selection in Hand mode
                for item in self._roi_items.values():
                    item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
                    item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
                for item in self._ann_items.values():
                    item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
                    item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
                
                # Keep active_tool temporarily but bypass its events?
                # No, if we set DragMode to ScrollHandDrag, QGraphicsView handles panning internally.
                # But active_tool logic in mousePressEvent might override it.
                # So we should probably bypass active_tool while Ctrl is held.
                # The bypass logic in mousePressEvent handles "interactable" items, 
                # but for pure Panning (clicking background), we also need to bypass active_tool.
                
                Logger.debug(f"[CanvasView] Ctrl pressed: pan mode enabled. rois={len(self._roi_items)} anns={len(self._ann_items)}")
            
            # Important: Do NOT accept the event if we want other widgets or parent to handle it?
            # Actually, for modifiers, we usually accept it.
            # But Multi-Select logic is in mousePressEvent which checks modifiers.
            event.accept()
            return

        # Ctrl+A: Select All ROIs (excluding LineScans, Annotations, ScaleBar)
        # Use StandardKey.SelectAll for cross-platform compatibility (Ctrl+A / Cmd+A)
        if event.matches(QKeySequence.StandardKey.SelectAll) or (event.key() == Qt.Key.Key_A and (event.modifiers() & Qt.KeyboardModifier.ControlModifier)):
            try:
                # Clear current selection first
                self.scene.clearSelection()
                
                # Block signals to prevent partial updates during loop
                self.scene.blockSignals(True)
                
                # Select relevant ROIs
                count = 0
                if self.roi_manager:
                    for item in self.scene.items():
                        if isinstance(item, RoiGraphicsItem):
                            # Get ROI object to check type
                            roi = self.roi_manager.get_roi(item.roi_id)
                            if roi:
                                # Filter out line scans
                                if getattr(roi, 'roi_type', '') != 'line_scan':
                                     item.setSelected(True)
                                     count += 1
                
                self.scene.blockSignals(False)
                
                # Manually trigger ONE update after batch selection
                self.on_scene_selection_changed()
                
                print(f"DEBUG: Selected {count} ROIs via Select All")
                event.accept()
                return
            except Exception as e:
                print(f"ERROR: Select All failed: {e}")
                self.scene.blockSignals(False) # Ensure unblocked
                return

        # Space: Temporarily switch to Pan mode
        # Also support Ctrl if user requests "Ctrl to Hand Tool" (though conflicts with Multi-Select)
        # For now, stick to Space as Pan, but we can allow Ctrl to temporarily disable tool (handled in mousePress)
        if event.key() == Qt.Key.Key_Space:
            # Handle AutoRepeat logic manually if needed, though checked at top.
            if not hasattr(self, '_prev_tool'):
                # Store current state
                self._prev_tool = self.active_tool
                self._prev_ann_mode = self.annotation_mode
                
                # Switch to Pan
                self.active_tool = None # Bypassing set_active_tool to avoid full reset
                self.annotation_mode = 'none'
                
                self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
                self.setCursor(Qt.CursorShape.OpenHandCursor)
                
                # Re-enable item movement in Hand mode
                for item in self._roi_items.values():
                    item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
                    item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
                for item in self._ann_items.values():
                    item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
                    item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
                    
            event.accept()
            return

        # ESC: Cancel current tool
        if event.key() == Qt.Key.Key_Escape:
            self.set_active_tool(None)
            self.set_annotation_mode('none')
            self.tool_cancelled.emit()
            event.accept()
            return

        # Brackets: Adjust brush/point size
        if event.key() in (Qt.Key.Key_BracketLeft, Qt.Key.Key_BracketRight):
            if self.active_tool and hasattr(self.active_tool, 'radius'):
                step = 0.5
                if event.key() == Qt.Key.Key_BracketLeft:
                    self.active_tool.radius = max(0.5, self.active_tool.radius - step)
                else:
                    self.active_tool.radius = min(50.0, self.active_tool.radius + step)
                
                # Notify main window to update its UI
                if hasattr(self.window(), 'roi_toolbox'):
                    self.window().roi_toolbox.spin_count_radius.setValue(self.active_tool.radius)
                
                # print(f"Tool radius adjusted to: {self.active_tool.radius}")
            event.accept()
            return

        # Delete/Backspace
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            selected_items = self.scene.selectedItems()
            roi_ids_to_remove = set()
            ann_ids_to_remove = set()

            def resolve_target_item(item):
                cur = item
                while cur and not isinstance(cur, (RoiGraphicsItem, AnnotationGraphicsItem)):
                    cur = cur.parentItem()
                return cur
            
            for item in selected_items:
                target = resolve_target_item(item)
                if isinstance(target, RoiGraphicsItem):
                    roi_ids_to_remove.add(target.roi_id)
                elif isinstance(target, AnnotationGraphicsItem):
                    ann_ids_to_remove.add(target.ann_id)

            # Remove ROIs
            if roi_ids_to_remove and self.session and self.session.roi_manager:
                for roi_id in roi_ids_to_remove:
                    self.session.roi_manager.remove_roi(roi_id, undoable=True)
            
            # Remove Annotations
            if ann_ids_to_remove and self.session:
                # Update Session model (global annotations list)
                self.session.annotations = [a for a in self.session.annotations if a.id not in ann_ids_to_remove]
                
                # Update local view items
                for ann_id in ann_ids_to_remove:
                    if ann_id in self._ann_items:
                        item = self._ann_items.pop(ann_id)
                        self.scene.removeItem(item)
                
                # Notify main window UI and propagate to all views
                window = self.window()
                if window:
                    if hasattr(window, 'annotation_panel'):
                        window.annotation_panel.update_annotation_list()
                    if hasattr(window, 'multi_view'):
                        window.multi_view.set_annotations(self.session.annotations)
                
                # Clear selection state in current view
                self.scene.clearSelection()
                
            return
                
        super().keyPressEvent(event)


    def _handle_annotation_click(self, scene_pos: QPointF):
        """Handles clicks for annotation creation."""
        mode = self.annotation_mode
        # print(f"DEBUG: Annotation Click - Mode: {mode}, Pos: {scene_pos}")
        
        # Fixed Size Mode Check
        if self.annotation_fixed_size_mode:
            self._create_fixed_size_annotation(scene_pos, mode)
            return

        # Start new shape
        if not self.current_ann_points:
            self.current_ann_points.append(scene_pos)
            # For Polygon, we need a second point (floating) to start with, 
            # otherwise the first point moves with the mouse.
            if mode == 'polygon':
                self.current_ann_points.append(scene_pos)
            # print("DEBUG: Started new annotation shape")
        else:
            # Continue shape
            if mode in ['polygon', 'line']:
                # For line, 2nd click finishes
                if mode == 'line':
                    self.current_ann_points[1] = scene_pos
                    self._finish_annotation()
                    # print("DEBUG: Finished line annotation")
                else:
                    # Polygon: add point
                    # The last point was the floating one. Fix it (by keeping it) and add a new floating one.
                    self.current_ann_points.append(scene_pos)
                    # print(f"DEBUG: Added polygon point (Total: {len(self.current_ann_points)})")
            elif mode in ['rect', 'circle', 'ellipse', 'arrow']:
                # These are usually drag-to-create. 
                # If we clicked again, it might be to finish if we didn't drag?
                # Or maybe we support click-click?
                # Let's assume Drag behavior: Click (start), Drag (update), Release (finish)
                # So this click is just start (handled above)
                pass
            elif mode == 'text':
                # Text is instant
                self.current_ann_points[0] = scene_pos
                self._create_text_annotation(scene_pos)
                self.current_ann_points = []
        
        self._update_annotation_preview()

    def _handle_annotation_move(self, scene_pos: QPointF):
        if not self.current_ann_points:
            return
            
        mode = self.annotation_mode
        # Update the last point (or second point) to current pos
        if mode == 'polygon':
            self.current_ann_points[-1] = scene_pos
        else:
            # For 2-point shapes (Line, Arrow, Rect, etc.)
            if len(self.current_ann_points) == 1:
                # First move after click -> Add 2nd point
                self.current_ann_points.append(scene_pos)
            elif len(self.current_ann_points) > 1:
                self.current_ann_points[1] = scene_pos
                
        self._update_annotation_preview()

    def keyReleaseEvent(self, event):
        """Restore tool after space or ctrl is released."""
        if event.isAutoRepeat():
            super().keyReleaseEvent(event)
            return

        # Ctrl: Restore Tool after Pan/Multi-Select
        if event.key() == Qt.Key.Key_Control:
            if getattr(self, '_is_ctrl_pan_active', False):
                self._is_ctrl_pan_active = False
                
                # Restore state
                # Only restore if they were set (safeguard)
                if hasattr(self, '_prev_drag_mode_ctrl'):
                    self.setDragMode(self._prev_drag_mode_ctrl)
                if hasattr(self, '_prev_cursor_ctrl'):
                    self.setCursor(self._prev_cursor_ctrl)
                
                # Re-disable item movement if tool was active
                # We check the CURRENT active_tool (which we didn't clear)
                # Or the restored one if we had cleared it.
                # In the new logic, we didn't clear active_tool, so self.active_tool is still valid.
                
                if self.active_tool or self.annotation_mode != 'none':
                    Logger.debug(f"[CanvasView] Ctrl released with active context: tool={type(self.active_tool).__name__ if self.active_tool else None} ann_mode={self.annotation_mode}")

                # Cleanup
                if hasattr(self, '_prev_tool_ctrl'): del self._prev_tool_ctrl
                if hasattr(self, '_prev_ann_mode_ctrl'): del self._prev_ann_mode_ctrl
                if hasattr(self, '_prev_drag_mode_ctrl'): del self._prev_drag_mode_ctrl
                if hasattr(self, '_prev_cursor_ctrl'): del self._prev_cursor_ctrl
                
                Logger.debug("[CanvasView] Ctrl released: pan mode restored")
            
            event.accept()
            return

        if event.key() == Qt.Key.Key_Space:
            if hasattr(self, '_prev_tool'):
                # Restore previous state
                # If _prev_tool is None, it means we were in Pan mode, so set_active_tool(None) works.
                # If we were in ROI tool, it restores it.
                self.set_active_tool(self._prev_tool)
                
                # Restore annotation mode if it was active
                if hasattr(self, '_prev_ann_mode') and self._prev_ann_mode != 'none':
                    self.set_annotation_mode(self._prev_ann_mode)
                
                # Cleanup
                del self._prev_tool
                if hasattr(self, '_prev_ann_mode'):
                    del self._prev_ann_mode
                    
            event.accept()
            return
            
        super().keyReleaseEvent(event)


    def _update_annotation_preview(self):
        path = QPainterPath()
        pts = self.current_ann_points
        if not pts:
            self.preview_ann_item.setPath(path)
            return
            
        mode = self.annotation_mode
        
        try:
            if mode == 'arrow' and len(pts) >= 2:
                start, end = pts[0], pts[1]
                path.moveTo(start)
                path.lineTo(end)
                # Arrowhead logic
                import math
                angle = math.atan2(end.y() - start.y(), end.x() - start.x())
                arrow_len = 15 / self.display_scale if self.display_scale > 0 else 15
                arrow_angle = math.pi / 6
                p1 = end - QPointF(arrow_len * math.cos(angle - arrow_angle), arrow_len * math.sin(angle - arrow_angle))
                p2 = end - QPointF(arrow_len * math.cos(angle + arrow_angle), arrow_len * math.sin(angle + arrow_angle))
                path.moveTo(end)
                path.lineTo(p1)
                path.moveTo(end)
                path.lineTo(p2)
                
            elif mode == 'line' and len(pts) >= 2:
                path.moveTo(pts[0])
                path.lineTo(pts[1])
                
            elif mode == 'rect' and len(pts) >= 2:
                path.addRect(QRectF(pts[0], pts[1]).normalized())
                
            elif mode == 'circle' and len(pts) >= 2:
                # Preview circle fitting in box
                rect = QRectF(pts[0], pts[1]).normalized()
                center = rect.center()
                radius = min(rect.width(), rect.height()) / 2.0
                path.addEllipse(center, radius, radius)
                
            elif mode == 'ellipse' and len(pts) >= 2:
                path.addEllipse(QRectF(pts[0], pts[1]).normalized())
                
            elif mode == 'polygon' and len(pts) >= 1:
                path.moveTo(pts[0])
                for p in pts[1:]:
                    path.lineTo(p)
                    
            self.preview_ann_item.setPath(path)
            self.preview_ann_item.setVisible(True) # Ensure visible
            pen = QPen(QColor("#FFFF00"), 2)
            pen.setStyle(Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            self.preview_ann_item.setPen(pen)
        except Exception as e:
            print(f"Error updating annotation preview: {e}")

    def _create_fixed_size_annotation(self, center_pos: QPointF, mode: str):
        """Creates an annotation immediately using stored fixed size."""
        points = []
        
        # Get Size
        # If tuple, use it. If scalar, use it.
        size = self.last_ann_size.get(mode, 50.0)
        width, height = 50.0, 50.0
        
        if isinstance(size, (tuple, list)):
            width, height = size[0], size[1]
        else:
            width, height = size, size
            
        if mode in ['rect', 'ellipse', 'circle']:
            # Center centered
            top_left = center_pos - QPointF(width / 2, height / 2)
            bottom_right = center_pos + QPointF(width / 2, height / 2)
            points = [(top_left.x(), top_left.y()), (bottom_right.x(), bottom_right.y())]
            
        elif mode in ['arrow', 'line']:
            # Start at click, apply saved vector (width=dx, height=dy)
            start = center_pos
            end = center_pos + QPointF(width, height)
            points = [(start.x(), start.y()), (end.x(), end.y())]
            
        elif mode == 'text':
             # Just place it
             points = [(center_pos.x(), center_pos.y())]
        
        if points:
            self.current_ann_points = points
            self._finish_annotation()

    def _finish_annotation(self):
        if not self.current_ann_points:
            return
            
        # Create Annotation Object
        mode = self.annotation_mode
        points = [(p.x(), p.y()) for p in self.current_ann_points]
        
        # Cleanup preview
        self.current_ann_points = []
        self.preview_ann_item.setPath(QPainterPath())
        self.preview_ann_item.setVisible(False)
        self.scene.update() # Force update to remove preview line immediately
        
        # Check validity
        # Polygon needs at least 3 points
        if mode == 'polygon' and len(points) < 3:
             print("Polygon annotation cancelled: Need at least 3 points.")
             return
             
        if len(points) < 2 and mode != 'text' and mode != 'polygon': # Polygon handled above
            return
            
        # Create ID
        import uuid
        ann_id = str(uuid.uuid4())
        
        # Determine Color (Default Yellow)
        color = "#FFFF00" 
        
        # Calculate initial properties based on current view scale
        props = {}
        if mode == 'arrow':
            # Default arrow head size in SCENE coordinates
            # We want it to look ~15px on screen.
            # display_scale = display / scene -> scene = 15 / display_scale
            scale = self.display_scale if self.display_scale > 0 else 1.0
            props['arrow_head_size'] = 15.0 / scale
        
        # Save Size for Fixed Mode
        if mode in ['rect', 'ellipse', 'circle']:
            if len(points) == 2:
                w = abs(points[1][0] - points[0][0])
                h = abs(points[1][1] - points[0][1])
                self.last_ann_size[mode] = (w, h)
        elif mode in ['arrow', 'line']:
            if len(points) == 2:
                import math
                dx = points[1][0] - points[0][0]
                dy = points[1][1] - points[0][1]
                length = math.sqrt(dx*dx + dy*dy)
                self.last_ann_size[mode] = length

        ann = GraphicAnnotation(
            id=ann_id,
            type=mode,
            points=points,
            text="" if mode != 'text' else "Text",
            color=color,
            thickness=2,
            visible=True,
            properties=props
        )
        
        # No reverse mapping needed! points are already in scene coordinates from mapToScene.
            
        self.annotation_created.emit(ann)
        
        # Ensure we refresh the view to show the new annotation
        # The main window should call set_annotations, but let's be sure
        self.viewport().update()
        
    def _create_text_annotation(self, pos):
        from PySide6.QtWidgets import QInputDialog
        text, ok = QInputDialog.getText(self, tr("Add Text"), tr("Enter text:"))
        if ok and text:
            import uuid
            ann = GraphicAnnotation(
                id=str(uuid.uuid4()),
                type='text',
                points=[(pos.x(), pos.y())],
                text=text,
                color="#FFFF00",
                thickness=2,
                visible=True
            )
            # Reverse map
            # if self.display_scale < 1.0:
            #    scale = 1.0 / self.display_scale
            #    ann.points = [(p[0] * scale, p[1] * scale) for p in ann.points]
            
            self.annotation_created.emit(ann)

    def set_selected(self, selected: bool):
        """Updates the selection state and triggers repaint."""
        if self.is_selected != selected:
            self.is_selected = selected
            self.viewport().update()

    def set_label(self, text: str):
        """Sets the label text to be displayed in the top-left corner."""
        self.label_text = text
        self.viewport().update()

    def update_image(self, image: np.ndarray, scene_rect: QRectF = None):
        """
        Updates the displayed image.
        Args:
            image: numpy array (H, W, 3) or (H, W) or None.
            scene_rect: Optional QRectF defining the full scene dimensions (for mapping).
        """
        print(f"[DEBUG] CanvasView({self.view_id}): update_image called")
        if image is None:
            print(f"[DEBUG] CanvasView({self.view_id}): image is None")
            self.pixmap_item.setPixmap(QPixmap())
            self.last_display_array = None
            self.display_scale = 1.0
            self.scene.update()
            self.viewport().update()
            return

        h, w = image.shape[:2]
        print(f"[DEBUG] CanvasView({self.view_id}): Image shape: {image.shape}, Mean: {image.mean():.2f}, Dtype: {image.dtype}")
        
        # 1. Update Pixmap
        try:
            qimg = qimage2ndarray.array2qimage(image, normalize=False)
            if qimg.isNull():
                 print(f"[DEBUG] CanvasView({self.view_id}): Generated QImage is Null!")
            pixmap = QPixmap.fromImage(qimg)
            if pixmap.isNull():
                 print(f"[DEBUG] CanvasView({self.view_id}): Generated QPixmap is Null!")
            self.pixmap_item.setPixmap(pixmap)
            print(f"[DEBUG] CanvasView({self.view_id}): Pixmap set. Size: {pixmap.size()}")
        except Exception as e:
            print(f"[ERROR] CanvasView({self.view_id}): Pixmap conversion failed: {e}")
            import traceback
            traceback.print_exc()

        self.last_display_array = image # Store for tool access
        
        # 2. Update Scene Rect and Scaling
        # If scene_rect is provided, it represents the "True" dimensions
        if scene_rect:
            print(f"[DEBUG] CanvasView({self.view_id}): SceneRect provided: {scene_rect}")
            self.scene.setSceneRect(scene_rect)
            
            # If the displayed image is smaller than scene_rect, it means we are downsampling
            # We need to scale the pixmap item to fill the scene rect?
            # NO. The scene coordinate system should match the "True" resolution (e.g. 10k x 10k).
            # The pixmap item is smaller (e.g. 2k x 2k).
            # So we scale the pixmap item UP to match the scene rect.
            
            scene_w = scene_rect.width()
            if scene_w > 0:
                scale = scene_w / w
                self.pixmap_item.setTransform(QTransform().scale(scale, scale))
                # Ensure position is reset
                self.pixmap_item.setPos(0, 0)
                self.display_scale = 1.0 / scale # display / full
                print(f"[DEBUG] CanvasView({self.view_id}): Applied Scale: {scale}")
            else:
                self.display_scale = 1.0
                self.pixmap_item.setTransform(QTransform())
                self.pixmap_item.setPos(0, 0)
        else:
            # No scene rect provided, assume 1:1
            self.scene.setSceneRect(0, 0, w, h)
            self.pixmap_item.setTransform(QTransform())
            self.pixmap_item.setPos(0, 0)
            self.display_scale = 1.0
            
        # 3. Update ROIs appearance based on new scale
        # We need to refresh all ROI items because their path scaling depends on display_scale
        if self.roi_manager:
            self._sync_rois()
            
        # Force refresh
        self.scene.update()
        self.viewport().update()
        
        # 4. Flash effect (optional)
        if self.flash_active:
            # TODO: Implement flash overlay
            pass

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            # Check if any file has a valid extension
            has_valid_image = False
            valid_exts = ('.tif', '.tiff', '.png', '.jpg', '.jpeg', '.bmp')
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith(valid_exts):
                    has_valid_image = True
                    break
            
            if has_valid_image:
                event.acceptProposedAction()
                self._update_quicklook(event)
                return
                
        event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._update_quicklook(event)

    def dragLeaveEvent(self, event):
        self.preview_label.hide()
        super().dragLeaveEvent(event)

    def _update_quicklook(self, event):
        """Updates the position and content of the quicklook tooltip."""
        urls = event.mimeData().urls()
        if not urls:
            return
            
        file_path = urls[0].toLocalFile()
        if not file_path:
            return

        # Position logic
        # Map global mouse pos to widget coords? Or use event.pos()?
        # event.pos() is relative to the view widget
        pos = event.position().toPoint()
        
        # Load thumbnail if not already loaded for this path (Caching could be added here)
        # For responsiveness, we'll do a quick load or use a placeholder
        # Since this is "Quicklook", we need it to be fast. 
        # Ideally, the MimeData would carry the pixmap, but we only have the URL.
        # We will load a small version.
        
        if self.preview_label.isHidden() or getattr(self, '_current_preview_path', None) != file_path:
             self._load_quicklook_image(file_path)
             self._current_preview_path = file_path
        
        # Move label to follow mouse (offset by 20px)
        global_pos = self.mapToGlobal(pos)
        self.preview_label.move(global_pos + QPoint(20, 20))
        self.preview_label.show()

    def _load_quicklook_image(self, path):
        try:
            # Use OpenCV for fast loading
            # Only read the first image if it's a stack
            # Use flags=-1 to read as-is (including alpha)
            # But for quicklook, grayscale or RGB is fine.
            # Let's read generic
            
            # Simple check for valid extensions
            if not path.lower().endswith(('.tif', '.tiff', '.png', '.jpg', '.jpeg')):
                 return

            # Read image (downsampled for speed?)
            # Since we can't easily "seek" in Tiff with cv2.imread without loading, 
            # we rely on OS caching.
            
            # We can use QImageReader for better performance on large Tiffs?
            # Or just stick to cv2 for consistency with the rest of the app.
            
            # img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
            # Fix for Unicode paths:
            img_stream = np.fromfile(path, dtype=np.uint8)
            img = cv2.imdecode(img_stream, cv2.IMREAD_UNCHANGED)
            
            if img is None:
                return
                
            # Handle dimensions
            # If 3D (Time/Z), take max proj or first slice
            if img.ndim == 3:
                 if img.shape[2] > 4: # Multi-channel > 4
                      img = np.max(img, axis=2)
                 # Else keep RGB
            
            # Normalize to 8-bit for display
            if img.dtype != np.uint8:
                # Min-Max Scaling
                min_val = np.min(img)
                max_val = np.max(img)
                if max_val > min_val:
                    img = ((img - min_val) / (max_val - min_val) * 255).astype(np.uint8)
                else:
                    img = np.zeros_like(img, dtype=np.uint8)
            
            # Convert to QPixmap
            h, w = img.shape[:2]
            
            # Resize for thumbnail (max 200x200)
            scale = min(200/w, 200/h)
            new_w, new_h = int(w*scale), int(h*scale)
            img_small = cv2.resize(img, (new_w, new_h))
            
            qimg = qimage2ndarray.array2qimage(img_small, normalize=False)
            pixmap = QPixmap.fromImage(qimg)
            
            self.preview_label.setPixmap(pixmap)
            self.preview_label.resize(pixmap.size())
            
        except Exception as e:
            print(f"Quicklook Error: {e}")

    def dropEvent(self, event):
        self.preview_label.hide()
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls:
                file_path = urls[0].toLocalFile()
                # Check extension?
                if file_path.lower().endswith(('.tif', '.tiff', '.png', '.jpg', '.jpeg')):
                    print(f"File dropped on {self.view_id}: {file_path}")
                    self.file_dropped.emit(file_path, self.active_channel_index)
                    event.acceptProposedAction()
                    return
        event.ignore()

    def paintEvent(self, event):
        """Override to draw overlay text and selection border."""
        super().paintEvent(event)
        
        # Only start painter if we have something to draw
        if self.is_selected or self.label_text or self.flash_active:
            painter = QPainter()
            # Explicitly begin the painter on the viewport
            if not painter.begin(self.viewport()):
                return
                
            try:
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                
                # 0. Flash Feedback (Top priority visual cue)
                if self.flash_active:
                    rect = self.viewport().rect().adjusted(2, 2, -3, -3)
                    # Green flash for update
                    pen = QPen(QColor("#00FF00"), 4) 
                    pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
                    painter.setPen(pen)
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawRect(rect)
                
                # 1. Draw Selection Border
                if self.is_selected and not self.flash_active: # Flash overrides selection border temporarily
                    rect = self.viewport().rect().adjusted(1, 1, -2, -2)
                    palette = QApplication.palette()
                    highlight_color = palette.color(QPalette.ColorRole.Highlight)
                    pen = QPen(highlight_color, 3)  # Theme highlight
                    pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
                    painter.setPen(pen)
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawRect(rect)
                
                # 2. Draw Label Text
                if self.label_text:
                    # Use widget's font to avoid loading issues, just scale it
                    font = self.font()
                    font.setBold(True)
                    font.setPointSize(12)
                    painter.setFont(font)
                    
                    # Calculate Text Rect
                    metrics = painter.fontMetrics()
                    text_width = metrics.horizontalAdvance(self.label_text)
                    text_height = metrics.height()
                    
                    padding = 5
                    x = 10
                    y = 10
                    rect = QRectF(x, y, text_width + 2*padding, text_height + 2*padding)
                    
                    # Draw Background (Theme Highlight if selected, else Black)
                    palette = QApplication.palette()
                    if self.is_selected:
                        bg_color = palette.color(QPalette.ColorRole.Highlight)
                        bg_color.setAlpha(200)
                    else:
                        bg_color = QColor(0, 0, 0, 150)
                        
                    painter.setBrush(QBrush(bg_color))
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.drawRoundedRect(rect, 4, 4)
                    
                    # Draw Text
                    painter.setPen(palette.color(QPalette.ColorRole.HighlightedText) if self.is_selected else QColor(255, 255, 255))
                    painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.label_text)
                
                # 3. Draw Placeholder Hint if empty
                if self.pixmap_item.pixmap().isNull() or self.pixmap_item.pixmap().width() <= 1:
                    hint = "Drop Image Here"
                    cx, cy = self.width() // 2, self.height() // 2
                    hint_rect = QRectF(cx - 100, cy - 20, 200, 40)
                    painter.setPen(QColor(200, 200, 200))
                    painter.drawText(hint_rect, Qt.AlignmentFlag.AlignCenter, hint)
                    
            except Exception as e:
                print(f"Paint Error: {e}")
            finally:
                # Ensure painter is ended properly
                painter.end()

    def set_active_tool(self, tool):
        self.active_tool = tool
        self._update_preview()
        
        if tool is not None:
            Logger.debug(f"[CanvasView] Active tool set: {type(tool).__name__}")
            # Clear annotation mode if a regular tool is selected
            # Note: The main window's "Nuclear Option" uses regular tools (like rect_tool) 
            # for annotations, so we should NOT clear the mode if it's just passing through.
            # But here set_annotation_mode('none') just clears the legacy drawing mode, which is fine.
            self.annotation_mode = 'none'
            self._update_annotation_preview()
            
            # Tool active: Disable drag
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            
            # Set appropriate cursor based on tool type
            # We check the class name or type to avoid circular imports if needed
            tool_name = type(tool).__name__.lower()
            
            if "pointcounter" in tool_name or "count" in tool_name:
                self.setCursor(Qt.CursorShape.CrossCursor)
            elif "rect" in tool_name or "ellipse" in tool_name or "polygon" in tool_name:
                self.setCursor(Qt.CursorShape.CrossCursor) # Drawing tools usually benefit from crosshair
            elif "annotation" in tool_name:
                 self.setCursor(Qt.CursorShape.CrossCursor)
            elif "linescan" in tool_name or "line" in tool_name:
                 self.setCursor(Qt.CursorShape.CrossCursor)
            elif "wand" in tool_name:
                self.setCursor(Qt.CursorShape.PointingHandCursor)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)
                
        else:
            # No tool (Hand mode): Enable Pan/Drag AND Item Movement
            Logger.debug("[CanvasView] Active tool cleared (Hand mode)")
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            self.setCursor(Qt.CursorShape.OpenHandCursor) # Use hand cursor for Pan mode
            for item in self._roi_items.values():
                # Allow moving ROIs in Hand mode
                item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
                item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
                item.setAcceptHoverEvents(True)
            for item in self._ann_items.values():
                # Allow moving Annotations in Hand mode
                item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
                item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
                item.setAcceptHoverEvents(True)

    def set_annotation_mode(self, mode: str):
        """Sets the current graphic annotation drawing mode."""
        # print(f"DEBUG: CanvasView({self.view_id}) - set_annotation_mode: {mode}")
        self.setFocus() # Ensure focus for keyboard shortcuts
        self.annotation_mode = mode
        self.current_ann_points = []
        self._update_annotation_preview()
        
        if mode != 'none':
            if self.active_tool is not None and not hasattr(self, "_prev_tool_for_annotation_mode"):
                self._prev_tool_for_annotation_mode = self.active_tool
                self.active_tool = None
                Logger.debug(f"[CanvasView] Enter annotation_mode={mode}: temporarily cleared active_tool={type(self._prev_tool_for_annotation_mode).__name__}")
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            self.setCursor(Qt.CursorShape.CrossCursor)
        else:
            if hasattr(self, "_prev_tool_for_annotation_mode"):
                prev_tool = self._prev_tool_for_annotation_mode
                del self._prev_tool_for_annotation_mode
                Logger.debug(f"[CanvasView] Exit annotation_mode: restoring active_tool={type(prev_tool).__name__}")
                self.set_active_tool(prev_tool)
                return
            if not self.active_tool:
                self.setDragMode(QGraphicsView.DragMode.NoDrag)
                self.setCursor(Qt.CursorShape.OpenHandCursor)

    def _update_annotation_preview(self, current_pos=None):
        """Updates the visual preview of the annotation being drawn."""
        path = QPainterPath()
        
        if self.annotation_mode == 'none' or not self.current_ann_points:
            self.preview_ann_item.setPath(path)
            self.preview_ann_item.setVisible(False)
            return

        start_pos = self.current_ann_points[0]
        end_pos = current_pos if current_pos else start_pos
        
        if self.annotation_mode == 'arrow':
            # Draw a line with a small arrowhead at the end
            path.moveTo(start_pos)
            path.lineTo(end_pos)
            
            # Simple arrowhead calculation
            import math
            angle = math.atan2(end_pos.y() - start_pos.y(), end_pos.x() - start_pos.x())
            arrow_len = 15 # pixels
            arrow_angle = math.pi / 6 # 30 degrees
            
            p1 = end_pos - QPointF(arrow_len * math.cos(angle - arrow_angle), arrow_len * math.sin(angle - arrow_angle))
            p2 = end_pos - QPointF(arrow_len * math.cos(angle + arrow_angle), arrow_len * math.sin(angle + arrow_angle))
            
            path.moveTo(end_pos)
            path.lineTo(p1)
            path.moveTo(end_pos)
            path.lineTo(p2)
            
        elif self.annotation_mode == 'line':
            path.moveTo(start_pos)
            path.lineTo(end_pos)
            
        elif self.annotation_mode == 'rect':
            rect = QRectF(start_pos, end_pos).normalized()
            path.addRect(rect)
            
        elif self.annotation_mode == 'circle':
            # Distance from start to end as radius
            import math
            dx = end_pos.x() - start_pos.x()
            dy = end_pos.y() - start_pos.y()
            radius = math.sqrt(dx*dx + dy*dy)
            path.addEllipse(start_pos, radius, radius)
            
        elif self.annotation_mode == 'ellipse':
            rect = QRectF(start_pos, end_pos).normalized()
            path.addEllipse(rect)
            
        elif self.annotation_mode == 'polygon':
            if len(self.current_ann_points) > 0:
                path.moveTo(self.current_ann_points[0])
                for p in self.current_ann_points[1:]:
                    path.lineTo(p)
                path.lineTo(end_pos) # Current line being drawn
                
        elif self.annotation_mode == 'text':
            # Just show a crosshair or small box for text insertion point
            path.addRect(end_pos.x()-5, end_pos.y()-5, 10, 10)

        # Style the preview
        pen = QPen(QColor("#FFFF00"), 2) # Yellow for annotations
        pen.setCosmetic(True)
        self.preview_ann_item.setPen(pen)
        self.preview_ann_item.setPath(path)
        self.preview_ann_item.setVisible(True)

    def get_image_coordinates(self, scene_pos: QPointF) -> QPointF:
        """
        Maps a point from Scene coordinates to original Image coordinates.
        Handles the scaling applied to the PixmapItem (Scene -> Image).
        
        Logic:
        - Scene Rect is the viewport into the world.
        - PixmapItem is scaled to fit the Scene Rect.
        - scale = scene_width / image_width
        - Image Coordinate = Scene Coordinate / scale
        """
        # Scientific Rigor: QGraphicsScene rect is always set to full image resolution.
        # Therefore, scene_pos IS the full-resolution image coordinate.
        # We perform an identity mapping here, but keep the logging for verification.
        
        # NOTE: If we were supporting downsampled scenes, we would use the scaling logic below.
        # But for now, we enforce Scene == Full Res.
        
        image_x = scene_pos.x()
        image_y = scene_pos.y()
        
        # Optional: Log if there's a discrepancy with the underlying pixmap (e.g. if pixmap is downsampled)
        if self.last_display_array is not None:
             h, w = self.last_display_array.shape[:2]
             scene_rect = self.scene.sceneRect()
             if scene_rect.width() > 0 and w > 0:
                 scale = scene_rect.width() / w
                 if abs(scale - 1.0) > 0.01:
                     print(f"DEBUG: [CanvasView] Coord Map: Scene matches Full Res. Underlying Pixmap is scaled by {scale:.2f}.")

        # print(f"DEBUG: [CanvasView] Coord Map: Identity ({image_x:.1f}, {image_y:.1f})")
        return QPointF(image_x, image_y)

    def on_scene_selection_changed(self):
        """Handle selection from Scene (Mouse Click) -> Manager."""
        if not self.roi_manager or self._is_updating_from_manager:
            return
            
        # Safeguard: If we are ignoring background clicks (e.g. during manual Smart Pan interaction), abort if empty
        if getattr(self, '_ignore_background_click', False):
             if not self.scene.selectedItems():
                 print("DEBUG: Ignoring background click selection clear (Smart Pan safeguard)")
                 return
            
        self._is_updating_from_manager = True
        try:
            selected_items = self.scene.selectedItems()
            
            # Detailed Logging for debugging selection issues
            # print(f"DEBUG: [CanvasView] on_scene_selection_changed. Raw Count: {len(selected_items)}")
            
            if not selected_items:
                # Clear selection when clicking empty space
                # But check if we are in Multi-Select mode (Ctrl pressed)
                # If Ctrl is pressed, maybe we don't want to clear all?
                # But scene.selectedItems() reflects the current state. 
                # If it's empty, it means everything was deselected.
                
                modifiers = QApplication.keyboardModifiers()
                is_ctrl = bool(modifiers & Qt.KeyboardModifier.ControlModifier)
                
                # If we are in Ctrl mode, usually we don't clear all on background click unless intentional?
                # But standard behavior is click background -> clear.
                
                self.roi_manager.set_selection(None, clear_others=True)
                self._emit_annotation_selected(None) # Clear annotation selection too
                return

            def resolve_target_item(item):
                cur = item
                while cur and not isinstance(cur, (RoiGraphicsItem, AnnotationGraphicsItem)):
                    cur = cur.parentItem()
                return cur

            # Optimize: Collect IDs directly from selected items
            selected_roi_ids = []
            selected_ann_ids = []
            
            # Use a set to avoid duplicates if multiple parts of same item selected
            processed_items = set()

            for it in selected_items:
                target = resolve_target_item(it)
                if target and target not in processed_items:
                    processed_items.add(target)
                    if isinstance(target, RoiGraphicsItem):
                        selected_roi_ids.append(target.roi_id)
                    elif isinstance(target, AnnotationGraphicsItem):
                        selected_ann_ids.append(target.ann_id)

            print(f"DEBUG: [CanvasView] Syncing Selection - ROIs: {len(selected_roi_ids)} ({selected_roi_ids}), Anns: {len(selected_ann_ids)}")

            # Sync ROIs
            # Always sync the full list of selected IDs to the manager
            # If Ctrl is held, set_selected_ids should probably just set the state, 
            # but Manager.set_selected_ids usually replaces selection.
            # Let's check if we need to merge? 
            # No, scene.selectedItems() IS the merged state if Qt handles it.
            # If Qt cleared others, then selected_roi_ids only has the new one.
            
            # If we are using manual Smart Stack logic, we might have set selection on one item,
            # but if we didn't block signals, this triggered.
            # If we didn't use QGraphicsScene.setSelectionArea, then Scene might not know about "keeping" others
            # unless the click event was handled as a "toggle" by the Item itself?
            # QGraphicsItem.setSelected() toggles it. It doesn't clear others unless the Scene does it.
            # Who clears others? The View's mousePressEvent usually.
            # If we bypassed super().mousePressEvent, then Scene shouldn't clear others.
            
            self.roi_manager.set_selected_ids(selected_roi_ids)

            # Sync Annotations
            # Emit the last selected annotation for property panel sync
            if selected_ann_ids:
                self._emit_annotation_selected(selected_ann_ids[-1])
            else:
                self._emit_annotation_selected(None)

        except Exception as e:
            print(f"ERROR: [CanvasView] Selection Sync Failed: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self._is_updating_from_manager = False

    def update_scale_bar(self, settings):
        """Updates the scale bar visual representation."""
        self.scale_bar_item.update_settings(settings)

    def on_annotation_updated(self, ann: GraphicAnnotation):
        """Updates or adds a single annotation item."""
        if ann.id in self._ann_items:
            self._ann_items[ann.id].update_from_model(ann)
        else:
            item = AnnotationGraphicsItem(ann)
            self.scene.addItem(item)
            self._ann_items[ann.id] = item

    def on_roi_moved(self, roi_id, new_path):
        """Called by RoiGraphicsItem when a drag operation finishes."""
        if self.roi_manager:
            self.roi_manager.update_roi_path(roi_id, new_path)

    def on_roi_added(self, roi: ROI):
        item = RoiGraphicsItem(roi)
        
        # Style
        pen = QPen(roi.color, 2) # Use ROI's assigned color
        pen.setStyle(Qt.PenStyle.DashLine)
        pen.setCosmetic(True) 
        item.setPen(pen)
        
        item.setBrush(Qt.BrushStyle.NoBrush)
        item.setZValue(10)
        
        # Flags
        if self.active_tool is None:
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
            
        self.scene.addItem(item)
        self._roi_items[roi.id] = item

    def on_roi_removed(self, roi_id: str):
        if roi_id in self._roi_items:
            item = self._roi_items[roi_id]
            self.scene.removeItem(item)
            del self._roi_items[roi_id]

    def stop_flash(self):
        self.flash_active = False
        self.viewport().update()

    def start_flash(self, duration_ms: int = 250):
        self.flash_active = True
        self.viewport().update()
        QTimer.singleShot(max(0, int(duration_ms)), self.stop_flash)

    def fit_view(self):
        pass

    def wheelEvent(self, event):
        """Handle zooming with physical dynamic damping."""
        # Calculate velocity impulse
        # angleDelta().y() is usually 120 or -120
        num_degrees = event.angleDelta().y() / 8
        num_steps = num_degrees / 15
        
        # Velocity impulse (0.1x - 5x/s equivalent?)
        # A single click (1 step) adds a bit of velocity
        impulse = num_steps * 0.05 
        
        # If we weren't zooming, initialize anchors
        if not self._is_zooming_smoothly:
            self._is_zooming_smoothly = True
            self._zoom_anchor_viewport = event.position().toPoint()
            self._zoom_anchor_scene = self.mapToScene(self._zoom_anchor_viewport)
            # Sync logical zoom with current scale
            self._current_zoom = self.transform().m11()
            self._target_zoom = self._current_zoom
            self._zoom_velocity = 0.0
            self._zoom_timer.start()
        else:
            # Update anchor if mouse moved significantly
            new_pos = event.position().toPoint()
            if (new_pos - self._zoom_anchor_viewport).manhattanLength() > 5:
                self._zoom_anchor_viewport = new_pos
                self._zoom_anchor_scene = self.mapToScene(new_pos)

        # Add impulse to velocity
        self._zoom_velocity += impulse
        
        event.accept()

    def _process_zoom_animation(self):
        if not self._is_zooming_smoothly:
            self._zoom_timer.stop()
            return

        # 1. Apply Velocity to Target
        # Exponential growth: target = target * (1 + velocity)
        self._target_zoom *= (1.0 + self._zoom_velocity)
        
        # 2. Damping
        self._zoom_velocity *= self.ZOOM_DAMPING
        if abs(self._zoom_velocity) < 0.0005:
            self._zoom_velocity = 0.0

        # 3. Spring back if out of bounds
        if self._target_zoom < self.ZOOM_MIN:
            # Pull back
            self._target_zoom += (self.ZOOM_MIN - self._target_zoom) * self.ZOOM_SPRING
            self._zoom_velocity *= 0.5 
        elif self._target_zoom > self.ZOOM_MAX:
            self._target_zoom += (self.ZOOM_MAX - self._target_zoom) * self.ZOOM_SPRING
            self._zoom_velocity *= 0.5

        # 4. Interpolate Current to Target
        diff = self._target_zoom - self._current_zoom
        if abs(diff) < 0.001 and self._zoom_velocity == 0.0:
            # Reached target
            self._current_zoom = self._target_zoom
            # Stop if stabilized inside bounds
            if self.ZOOM_MIN <= self._target_zoom <= self.ZOOM_MAX:
                self._is_zooming_smoothly = False
                self._zoom_timer.stop()
        else:
            self._current_zoom += diff * 0.2 # Smooth follow

        # 5. Apply Scale
        current_scale = self.transform().m11()
        if current_scale == 0: current_scale = 1.0
        
        # Calculate required relative scale
        scale_factor = self._current_zoom / current_scale
        
        # --- Smart Smoothing: Prevent aliasing flicker when zoomed out ---
        # Calculate effective image scale on screen
        item_scale = self.pixmap_item.transform().m11()
        total_scale = self._current_zoom * item_scale
        
        should_smooth = total_scale < 1.0
        current_hints = self.renderHints()
        is_smooth = bool(current_hints & QPainter.RenderHint.SmoothPixmapTransform)
        
        if should_smooth != is_smooth:
            self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, should_smooth)
        # ---------------------------------------------------------------

        if abs(scale_factor - 1.0) < 0.0001:
            return

        # Temporarily disable anchors
        old_anchor = self.transformationAnchor()
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        
        self.scale(scale_factor, scale_factor)
        
        # Compensate drift
        new_viewport_pos = self.mapFromScene(self._zoom_anchor_scene)
        delta = new_viewport_pos - self._zoom_anchor_viewport
        
        # Scroll to correct
        self.horizontalScrollBar().setValue(int(self.horizontalScrollBar().value() + delta.x()))
        self.verticalScrollBar().setValue(int(self.verticalScrollBar().value() + delta.y()))
        
        self.setTransformationAnchor(old_anchor)
        
        # Emit signal
        t = self.transform()
        self.zoom_changed.emit(t.m11(), t.m22(), self._zoom_anchor_scene)

    def _update_preview(self):
        """Helper to sync temp path item with tool state."""
        path = None
        if self.active_tool:
            if hasattr(self.active_tool, 'get_preview_path'):
                path = self.active_tool.get_preview_path()
            elif hasattr(self.active_tool, 'current_path'):
                path = self.active_tool.current_path

        if path and not path.isEmpty():
            tool_name = self.active_tool.__class__.__name__ if self.active_tool else ""
            if tool_name == "BatchSelectionTool":
                pen = QPen(QColor("#B0B0B0"), 1)
                pen.setCosmetic(True)
                pen.setStyle(Qt.PenStyle.DashLine)
                self.temp_path_item.setPen(pen)

                fill_color = QColor("#B0B0B0")
                fill_color.setAlpha(40)
                self.temp_path_item.setBrush(QBrush(fill_color))
            else:
                pen = QPen(QColor("#00FFFF"), 2)
                pen.setStyle(Qt.PenStyle.SolidLine)
                pen.setCosmetic(True)
                self.temp_path_item.setPen(pen)

                fill_color = QColor("#00FFFF")
                fill_color.setAlpha(60)
                self.temp_path_item.setBrush(QBrush(fill_color))

            self.temp_path_item.setPath(path)
            self.temp_path_item.setVisible(True)
        else:
            self.temp_path_item.setPath(QPainterPath())
            self.temp_path_item.setVisible(False)
