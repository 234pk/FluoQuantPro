from PySide6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QGraphicsPathItem, QLabel, QGraphicsItem, QApplication, QGraphicsRectItem, QGraphicsObject, QGraphicsLineItem
from PySide6.QtGui import QPixmap, QPainter, QPen, QColor, QBrush, QPainterPath, QFont, QTransform, QPalette, QFontMetrics, QPainterPathStroker, QKeySequence, QImage
from PySide6.QtCore import Qt, Signal, QRectF, QPoint, QPointF, QTimer, QObject, QLineF, QSettings, QMutex
from PySide6.QtOpenGLWidgets import QOpenGLWidget
import numpy as np
import cv2
import time
from src.core.language_manager import tr
from src.core.logger import Logger
from src.core.performance_monitor import PerformanceMonitor
from src.core.roi_model import ROI, create_smooth_path_from_points
from src.gui.tools import PolygonTool, LineScanTool, DrawToolFactory, BaseDrawTool
from src.gui.rendering.qt_engine import QtRenderEngine
from src.gui.rendering.engine import StyleConfigCenter
from src.utils.physical_style import PhysicalRenderStyle
from src.gui.graphics_items import UnifiedGraphicsItem, RoiHandleItem, ScaleBarItem, LineScanGraphicsItem
from src.gui.interaction_utils import (
    find_item_at_position, 
    resolve_unified_item, 
    should_bypass_tool, 
    is_selection_modifier_active,
    handle_selection_modifier,
    execute_tool_press,
    execute_tool_move,
    execute_tool_release,
    handle_temp_pan_press,
    handle_temp_pan_release
)

class CanvasView(QGraphicsView):
    """
    The main viewport for displaying the multi-channel image.
    Supports zooming and panning.
    Handles ROI rendering via QGraphicsPathItem.
    Now Unified: All shapes (Scientific ROIs and Visual Annotations) are rendered as ROIs.
    """
    zoom_changed = Signal(float, float, QPointF) # scale_x, scale_y, focus_scene_pos
    file_dropped = Signal(str, int) # file_path, channel_index
    view_clicked = Signal(str, int) # view_id, channel_index (For channel selection)
    mouse_moved = Signal(int, int) # scene_x, scene_y
    tool_cancelled = Signal() # Emitted when ESC is pressed
    scale_bar_moved = Signal(QPointF) # Emitted when scale bar is moved

    def __init__(self, parent=None, view_id="canvas", session=None):
        super().__init__(parent)
        self.view_id = view_id
        self.session = session
        
        # --- GPU Acceleration: Enable OpenGL Viewport ---
        gl_widget = QOpenGLWidget()
        # WA_OpaquePaintEvent and WA_NoSystemBackground help reduce flickering in some cases
        gl_widget.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        gl_widget.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setViewport(gl_widget)
        
        # --- Advanced Rendering Optimizations ---
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        self.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        
        # Cache background disabled to avoid flickering with OpenGL
        self.setCacheMode(QGraphicsView.CacheModeFlag.CacheNone if hasattr(QGraphicsView.CacheModeFlag, "CacheNone") else QGraphicsView.CacheModeFlag(0))
        
        # Viewport update mode: FullViewportUpdate is often more stable for OpenGL viewports
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        
        # Optimization flags
        self.setOptimizationFlag(QGraphicsView.OptimizationFlag.DontAdjustForAntialiasing, False)
        self.setOptimizationFlag(QGraphicsView.OptimizationFlag.DontSavePainterState, True)
        
        # Performance Monitor
        self.perf_monitor = PerformanceMonitor.instance()
        self.perf_monitor.performance_mode_changed.connect(self.update_render_quality)
        self.perf_monitor.violent_interaction_detected.connect(self._handle_violent_interaction)
        self.update_render_quality(not self.perf_monitor.use_antialiasing)

        # Performance: Interaction Stability
        self._interaction_stability_timer = QTimer(self)
        self._interaction_stability_timer.setSingleShot(True)
        self._interaction_stability_timer.timeout.connect(self._restore_interaction_stability)
        self._is_interaction_violent = False
        self._is_using_low_res = False

        self.setAcceptDrops(True) # Enable Drag & Drop
        self.setMouseTracking(True) # Enable Mouse Tracking for status bar info
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus) # Enable Keyboard Events
        self._scene = QGraphicsScene(self)
        # Optimization: Disable BSP tree indexing for better performance with complex dynamic items
        # This significantly reduces freeze time when adding/moving complex ROIs (like Magic Wand results)
        self._scene.setItemIndexMethod(QGraphicsScene.NoIndex)
        self.setScene(self._scene)
        self._scene.selectionChanged.connect(self.on_scene_selection_changed)
        
        # Quicklook Preview Label (Hidden by default)
        self.preview_label = QLabel(self)
        self.preview_label.setWindowFlags(Qt.WindowType.ToolTip)
        self.preview_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.preview_label.setProperty("role", "preview")
        self.preview_label.hide()

        # Drop Hint Overlay (Centered)
        self.drop_hint = QLabel(tr("Drop to Load Image"), self)
        self.drop_hint.setStyleSheet("""
            QLabel {
                background-color: rgba(0, 122, 204, 180);
                color: white;
                font-weight: bold;
                font-size: 14px;
                padding: 10px 20px;
                border-radius: 5px;
            }
        """)
        self.drop_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.drop_hint.hide()
        
        self._snap_scale_mutex = QMutex()
        
        # Image Item (Z-value 0)
        self.pixmap_item = QGraphicsPixmapItem()
        self.pixmap_item.setZValue(0)
        self.scene().addItem(self.pixmap_item)
        
        # USER REQUEST: Add border to distinguish image from black background
        self.image_border_item = QGraphicsRectItem(self.pixmap_item)
        # USER REQUEST: Optimized border (Subtle Gray) + Dark Background
        border_pen = QPen(QColor(80, 80, 80), 1) # Subtle gray border
        border_pen.setCosmetic(True) # Keep 1px width regardless of zoom
        self.image_border_item.setPen(border_pen)
        self.image_border_item.setBrush(Qt.BrushStyle.NoBrush)
        self.image_border_item.setZValue(0.1)
        self.image_border_item.hide()
        
        # Label Overlay
        self.label_text = None
        self.is_selected = False
        self.flash_active = False # For visual feedback
        
        # Temp Path Item (For Lasso/Wand Preview)
        self.temp_path_item = QGraphicsPathItem()
        self.temp_path_item.setZValue(100) # Topmost
        
        # Use theme-aware color for preview
        highlight_color = QApplication.palette().color(QPalette.ColorRole.Highlight)
        pen = QPen(highlight_color.lighter(150), 2)
        pen.setStyle(Qt.PenStyle.SolidLine)
        pen.setCosmetic(True)
        self.temp_path_item.setPen(pen)
        
        # Add a semi-transparent fill for the preview
        fill_color = highlight_color.lighter(150)
        fill_color.setAlpha(60) # Light theme color fill
        self.temp_path_item.setBrush(QBrush(fill_color))
        
        self.scene().addItem(self.temp_path_item)
        
        # View settings
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True) # AA for ROIs
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        
        # Optimization: FullViewportUpdate is best for OpenGL viewports
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        
        # EXPERIMENTAL FIX: Ensure viewport mouse tracking
        self.viewport().setMouseTracking(True)
        
        # Dark Gray background (not pure black) to distinguish image boundaries
        self.setBackgroundBrush(QBrush(QColor(30, 30, 30)))

        # State
        self._zoom_level = 1.0
        self.roi_manager = None
        self.active_tool = None
        self.active_channel_index = 0
        self._wheel_enabled = True # USER REQUEST: Ability to disable wheel for thumbnails
        
        # Performance: Pixmap Proxies (Multi-level Resolution)
        self.pixmap_l0 = None  # Original (100%)
        self.pixmap_l1 = None  # Level 1 (e.g. 2048px)
        self.pixmap_l2 = None  # Level 2 (e.g. 512px)
        self.full_res_pixmap = None # Legacy reference
        self.low_res_pixmap = None  # Legacy reference
        self._base_pixmap_transform = QTransform()
        
        # Map ROI ID -> GraphicsItem
        self._roi_items = {}
        self._is_updating_from_manager = False
        
        self.label_text = None
        self.is_selected = False
        self.flash_active = False # Visual feedback for updates
        self._is_hand_panning = False
        self._hand_pan_last_pos = None
        self._bypass_active_tool_events = False
        
        # --- Scientific Rigor: Data/Display Mapping ---
        self.last_display_array = None # The (H,W,3) array currently shown
        self.display_scale = 1.0 # display_size / full_res_size

        # --- Unified Annotation State ---
        # Note: We no longer have separate 'annotation_mode' logic. Everything is a Tool.
        # But we keep this property for compatibility with Controller checks if needed.
        self._current_mode_name = 'none' 

        # --- Scale Bar ---
        from src.core.data_model import ScaleBarSettings
        if self.session:
            self.scale_bar_item = ScaleBarItem(self.session.scale_bar_settings)
        else:
            self.scale_bar_item = ScaleBarItem(ScaleBarSettings())
        self.scale_bar_item.moved.connect(self.scale_bar_moved.emit)
        self.scene().addItem(self.scale_bar_item)
        
        self._shape_items = {}

        # Text Input Overlay (for Text Tool)
        from PySide6.QtWidgets import QLineEdit
        self.text_input = QLineEdit(self.viewport())
        self.text_input.hide()
        self.text_input.editingFinished.connect(self._on_text_input_finished)
        # PPT style: Dark semi-transparent background, no border, white text, clear cursor
        self.text_input.setStyleSheet("""
            QLineEdit {
                background: rgba(20, 20, 20, 200);
                color: white;
                border: 1px solid #0078d7;
                padding: 4px;
                font-family: 'Segoe UI', Arial;
                font-size: 14px;
                selection-background-color: #0078d7;
            }
        """)
        self._text_input_callback = None

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

        # --- UX Enhancements: Snapping & Feedback ---
        self._last_snap_scale = 0.0
        self._snap_feedback_timer = QTimer(self)
        self._snap_feedback_timer.setSingleShot(True)
        self._snap_feedback_timer.timeout.connect(self._stop_snap_feedback)
        self._is_snapped = False
        
        self._glow_active = False
        self._glow_timer = QTimer(self)
        self._glow_timer.setSingleShot(True)
        self._glow_timer.timeout.connect(self._stop_glow)
        
        self._size_indicator_visible = False
        self._size_indicator_text = ""
        self._size_indicator_opacity = 0.0
        self._indicator_fade_timer = QTimer(self)
        self._indicator_fade_timer.setInterval(30)
        self._indicator_fade_timer.timeout.connect(self._update_indicator_fade)

    def _update_indicator_fade(self):
        # Existing method logic ...
        pass

    # USER REQUEST: Auto-focus view on hover to enable keyboard shortcuts (Space, Ctrl) immediately
    def enterEvent(self, event):
        super().enterEvent(event)
        # Only steal focus if the window is active to avoid stealing from other apps
        if self.window().isActiveWindow():
             self.setFocus(Qt.FocusReason.MouseFocusReason)

    def show_text_input(self, scene_pos: QPointF, initial_text: str = "", callback=None):
        """Shows a text input box at the given scene position."""
        self._text_input_callback = callback
        view_pos = self.mapFromScene(scene_pos)
        self.text_input.setText(initial_text)
        self.text_input.move(view_pos)
        self.text_input.show()
        self.text_input.setFocus()
        self.text_input.selectAll()

    def _on_text_input_finished(self):
        if self.text_input.isVisible():
            text = self.text_input.text()
            self.text_input.hide()
            if self._text_input_callback:
                self._text_input_callback(text)
            self._text_input_callback = None
            self.setFocus() # Return focus to view


    def get_image_coordinates(self, scene_pos: QPointF) -> QPointF:
        """
        Maps a scene position to the image local coordinates.
        Ensures robust mapping even if the image item is offset or transformed.
        
        Returns full-resolution coordinates (matching the scene rect).
        """
        if hasattr(self, 'pixmap_item') and self.pixmap_item:
            # The scene is already in full-resolution coordinates (scene_rect = 0,0,w,h).
            # The pixmap_item is scaled to fit the scene.
            # mapFromScene would apply the inverse of the scaling (mapping to downsampled space).
            # We want to STAY in full-resolution space, but relative to the image top-left.
            return scene_pos - self.pixmap_item.pos()
        return scene_pos

    def _emit_view_clicked(self):
        try:
            # Relay the click signal. Redundancy check should be done by the receiver
            # to allow visual updates (like highlighting the clicked thumbnail)
            # even if it shows the same channel index.
            self.view_clicked.emit(self.view_id, self.active_channel_index)
        except Exception as e:
            Logger.warning(f"CanvasView({self.view_id}) view_clicked emit failed: {e}")

    def clear_active_tool(self):
        """Forces the active tool to be cleared, switching to edit mode."""
        if self.active_tool:
            Logger.info(f"[CanvasView] Force clearing active tool: {type(self.active_tool).__name__}")
            if hasattr(self.active_tool, 'preview_item') and self.active_tool.preview_item:
                 if self.active_tool.preview_item.scene():
                     self.scene().removeItem(self.active_tool.preview_item)
                 self.active_tool.preview_item = None
            self.active_tool = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self._current_mode_name = 'none'

    def get_label_rect(self) -> QRectF:
        """Calculates the rectangle of the channel label in viewport coordinates."""
        if not self.label_text:
            return QRectF()
            
        font = self.font()
        font.setBold(True)
        font_size = 12
        # Ensure font_size is at least 1 to avoid QFont warning
        if font_size <= 0:
            font_size = 12
        font.setPointSize(font_size)
        metrics = QFontMetrics(font)
        
        text_width = metrics.horizontalAdvance(self.label_text)
        text_height = metrics.height()
        
        padding = 5
        x = 10
        y = 10
        return QRectF(x, y, text_width + 2*padding, text_height + 2*padding)

    def mouseDoubleClickEvent(self, event):
        """Handle double-clicks, primarily for re-editing text ROIs."""
        if self._handle_text_re_editing(event):
            return
        super().mouseDoubleClickEvent(event)

    def _handle_text_re_editing(self, event) -> bool:
        """
        Check if the double-click is on a text ROI and initiate re-editing.
        Returns True if the event was handled.
        """
        click_pos = event.position().toPoint()
        scene_pos = self.mapToScene(click_pos)
        
        # Use fat-finger logic to find if we clicked a text ROI
        item = find_item_at_position(self, scene_pos)
        if isinstance(item, UnifiedGraphicsItem) and item.roi_type == 'text':
            roi = item.roi
            current_text = roi.properties.get('text', "")
            text_pos = item.mapToScene(item.path().boundingRect().topLeft())
            
            def update_text(new_text):
                if new_text and new_text != current_text:
                    roi.properties['text'] = new_text
                    item.update_from_model(roi)
                    item.modified.emit(roi)
                    if self.roi_manager:
                        self.roi_manager.roi_updated.emit(roi)
            
            self.show_text_input(text_pos, initial_text=current_text, callback=update_text)
            event.accept()
            return True
        return False

    def mousePressEvent(self, event):
        # --- 0. Select this channel on ANY click (Parallel Signal) ---
        # USER REQUEST: Optimization - click always selects, parallel signal, no interference.
        # Regardless of button (Left/Right/Middle), emit the selection signal.
        self._emit_view_clicked()

        # --- 1. Stop Inertia (Immediate Interaction) ---
        if self._is_zooming_smoothly:
            self._is_zooming_smoothly = False
            self._zoom_timer.stop()
            self._zoom_velocity = 0.0
            # Restore rendering quality
            self._disable_low_res_proxy()
            if self.pixmap_item.transformationMode() != Qt.TransformationMode.SmoothTransformation:
                self.pixmap_item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
                if not self.perf_monitor.is_low_quality:
                    self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            self.viewport().update()
            
        # Ensure focus for keyboard events
        self.setFocus()

        click_pos = event.position().toPoint()
        scene_pos = self.mapToScene(click_pos)
        
        # --- 1. Check for Label Click ---
        if self.label_text:
            label_rect = self.get_label_rect()
            if label_rect.contains(event.position()):
                Logger.debug(f"[CanvasView] Label clicked: {self.label_text}")
                self._emit_view_clicked()
                event.accept()
                return
        
        # Record start position for drag detection
        self._view_drag_start_pos = event.position()
        self._is_actually_dragging = False

        # --- 2. Determine Interaction Strategy ---
        # Use extracted utility to decide if we should bypass the active tool
        self._bypass_active_tool_events = should_bypass_tool(self, event)
        
        # Additional logic for specific tools (e.g. Text Tool re-editing)
        if not self._bypass_active_tool_events and self.active_tool:
            is_text_tool = (isinstance(self.active_tool, BaseDrawTool) and self.active_tool.shape_type == "text")
            if is_text_tool:
                # Check for existing text ROI under click to allow re-editing
                item = find_item_at_position(self, scene_pos)
                if isinstance(item, UnifiedGraphicsItem) and item.roi_type == 'text':
                    self._bypass_active_tool_events = True

        # --- 3. Handle Bypass (Interaction with existing items/scene) ---
        if self._bypass_active_tool_events:
            super().mousePressEvent(event)
            return

        # --- 4. Handle Active Tool ---
        if execute_tool_press(self, event, scene_pos):
            return


        # --- 4. Smart Pan & Interaction Logic (Fat Finger Detection) ---
        # Use extracted utility to find the most relevant item
        interactable = find_item_at_position(self, scene_pos)
        
        if interactable:
            # --- Text Re-editing Logic ---
            # If we click on a text ROI, allow re-editing even if no special tool is active
            if isinstance(interactable, UnifiedGraphicsItem) and interactable.roi_type == 'text':
                is_ctrl = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
                is_hand_mode = self.dragMode() == QGraphicsView.DragMode.ScrollHandDrag
                
                if event.button() == Qt.MouseButton.LeftButton and not (is_ctrl or is_hand_mode):
                    roi = interactable.roi
                    current_text = roi.properties.get('text', "")
                    text_pos = interactable.mapToScene(interactable.path().boundingRect().topLeft())
                    
                    def update_text(new_text):
                        if new_text and new_text != current_text:
                            roi.properties['text'] = new_text
                            interactable.update_from_model(roi)
                            interactable.modified.emit(roi)
                            if self.roi_manager:
                                self.roi_manager.roi_updated.emit(roi)
                    
                    self.show_text_input(text_pos, initial_text=current_text, callback=update_text)
                    event.accept()
                    return

            # Use utility to handle selection and event forwarding
            if handle_selection_modifier(self, event, interactable):
                event.accept()
                return
        
        # Default behavior for background clicks
        super().mousePressEvent(event)

    def update_ruler_position(self, pos: QPointF):
        """Updates the ruler position from external sync."""
        if hasattr(self, 'scale_bar_item') and self.scale_bar_item:
            self.scale_bar_item.setPos(pos)

    def _on_roi_added(self, roi):
        """Called when a new ROI is added to the manager."""
        Logger.debug(f"[CanvasView._on_roi_added] ENTER - ROI: {roi.label} ({roi.id})")
        # Create item with current display scale
        try:
            item = UnifiedGraphicsItem(roi)
            item.roi_manager = self.roi_manager # Inject manager for sync
            self.scene().addItem(item)
            try:
                item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
                item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
                item.setAcceptHoverEvents(True)
            except Exception:
                pass
            self._roi_items[roi.id] = item
            self._shape_items[f"roi:{roi.id}"] = item
            Logger.debug(f"[CanvasView._on_roi_added] Item added to scene and tracked.")
        except Exception as e:
            Logger.error(f"[CanvasView._on_roi_added] Failed to create or add ROI item: {e}")
            import traceback
            Logger.error(traceback.format_exc())

    def _on_roi_removed(self, roi_id):
        if roi_id in self._roi_items:
            item = self._roi_items.pop(roi_id)
            self.scene().removeItem(item)
        key = f"roi:{roi_id}"
        if key in self._shape_items:
            del self._shape_items[key]

    def _on_roi_updated(self, roi_or_id):
        # 修复：区分传入的是对象还是 ID 字符串
        if isinstance(roi_or_id, str):
            roi_id = roi_or_id
            # 从字典中查找对象（假设字典是以 ID 为 key）
            item = self._roi_items.get(roi_id)
            if item and hasattr(item, 'roi'):
                roi = item.roi # 获取内部数据模型
            elif self.roi_manager:
                roi = self.roi_manager.get_roi(roi_id)
                if not roi:
                    return # 没找到，忽略
            else:
                return # 没找到，忽略
        else:
            roi = roi_or_id # 假设它是对象
            
        if roi.id in self._roi_items:
            item = self._roi_items[roi.id]
            
            # Prevent update loop if this item is currently being manipulated by the user
            if getattr(item, 'is_dragging', False):
                return

            # Use flag to prevent itemChange from triggering a feedback loop
            item._is_updating = True
            try:
                # Use the unified update logic from the item itself
                item.update_from_model(roi)
            finally:
                item._is_updating = False
    
    def set_roi_manager(self, manager):
        """Connects to the ROI manager signals."""
        if self.roi_manager:
            try:
                self.roi_manager.roi_added.disconnect(self._on_roi_added)
                self.roi_manager.roi_removed.disconnect(self._on_roi_removed)
                self.roi_manager.roi_updated.disconnect(self._on_roi_updated)
                self.roi_manager.rois_reset.disconnect(self._sync_rois) # Connect reset to sync
                self.scene().selectionChanged.disconnect(self.on_scene_selection_changed)
            except:
                pass
        
        self.roi_manager = manager
        if manager:
            manager.roi_added.connect(self._on_roi_added)
            manager.roi_removed.connect(self._on_roi_removed)
            manager.roi_updated.connect(self._on_roi_updated)
            manager.rois_reset.connect(self._sync_rois) # Connect reset to sync
            self.scene().selectionChanged.connect(self.on_scene_selection_changed)
            
            # Load existing
            self._sync_rois()

    def set_label(self, text: str):
        """Sets the label text to be displayed in the top-left corner."""
        self.label_text = text
        self.viewport().update()

    def set_selected(self, selected: bool):
        """Updates the selection state and triggers repaint."""
        if self.is_selected != selected:
            self.is_selected = selected
            self.viewport().update()

    def _sync_rois(self):
        # Clear
        for item in self._roi_items.values():
            self.scene().removeItem(item)
        self._roi_items.clear()
        self._shape_items = {k: v for k, v in self._shape_items.items() if not k.startswith("roi:")}
        
        if self.roi_manager:
            for roi in self.roi_manager.get_all_rois():
                self._on_roi_added(roi)

    def set_active_tool(self, tool):
        from src.gui.interaction_utils import activate_tool
        activate_tool(self, tool)
        self.setFocus()

    def set_annotation_mode(self, mode: str):
        """
        Sets the drawing mode.
        Unified: 'annotation_mode' is now just setting the appropriate Tool.
        """
        Logger.info(f"[CanvasView] set_annotation_mode: {mode} (Unified)")
        self._current_mode_name = mode
        
        if mode == 'none':
            self.set_active_tool(None)
            return

        # Special handling for Point Counter which might be stored on MainWindow
        if mode == 'point':
            if hasattr(self.session, 'main_window') and hasattr(self.session.main_window, 'point_counter_tool'):
                self.set_active_tool(self.session.main_window.point_counter_tool)
                return

        # Use DrawToolFactory for all shapes (scientific or visual)
        try:
            tool = DrawToolFactory.create(self.session, mode)
            
            # Inject properties from panel if available
            if hasattr(self.session, 'main_window') and hasattr(self.session.main_window, 'annotation_panel'):
                try:
                    panel = self.session.main_window.annotation_panel
                    props = panel.get_current_properties()
                    if isinstance(props, dict):
                        # Text tool specific: defer applying text
                        if mode == 'text':
                            props = dict(props)
                            props['defer_text_apply'] = True
                        tool.set_properties(props)
                    
                    # Connect signals
                    mw = self.session.main_window
                    if hasattr(mw, 'multi_view'):
                        tool.preview_changed.connect(mw.multi_view.update_all_previews, Qt.ConnectionType.UniqueConnection)
                    if hasattr(mw, '_on_tool_committed'):
                        tool.committed.connect(mw._on_tool_committed, Qt.ConnectionType.UniqueConnection)
                    
                    # Live property updates
                    def _apply_panel_props():
                        try:
                            p = panel.get_current_properties()
                            tool.set_properties(p)
                            mw.multi_view.update_all_previews()
                        except Exception:
                            pass
                    panel.settings_changed.connect(_apply_panel_props, Qt.ConnectionType.UniqueConnection)
                    
                except Exception as e:
                    Logger.warning(f"[CanvasView] Failed to setup tool properties: {e}")

            self.set_active_tool(tool)
        except Exception as e:
            Logger.error(f"[CanvasView] Failed to create tool for mode {mode}: {e}")
            self.set_active_tool(None)

    def contextMenuEvent(self, event):
        """Handle Context Menu events (Right Click)."""
        # If we have an active tool, it might handle right click (e.g. Polygon finish)
        if self.active_tool:
             event.accept()
             return
        super().contextMenuEvent(event)

    def mouseMoveEvent(self, event):
        # Ensure we can get a valid position from the event
        try:
            pos = event.position()
        except AttributeError:
            pos = event.pos()
            
        scene_pos = self.mapToScene(pos.toPoint())
             
        # THROTTELED: mouse_moved signal (Update status bar)
        current_time = time.perf_counter()
        if not hasattr(self, '_last_mouse_move_time'):
            self._last_mouse_move_time = 0
            
        if current_time - self._last_mouse_move_time > 0.033: # ~30 FPS
            self.mouse_moved.emit(int(scene_pos.x()), int(scene_pos.y()))
            self._last_mouse_move_time = current_time
        
        is_drawing = False
        if self.active_tool:
             if hasattr(self.active_tool, 'is_dragging') and self.active_tool.is_dragging:
                 is_drawing = True
             elif hasattr(self.active_tool, 'is_active') and self.active_tool.is_active:
                 is_drawing = True
        
        if is_drawing:
             # Force update regardless of bypass flag
             try:
                 self.active_tool.mouse_move(scene_pos, event.modifiers())
                 self._update_preview()
                 if self.scene(): self.scene().update()
                 self.viewport().update() # Force viewport redraw
             except Exception as e:
                 Logger.error(f"[CanvasView] Tool mouse_move failed: {e}")
             return

        # 1. Handle Bypass FIRST (e.g. Handle Dragging, Item Moving)
        if getattr(self, '_bypass_active_tool_events', False):
             if hasattr(self, '_view_drag_start_pos'):
                 delta = event.position() - self._view_drag_start_pos
                 if delta.manhattanLength() < 1:
                     return
             
             self._is_actually_dragging = True
             # PERFORMANCE: Enable low-res proxy during dragging if needed
             if self.dragMode() == QGraphicsView.DragMode.ScrollHandDrag:
                 self._enable_low_res_proxy()
             
             super().mouseMoveEvent(event)
             return

        if execute_tool_move(self, event, scene_pos):
            return
        
        # 0. Smart Pan Threshold
        if hasattr(self, '_view_drag_start_pos'):
            delta = event.position() - self._view_drag_start_pos
            if delta.manhattanLength() > 2:
                # PERFORMANCE: Enable low-res proxy during panning
                if self.dragMode() == QGraphicsView.DragMode.ScrollHandDrag:
                    self._enable_low_res_proxy()
            else:
                return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        # PERFORMANCE: Restore high-res pixmap
        self._disable_low_res_proxy()
        
        was_bypassing = getattr(self, '_bypass_active_tool_events', False)
        self._bypass_active_tool_events = False

        # Restore drag mode if we were moving an item
        if hasattr(self, '_temp_drag_restore'):
            self.setDragMode(self._temp_drag_restore)
            del self._temp_drag_restore
            
        if getattr(self, '_temp_drag_mode', False):
            self._temp_drag_mode = False
            
        scene_pos = self.mapToScene(event.position().toPoint())
        
        # 2. 优先处理旁路逻辑（如：Handle 拖拽、ROI 移动等）
        if was_bypassing:
             Logger.debug(f"[CanvasView] Bypass tool release due to item interaction")
             super().mouseReleaseEvent(event)
             return

        # 3. 处理活动工具的松手逻辑
        if execute_tool_release(self, event, scene_pos):
            return
        
        # 3. Handle Click-to-Clear Selection in Hand Mode
        if self.active_tool is None and event.button() == Qt.MouseButton.LeftButton:
             if hasattr(self, '_view_drag_start_pos'):
                 dist = (event.position() - self._view_drag_start_pos).manhattanLength()
                 if dist < 3:
                     modifiers = QApplication.keyboardModifiers()
                     is_ctrl = bool(modifiers & Qt.KeyboardModifier.ControlModifier)
                     is_shift = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)
                     
                     if not is_ctrl and not is_shift and self.scene():
                        self.scene().clearSelection()

        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        """Handle keyboard events (Delete/Backspace to remove items, Space for Pan, [ ] for size)."""
        if event.isAutoRepeat():
            super().keyPressEvent(event)
            return

        # --- 1. Handle Temporary Pan (Space / Ctrl) ---
        if handle_temp_pan_press(self, event):
            event.accept()
            return

        # --- 2. Standard Shortcuts ---
        # Ctrl+A: Select All ROIs
        if event.matches(QKeySequence.StandardKey.SelectAll) or (event.key() == Qt.Key.Key_A and (event.modifiers() & Qt.KeyboardModifier.ControlModifier)):
            try:
                self.scene().clearSelection()
                self.scene().blockSignals(True)
                
                count = 0
                if self.roi_manager:
                    for item in self.scene().items():
                        if isinstance(item, UnifiedGraphicsItem):
                            roi = self.roi_manager.get_roi(item.roi_id)
                            if roi:
                                # Filter out line scans? Maybe select them too if unified.
                                # But usually select all is for processing.
                                # Let's keep existing logic: exclude line scans if they are special?
                                # Actually, unified means select everything.
                                item.setSelected(True)
                                count += 1
                
                self.scene().blockSignals(False)
                self.on_scene_selection_changed()
                
                Logger.debug(f"[CanvasView] Selected {count} ROIs via Select All")
                event.accept()
                return
            except Exception as e:
                Logger.error(f"[CanvasView] Select All failed: {e}")
                self.scene().blockSignals(False)
                return

        # ESC: Cancel current tool
        if event.key() == Qt.Key.Key_Escape:
            self.set_active_tool(None)
            self._current_mode_name = 'none'
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
                
                if hasattr(self.window(), 'roi_toolbox'):
                    self.window().roi_toolbox.spin_count_radius.setValue(self.active_tool.radius)
            event.accept()
            return

        # Delete/Backspace
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            selected_items = self.scene().selectedItems()
            roi_ids_to_remove = set()

            def resolve_target_item(item):
                cur = item
                while cur and not isinstance(cur, UnifiedGraphicsItem):
                    cur = cur.parentItem()
                return cur
            
            for item in selected_items:
                target = resolve_target_item(item)
                if isinstance(target, UnifiedGraphicsItem):
                    roi_ids_to_remove.add(target.roi_id)

            if roi_ids_to_remove and self.session and self.session.roi_manager:
                for roi_id in roi_ids_to_remove:
                    self.session.roi_manager.remove_roi(roi_id, undoable=True)
            
            return
                
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        """Restore tool after space or ctrl is released."""
        if event.isAutoRepeat():
            super().keyReleaseEvent(event)
            return

        # --- 1. Handle Temporary Pan Restore ---
        if handle_temp_pan_release(self, event):
            event.accept()
            return

        super().keyReleaseEvent(event)

    def drawBackground(self, painter: QPainter, rect: QRectF):
        """
        Custom background drawing with tiled rendering optimization for large images.
        Also handles viewport-only rendering logic.
        """
        # PERFORMANCE: Only render what's visible in the viewport
        # Get the actual visible rect in scene coordinates
        viewport_rect = self.mapToScene(self.viewport().rect()).boundingRect()
        
        # If the image is extremely large, we can limit the drawing area here
        # or use specialized tiling logic. 
        # For now, super().drawBackground is sufficient as QGraphicsView already does culling,
        # but we can add custom rendering logic if needed.
        super().drawBackground(painter, rect)


    def _update_preview(self):
        """Helper to sync temp path item with tool state."""
        # NEW: Skip redundant preview for Polygon/MagicWand tools to avoid interference with their internal real-time display
        # MagicWandTool handles its own preview item (with correct scaling for downsampled data)
        # PolygonSelectionTool handles its own preview for complex interaction
        if self.active_tool:
            tool_name = self.active_tool.__class__.__name__
            if tool_name in ["PolygonSelectionTool", "MagicWandTool"]:
                if hasattr(self, 'temp_path_item') and self.temp_path_item:
                    self.temp_path_item.setVisible(False)
                    self.temp_path_item.setPath(QPainterPath())
                return

        path = None
        if self.active_tool:
            if hasattr(self.active_tool, 'get_preview_path'):
                last_pos = self.mapToScene(self.mapFromGlobal(self.cursor().pos()))
                try:
                    path = self.active_tool.get_preview_path(last_pos)
                except TypeError:
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
            
        if self.scene():
            self.scene().update()

    def update_scale_bar(self, settings):
        """Updates the scale bar settings and refreshes the view."""
        if hasattr(self, 'scale_bar_item'):
            self.scale_bar_item.update_settings(settings)
            self.scene().update()

    def update_ruler_position(self, pos: QPointF):
        """Updates the position of the scale bar."""
        if hasattr(self, 'scale_bar_item'):
            self.scale_bar_item.setPos(pos)
            self.scene().update()

    def fit_to_width(self):
        """Zoom to fit image width to viewport."""
        scales = self._get_snap_scales()
        for scale, label in scales:
            if label in ("Fit Width", "Fit"):
                self._apply_zoom_scale(scale)
                break

    def fit_to_height(self):
        """Zoom to fit image height to viewport."""
        scales = self._get_snap_scales()
        for scale, label in scales:
            if label in ("Fit Height", "Fit"):
                self._apply_zoom_scale(scale)
                break

    def _apply_zoom_scale(self, scale):
        """Helper to apply a specific zoom scale immediately."""
        if scale <= 0: return
        
        # Reset smooth zoom state
        self._target_zoom = scale
        self._current_zoom = scale
        self._zoom_velocity = 0.0
        self._is_zooming_smoothly = False
        self._zoom_timer.stop()
        
        # Apply transformation directly
        # We want to maintain the relative scale of the pixmap_item if it has a base transform
        base_scale = self._base_pixmap_transform.m11()
        if base_scale == 0: base_scale = 1.0
        
        # The scale we want is the TOTAL scale from image pixels to viewport pixels
        # QGraphicsView.scale() adds to the view's transform.
        # Total scale = ViewTransform.m11() * ItemTransform.m11()
        # We want Total scale = target_scale
        # So ViewTransform.m11() = target_scale / ItemTransform.m11()
        
        view_scale = scale / base_scale
        self.setTransform(QTransform().scale(view_scale, view_scale))
        
        # Center the image in the view
        self.centerOn(self.pixmap_item)
        
        # Update and notify
        t = self.transform()
        self.zoom_changed.emit(t.m11(), t.m22(), self.pixmap_item.boundingRect().center())
        self._disable_low_res_proxy()
        self.viewport().update()

    def update_image(self, image: np.ndarray, scene_rect: QRectF = None):
        """
        Updates the displayed image with multi-level resolution pre-generation.
        USER REQUEST: Level 0 (100%), Level 1 (2048px), Level 2 (512px).
        """
        if image is None:
            self.pixmap_item.setPixmap(QPixmap())
            self.image_border_item.hide()
            self.pixmap_l0 = self.pixmap_l1 = self.pixmap_l2 = None
            self.full_res_pixmap = self.low_res_pixmap = None
            self.last_display_array = None
            self.display_scale = 1.0
            self.scene().update()
            self.viewport().update()
            return

        h, w = image.shape[:2]
        self._is_using_low_res = False # Reset state for new image
        self.pixmap_l0 = None # Initialize to avoid AttributeError if generation fails
        
        # 1. Generate Multi-level Pixmaps
        try:
            # USER REQUEST: Level 0 should respect quality settings
            # If performance mode is set, Level 0 might be capped
            settings = QSettings("FluoQuantPro", "Settings")
            quality_key = settings.value("display/quality_key", "balanced")
            
            # USER REQUEST: FIX Red-Blue Channel Reversal
            # Explicitly convert to uint8 RGB and create QImage with Format_RGB888.
            # This avoids ambiguity in qimage2ndarray or platform-specific BGR defaults.
            if image.dtype != np.uint8:
                img_u8 = (np.clip(image, 0, 1) * 255).astype(np.uint8)
            else:
                img_u8 = image
                
            if not img_u8.flags['C_CONTIGUOUS']:
                img_u8 = np.ascontiguousarray(img_u8)
                
            h_img, w_img = img_u8.shape[:2]
            channels = 1 if img_u8.ndim == 2 else img_u8.shape[2]
            
            if channels == 3:
                qimg = QImage(img_u8.data, w_img, h_img, w_img * 3, QImage.Format.Format_RGB888)
            elif channels == 4:
                qimg = QImage(img_u8.data, w_img, h_img, w_img * 4, QImage.Format.Format_RGBA8888)
            else:
                # Grayscale
                qimg = QImage(img_u8.data, w_img, h_img, w_img, QImage.Format.Format_Grayscale8)

            full_pixmap = QPixmap.fromImage(qimg)
            
            # Default: Level 0 is full resolution
            self.pixmap_l0 = full_pixmap
            
            # Performance Optimization: Respect "Rendering Quality" setting
            if quality_key == "performance":
                # USER REQUEST: Performance mode: Cap at 1024px
                max_dim = 1024
                if w > max_dim or h > max_dim:
                    self.pixmap_l0 = full_pixmap.scaled(max_dim, max_dim, 
                                                       Qt.AspectRatioMode.KeepAspectRatio, 
                                                       Qt.TransformationMode.SmoothTransformation)
                    Logger.info(f"CanvasView({self.view_id}): Rendering Quality is 'Performance'. Level 0 capped at {max_dim}px.")
            elif quality_key == "balanced":
                # USER REQUEST: Balanced mode: Cap at 2560px (2.5K)
                max_dim = 2560
                if w > max_dim or h > max_dim:
                    self.pixmap_l0 = full_pixmap.scaled(max_dim, max_dim, 
                                                       Qt.AspectRatioMode.KeepAspectRatio, 
                                                       Qt.TransformationMode.SmoothTransformation)
                    Logger.info(f"CanvasView({self.view_id}): Rendering Quality is 'Balanced'. Level 0 capped at {max_dim}px.")
            elif quality_key == "4k":
                # USER REQUEST: 4K mode: Cap at 3840px
                max_dim = 3840
                if w > max_dim or h > max_dim:
                    self.pixmap_l0 = full_pixmap.scaled(max_dim, max_dim, 
                                                       Qt.AspectRatioMode.KeepAspectRatio, 
                                                       Qt.TransformationMode.SmoothTransformation)
                    Logger.info(f"CanvasView({self.view_id}): Rendering Quality is '4K'. Level 0 capped at {max_dim}px.")
            else: # "high" or other
                # High Quality: Use original resolution
                Logger.info(f"CanvasView({self.view_id}): Rendering Quality is 'High'. Using full resolution for Level 0.")
            
            self.full_res_pixmap = self.pixmap_l0 # Sync legacy
            
            # Level 1: Long edge 2048px (Always generated for fast zoom)
            l1_size = 2048
            if w > l1_size or h > l1_size:
                self.pixmap_l1 = self.pixmap_l0.scaled(l1_size, l1_size, 
                                                    Qt.AspectRatioMode.KeepAspectRatio, 
                                                    Qt.TransformationMode.SmoothTransformation)
            else:
                self.pixmap_l1 = self.pixmap_l0
            
            # Level 2: Long edge 512px (Used for fast scaling/panning)
            l2_size = 512
            if w > l2_size or h > l2_size:
                self.pixmap_l2 = self.pixmap_l0.scaled(l2_size, l2_size, 
                                                    Qt.AspectRatioMode.KeepAspectRatio, 
                                                    Qt.TransformationMode.FastTransformation)
                self.low_res_pixmap = self.pixmap_l2 # Sync legacy
            else:
                self.pixmap_l2 = self.pixmap_l0
                self.low_res_pixmap = None

            # Initial display uses Level 0
            self.pixmap_item.setPixmap(self.pixmap_l0)
            self.pixmap_item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
            
            # USER REQUEST: Update border to match image size
            if self.pixmap_l0:
                self.image_border_item.setRect(QRectF(self.pixmap_l0.rect()))
                self.image_border_item.show()
            else:
                self.image_border_item.hide()
            
        except Exception as e:
            Logger.error(f"CanvasView({self.view_id}): Multi-level Pixmap generation failed: {e}", exc_info=True)

        self.last_display_array = image # Store for tool access
        
        # 2. Update Scene Rect and Scaling
        if scene_rect:
            self.scene().setSceneRect(scene_rect)
            
            scene_w = scene_rect.width()
            pix_w = self.pixmap_l0.width() if self.pixmap_l0 else 0
            
            if pix_w > 0:
                # Scale pixmap_item so its width (pix_w) matches scene_w
                scale = scene_w / pix_w
                base_transform = QTransform().scale(scale, scale)
                self.pixmap_item.setTransform(base_transform)
                self._base_pixmap_transform = base_transform
                self.pixmap_item.setPos(0, 0)
                
                # display_scale = display_size / full_res_size
                # Here full_res is represented by 'scene_w' (original width)
                # pix_w is the downsampled width
                self.display_scale = pix_w / scene_w if scene_w > 0 else 1.0
            else:
                self.display_scale = 1.0
                self.pixmap_item.setTransform(QTransform())
                self._base_pixmap_transform = QTransform()
                self.pixmap_item.setPos(0, 0)
        else:
            self.scene().setSceneRect(0, 0, w, h)
            
            pix_w = self.pixmap_l0.width() if self.pixmap_l0 else 0
            if pix_w > 0:
                scale = w / pix_w
                base_transform = QTransform().scale(scale, scale)
                self.pixmap_item.setTransform(base_transform)
                self._base_pixmap_transform = base_transform
                self.display_scale = pix_w / w
            else:
                self.pixmap_item.setTransform(QTransform())
                self._base_pixmap_transform = QTransform()
                self.display_scale = 1.0
            
            self.pixmap_item.setPos(0, 0)
            
        # 3. Update ROIs appearance based on new scale
        if self.roi_manager:
            self._sync_rois()
            
        # Update scale bar position
        if hasattr(self, 'scale_bar_item'):
            self.scale_bar_item.update_settings(self.scale_bar_item.settings)
            
        self.scene().update()
        self.viewport().update()

    def _enable_low_res_proxy(self):
        """
        Optimizes rendering during interaction using pre-generated Level 2 pixmap.
        USER REQUEST: During interaction, use low-res for speed.
        """
        if self._is_using_low_res:
            return

        Logger.debug(f"[CanvasView:{self.view_id}] Enabling low-res proxy")
        # Disable smoothing for better performance during movement
        self.pixmap_item.setTransformationMode(Qt.TransformationMode.FastTransformation)
        
        # Use Level 2 pixmap (512px) if it exists and is smaller than original
        if self.pixmap_l2 and self.pixmap_l0 and self.pixmap_l2 != self.pixmap_l0:
            scale_x = self.pixmap_l0.width() / self.pixmap_l2.width()
            scale_y = self.pixmap_l0.height() / self.pixmap_l2.height()
            
            self.pixmap_item.setPixmap(self.pixmap_l2)
            transform = QTransform(self._base_pixmap_transform)
            transform.scale(scale_x, scale_y)
            self.pixmap_item.setTransform(transform)
            
            # Sync border to low-res pixmap size
            self.image_border_item.setRect(QRectF(self.pixmap_l2.rect()))
            
            self._is_using_low_res = True

    def _disable_low_res_proxy(self):
        """Restores high-resolution (Level 0) pixmap after interaction."""
        if not self._is_using_low_res:
            # Ensure SmoothTransformation is restored
            if self.pixmap_item.transformationMode() != Qt.TransformationMode.SmoothTransformation:
                 self.pixmap_item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
            return

        Logger.debug(f"[CanvasView:{self.view_id}] Disabling low-res proxy")
        if self.pixmap_l0:
            self.pixmap_item.setPixmap(self.pixmap_l0)
            self.pixmap_item.setTransform(self._base_pixmap_transform)
            self.pixmap_item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
            
            # Sync border to high-res pixmap size
            self.image_border_item.setRect(QRectF(self.pixmap_l0.rect()))
            
            self._is_using_low_res = False
            self.viewport().update()

    def scrollContentsBy(self, dx, dy):
        """
        Enable low-res proxy during panning for better performance.
        USER REQUEST: Viewport rendering optimization.
        """
        super().scrollContentsBy(dx, dy)
        if abs(dx) > 1 or abs(dy) > 1:
            self._enable_low_res_proxy()
            # Restore after 300ms of inactivity
            self._interaction_stability_timer.start(300)

    def _handle_violent_interaction(self, active=True):
        """Callback from PerformanceMonitor when flickering/rapid movement is detected."""
        if active:
            if not self._is_interaction_violent:
                self._is_interaction_violent = True
                
                # Disable AA on the VIEW to improve performance and reduce flickering
                self.setRenderHint(QPainter.RenderHint.Antialiasing, False)
                self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
                
                # Logger.info("[CanvasView] Interaction stability mode ENABLED (Low-res locked)")
                self._enable_low_res_proxy()
            
            # Refresh timer (stay in low-res for at least 500ms after last violent signal)
            self._interaction_stability_timer.start(500)

    def _restore_interaction_stability(self):
        """Timer callback to restore high-res after interaction ends (Debounce)."""
        # Reset violent flag if it was set
        if self._is_interaction_violent:
            self._is_interaction_violent = False
            Logger.info("[CanvasView] Interaction stability mode DISABLED (High-res unlocked)")
            
            # Restore rendering quality based on settings
            use_aa = True
            if self.perf_monitor and hasattr(self.perf_monitor, 'use_antialiasing'):
                use_aa = self.perf_monitor.use_antialiasing
            
            self.setRenderHint(QPainter.RenderHint.Antialiasing, use_aa)
            self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            
        # Ensure we are not currently interacting
        is_mouse_pressed = QApplication.mouseButtons() != Qt.MouseButton.NoButton
        
        if not self._is_zooming_smoothly and not is_mouse_pressed:
            # Check if we are still within the debounce period if triggered by something else
            # But the timer itself is the debounce.
            self._disable_low_res_proxy()
            self.viewport().update()
        else:
            # If still interacting (e.g. mouse still down or zoom active), 
            # postpone high-res restoration.
            self._interaction_stability_timer.start(300)

    def on_scene_selection_changed(self):
        """Handle selection from Scene (Mouse Click) -> Manager."""
        if not self.roi_manager or self._is_updating_from_manager:
            return
            
        if getattr(self, '_ignore_background_click', False):
             if not self.scene().selectedItems():
                 return
            
        self._is_updating_from_manager = True
        try:
            selected_items = self.scene().selectedItems()
            
            if not selected_items:
                self.roi_manager.set_selection(None, clear_others=True)
                return

            def resolve_target_item(item):
                cur = item
                while cur and not isinstance(cur, UnifiedGraphicsItem):
                    cur = cur.parentItem()
                return cur

            selected_roi_ids = []
            processed_items = set()

            for it in selected_items:
                target = resolve_target_item(it)
                if target and target not in processed_items:
                    processed_items.add(target)
                    if isinstance(target, UnifiedGraphicsItem):
                        selected_roi_ids.append(target.roi_id)

            self.roi_manager.set_selected_ids(selected_roi_ids)

        except Exception as e:
            Logger.error(f"[CanvasView] Selection Sync Failed: {e}", exc_info=True)
        finally:
            self._is_updating_from_manager = False

    def select_annotation(self, ann_id):
        """
        Selects an ROI by ID (Unified name).
        """
        if not ann_id:
            self.scene().clearSelection()
            return
            
        if ann_id in self._roi_items:
            item = self._roi_items[ann_id]
            if not item.isSelected():
                self._is_updating_from_manager = True 
                try:
                    item.setSelected(True)
                finally:
                    self._is_updating_from_manager = False
            item.ensureVisible(item.boundingRect())

    # --- Drag & Drop, Paint, Zoom events (Mostly standard) ---
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            has_valid_image = False
            valid_exts = ('.tif', '.tiff', '.png', '.jpg', '.jpeg', '.bmp')
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith(valid_exts):
                    has_valid_image = True
                    break
            if has_valid_image:
                event.acceptProposedAction()
                self._update_quicklook(event)
                
                # Show drop hint
                self.drop_hint.show()
                self._update_drop_hint_pos()
                return
        event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._update_quicklook(event)
            self._update_drop_hint_pos()

    def dragLeaveEvent(self, event):
        self.preview_label.hide()
        self.drop_hint.hide()
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        self.drop_hint.hide()
        self.preview_label.hide()
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls:
                file_path = urls[0].toLocalFile()
                if file_path.lower().endswith(('.tif', '.tiff', '.png', '.jpg', '.jpeg')):
                    self.file_dropped.emit(file_path, self.active_channel_index)
                    event.acceptProposedAction()
                    return
        super().dropEvent(event)

    def _update_drop_hint_pos(self):
        """Centers the drop hint in the viewport."""
        self.drop_hint.adjustSize()
        x = (self.viewport().width() - self.drop_hint.width()) // 2
        y = (self.viewport().height() - self.drop_hint.height()) // 2
        self.drop_hint.move(x, y)

    def _update_quicklook(self, event):
        urls = event.mimeData().urls()
        if not urls: return
        file_path = urls[0].toLocalFile()
        if not file_path: return
        pos = event.position().toPoint()
        
        if self.preview_label.isHidden() or getattr(self, '_current_preview_path', None) != file_path:
             self._load_quicklook_image(file_path)
             self._current_preview_path = file_path
        
        global_pos = self.mapToGlobal(pos)
        self.preview_label.move(global_pos + QPoint(20, 20))
        self.preview_label.show()

    def _load_quicklook_image(self, path):
        try:
            if not path.lower().endswith(('.tif', '.tiff', '.png', '.jpg', '.jpeg')): return
            img_stream = np.fromfile(path, dtype=np.uint8)
            img = cv2.imdecode(img_stream, cv2.IMREAD_UNCHANGED)
            if img is None: return
            if img.ndim == 3 and img.shape[2] > 4: img = np.max(img, axis=2)
            if img.dtype != np.uint8:
                min_val, max_val = np.min(img), np.max(img)
                if max_val > min_val: img = ((img - min_val) / (max_val - min_val) * 255).astype(np.uint8)
                else: img = np.zeros_like(img, dtype=np.uint8)
            h, w = img.shape[:2]
            scale = min(200/w, 200/h)
            new_w, new_h = int(w*scale), int(h*scale)
            img_small = cv2.resize(img, (new_w, new_h))
            
            # Explicit QImage creation to avoid qimage2ndarray dependency
            if not img_small.flags['C_CONTIGUOUS']:
                img_small = np.ascontiguousarray(img_small)
            
            h_s, w_s = img_small.shape[:2]
            ch_s = 1 if img_small.ndim == 2 else img_small.shape[2]
            
            if ch_s == 3:
                qimg = QImage(img_small.data, w_s, h_s, w_s * 3, QImage.Format.Format_RGB888)
            elif ch_s == 4:
                qimg = QImage(img_small.data, w_s, h_s, w_s * 4, QImage.Format.Format_RGBA8888)
            else:
                qimg = QImage(img_small.data, w_s, h_s, w_s, QImage.Format.Format_Grayscale8)
                
            pixmap = QPixmap.fromImage(qimg)
            self.preview_label.setPixmap(pixmap)
            self.preview_label.resize(pixmap.size())
        except Exception as e:
            Logger.warning(f"[CanvasView] Quicklook preview generation failed: {e}")

    def update_render_quality(self, high_perf_mode):
        antialiasing = not high_perf_mode
        self.setRenderHint(QPainter.RenderHint.Antialiasing, antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, antialiasing)
        if high_perf_mode:
            self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.BoundingRectViewportUpdate)
            self.setOptimizationFlag(QGraphicsView.OptimizationFlag.DontAdjustForAntialiasing, True)
        else:
            self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.SmartViewportUpdate)
            self.setOptimizationFlag(QGraphicsView.OptimizationFlag.DontAdjustForAntialiasing, False)
        self.viewport().update()

    def paintEvent(self, event):
        t0 = time.time()
        super().paintEvent(event)
        
        if self.is_selected or self.label_text or self.flash_active:
            painter = QPainter()
            if not painter.begin(self.viewport()): return
            try:
                if self.perf_monitor.use_antialiasing: painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                if self.flash_active:
                    rect = self.viewport().rect().adjusted(2, 2, -3, -3)
                    pen = QPen(QColor("#00FF00"), 4) 
                    pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
                    painter.setPen(pen)
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawRect(rect)
                
                if self.is_selected and not self.flash_active:
                    rect = self.viewport().rect().adjusted(1, 1, -2, -2)
                    palette = QApplication.palette()
                    highlight_color = palette.color(QPalette.ColorRole.Highlight)
                    pen = QPen(highlight_color, 3)
                    pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
                    painter.setPen(pen)
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawRect(rect)
                
                if self.label_text:
                    rect = self.get_label_rect()
                    font = self.font()
                    font.setBold(True)
                    font_size = 12
                    # Ensure font_size is at least 1 to avoid QFont warning
                    if font_size <= 0:
                        font_size = 12
                    font.setPointSize(font_size)
                    painter.setFont(font)
                    palette = QApplication.palette()
                    if self.is_selected:
                        bg_color = palette.color(QPalette.ColorRole.Highlight)
                        bg_color.setAlpha(220)
                    else:
                        bg_color = QColor(0, 0, 0, 150)
                    painter.setBrush(QBrush(bg_color))
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.drawRoundedRect(rect, 4, 4)
                    painter.setPen(palette.color(QPalette.ColorRole.HighlightedText) if self.is_selected else QColor(255, 255, 255))
                    painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.label_text)
                    if self.is_selected:
                        pen = QPen(palette.color(QPalette.ColorRole.WindowText), 1)
                        painter.setPen(pen)
                        painter.setBrush(Qt.BrushStyle.NoBrush)
                        painter.drawRoundedRect(rect, 4, 4)
                
                if self.pixmap_item.pixmap().isNull() or self.pixmap_item.pixmap().width() <= 1:
                    hint = "Drop Image Here"
                    cx, cy = self.width() // 2, self.height() // 2
                    hint_rect = QRectF(cx - 100, cy - 20, 200, 40)
                    painter.setPen(QColor(200, 200, 200))
                    painter.drawText(hint_rect, Qt.AlignmentFlag.AlignCenter, hint)
            except Exception: pass
            finally: painter.end()

        dt = (time.time() - t0) * 1000
        self.perf_monitor.report_render_time(dt)

    def wheelEvent(self, event):
        if not self._wheel_enabled:
            # If wheel is disabled, ignore and let it bubble up to parent (e.g. FilmstripWidget)
            event.ignore()
            return

        num_degrees = event.angleDelta().y() / 8
        num_steps = num_degrees / 15
        impulse = num_steps * 0.05 
        
        if not self._is_zooming_smoothly:
            self._is_zooming_smoothly = True
            self._zoom_anchor_viewport = event.position().toPoint()
            self._zoom_anchor_scene = self.mapToScene(self._zoom_anchor_viewport)
            self._current_zoom = self.transform().m11()
            self._target_zoom = self._current_zoom
            self._zoom_velocity = 0.0
            self._zoom_timer.start()
        else:
            new_pos = event.position().toPoint()
            if (new_pos - self._zoom_anchor_viewport).manhattanLength() > 5:
                self._zoom_anchor_viewport = new_pos
                self._zoom_anchor_scene = self.mapToScene(new_pos)

        self._zoom_velocity += impulse
        
        # PERFORMANCE: Report interaction speed to detect "violent" zooming
        self.perf_monitor.report_interaction_speed(abs(self._zoom_velocity))
        
        event.accept()

    def _process_zoom_animation(self):
        if not self._is_zooming_smoothly:
            self._zoom_timer.stop()
            self._disable_low_res_proxy()
            return

        if abs(self._zoom_velocity) > 0.005:
            # PERFORMANCE: Enable low-res proxy during zoom
            self._enable_low_res_proxy()
            
            if self.pixmap_item.transformationMode() != Qt.TransformationMode.FastTransformation:
                self.pixmap_item.setTransformationMode(Qt.TransformationMode.FastTransformation)
                if not self.perf_monitor.is_low_quality:
                    self.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        
        self._target_zoom *= (1.0 + self._zoom_velocity)
        
        # --- Snap to Fit Logic (Magnetic Suction) ---
        snap_scales = self._get_snap_scales()
        
        # USER REQUEST: Prevent flickering by picking ONLY the closest snap point
        best_snap = None
        min_dist = float('inf')
        
        for snap_scale, label in snap_scales:
            ratio = self._target_zoom / snap_scale
            # USER REQUEST: Reduce detection range (4% -> 2%) to prevent accidental snaps
            # and prevent "return to original size" issues during fast zooming.
            if 0.98 <= ratio <= 1.02:
                dist = abs(self._target_zoom - snap_scale)
                if dist < min_dist:
                    min_dist = dist
                    best_snap = (snap_scale, label, ratio)
        
        if best_snap:
            snap_scale, label, ratio = best_snap
            
            # 1. "Magnetic Braking": Strong viscous drag
            # REDUCED damping (0.60 -> 0.80) to make passing through easier
            self._zoom_velocity *= 0.80

            # 2. "Smart Suction": 
            # - TIGHTENED velocity threshold (0.35 -> 0.15) so fast zooms skip snapping
            # - TIGHTENED "close enough" range (2% -> 1%)
            velocity_ok = abs(self._zoom_velocity) < 0.15
            close_enough = 0.99 <= ratio <= 1.01
            
            if velocity_ok or close_enough:
                # Suction force (REDUCED: 0.40 -> 0.20) for gentler pull
                suction_force = (snap_scale - self._target_zoom) * 0.20
                self._target_zoom += suction_force
                
                # Hard Snap (Lock)
                # TIGHTENED lock tolerance (0.5% -> 0.2%)
                if 0.998 <= ratio <= 1.002: 
                    if not self._is_snapped:
                        Logger.debug(f"[CanvasView:{self.view_id}] SNAPPED to {label} at {snap_scale:.4f}")
                    self._target_zoom = snap_scale
                    self._trigger_snap_feedback(snap_scale, label)
                    self._zoom_velocity = 0.0
                else:
                    # Braking when pulling in (0.50 -> 0.60)
                    self._zoom_velocity *= 0.60

        self._zoom_velocity *= self.ZOOM_DAMPING
        if abs(self._zoom_velocity) < 0.0005:
            self._zoom_velocity = 0.0

        if self._target_zoom < self.ZOOM_MIN:
            self._target_zoom += (self.ZOOM_MIN - self._target_zoom) * self.ZOOM_SPRING
            self._zoom_velocity *= 0.5 
        elif self._target_zoom > self.ZOOM_MAX:
            self._target_zoom += (self.ZOOM_MAX - self._target_zoom) * self.ZOOM_SPRING
            self._zoom_velocity *= 0.5

        diff = self._target_zoom - self._current_zoom
        if abs(diff) < 0.0001 and self._zoom_velocity == 0.0:
            self._current_zoom = self._target_zoom
            if self.ZOOM_MIN <= self._target_zoom <= self.ZOOM_MAX:
                self._is_zooming_smoothly = False
                self._zoom_timer.stop()
                
                # USER REQUEST: Debounce high-res loading (200-300ms)
                # Instead of immediate _disable_low_res_proxy, start the timer
                self._interaction_stability_timer.start(300)
                
                if self.pixmap_item.transformationMode() != Qt.TransformationMode.SmoothTransformation:
                    self.pixmap_item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
                    if not self.perf_monitor.is_low_quality:
                        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                self.viewport().update()
        else:
            follow_speed = 0.25 if not self._is_snapped else 0.15
            self._current_zoom += diff * follow_speed

        current_scale = self.transform().m11()
        if current_scale == 0: current_scale = 1.0
        scale_factor = self._current_zoom / current_scale
        
        item_scale = self.pixmap_item.transform().m11()
        total_scale = self._current_zoom * item_scale
        should_smooth = total_scale < 1.0
        is_smooth = bool(self.renderHints() & QPainter.RenderHint.SmoothPixmapTransform)
        if should_smooth != is_smooth:
            self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, should_smooth)

        if abs(scale_factor - 1.0) < 0.0001:
            return

        old_anchor = self.transformationAnchor()
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.scale(scale_factor, scale_factor)
        
        new_viewport_pos = self.mapFromScene(self._zoom_anchor_scene)
        delta = new_viewport_pos - self._zoom_anchor_viewport
        self.horizontalScrollBar().setValue(int(self.horizontalScrollBar().value() + delta.x()))
        self.verticalScrollBar().setValue(int(self.verticalScrollBar().value() + delta.y()))
        self.setTransformationAnchor(old_anchor)
        
        t = self.transform()
        self.zoom_changed.emit(t.m11(), t.m22(), self._zoom_anchor_scene)
        self.viewport().update()

    def _get_snap_scales(self):
        """
        Calculates important zoom scales for snapping (Fit, Fit Width, Fit Height).
        USER REQUEST: Prevent flickering by merging close fit modes and using a Mutex.
        """
        self._snap_scale_mutex.lock()
        try:
            if not self.pixmap_item.pixmap() or self.pixmap_item.pixmap().isNull(): return []
            
            # STABILITY OPTIMIZATION: Use widget size explicitly to ensure we fit to the VISIBLE window.
            # maximumViewportSize() can be misleading in some layout contexts.
            # We want the size of the area available for the view, excluding borders.
            view_size = self.size()
            fw = self.frameWidth()
            available_w = max(10, view_size.width() - 2 * fw)
            available_h = max(10, view_size.height() - 2 * fw)
            
            # USER FIX: Use sceneRect() instead of pixmap().rect().
            # sceneRect() represents the logical size of the image in the view (e.g. 2048x2048),
            # regardless of whether the underlying pixmap is downsampled for performance.
            if not self.scene(): return []
            scene_rect = self.scene().sceneRect()
            if scene_rect.width() <= 0 or scene_rect.height() <= 0: return []
            
            scale_w = available_w / scene_rect.width()
            scale_h = available_h / scene_rect.height()
            fit_scale = min(scale_w, scale_h)
            
            # USER REQUEST: Prevent flickering by merging close fit modes (Threshold 0.05).
            # If the scales are very close, only return ONE "Fit" signal to avoid jitter.
            rel_diff = abs(scale_w - scale_h) / max(1e-5, max(scale_w, scale_h))
            
            # Log for debugging flickering (Terminal #632-1008 context)
            Logger.debug(f"[CanvasView:{self.view_id}] Snap calculation: view={available_w}x{available_h}, scale_w={scale_w:.4f}, scale_h={scale_h:.4f}, rel_diff={rel_diff:.4f}")
            
            if rel_diff < 0.05: 
                # When they are close, only return the one that ensures the whole image fits.
                return [(fit_scale, "Fit")]
                
            # If they are distinct, return all three, but ensure labels are accurate.
            scales = []
            # Only add specific labels if they are significantly different from the master "Fit"
            if abs(scale_w - fit_scale) > 0.001:
                scales.append((scale_w, "Fit Width"))
            if abs(scale_h - fit_scale) > 0.001:
                scales.append((scale_h, "Fit Height"))
            
            # Always include the universal "Fit"
            scales.append((fit_scale, "Fit"))
            
            # Sort by scale value for consistent snapping behavior
            scales.sort(key=lambda x: x[0])
            return scales
        finally:
            self._snap_scale_mutex.unlock()

    def _trigger_snap_feedback(self, scale, label):
        if abs(self._last_snap_scale - scale) < 0.001 and self._is_snapped: return
        self._last_snap_scale = scale
        self._is_snapped = True
        self._snap_feedback_timer.start(1000)
        self._glow_active = True
        self._glow_timer.start(500)
        
        # USER REQUEST: Remove QToolTip prompts (text indicator), only keep border glow
        self._size_indicator_visible = False
        self._size_indicator_text = ""
        self._size_indicator_opacity = 0.0
        self._indicator_fade_timer.stop()
        
        self.viewport().update()

    def _update_indicator_fade(self):
        if self._size_indicator_opacity > 0:
            self._size_indicator_opacity -= 0.05
            if self._size_indicator_opacity <= 0:
                self._size_indicator_opacity = 0
                self._size_indicator_visible = False
                self._indicator_fade_timer.stop()
            self.viewport().update()

    def _stop_snap_feedback(self): self._is_snapped = False
    def _stop_glow(self): self._glow_active = False; self.viewport().update()

    def drawForeground(self, painter, rect):
        super().drawForeground(painter, rect)
        if self._glow_active:
            painter.save()
            painter.setWorldMatrixEnabled(False)
            view_rect = self.viewport().rect()
            glow_color = QApplication.palette().color(QPalette.ColorRole.Highlight)
            glow_color.setAlpha(100)
            pen = QPen(glow_color, 10)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(view_rect.adjusted(5, 5, -5, -5))
            painter.restore()
        if self._size_indicator_visible and self._size_indicator_opacity > 0:
            painter.save()
            painter.setWorldMatrixEnabled(False)
            view_rect = self.viewport().rect()
            font = QFont("Segoe UI", 12, QFont.Weight.Bold)
            painter.setFont(font)
            metrics = QFontMetrics(font)
            text_rect = metrics.boundingRect(self._size_indicator_text).adjusted(-10, -5, 10, 5)
            text_rect.moveCenter(view_rect.center())
            text_rect.moveBottom(view_rect.bottom() - 100)
            bg_color = QColor(0, 0, 0, int(180 * self._size_indicator_opacity))
            painter.setBrush(bg_color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(text_rect, 5, 5)
            text_color = QColor(255, 255, 255, int(255 * self._size_indicator_opacity))
            painter.setPen(text_color)
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, self._size_indicator_text)
            painter.restore()

    def stop_flash(self):
        self.flash_active = False
        self.viewport().update()

    def start_flash(self, duration_ms: int = 250):
        self.flash_active = True
        self.viewport().update()
        QTimer.singleShot(max(0, int(duration_ms)), self.stop_flash)

    def fitInView(self, *args, **kwargs):
        v_rect = self.viewport().rect()
        Logger.debug(f"[CanvasView:{self.view_id}] fitInView started. Viewport size: {v_rect.width()}x{v_rect.height()}")
        super().fitInView(*args, **kwargs)
        t = self.transform()
        Logger.debug(f"[CanvasView:{self.view_id}] fitInView finished, scale={t.m11():.4f}")
        self.zoom_changed.emit(t.m11(), t.m22(), QPointF())

    def setTransform(self, *args, **kwargs):
        # Logger.debug(f"[CanvasView:{self.view_id}] setTransform")
        super().setTransform(*args, **kwargs)

    def centerOn(self, *args, **kwargs):
        # Logger.debug(f"[CanvasView:{self.view_id}] centerOn")
        super().centerOn(*args, **kwargs)
