from PySide6.QtCore import QObject
from PySide6.QtWidgets import QGraphicsView

class SyncManager(QObject):
    """
    Manages synchronization of panning and zooming across multiple QGraphicsView instances.
    Prevents infinite recursion during signal propagation.
    """
    def __init__(self):
        super().__init__()
        self.views = []
        self._is_syncing = False
        self._enabled = True

    def set_enabled(self, enabled: bool):
        """Enable or disable synchronization globally."""
        self._enabled = enabled

    def add_view(self, view: QGraphicsView):
        """Register a view to be synchronized."""
        if view in self.views:
            return
            
        self.views.append(view)
        
        # Connect ScrollBars (Panning)
        view.horizontalScrollBar().valueChanged.connect(
            lambda val: self._sync_scroll(view, 'h', val)
        )
        view.verticalScrollBar().valueChanged.connect(
            lambda val: self._sync_scroll(view, 'v', val)
        )
        
        # Connect Zoom (Custom Signal from CanvasView)
        if hasattr(view, 'zoom_changed'):
            view.zoom_changed.connect(
                lambda sx, sy, focus: self._sync_zoom(view, sx, sy, focus)
            )
            
        # Connect Ruler Sync (Custom Signal from CanvasView)
        if hasattr(view, 'ruler_moved'):
            view.ruler_moved.connect(
                lambda pos: self.sync_ruler(view, pos)
            )

    def remove_view(self, view: QGraphicsView):
        if view in self.views:
            self.views.remove(view)
            # Disconnects are automatic when object is deleted, 
            # but explicit disconnect might be needed if view persists.

    def _sync_scroll(self, source_view, orientation, value):
        """
        Synchronizes scene center across views.
        This is more robust than syncing scrollbar values directly, 
        especially when viewports have different sizes.
        """
        if self._is_syncing or not self._enabled:
            return

        self._is_syncing = True
        try:
            # Get the center of the source view in scene coordinates
            center = source_view.mapToScene(source_view.viewport().rect().center())
            
            for view in self.views:
                if view is source_view:
                    continue
                
                # Center the other view on the same scene point
                view.centerOn(center)
        finally:
            self._is_syncing = False

    def _sync_zoom(self, source_view, scale_x, scale_y, focus_point):
        """
        Synchronizes zoom level (Transform) and focus point position.
        Ensures that the same scene point remains at the same relative viewport position 
        across all views, even if they have slightly different sizes.
        """
        if self._is_syncing or not self._enabled:
            return

        self._is_syncing = True
        try:
            target_transform = source_view.transform()
            
            # 1. Get where the focus point is in the SOURCE viewport (relative 0.0 to 1.0)
            view_rect = source_view.viewport().rect()
            if view_rect.width() == 0 or view_rect.height() == 0:
                return # Avoid div by zero
                
            view_pos = source_view.mapFromScene(focus_point)
            rel_x = view_pos.x() / view_rect.width()
            rel_y = view_pos.y() / view_rect.height()
            
            for view in self.views:
                if view is source_view:
                    continue
                
                # 2. Apply the same zoom/transform
                view.setTransform(target_transform)
                
                # 3. Align focus_point to the same relative position in this view
                target_view_rect = view.viewport().rect()
                target_px = rel_x * target_view_rect.width()
                target_py = rel_y * target_view_rect.height()
                
                # Center view on focus_point first (puts it at viewport center)
                view.centerOn(focus_point)
                
                # Calculate how much we need to shift from viewport center to target_px/py
                # Note: centerOn() might not be perfect if we are at the edges of the scene
                # So we verify the actual position after centerOn
                new_view_pos = view.mapFromScene(focus_point)
                dx = target_px - new_view_pos.x()
                dy = target_py - new_view_pos.y()
                
                # Adjust scrollbars to finalize alignment
                h_bar = view.horizontalScrollBar()
                v_bar = view.verticalScrollBar()
                h_bar.setValue(int(h_bar.value() - dx))
                v_bar.setValue(int(v_bar.value() - dy))
                
        finally:
            self._is_syncing = False

    def sync_ruler(self, source_view, pos):
        """
        Synchronizes ruler position across views.
        pos: QPointF in scene coordinates (relative to the item's initial position 0,0, 
             so this is actually the item's position in the scene).
        """
        if self._is_syncing or not self._enabled:
            return

        self._is_syncing = True
        try:
            for view in self.views:
                if view is source_view:
                    continue
                
                if hasattr(view, 'update_ruler_position'):
                    view.update_ruler_position(pos)
        finally:
            self._is_syncing = False
