from PySide6.QtCore import QObject
from PySide6.QtWidgets import QGraphicsView
from src.core.logger import Logger

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
        if self._enabled != enabled:
            Logger.debug(f"[SyncManager] set_enabled: {enabled}")
        self._enabled = enabled

    def add_view(self, view: QGraphicsView):
        """Register a view to be synchronized."""
        if view in self.views:
            return
            
        Logger.debug(f"[SyncManager] Adding view: {getattr(view, 'view_id', 'Unknown')}")
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
            Logger.debug(f"[SyncManager] Removing view: {getattr(view, 'view_id', 'Unknown')}")
            self.views.remove(view)
            # Disconnects are automatic when object is deleted, 
            # but explicit disconnect might be needed if view persists.

    def _sync_scroll(self, source_view, orientation, value):
        """
        Synchronizes scene center across views.
        This is more robust than syncing scrollbar values directly, 
        especially when viewports have different sizes.
        """
        if not self._enabled:
            return
            
        if self._is_syncing:
            return

        self._is_syncing = True
        try:
            # Get the center of the source view in scene coordinates
            center = source_view.mapToScene(source_view.viewport().rect().center())
            Logger.debug(f"[SyncManager] _sync_scroll from {getattr(source_view, 'view_id', 'Unknown')} at {center}")
            
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
        if not self._enabled:
            return
            
        if self._is_syncing:
            return

        self._is_syncing = True
        try:
            target_transform = source_view.transform()
            Logger.debug(f"[SyncManager] _sync_zoom from {getattr(source_view, 'view_id', 'Unknown')} scale={target_transform.m11():.4f}")
            
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
                
                # Apply the same transform (zoom level)
                # IMPORTANT: Set NoAnchor to prevent view from jumping based on its internal anchor
                old_anchor = view.transformationAnchor()
                view.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
                try:
                    view.setTransform(target_transform)
                    
                    # Adjust position so focus point stays at same relative viewport position
                    # 1. Map focus point to new viewport coordinates with new zoom
                    new_view_pos = view.mapFromScene(focus_point)
                    
                    # 2. Calculate offset needed to put it at rel_x, rel_y
                    target_v_rect = view.viewport().rect()
                    target_v_pos_x = rel_x * target_v_rect.width()
                    target_v_pos_y = rel_y * target_v_rect.height()
                    
                    diff_x = new_view_pos.x() - target_v_pos_x
                    diff_y = new_view_pos.y() - target_v_pos_y
                    
                    # 3. Scroll to compensate
                    view.horizontalScrollBar().setValue(view.horizontalScrollBar().value() + int(diff_x))
                    view.verticalScrollBar().setValue(view.verticalScrollBar().value() + int(diff_y))
                finally:
                    view.setTransformationAnchor(old_anchor)
        finally:
            self._is_syncing = False

    def sync_ruler(self, source_view, pos):
        """Synchronizes ruler position across views."""
        if not self._enabled:
            return
            
        if self._is_syncing:
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
