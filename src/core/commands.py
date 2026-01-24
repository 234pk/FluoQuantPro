import copy
from PySide6.QtGui import QUndoCommand
import numpy as np
from src.core.language_manager import tr
from src.core.analysis import calculate_channel_stats

class AddManualSceneCommand(QUndoCommand):
    def __init__(self, model, name, channel_templates):
        super().__init__("Add Empty Sample")
        self.model = model
        self.name = name
        self.channel_templates = channel_templates

    def redo(self):
        self.model._add_manual_scene_internal(self.name, self.channel_templates)

    def undo(self):
        self.model._remove_scene_internal(self.name)


class RemoveSceneCommand(QUndoCommand):
    def __init__(self, model, scene_id):
        super().__init__("Remove Sample")
        self.model = model
        self.scene_id = scene_id
        self.scene_data = None
        self.index = -1

    def redo(self):
        # Store data before removing for undo
        scene = self.model.get_scene(self.scene_id)
        if scene:
            self.scene_data = copy.deepcopy(scene)
            self.index = self.model.scenes.index(scene)
            self.model._remove_scene_internal(self.scene_id)

    def undo(self):
        if self.scene_data:
            self.model.scenes.insert(self.index, self.scene_data)
            self.model._scene_map[self.scene_data.id] = self.scene_data
            self.model.is_dirty = True
            self.model.project_changed.emit()


class BatchRemoveScenesCommand(QUndoCommand):
    def __init__(self, model, scene_ids):
        super().__init__(f"Remove {len(scene_ids)} Samples")
        self.model = model
        self.scene_ids = scene_ids
        self.scenes_data = [] # List of (index, data)

    def redo(self):
        self.scenes_data = []
        # Process in reverse order to maintain indices logic during undo if possible,
        # but insertion order matters.
        # We'll just store (index, data) and restore by sorting indices.
        
        # Sort ids by current index to be safe?
        # Actually, we just need to capture them.
        for sid in self.scene_ids:
            scene = self.model.get_scene(sid)
            if scene:
                idx = self.model.scenes.index(scene)
                self.scenes_data.append((idx, copy.deepcopy(scene)))
        
        # Sort by index descending to remove without shifting problems? 
        # Actually _remove_scene_internal searches by ID, so order doesn't strictly matter for removal,
        # but for restoration we want to put them back in right places.
        
        for sid in self.scene_ids:
            self.model._remove_scene_internal(sid)

    def undo(self):
        # Restore in order of index (ascending)
        sorted_data = sorted(self.scenes_data, key=lambda x: x[0])
        for idx, data in sorted_data:
            self.model.scenes.insert(idx, data)
            self.model._scene_map[data.id] = data
            
        self.model.is_dirty = True
        self.model.project_changed.emit()


class RenameSceneCommand(QUndoCommand):
    def __init__(self, model, old_id, new_name):
        super().__init__("Rename Sample")
        self.model = model
        self.old_id = old_id
        self.new_name = new_name

    def redo(self):
        self.model._rename_scene_internal(self.old_id, self.new_name)

    def undo(self):
        self.model._rename_scene_internal(self.new_name, self.old_id)


class UpdateChannelPathCommand(QUndoCommand):
    def __init__(self, model, scene_id, ch_index, old_path, new_path):
        super().__init__("Update Channel")
        self.model = model
        self.scene_id = scene_id
        self.ch_index = ch_index
        self.old_path = old_path
        self.new_path = new_path

    def redo(self):
        self.model._update_channel_path_internal(self.scene_id, self.ch_index, self.new_path)

    def undo(self):
        self.model._update_channel_path_internal(self.scene_id, self.ch_index, self.old_path)


class AddFilesCommand(QUndoCommand):
    def __init__(self, model, file_paths):
        super().__init__("Add Files")
        self.model = model
        self.file_paths = file_paths
        self.added_scenes = [] # List of IDs

    def redo(self):
        # We need to track which scenes were added.
        # This is tricky because _add_files_internal does logic.
        # We'll implement a simplified version or capture state.
        # For simplicity, we'll assume _add_files_internal works and we can't easily undo 
        # the specific logic without refactoring _add_files_internal to return added IDs.
        # So let's refactor the model method to be more command-friendly or just snapshot?
        # Snapshot is too heavy.
        
        # Let's rely on the fact that we can calc what will be added? No.
        # Let's Modify _add_files_internal to return added IDs? 
        # Or, we can just capture the list of scene IDs before and after.
        
        ids_before = set(self.model._scene_map.keys())
        self.model._add_files_internal(self.file_paths)
        ids_after = set(self.model._scene_map.keys())
        self.added_scenes = list(ids_after - ids_before)

    def undo(self):
        for sid in self.added_scenes:
            self.model._remove_scene_internal(sid)


class AddFilesToPoolCommand(QUndoCommand):
    def __init__(self, model, file_paths):
        super().__init__("Add to Pool")
        self.model = model
        self.file_paths = file_paths
        self.added_files = []

    def redo(self):
        before = set(self.model.pool_files)
        self.model._add_to_pool_internal(self.file_paths)
        after = set(self.model.pool_files)
        self.added_files = list(after - before)

    def undo(self):
        for f in self.added_files:
            self.model._remove_from_pool_internal(f)


class RemoveFromPoolCommand(QUndoCommand):
    def __init__(self, model, file_path):
        super().__init__("Remove from Pool")
        self.model = model
        self.file_path = file_path
        self.index = -1

    def redo(self):
        if self.file_path in self.model.pool_files:
            self.index = self.model.pool_files.index(self.file_path)
            self.model._remove_from_pool_internal(self.file_path)

    def undo(self):
        if self.index >= 0:
            self.model.pool_files.insert(self.index, self.file_path)
            self.model.is_dirty = True
            self.model.project_changed.emit()


class BatchRemoveFromPoolCommand(QUndoCommand):
    def __init__(self, model, file_paths):
        super().__init__(f"Remove {len(file_paths)} files from Pool")
        self.model = model
        self.file_paths = file_paths
        self.indices = [] # (path, index)

    def redo(self):
        self.indices = []
        # Sort to ensure we can restore in correct order (though set and pool_files might change)
        # Actually, we should store indices from the end to the beginning to make it easier if we were removing in redo,
        # but here we are removing individual items.
        
        # Block signals for performance during batch redo
        self.model.blockSignals(True)
        try:
            for path in self.file_paths:
                if path in self.model.pool_files:
                    idx = self.model.pool_files.index(path)
                    self.indices.append((path, idx))
                    self.model._remove_from_pool_internal(path)
        finally:
            self.model.blockSignals(False)
            self.model.project_changed.emit()

    def undo(self):
        # Restore in reverse order of indices to maintain original order
        self.model.blockSignals(True)
        try:
            # Sort by original index to restore correctly
            sorted_indices = sorted(self.indices, key=lambda x: x[1])
            for path, idx in sorted_indices:
                if path not in self.model.pool_files:
                    self.model.pool_files.insert(idx, path)
        finally:
            self.model.blockSignals(False)
            self.model.is_dirty = True
            self.model.project_changed.emit()


class AddChannelToSceneCommand(QUndoCommand):
    def __init__(self, model, scene_id, file_path, channel_type, color):
        super().__init__("Add Channel to Sample")
        self.model = model
        self.scene_id = scene_id
        self.file_path = file_path
        self.channel_type = channel_type
        self.color = color
        self.scene_data_before = copy.deepcopy(model.get_scene(scene_id))

    def redo(self):
        self.model._add_channel_to_scene_internal(self.scene_id, self.file_path, self.channel_type, self.color)

    def undo(self):
        scene = self.model.get_scene(self.scene_id)
        if scene and self.scene_data_before:
            scene.channels = copy.deepcopy(self.scene_data_before.channels)
            self.model.project_changed.emit()


class SetProjectTemplateCommand(QUndoCommand):
    def __init__(self, model, template):
        super().__init__("Set Project Template")
        self.model = model
        self.template = template
        self.old_template = copy.deepcopy(model.project_channel_template)

    def redo(self):
        self.model._set_project_template_internal(self.template)

    def undo(self):
        self.model._set_project_template_internal(self.old_template)


class AddEmptyChannelCommand(QUndoCommand):
    def __init__(self, model, scene_id):
        super().__init__("Add Empty Channel")
        self.model = model
        self.scene_id = scene_id
        
    def redo(self):
        self.model._add_empty_channel_internal(self.scene_id)
        
    def undo(self):
        # Remove the last channel
        scene = self.model.get_scene(self.scene_id)
        if scene and scene.channels:
            scene.channels.pop()
            self.model.is_dirty = True
            self.model.project_changed.emit()


class UpdateChannelColorCommand(QUndoCommand):
    def __init__(self, model, scene_id, ch_index, old_color, new_color):
        super().__init__("Change Channel Color")
        self.model = model
        self.scene_id = scene_id
        self.ch_index = ch_index
        self.old_color = old_color
        self.new_color = new_color

    def redo(self):
        self.model._update_channel_color_internal(self.scene_id, self.ch_index, self.new_color)

    def undo(self):
        self.model._update_channel_color_internal(self.scene_id, self.ch_index, self.old_color)


class RemoveChannelCommand(QUndoCommand):
    def __init__(self, model, scene_id, ch_index):
        super().__init__("Remove Channel")
        self.model = model
        self.scene_id = scene_id
        self.ch_index = ch_index
        self.ch_def = None

    def redo(self):
        scene = self.model.get_scene(self.scene_id)
        if scene and 0 <= self.ch_index < len(scene.channels):
            self.ch_def = copy.deepcopy(scene.channels[self.ch_index])
            self.model._remove_channel_internal(self.scene_id, self.ch_index)

    def undo(self):
        if self.ch_def:
            self.model._insert_channel_internal(self.scene_id, self.ch_index, self.ch_def)


class EnhanceCommand(QUndoCommand):
    def __init__(self, session, channel_index, old_params, new_params, old_percents, new_percents):
        super().__init__("Adjust Enhancement")
        self.session = session
        self.channel_index = channel_index
        self.old_params = old_params
        self.new_params = new_params
        self.old_percents = old_percents
        self.new_percents = new_percents

    def redo(self):
        ch = self.session.get_channel(self.channel_index)
        if ch:
            ch.display_settings.enhance_params = self.new_params
            ch.display_settings.enhance_percents = self.new_percents
            self.session.data_changed.emit()

    def undo(self):
        ch = self.session.get_channel(self.channel_index)
        if ch:
            ch.display_settings.enhance_params = self.old_params
            ch.display_settings.enhance_percents = self.old_percents
            self.session.data_changed.emit()


class AdjustmentCommand(QUndoCommand):
    def __init__(self, session, channel_index, old_settings, new_settings):
        super().__init__("Adjust Display Settings")
        self.session = session
        self.channel_index = channel_index
        self.old_settings = old_settings
        self.new_settings = new_settings

    def redo(self):
        ch = self.session.get_channel(self.channel_index)
        if ch:
            ch.display_settings.min_val = self.new_settings['min']
            ch.display_settings.max_val = self.new_settings['max']
            ch.display_settings.gamma = self.new_settings['gamma']
            self.session.data_changed.emit()

    def undo(self):
        ch = self.session.get_channel(self.channel_index)
        if ch:
            ch.display_settings.min_val = self.old_settings['min']
            ch.display_settings.max_val = self.old_settings['max']
            ch.display_settings.gamma = self.old_settings['gamma']
            self.session.data_changed.emit()

class CropCommand(QUndoCommand):
    def __init__(self, session, rect):
        super().__init__(tr("Crop Image"))
        self.session = session
        self.rect = rect # (x, y, w, h)
        self.old_channels = [] # List of (index, data)
        self.new_channels = []
        
    def redo(self):
        # Capture state if first run
        if not self.old_channels:
            for i, ch in enumerate(self.session.channels):
                # Use .copy() instead of deepcopy for numpy arrays (faster and sufficient)
                self.old_channels.append((i, ch.raw_data.copy()))
        
        # Perform Crop
        x, y, w, h = self.rect
        
        for i, ch in enumerate(self.session.channels):
            # Crop raw data
            # Handle 2D or 3D
            if ch.raw_data.ndim == 2:
                cropped = ch.raw_data[y:y+h, x:x+w]
            elif ch.raw_data.ndim == 3:
                # Assuming (H, W, C) or (C, H, W)?
                # ImageChannel usually stores (H, W) or (H, W, C) for RGB?
                # Let's assume (H, W) for standard, but check.
                # If RGB (H, W, 3)
                if ch.raw_data.shape[2] in [3, 4]:
                     cropped = ch.raw_data[y:y+h, x:x+w, :]
                else:
                     # (Z, H, W) or (C, H, W)?
                     # Standard is (H, W) for analysis.
                     # If we have Z-stack, we might have flattened it.
                     # Let's try basic slicing
                     cropped = ch.raw_data[y:y+h, x:x+w]
            
            # Use update_data to correctly set private _raw_data and update shape/dtype
            ch.update_data(np.ascontiguousarray(cropped))
            ch.stats = calculate_channel_stats(cropped)
            
        self.session.data_changed.emit()
        
    def undo(self):
        # Restore old data
        for i, old_data in self.old_channels:
            if i < len(self.session.channels):
                ch = self.session.channels[i]
                # Use update_data to correctly restore raw data and properties
                ch.update_data(old_data)
                ch.stats = calculate_channel_stats(old_data)
                
        self.session.data_changed.emit()
