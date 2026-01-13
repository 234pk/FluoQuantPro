from PySide6.QtWidgets import QGraphicsRectItem, QGraphicsItem, QApplication, QGraphicsPathItem, QGraphicsObject, QGraphicsPixmapItem
from PySide6.QtGui import QBrush, QPen, QPalette, QColor, QPainterPath, QFont, QPainter, QTransform, QPainterPathStroker, QFontMetrics
from PySide6.QtCore import Qt, Signal, QRectF, QPointF, QTimer, QObject, QLineF
import time
from src.core.language_manager import tr
from src.core.logger import Logger
from src.core.roi_model import create_smooth_path_from_points
from src.gui.rendering.engine import StyleConfigCenter

class RoiHandleItem(QGraphicsRectItem):
    """Handle for resizing/manipulating ROIs."""
    
    def __init__(self, parent, position_flag, size=14):
        # position_flag: 'top-left', 'top-right', 'bottom-left', 'bottom-right', 'top', 'bottom', 'left', 'right'
        # User Request: Increased hit area (14x14 visual, larger hit test)
        super().__init__(-size/2, -size/2, size, size, parent)
        self.position_flag = position_flag
        self.base_size = size
        self._is_hovered = False
        self._is_selected = False
        
        # High contrast style (Theme aware)
        palette = QApplication.palette()
        self.setBrush(QBrush(palette.color(QPalette.ColorRole.Base))) 
        self.setPen(QPen(palette.color(QPalette.ColorRole.Text), 1.5)) 
        
        self.setZValue(200) # Ensure handles are way above parent items
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False) 
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True) # Keep constant size on screen
        self.setAcceptHoverEvents(True)
        self.setCursor(self._get_cursor())
        self.setVisible(False) # Hidden by default until parent is selected
        
        # Tooltip
        self._update_tooltip()

    def _update_tooltip(self):
        type_str = tr("Rotate") if self.position_flag == 'rotate' else tr("Resize")
        selected_str = f" [{tr('Selected')}]" if self._is_selected else ""
        self.setToolTip(f"{tr('Control Point')}: {type_str}{selected_str}")

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
            return Qt.CursorShape.PointingHandCursor
        return Qt.CursorShape.ArrowCursor

    def set_selected(self, selected):
        if self._is_selected != selected:
            self._is_selected = selected
            self._update_tooltip()
            self.update()

    def hoverEnterEvent(self, event):
        self._is_hovered = True
        # Scale up effect (visual only via rect update since IgnoresTransformations is on)
        s = self.base_size * 1.4
        self.setRect(-s/2, -s/2, s, s)
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self._is_hovered = False
        s = self.base_size
        self.setRect(-s/2, -s/2, s, s)
        self.update()
        super().hoverLeaveEvent(event)
        
    def mousePressEvent(self, event):
        # Consume event to prevent parent from getting it (which would be move)
        self.start_pos = event.scenePos()
        self.parentItem().handle_press(self.position_flag, event.scenePos())
        event.accept()

    def mouseMoveEvent(self, event):
        # Forward move event to parent for resizing
        if self.parentItem():
             self.parentItem().handle_move(self.position_flag, event.scenePos())
        event.accept()

    def mouseReleaseEvent(self, event):
        # Forward release event to parent
        if self.parentItem():
             self.parentItem().handle_release(self.position_flag, event.scenePos())
        event.accept()

    def paint(self, painter, option, widget):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        rect = self.rect()
        
        # Selection Feedback: Glow or Color Invert
        if self._is_selected:
            # Pulsing/Glowing effect (simplified: Use Palette Highlight)
            palette = QApplication.palette()
            highlight = palette.color(QPalette.ColorRole.Highlight)
            glow_pen = QPen(highlight, 3)
            painter.setPen(glow_pen)
            painter.setBrush(QBrush(palette.color(QPalette.ColorRole.Text))) # Invert fill
            painter.drawRect(rect.adjusted(-1, -1, 1, 1))
        
        # High contrast base style
        palette = QApplication.palette()
        text_color = palette.color(QPalette.ColorRole.Text)
        bg_color = palette.color(QPalette.ColorRole.Base)
        
        pen_color = bg_color if self._is_selected else text_color
        brush_color = text_color if self._is_selected else bg_color
        
        if self.position_flag == 'rotate':
            # Draw circle for rotate handle
            painter.setPen(QPen(pen_color, 1.5))
            painter.setBrush(QBrush(brush_color))
            painter.drawEllipse(rect)
            
            # Draw Circular Arrow using Path (Standardized)
            painter.setPen(QPen(pen_color, 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            
            # Draw an arc
            arc_rect = rect.adjusted(rect.width()*0.2, rect.height()*0.2, -rect.width()*0.2, -rect.height()*0.2)
            painter.drawArc(arc_rect, 45 * 16, 270 * 16)
            
            # Draw arrowhead
            painter.setBrush(QBrush(pen_color))
            arrow_head = QPainterPath()
            # Tip of the arrow at the end of the arc (approx)
            tip = QPointF(arc_rect.right(), arc_rect.center().y())
            arrow_head.moveTo(tip)
            arrow_head.lineTo(tip + QPointF(-4, -4))
            arrow_head.lineTo(tip + QPointF(-4, 4))
            arrow_head.closeSubpath()
            painter.drawPath(arrow_head)
        else:
            # Standard resize handle
            painter.setPen(QPen(pen_color, 1.5))
            painter.setBrush(QBrush(brush_color))
            painter.drawRect(rect)
            
            # Add a small dot in center for "grippy" look
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(pen_color))
            dot_size = rect.width() * 0.2
            painter.drawRect(QRectF(-dot_size/2, -dot_size/2, dot_size, dot_size))

class UnifiedGraphicsItem(QGraphicsPathItem, QObject):
    modified = Signal(object)
    
    def __init__(self, model, parent=None):
        QGraphicsPathItem.__init__(self, parent)
        QObject.__init__(self)
        
        # Unified Model: Always ROI
        self.roi = model
        self.roi_id = getattr(model, 'id', None)
        self.roi_type = getattr(model, 'roi_type', None)
        
        self.points = []
        self.handles = {}
        self.text_item = None
        self._handles_visible = False
        self._is_resizing = False
        self._start_resize_rect = None
        self._start_resize_path = None
        self._resize_flag = None
        self._dragging_no_smooth = False
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setPos(0, 0)
        self.setCacheMode(QGraphicsItem.CacheMode.DeviceCoordinateCache)
        self.setAcceptHoverEvents(True)
        self.style_center = StyleConfigCenter()
        self.style_center.style_changed.connect(self.update)
        self.update_from_model(model)
        # Optimization: Don't create handles until selected
        # self._create_handles() 
        self.update_appearance()
        
        # Special case for LineScan: High Z-Value
        if self.roi_type == 'line_scan':
             self.setZValue(200)

    def itemChange(self, change, value):
        res = super().itemChange(change, value)
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedChange:
            sel = bool(value)
            self._handles_visible = sel
            if sel and not self.handles:
                self._create_handles()
            self.update_appearance(is_selected=sel)
            if sel:
                QTimer.singleShot(0, self._update_handles_pos)
        return res

    def shape(self):
        p = self.path()
        stroker = QPainterPathStroker()
        # USER REQUEST: Extra-wide hit area specifically for LineScan
        if self.roi_type == 'line_scan':
            stroker.setWidth(15)
        else:
            stroker.setWidth(10)
        stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
        stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        sp = stroker.createStroke(p)
        return sp + p

    def _scale_path(self, path, scale):
        if scale >= 1.0:
            return path
        transform = QTransform()
        transform.scale(scale, scale)
        return transform.map(path)

    def update_appearance(self, is_selected=None):
        if is_selected is None:
            is_selected = self.isSelected()
        pen = self.pen()
        
        color = QColor(getattr(self.roi, 'color', QColor(255,255,0)))
        
        # Check properties for thickness, defaulting to 2
        t = 2
        if hasattr(self.roi, 'properties'):
            t = int(self.roi.properties.get('thickness', 2))
            
        pen.setColor(QApplication.palette().color(QPalette.ColorRole.Highlight) if is_selected else color)
        pen.setWidth(t if t > 0 else 1)
        
        # Support dashed style
        style = Qt.PenStyle.SolidLine
        if hasattr(self.roi, 'properties'):
             s = self.roi.properties.get('style', 'solid')
             if s == 'dashed':
                 style = Qt.PenStyle.DashLine
                 
        pen.setStyle(style)
        pen.setCosmetic(True)
        self.setPen(pen)
        for h in self.handles.values():
            h.setVisible(bool(self._handles_visible))

    def _create_handles(self):
        """
        Creates control handles for the ROI.
        USER REQUEST: Further optimize handle count for complex polygons to maintain performance.
        Strategy: Dynamic sampling for polygons to keep handle count manageable.
        """
        flags = []
        t = self.roi_type
        if t in ['arrow', 'line', 'line_scan']:
            flags = [0, 1]
        elif t in ['rect', 'ellipse', 'circle', 'rectangle']:
            flags = ['top-left', 'top-right', 'bottom-left', 'bottom-right', 
                     'top', 'bottom', 'left', 'right', 'rotate']
        elif t == 'polygon':
                n = len(self.points) if self.points else 0
                
                # Dynamic sampling based on point count
                # USER REQUEST: Further optimize handle count for complex polygons.
                if n > 150:
                    # For extremely complex polygons, still show some sampled handles 
                    # but keep it very sparse (e.g., 10-15 handles total)
                    step = n // 15
                    flags = list(range(0, n, step))
                    flags.append('rotate')
                    Logger.debug(f"[UnifiedGraphicsItem] ROI {self.roi_id} extremely complex ({n} pts). Sparsely sampled {len(flags)} handles.")
                elif n > 25:
                    # For moderately complex polygons, sample points to keep handles ~10-15.
                    step = max(2, n // 12)
                    flags = list(range(0, n, step))
                    flags.append('rotate')
                    Logger.debug(f"[UnifiedGraphicsItem] ROI {self.roi_id} sampled: {len(flags)} handles for {n} pts.")
                else:
                    # Simple polygons: show all points
                    flags = list(range(n))
                    flags.append('rotate')
        elif t == 'text':
            flags = ['rotate']
            
        for flag in flags:
            handle = RoiHandleItem(self, flag)
            self.handles[flag] = handle

    def _update_handles_pos(self):
        path = self.path()
        if path.elementCount() == 0 and self.roi_type != 'text':
            return
        t = self.roi_type
        if t in ['arrow', 'line', 'line_scan']:
            if path.elementCount() >= 2:
                # Use mapFromScene to ensure handles follow item transformation (rotation/pos)
                p0 = self.mapFromScene(self.roi.points[0]) if len(self.roi.points) > 0 else QPointF(path.elementAt(0).x, path.elementAt(0).y)
                p1 = self.mapFromScene(self.roi.points[1]) if len(self.roi.points) > 1 else QPointF(path.elementAt(1).x, path.elementAt(1).y)
                if 0 in self.handles: self.handles[0].setPos(p0)
                if 1 in self.handles: self.handles[1].setPos(p1)
        elif t in ['rect', 'ellipse', 'circle', 'rectangle', 'text']:
            rect = path.boundingRect()
            if 'top-left' in self.handles: self.handles['top-left'].setPos(rect.topLeft())
            if 'top-right' in self.handles: self.handles['top-right'].setPos(rect.topRight())
            if 'bottom-left' in self.handles: self.handles['bottom-left'].setPos(rect.bottomLeft())
            if 'bottom-right' in self.handles: self.handles['bottom-right'].setPos(rect.bottomRight())
            if 'top' in self.handles: self.handles['top'].setPos(QPointF(rect.center().x(), rect.top()))
            if 'bottom' in self.handles: self.handles['bottom'].setPos(QPointF(rect.center().x(), rect.bottom()))
            if 'left' in self.handles: self.handles['left'].setPos(QPointF(rect.left(), rect.center().y()))
            if 'right' in self.handles: self.handles['right'].setPos(QPointF(rect.right(), rect.center().y()))
            
            # Compatibility with old flags 0, 1
            if 0 in self.handles: self.handles[0].setPos(rect.topLeft())
            if 1 in self.handles: self.handles[1].setPos(rect.bottomRight())
            
            if 'rotate' in self.handles:
                self.handles['rotate'].setPos(QPointF(rect.center().x(), rect.top() - 20))
        elif t == 'polygon':
            # Use mapFromScene to ensure handles follow item transformation (rotation/pos)
            if self.roi and hasattr(self.roi, 'points'):
                for idx, handle in self.handles.items():
                    if isinstance(idx, int) and idx < len(self.roi.points):
                        lp = self.mapFromScene(self.roi.points[idx])
                        handle.setPos(lp)
            if 'rotate' in self.handles:
                rect = path.boundingRect()
                self.handles['rotate'].setPos(QPointF(rect.center().x(), rect.top() - 20))

    def handle_press(self, flag, scene_pos):
        self.setCacheMode(QGraphicsItem.CacheMode.NoCache)
        self._is_resizing = True
        self._start_resize_rect = self.path().boundingRect()
        self._start_resize_path = self.path()
        self._resize_flag = flag

    def _build_arrow_paths(self, start, end):
        """Helper to construct shaft and head paths for arrows separately."""
        shaft_path = QPainterPath()
        shaft_path.moveTo(start)
        shaft_path.lineTo(end)
        
        head_path = QPainterPath()
        
        # Get properties
        props = self.roi.properties
        # USER REQUEST: Default to triangle and fill it
        head_shape = 'triangle' 
        arrow_len = float(props.get('arrow_head_size', 15.0))
        
        import math
        angle = math.atan2(end.y() - start.y(), end.x() - start.x())
        
        arrow_angle = math.pi / 6
        p1 = end - QPointF(arrow_len * math.cos(angle - arrow_angle), arrow_len * math.sin(angle - arrow_angle))
        p2 = end - QPointF(arrow_len * math.cos(angle + arrow_angle), arrow_len * math.sin(angle + arrow_angle))
        
        # Create a closed polygon for the head to allow filling
        head_path.moveTo(end)
        head_path.lineTo(p1)
        head_path.lineTo(p2)
        head_path.closeSubpath()
            
        return shaft_path, head_path

    def paint(self, painter, option, widget):
        """Override paint to handle filled arrow heads and LOD optimizations."""
        # LOD Optimization: If the item is very small on screen, draw a simplified version
        # This significantly improves performance when zoomed out with many complex ROIs.
        lod = option.levelOfDetailFromTransform(painter.worldTransform())
        if lod < 0.05: # Very zoomed out
            painter.setPen(self.pen())
            painter.drawRect(self.boundingRect())
            return

        if self.roi_type == 'arrow':
            # Draw shaft with current pen
            painter.setPen(self.pen())
            
            # Reconstruct paths to get head for filling
            points = self.roi.points
            if len(points) >= 2:
                shaft, head = self._build_arrow_paths(self.mapFromScene(points[0]), self.mapFromScene(points[1]))
                
                # Draw shaft
                painter.drawPath(shaft)
                
                # Draw filled head
                painter.setBrush(QBrush(self.pen().color()))
                painter.drawPath(head)
            return
            
        super().paint(painter, option, widget)

    def handle_move(self, flag, scene_pos):
        if not self._is_resizing:
            return
        t = self.roi_type
        
        # 1. Handle Rotation (Common for all types with 'rotate' handle)
        if flag == 'rotate':
            # Use absolute scene coordinates for angle calculation to avoid transform recursion
            rect = self.path().boundingRect()
            center_scene = self.mapToScene(rect.center())
            
            # QLineF.angle() is counter-clockwise, 0 at 3 o'clock
            angle_deg = QLineF(center_scene, scene_pos).angle()
            
            # Convert to Qt rotation: clockwise, 0 at 3 o'clock
            # And handle the 90-degree offset because our handle is at the top (12 o'clock)
            rotation = -(angle_deg - 90)
            
            self.setTransformOriginPoint(rect.center())
            self.setRotation(rotation)
            
            if self.roi:
                if not hasattr(self.roi, 'properties'):
                    self.roi.properties = {}
                self.roi.properties['rotation'] = rotation
            self._update_handles_pos()
            return # Done with rotation

        # 2. Update Model Points (Scene Coords) for point-based shapes
        if isinstance(flag, int):
            if self.roi and hasattr(self.roi, 'points'):
                if 0 <= flag < len(self.roi.points):
                    self.roi.points[flag] = scene_pos
        elif flag in ['start', 'end', 0, 1] and t in ['arrow', 'line', 'line_scan']:
            idx = 0 if flag in ['start', 0] else 1
            if self.roi and hasattr(self.roi, 'points'):
                if idx < len(self.roi.points):
                    self.roi.points[idx] = scene_pos

        # 3. Handle Specific Shape Resizing
        if t in ['arrow', 'line', 'line_scan']:
            lp = self.mapFromScene(scene_pos)
            path = self.path()
            if path.elementCount() < 2:
                return
            start = QPointF(path.elementAt(0).x, path.elementAt(0).y)
            end = QPointF(path.elementAt(1).x, path.elementAt(1).y)
            if flag in (0, 'start'):
                start = lp
            elif flag in (1, 'end'):
                end = lp
            
            if t == 'arrow' and hasattr(self, '_build_arrow_paths'):
                 shaft, head = self._build_arrow_paths(start, end)
                 p = QPainterPath()
                 p.addPath(shaft)
                 p.addPath(head)
            else:
                 p = QPainterPath()
                 p.moveTo(start)
                 p.lineTo(end)
            self.setPath(p)
            
            # Update Model Path (Absolute Coords)
            if self.roi:
                abs_start = self.mapToScene(start)
                abs_end = self.mapToScene(end)
                if t == 'arrow' and hasattr(self, '_build_arrow_paths'):
                    s_abs, h_abs = self._build_arrow_paths(abs_start, abs_end)
                    p_abs = QPainterPath()
                    p_abs.addPath(s_abs)
                    p_abs.addPath(h_abs)
                    self.roi.path = p_abs
                else:
                    p_abs = QPainterPath()
                    p_abs.moveTo(abs_start)
                    p_abs.lineTo(abs_end)
                    self.roi.path = p_abs
            self._update_handles_pos()

        elif t in ['rect', 'ellipse', 'circle', 'rectangle']:
            # Get current path bounding rect in local coordinates
            rect = self.path().boundingRect()
            lp = self.mapFromScene(scene_pos)
            
            # Resizing logic for all 8 handles + legacy flags
            if flag in ['top-left', 0]:
                rect.setTopLeft(lp)
            elif flag in ['top-right']:
                rect.setTopRight(lp)
            elif flag in ['bottom-left']:
                rect.setBottomLeft(lp)
            elif flag in ['bottom-right', 1]:
                rect.setBottomRight(lp)
            elif flag == 'top':
                rect.setTop(lp.y())
            elif flag == 'bottom':
                rect.setBottom(lp.y())
            elif flag == 'left':
                rect.setLeft(lp.x())
            elif flag == 'right':
                rect.setRight(lp.x())
            
            # For circle, maintain aspect ratio 1:1 using the largest dimension or average?
            # Usually, dragging a corner resizes both, dragging an edge resizes one.
            # For a circle, we probably want it to stay a circle.
            if t == 'circle':
                center = rect.center()
                # Use distance from center to lp as radius
                radius = QLineF(center, lp).length()
                rect = QRectF(center.x() - radius, center.y() - radius, radius * 2, radius * 2)

            path = QPainterPath()
            if t == 'ellipse':
                path.addEllipse(rect.normalized())
            elif t == 'circle':
                path.addEllipse(rect.normalized())
            else:
                path.addRect(rect.normalized())
            self.setPath(path)
            
            if self.roi:
                # Update model path (Absolute Coords)
                # Important: When rotated, we must map the local normalized rect to scene
                # But a simple mapToScene(rect) might not be enough if we want to preserve rotation in the model.
                # Actually, the model.path is usually the absolute path.
                
                # Create a temporary transform that matches the item's current transform
                # to map the local path to scene coordinates correctly.
                transform = self.sceneTransform()
                p_abs = transform.map(path)
                self.roi.path = p_abs
                
                # If the shape is a simple rect/ellipse, we might also want to update points
                # if the model uses them.
                if hasattr(self.roi, 'points') and len(self.roi.points) >= 2:
                    self.roi.points[0] = self.mapToScene(rect.topLeft())
                    self.roi.points[1] = self.mapToScene(rect.bottomRight())
            
            self._update_handles_pos()
            
        elif t == 'polygon':
            if isinstance(flag, int):
                # We already updated self.roi.points[flag] = scene_pos above
                # Now just regenerate the smooth path and update visual item
                if self.roi:
                    local_points = [self.mapFromScene(p) for p in self.roi.points]
                    new_path = create_smooth_path_from_points(local_points, closed=True)
                    self.setPath(new_path)
                    
                    # Update model path (Absolute Coords)
                    abs_path = create_smooth_path_from_points(self.roi.points, closed=True)
                    self.roi.path = abs_path
                self._update_handles_pos()
        
        # Immediate refresh during interaction removed as requested (update on release only)
        # self._notify_modified()

    def handle_release(self, flag, scene_pos):
        self._is_resizing = False
        self.setCacheMode(QGraphicsItem.CacheMode.DeviceCoordinateCache)
        self._notify_modified()

    def start_text_edit(self):
        if getattr(self, 'text_item', None):
            self.text_item.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
            self.text_item.setFocus()

    def _notify_modified(self, force=False):
        if hasattr(self, 'roi_manager') and self.roi_manager and hasattr(self.roi_manager, 'roi_updated'):
            self.roi_manager.roi_updated.emit(self.roi_id)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        
        # Check if item moved (dragged)
        # Threshold to ignore micro-jitters
        if self.pos().manhattanLength() > 0.1:
             offset = self.pos()
             self._update_roi_position(offset)

    def _update_roi_position(self, offset: QPointF):
        if not self.roi:
            return

        # 1. Update Points if present (Polygon/Count/Text/Arrow)
        if hasattr(self.roi, 'points') and self.roi.points:
            new_points = [p + offset for p in self.roi.points]
            self.roi.points = new_points
            self.points = list(new_points) # Sync internal points cache
        
        # 2. Update Path (Always)
        if hasattr(self.roi, 'path'):
            path = self.roi.path
            transform = QTransform().translate(offset.x(), offset.y())
            self.roi.path = transform.map(path)
            # For most items, we also need to update the item's own path
            # to match the model's new path, otherwise hit testing stays at old pos
            if self.roi.roi_type not in ['text', 'arrow']:
                self.setPath(self.roi.path)

        # 3. Handle Special Types (Text, Arrow)
        t = self.roi.roi_type
        if t == 'text' and getattr(self, 'text_item', None):
            self.text_item.setPos(self.points[0])
            # Update hit area path
            rect = self.text_item.boundingRect()
            p = QPainterPath()
            p.addRect(rect.translated(self.points[0]))
            self.setPath(p)
        elif t == 'arrow' and len(self.points) >= 2:
            # Rebuild arrow paths at new positions
            start, end = self.mapFromScene(self.points[0]), self.mapFromScene(self.points[1])
            if hasattr(self, '_build_arrow_paths'):
                shaft, head = self._build_arrow_paths(start, end)
                p = QPainterPath()
                p.addPath(shaft)
                p.addPath(head)
                self.setPath(p)

        # 4. Reset Item Pos
        self.setPos(0, 0)
        
        # 5. Sync Visuals
        self._update_handles_pos()
        self._notify_modified()

    def _reconstruct_path(self, points):
        """Reconstructs the ROI path strictly from the given points."""
        t = self.roi.roi_type
        p = QPainterPath()
        
        if t in ['rect', 'rectangle']:
            if len(points) >= 2:
                r = QRectF(points[0], points[1]).normalized()
                p.addRect(r)
        elif t in ['ellipse', 'circle']:
             if len(points) >= 2:
                 r = QRectF(points[0], points[1]).normalized()
                 if t == 'circle':
                     radius = min(r.width(), r.height())
                     p.addEllipse(r.center(), radius/2, radius/2)
                 else:
                     p.addEllipse(r)
        elif t in ['line', 'arrow']:
             if len(points) >= 2:
                 p.moveTo(points[0])
                 p.lineTo(points[1])
        elif t == 'polygon':
             p = create_smooth_path_from_points(points, closed=True)
        else:
             # Fallback
             pass
             
        if not p.isEmpty():
            self.roi.path = p
            self.setPath(p)

    def update_from_model(self, model):
        roi = model
        self.setVisible(roi.visible)
        self.points = list(roi.points) if hasattr(roi, 'points') else []
        
        # Handle complex shapes for ROI (Arrow, Text) that need visual generation
        t = roi.roi_type
        if t == 'arrow' and len(self.points) >= 2:
            start, end = self.mapFromScene(self.points[0]), self.mapFromScene(self.points[1])
            if hasattr(self, '_build_arrow_paths'):
                shaft, head = self._build_arrow_paths(start, end)
                p = QPainterPath()
                p.addPath(shaft)
                p.addPath(head)
                self.setPath(p)
            else:
                self.setPath(roi.path)
        elif t == 'text':
            try:
                from PySide6.QtWidgets import QGraphicsTextItem
            except Exception:
                QGraphicsTextItem = None
            
            # Clear existing text item
            if getattr(self, 'text_item', None):
                if self.scene():
                    self.scene().removeItem(self.text_item)
                self.text_item = None
                
            if QGraphicsTextItem:
                text_content = roi.properties.get('text', roi.label or "")
                self.text_item = QGraphicsTextItem(text_content, self)
                
                # Style
                color = QColor(getattr(roi, 'color', QColor(255,255,0)))
                self.text_item.setDefaultTextColor(color)
                
                fsize = roi.properties.get('font_size', 12.0)
                try:
                    fsize = float(fsize)
                except Exception:
                    fsize = 12.0
                if fsize <= 0: fsize = 1.0
                
                font_family = roi.properties.get('font_family', 'Arial')
                font = QFont(font_family, int(fsize))
                self.text_item.setFont(font)
                self.text_item.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
                
                if self.points:
                    self.text_item.setPos(self.points[0])
                    # Set path to bounding rect for selection
                    rect = self.text_item.boundingRect()
                    p = QPainterPath()
                    p.addRect(rect.translated(self.points[0]))
                    self.setPath(p)
                    
                    # For text, we don't want the bounding box pen to show
                    # Unless it's selected (handled by paint or by setting pen to NoPen)
                    # We'll set the pen to NoPen here and let selection handles show selection.
                    pen = QPen(Qt.PenStyle.NoPen)
                    self.setPen(pen)
                else:
                    self.setPath(roi.path)
                    pen = QPen(Qt.PenStyle.NoPen)
                    self.setPen(pen)
                
                return # Skip standard pen/brush setup below for text
        else:
            self.setPath(roi.path)

        # Apply rotation if present
        if hasattr(roi, 'properties'):
            rotation = roi.properties.get('rotation', 0)
            # FIX: Must set transform origin to center of path for rotation to be correct
            self.setTransformOriginPoint(self.path().boundingRect().center())
            self.setRotation(rotation)

        color = QColor(getattr(roi, 'color', QColor(255,255,0)))
        t = getattr(roi, 'properties', {}).get('thickness', 2) if hasattr(roi, 'properties') else 2
        style = getattr(roi, 'properties', {}).get('style', 'solid') if hasattr(roi, 'properties') else 'solid'
        
        pen = QPen(color, t if t > 0 else 1)
        if style == 'dashed':
            pen.setStyle(Qt.PenStyle.DashLine)
            dash_len = getattr(roi, 'properties', {}).get('dash_length', 10)
            dash_gap = getattr(roi, 'properties', {}).get('dash_gap', 5)
            pen.setDashPattern([dash_len, dash_gap])
        else:
            pen.setStyle(Qt.PenStyle.SolidLine)
            
        pen.setCosmetic(True)
        self.setPen(pen)
        
        # Ensure handles are in sync
        self._update_handles_pos()
        self.update() # Force refresh

class ScaleBarItem(QGraphicsObject):
    """Movable GraphicsItem for Scale Bar."""
    moved = Signal(QPointF)

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setZValue(200) # Above everything
        
        # Performance: Enable Device Coordinate Caching for static rendering
        self.setCacheMode(QGraphicsItem.CacheMode.DeviceCoordinateCache)
        
        self._last_preset_pos = None
        self.update_settings(settings)

    def mousePressEvent(self, event):
        Logger.debug(f"[ScaleBarItem.mousePressEvent] ENTER")
        # Performance: Disable cache during dragging to prevent blurring
        if self.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable:
            self.setCacheMode(QGraphicsItem.CacheMode.NoCache)
        super().mousePressEvent(event)
        Logger.debug(f"[ScaleBarItem.mousePressEvent] EXIT")

    def mouseMoveEvent(self, event):
        # Allow default movement logic
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        Logger.debug(f"[ScaleBarItem.mouseReleaseEvent] ENTER")
        super().mouseReleaseEvent(event)
        self.moved.emit(self.pos())
        # Update settings to reflect custom position
        self.settings.custom_pos = (self.pos().x(), self.pos().y())
        self.settings.position = "Custom"
        
        # Performance: Restore cache after dragging
        self.setCacheMode(QGraphicsItem.CacheMode.DeviceCoordinateCache)
        self.update() # Force redraw to ensure clarity
        Logger.debug(f"[ScaleBarItem.mouseReleaseEvent] EXIT")

    def update_settings(self, settings):
        start = time.perf_counter()
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
            
            # Use font metrics for label width to ensure padding is correct
            font_size = self.settings.font_size if self.settings.font_size > 0 else 1
            font = QFont("Arial", font_size)
            fm = QFontMetrics(font)
            label = f"{self.settings.bar_length_um} \u00B5m"
            tw = fm.horizontalAdvance(label)
            
            effective_width = max(length_px, tw)
            padding = 50
            
            # If position preset changed, or first time, or image changed
            if settings.position != "Custom":
                if settings.position == "Bottom Right":
                    new_pos = QPointF(image_rect.right() - effective_width - padding, image_rect.bottom() - padding - (fm.height() if settings.show_label else 0))
                elif settings.position == "Bottom Left":
                    new_pos = QPointF(image_rect.left() + padding, image_rect.bottom() - padding - (fm.height() if settings.show_label else 0))
                elif settings.position == "Top Right":
                    new_pos = QPointF(image_rect.right() - effective_width - padding, image_rect.top() + padding)
                elif settings.position == "Top Left":
                    new_pos = QPointF(image_rect.left() + padding, image_rect.top() + padding)
                else:
                    new_pos = self.pos()
                
                self.setPos(new_pos)
                self._last_preset_pos = settings.position
            elif settings.custom_pos:
                self.setPos(QPointF(settings.custom_pos[0], settings.custom_pos[1]))
                
        self.update() # Force repaint to apply color/thickness/label changes

    def boundingRect(self):
        if not self.settings.enabled:
            return QRectF()
        
        # Estimate size based on settings
        pix_size = self.settings.pixel_size if self.settings.pixel_size > 0 else 1.0
        length_px = self.settings.bar_length_um / pix_size
        
        # Get font metrics for label size
        font_size = self.settings.font_size if self.settings.font_size > 0 else 1
        font = QFont("Arial", font_size)
        font.setBold(True)
        fm = QFontMetrics(font)
        label = f"{self.settings.bar_length_um} \u00B5m"
        tw = fm.horizontalAdvance(label)
        th = fm.height()
        
        width = max(length_px, tw)
        height = self.settings.thickness + (th + 10 if self.settings.show_label else 0)
        
        # Adjust x to center the bar if label is wider
        x_offset = min(0, (length_px - tw) / 2)
        return QRectF(x_offset, 0, width, height)

    def itemChange(self, change, value):
        # ScaleBar doesn't have handles or selection appearance like Annotation
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
            # Use same font logic as renderer.py for consistency
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(color)
            label = f"{self.settings.bar_length_um} \u00B5m"
            
            # Use font metrics for precise text rect calculation
            fm = QFontMetrics(font)
            tw = fm.horizontalAdvance(label)
            th = fm.height()
            
            text_rect = QRectF(0, self.settings.thickness + 5, max(length_px, tw), th + 5)
            # Center text relative to bar
            text_rect.moveLeft((length_px - text_rect.width()) / 2)
            
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, label)

class LineScanGraphicsItem(UnifiedGraphicsItem):
    """
    Specialized GraphicsItem for Line Scan sampling line.
    Has a much larger hit area for easier selection as requested by user.
    """
    def __init__(self, roi, parent=None):
        super().__init__(roi, parent)
        # Use a distinctive color for LineScan if not specified
        if roi.color.name() == "#FFFF00": # Default yellow
             self.setZValue(200) # Ensure it's very high priority

    def shape(self):
        """
        USER REQUEST: Extra-wide hit area specifically for LineScan.
        15px hit area makes it almost impossible to miss.
        """
        path = self.path()
        stroker = QPainterPathStroker()
        stroker.setWidth(15) # Even wider than normal annotations
        stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
        stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        
        stroke_path = stroker.createStroke(path)
        return stroke_path + path
