from PySide6.QtWidgets import QGraphicsView, QGraphicsItem, QGraphicsPixmapItem
from PySide6.QtCore import Qt, QRectF, QPointF, QLineF
from PySide6.QtGui import QPainterPath, QPainter
from src.gui.graphics_items import UnifiedGraphicsItem, RoiHandleItem, ScaleBarItem
from src.core.logger import Logger

def get_distance_to_path(path: QPainterPath, point: QPointF) -> float:
    """Calculates minimum distance from a point to a QPainterPath by sampling."""
    if path.isEmpty():
        return 999.0
        
    min_dist = 999.0
    steps = 50
    for i in range(steps + 1):
        percent = i / steps
        p = path.pointAtPercent(percent)
        d = QLineF(point, p).length()
        if d < min_dist:
            min_dist = d
            if min_dist < 1.0:
                return min_dist
    return min_dist

def resolve_unified_item(item: QGraphicsItem) -> QGraphicsItem:
    """
    Walks up the parent tree to find a UnifiedGraphicsItem, ScaleBarItem, 
    RoiHandleItem or any selectable/movable item.
    """
    curr = item
    while curr:
        if isinstance(curr, (UnifiedGraphicsItem, ScaleBarItem, RoiHandleItem)):
            return curr
        if (curr.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable) or \
           (curr.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable):
            return curr
        curr = curr.parentItem()
    return None

def find_item_at_position(view: QGraphicsView, scene_pos: QPointF, tolerance: int = 5) -> QGraphicsItem:
    """
    Finds the most relevant item at a scene position using 'Fat Finger' logic.
    Priority is based on distance to the actual path/shape.
    
    Args:
        view: The QGraphicsView instance.
        scene_pos: Position in scene coordinates.
        tolerance: Hit test tolerance in viewport pixels.
        
    Returns:
        The found QGraphicsItem or None.
    """
    view_pos = view.mapFromScene(scene_pos)
    rect = QRectF(view_pos.x() - tolerance, view_pos.y() - tolerance, tolerance * 2, tolerance * 2).toRect()
    items_in_rect = view.items(rect)
    
    candidates = []
    for item in items_in_rect:
        target = resolve_unified_item(item)
        if target and target not in [c[0] for c in candidates]:
            local_pos = target.mapFromScene(scene_pos)
            dist = 999.0
            
            if isinstance(target, RoiHandleItem):
                dist = 0.0 # Handles are extremely high priority
            elif isinstance(target, UnifiedGraphicsItem):
                dist = get_distance_to_path(target.path(), local_pos)
            else:
                dist = QLineF(local_pos, target.boundingRect().center()).length()
            
            candidates.append((target, dist))

    if not candidates:
        return None
        
    # Sort by distance: closest item wins
    candidates.sort(key=lambda x: x[1])
    return candidates[0][0]

def is_selection_modifier_active(event) -> bool:
    """Checks if Ctrl or Shift is pressed."""
    modifiers = event.modifiers()
    return bool(modifiers & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier))

def handle_selection_modifier(view: QGraphicsView, event, item: QGraphicsItem):
    """
    Handles selection logic with modifiers (Ctrl/Shift) and manual event forwarding.
    Useful when standard Scene selection fails (e.g. fat-finger clicks).
    """
    if not item:
        return False

    modifiers = event.modifiers()
    is_ctrl = bool(modifiers & Qt.KeyboardModifier.ControlModifier)
    is_shift = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)
    
    # Force Movable/Selectable Flags for safety
    item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
    item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)

    scene = view.scene()
    if not scene:
        return False

    def forward_press_event(target_item, scene_pos):
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
            def buttons(self): return Qt.MouseButton.LeftButton
            def button(self): return Qt.MouseButton.LeftButton
            def lastPos(self): return self._p
            def screenPos(self): return self._sp.toPoint()
            
        mock_event = MockEvent(local_pos, scene_pos, modifiers)
        target_item.mousePressEvent(mock_event)
        target_item.grabMouse()

    scene_pos = view.mapToScene(event.position().toPoint())

    if is_ctrl:
        # Toggle selection
        item.setSelected(not item.isSelected())
        if item.isSelected():
            forward_press_event(item, scene_pos)
        return True
        
    elif is_shift:
        # Add to selection
        item.setSelected(True)
        forward_press_event(item, scene_pos)
        return True
        
    else:
        # Exclusive selection
        scene.blockSignals(True)
        for it in scene.selectedItems():
            if it != item:
                it.setSelected(False)
        scene.blockSignals(False)
        
        item.setSelected(True)
        forward_press_event(item, scene_pos)
        return True

    return False

def should_bypass_tool(view: QGraphicsView, event) -> bool:
    """
    Determines if the active tool should be bypassed for a mouse press event.
    """
    modifiers = event.modifiers()
    is_ctrl = bool(modifiers & Qt.KeyboardModifier.ControlModifier)
    is_hand_mode = view.dragMode() == QGraphicsView.DragMode.ScrollHandDrag
    
    # 1. Hand mode or Ctrl always bypass tool
    if is_ctrl or is_hand_mode:
        return True
        
    # 2. Space bar panning bypasses tool
    if getattr(view, '_is_space_pressed', False):
        return True
        
    click_pos = event.position().toPoint()
    scene_pos = view.mapToScene(click_pos)
    
    # 3. Use fat-finger logic to find item
    item = find_item_at_position(view, scene_pos)
    
    # 4. Handle click always bypasses tool
    if isinstance(item, RoiHandleItem):
        return True
        
    # 5. Click on an ALREADY SELECTED item bypasses tool (to allow moving it)
    if item and item.isSelected():
        return True
        
    return False

def execute_tool_press(view, event, scene_pos):
    """Executes the active tool's mouse press logic."""
    if not view.active_tool:
        return False
        
    if event.button() == Qt.MouseButton.RightButton and hasattr(view.active_tool, 'mouse_right_click'):
        view.active_tool.mouse_right_click(scene_pos)
    else:
        # Context for tool execution (Magic Wand needs display data)
        tool_context = {
            'display_scale': getattr(view, 'display_scale', 1.0),
            'view': view,
            'display_data': getattr(view, 'last_display_array', None)
        }
        
        view.active_tool.mouse_press(
            scene_pos,
            getattr(view, 'active_channel_index', -1),
            context=tool_context
        )
    
    event.accept()
    return True

def execute_tool_move(view, event, scene_pos):
    """Executes the active tool's mouse move logic."""
    if not view.active_tool:
        return False
        
    try:
        view.active_tool.mouse_move(scene_pos, event.modifiers())
        
        # UI updates triggered by tool move
        if hasattr(view, '_update_preview'):
            view._update_preview()
        if view.scene():
            view.scene().update()
        view.viewport().update()
        
        return True
    except Exception as e:
        Logger.error(f"[InteractionUtils] Tool mouse_move failed: {e}")
        return False

def execute_tool_release(view, event, scene_pos):
    """Executes the active tool's mouse release logic if any."""
    if not view.active_tool:
        return False
        
    if hasattr(view.active_tool, 'mouse_release'):
        view.active_tool.mouse_release(scene_pos, event.modifiers())
        
        # UI updates triggered by tool release
        if hasattr(view, '_update_preview'):
            view._update_preview()
        if view.scene():
            view.scene().update()
        view.viewport().update()
        
        return True
    return False

def activate_tool(view, tool):
    """
    Handles tool activation and deactivation on a view.
    Ensures correct cursor, drag mode, and item flags.
    """
    if view.active_tool == tool:
        return
    
    # Deactivate old tool
    if view.active_tool:
        try:
            if hasattr(view.active_tool, 'deactivate'):
                view.active_tool.deactivate()
        except Exception as e:
            Logger.error(f"[InteractionUtils] Error deactivating old tool: {e}")
            
    view.active_tool = tool
    
    if hasattr(view, '_update_preview'):
        view._update_preview()

    if tool is not None:
        Logger.debug(f"[InteractionUtils] Active tool set: {type(tool).__name__} on {view.view_id}")
        
        # Tool active: Disable drag
        view.setDragMode(QGraphicsView.DragMode.NoDrag)
        
        # Set appropriate cursor
        if hasattr(tool, 'cursor_shape'):
            view.setCursor(tool.cursor_shape)
        else:
            view.setCursor(Qt.CursorShape.CrossCursor)

    else:
        # No tool (Hand mode): Enable Pan/Drag AND Item Movement
        Logger.debug(f"[InteractionUtils] Active tool cleared (Hand mode) on {view.view_id}")
        view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        view.setCursor(Qt.CursorShape.OpenHandCursor)
        
        # Re-enable item movement in Hand mode
        # Note: view._roi_items is assumed to exist if it's a CanvasView
        roi_items = getattr(view, '_roi_items', {})
        for item in roi_items.values():
            try:
                item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
                item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
                item.setAcceptHoverEvents(True)
            except Exception as e:
                    Logger.error(f"[InteractionUtils] Failed to reset ROI item flags: {e}")

def handle_temp_pan_press(view: QGraphicsView, event) -> bool:
    """
    Handles key press for temporary pan mode (Space or Ctrl).
    Returns True if the event was handled.
    """
    key = event.key()
    
    # 1. Space Bar Pan
    if key == Qt.Key.Key_Space:
        view._is_space_pressed = True
        if not hasattr(view, '_prev_tool'):
            # Store current state
            view._prev_tool = view.active_tool
            view._prev_mode_name = getattr(view, '_current_mode_name', 'none')
            
            # Switch to Pan (using activate_tool(None))
            activate_tool(view, None)
        return True
        
    # 2. Ctrl Key (Pan + Multi-Select)
    elif key == Qt.Key.Key_Control:
        if not getattr(view, '_is_ctrl_pan_active', False):
            view._is_ctrl_pan_active = True
            
            # Store state
            view._prev_tool_ctrl = view.active_tool
            view._prev_drag_mode_ctrl = view.dragMode()
            view._prev_cursor_ctrl = view.viewport().cursor()
            
            # Switch to Pan
            activate_tool(view, None)
        return True
        
    return False

def handle_temp_pan_release(view: QGraphicsView, event) -> bool:
    """
    Handles key release for temporary pan mode (Space or Ctrl).
    Returns True if the event was handled.
    """
    key = event.key()
    
    # 1. Space Bar Pan
    if key == Qt.Key.Key_Space:
        view._is_space_pressed = False
        if hasattr(view, '_prev_tool'):
            # Restore previous state
            activate_tool(view, view._prev_tool)
            if hasattr(view, '_prev_mode_name'):
                view._current_mode_name = view._prev_mode_name
                del view._prev_mode_name
            
            del view._prev_tool
            view.setFocus()
        return True
        
    # 2. Ctrl Key
    elif key == Qt.Key.Key_Control:
        if getattr(view, '_is_ctrl_pan_active', False):
            view._is_ctrl_pan_active = False
            
            # Restore state
            if hasattr(view, '_prev_drag_mode_ctrl'):
                if view.active_tool:
                    view.setDragMode(QGraphicsView.DragMode.NoDrag)
                else:
                    view.setDragMode(view._prev_drag_mode_ctrl)
                del view._prev_drag_mode_ctrl
                
            if hasattr(view, '_prev_cursor_ctrl'):
                view.setCursor(view._prev_cursor_ctrl)
                del view._prev_cursor_ctrl
                
            if hasattr(view, '_prev_tool_ctrl'):
                del view._prev_tool_ctrl
                
            view.setFocus()
        return True
        
    return False
