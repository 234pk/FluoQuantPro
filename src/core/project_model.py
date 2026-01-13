import json
import os
import re
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Tuple, Union

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QUndoStack

@dataclass
class ChannelDef:
    """Definition of a single channel file within a scene."""
    path: str
    channel_type: str # DAPI, GFP, etc.
    color: str        # Hex color
    display_settings: dict = field(default_factory=dict) # Min, Max, Gamma

@dataclass
class SceneData:
    """Represents a single field of view (Scene) containing multiple channels."""
    id: str
    name: str
    channels: List[ChannelDef] = field(default_factory=list)
    status: str = "Pending" # Pending, Measured, etc.
    rois: List[dict] = field(default_factory=list) # Serialized ROIs
    annotations: List[dict] = field(default_factory=list) # Serialized GraphicAnnotations

    @classmethod
    def from_dict(cls, data: dict):
        channels = [ChannelDef(**ch) for ch in data.get("channels", [])]
        return cls(id=data["id"], 
                   name=data["name"], 
                   channels=channels, 
                   status=data.get("status", "Pending"),
                   rois=data.get("rois", []),
                   annotations=data.get("annotations", []))

class ProjectModel(QObject):
    """
    Manages a collection of Scenes (Samples).
    Handles smart grouping of files into scenes based on naming conventions.
    """
    project_changed = Signal()

    def __init__(self, undo_stack: Optional[QUndoStack] = None, root_path: str = None):
        super().__init__()
        self.root_path = root_path
        self.scenes: List[SceneData] = []
        self._scene_map: Dict[str, SceneData] = {} # id -> SceneData
        self.pool_files: List[str] = [] # List of all imported file paths
        self.pool_display_settings: Dict[str, dict] = {} # path -> display_settings dict
        self.undo_stack = undo_stack or QUndoStack(self)
        
        # Default Channel Configs (Keyword -> (Type, Color))
        self.channel_patterns = {
            "DAPI": ("DAPI", "#0000FF"),
            "HOECHST": ("DAPI", "#0000FF"),
            "GFP": ("GFP", "#00FF00"),
            "FITC": ("GFP", "#00FF00"),
            "RFP": ("RFP", "#FF0000"),
            "TRITC": ("RFP", "#FF0000"),
            "CY3": ("CY3", "#FF9900"), # Orange
            "CY5": ("CY5", "#FF00FF"), # Magenta (Standard pseudo-color for Far Red)
            "YFP": ("YFP", "#FFFF00"),
            # Generic fallbacks
            "CH1": ("Ch1", "#0000FF"),
            "CH2": ("Ch2", "#00FF00"),
            "CH3": ("Ch3", "#FF0000"),
            "CH4": ("Ch4", "#FF00FF"),
        }
        
        # Project-wide channel template
        # List of dicts: [{'name': 'DAPI', 'color': '#0000FF'}, ...]
        self.project_channel_template: List[Dict[str, str]] = []
        
        # Global Mode Configuration
        self.is_single_channel_mode: bool = False
        
        # Dirty flag to track unsaved changes
        self.is_dirty = False
        self.last_template_warnings: List[str] = []

    def _normalize_project_template(self, template: Optional[List[Dict]]) -> Tuple[List[Dict[str, str]], List[str]]:
        if not template:
            return [], []

        normalized: List[Dict[str, str]] = []
        errors: List[str] = []
        seen = set()

        for i, raw in enumerate(template):
            if not isinstance(raw, dict):
                errors.append(f"template[{i}] is not a dict")
                continue

            name = raw.get("name") or raw.get("channel_type") or raw.get("type") or raw.get("label")
            if not isinstance(name, str):
                errors.append(f"template[{i}].name is invalid")
                continue

            name = name.strip()
            if not name:
                errors.append(f"template[{i}].name is empty")
                continue

            key = name.upper()
            if key in seen:
                continue
            seen.add(key)

            color = raw.get("color") or raw.get("hex") or raw.get("colour")
            if not isinstance(color, str):
                color = ""
            color = color.strip()

            if not re.match(r"^#[0-9A-Fa-f]{6}$", color):
                fallback = None
                for k, (ctype, c) in self.channel_patterns.items():
                    if k == key or ctype.upper() == key:
                        fallback = c
                        break
                color = fallback or "#FFFFFF"

            normalized.append({"name": name, "color": color})

        return normalized, errors

    def get_scene_count(self) -> int:
        return len(self.scenes)

    def get_pool_count(self) -> int:
        return len(self.pool_files)

    def set_root_path(self, path: str):
        self.root_path = path
        if path:
            os.makedirs(os.path.join(path, "exports"), exist_ok=True)

    def get_export_path(self) -> str:
        """Returns the default export directory for this project."""
        if self.root_path:
            export_dir = os.path.join(self.root_path, "exports")
            os.makedirs(export_dir, exist_ok=True)
            return export_dir
        return os.getcwd()

    def update_channel_name(self, scene_id: str, ch_index: int, new_name: str):
        """Updates the name (type) of a specific channel."""
        if scene_id in self._scene_map:
            scene = self._scene_map[scene_id]
            if 0 <= ch_index < len(scene.channels):
                scene.channels[ch_index].channel_type = new_name
                self.is_dirty = True
                self.project_changed.emit()

    def save_scene_state(self, scene_id: str, rois: List[dict], channel_settings: List[dict], annotations: List[dict] = None):
        """Updates the in-memory scene data with current ROI and display settings."""
        if scene_id in self._scene_map:
            scene = self._scene_map[scene_id]
            scene.rois = rois
            if annotations is not None:
                scene.annotations = annotations
            
            # Update channel display settings
            for i, ch_def in enumerate(scene.channels):
                if i < len(channel_settings):
                    ch_def.display_settings = channel_settings[i]
            
            self.is_dirty = True

    def save_project(self):
        """
        Saves the current project state to project.fluo in root_path.
        Always saves what is currently in memory. 
        Filtering of what gets into memory should be handled by the caller.
        """
        if not self.root_path:
            return
            
        scenes_data = []
        for scene in self.scenes:
            s_dict = asdict(scene)
            scenes_data.append(s_dict)
            
        data = {
            "root_path": self.root_path,
            "pool_files": self.pool_files,
            "project_channel_template": self.project_channel_template,
            "scenes": scenes_data
        }
        
        config_path = os.path.join(self.root_path, "project.fluo")
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
            self.is_dirty = False
        except Exception as e:
            print(f"Error saving project: {e}")

    def load_project(self, path: str) -> bool:
        """Loads project state from a directory."""
        # Check for .fluo first, fallback to .json for compatibility
        config_path = os.path.join(path, "project.fluo")
        if not os.path.exists(config_path):
            config_path = os.path.join(path, "project.json")
            
        if not os.path.exists(config_path):
            return False
            
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            # Normalize paths for cross-platform compatibility (Windows <-> Mac/Linux)
            # 1. Update root_path
            raw_root = data.get("root_path", "")
            if raw_root:
                # If loading on Mac/Linux but path is Windows-style, or vice versa
                self.root_path = os.path.normpath(raw_root)
            else:
                self.root_path = path
                
            # 2. Update pool_files
            self.pool_files = [os.path.normpath(p) for p in data.get("pool_files", [])]
            
            # 3. Update Scenes and Channel paths
            self.scenes = []
            for s_data in data.get("scenes", []):
                # Normalize channel paths
                for ch in s_data.get("channels", []):
                    if ch.get("path"):
                        ch["path"] = os.path.normpath(ch["path"])
                
                scene = SceneData.from_dict(s_data)
                self.scenes.append(scene)
                self._scene_map[scene.id] = scene
                
            self.project_channel_template = data.get("project_channel_template", [])
            self.is_dirty = False
            return True
        except Exception as e:
            print(f"Error loading project: {e}")
            import traceback
            traceback.print_exc()
            return False

    def clear(self, clear_undo: bool = True):
        self.scenes = []
        self._scene_map = {}
        self.pool_files = []
        self.project_channel_template = []
        self.root_path = None
        self.is_dirty = False
        if clear_undo and self.undo_stack:
            self.undo_stack.clear()
        self.project_changed.emit()


    def set_project_template(self, template: List[Dict[str, str]]):
        """Sets the global channel template for new samples with Undo support."""
        from .commands import SetProjectTemplateCommand
        self.undo_stack.push(SetProjectTemplateCommand(self, template))

    def _set_project_template_internal(self, template: List[Dict[str, str]]):
        print(f"DEBUG: [ProjectModel] _set_project_template_internal called with: {template}")
        normalized_template, template_errors = self._normalize_project_template(template)
        print(f"DEBUG: [ProjectModel] Normalized template: {normalized_template}")
        if template_errors:
            print(f"DEBUG: [ProjectModel] Template errors: {template_errors}")
            
        self.project_channel_template = normalized_template
        self.last_template_warnings = template_errors
        self.is_dirty = True
        self.project_changed.emit()

    def scan_folder(self, folder_path: str, extensions: tuple = ('.tif', '.tiff', '.png', '.jpg', '.jpeg'), recursive: bool = False) -> List[str]:
        """Scans a folder for image files (non-recursive by default)."""
        files = []
        if recursive:
            for root, _, fnames in os.walk(folder_path):
                for fname in fnames:
                    if fname.lower().endswith(extensions):
                        files.append(os.path.join(root, fname))
        else:
            try:
                for fname in os.listdir(folder_path):
                    if fname.lower().endswith(extensions):
                        files.append(os.path.join(folder_path, fname))
            except Exception as e:
                print(f"Error scanning folder: {e}")
        return files

    def get_project_template(self) -> List[Dict[str, str]]:
        return self.project_channel_template


    def add_files(self, file_paths: List[str]):
        """Smartly groups files into scenes with Undo support."""
        from .commands import AddFilesCommand
        self.undo_stack.push(AddFilesCommand(self, file_paths))

    def _add_files_internal(self, file_paths: List[str]):
        """Internal method for adding files without pushing to Undo stack."""
        # Add to pool first
        self.add_to_pool(file_paths, undoable=False)
        
        last_modified_scene = None

        for path in file_paths:
            path = os.path.normpath(path)
            filename = os.path.basename(path)
            name_no_ext = os.path.splitext(filename)[0]
            name_upper = filename.upper()
            
            # Detect Channel
            matched_key = None
            ch_type = "Other"
            ch_color = "#808080"
            
            # Sort patterns by length desc to match "CY5" before "C" if we had "C"
            sorted_keys = sorted(self.channel_patterns.keys(), key=len, reverse=True)
            
            for key in sorted_keys:
                if key in name_upper:
                    matched_key = key
                    ch_type, ch_color = self.channel_patterns[key]
                    break
            
            # --- Logic Branch based on Mode ---
            if self.is_single_channel_mode:
                # SINGLE CHANNEL MODE: Direct mapping (1 File -> 1 Sample)
                # Use filename as Sample Name
                scene_id = name_no_ext
                
                # Ensure uniqueness (avoid merging with existing if names collide in this mode)
                base_name = scene_id
                counter = 1
                while scene_id in self._scene_map:
                    scene_id = f"{base_name}_{counter}"
                    counter += 1
                    
                new_scene = SceneData(id=scene_id, name=scene_id)
                new_scene.channels.append(ChannelDef(path=path, channel_type=ch_type, color=ch_color))
                
                self.scenes.append(new_scene)
                self._scene_map[scene_id] = new_scene
                last_modified_scene = new_scene
                
            else:
                # MULTI CHANNEL MODE: Smart Grouping
                # Determine Scene Name (Base Name)
                if matched_key:
                    pattern = re.compile(re.escape(matched_key), re.IGNORECASE)
                    base_name = pattern.sub("", name_no_ext)
                    base_name = re.sub(r'^[\W_]+|[\W_]+$', '', base_name)
                    if not base_name:
                        base_name = name_no_ext
                else:
                    base_name = name_no_ext
                
                # Create or Get Scene
                scene_id = base_name
                if scene_id not in self._scene_map:
                    new_scene = SceneData(id=scene_id, name=base_name)
                    
                    # INHERIT PROJECT TEMPLATE if available
                    if self.project_channel_template:
                        # Pre-populate channels from template
                        for ch_def in self.project_channel_template:
                            new_scene.channels.append(
                                ChannelDef(path="", channel_type=ch_def.get('name', 'Other'), color=ch_def.get('color', '#FFFFFF'))
                            )
                            
                    self.scenes.append(new_scene)
                    self._scene_map[scene_id] = new_scene
                
                scene = self._scene_map[scene_id]
                last_modified_scene = scene
                
                # Assign file to appropriate channel slot
                assigned = False
                
                # 1. Try to match by channel type in existing slots (from template or previous auto-add)
                for ch in scene.channels:
                    if ch.channel_type == ch_type and not ch.path:
                        ch.path = path
                        # Keep template color or update? Usually template color is preferred.
                        # But if auto-detection found a specific color (e.g. from filename), maybe use it?
                        # Let's stick to template color if it exists, otherwise auto color.
                        if not ch.color or ch.color == "#FFFFFF":
                             ch.color = ch_color
                        assigned = True
                        break
                
                # 2. If not assigned (no empty slot matching type), append new channel
                if not assigned:
                    # Only append if we didn't fully fill the template?
                    # Or always append if extra file?
                    # If we have a template, we might want to be strict or flexible.
                    # Flexible: Append extra channels.
                    scene.channels.append(ChannelDef(path=path, channel_type=ch_type, color=ch_color))
            
        # --- AUTO-DETECTION LOGIC ---
        if last_modified_scene:
            # If the resulting sample has only 1 channel, switch to Single Channel Mode.
            # If > 1 channel, switch to Multi Channel Mode.
            if len(last_modified_scene.channels) > 1:
                self.is_single_channel_mode = False
            elif len(last_modified_scene.channels) == 1:
                self.is_single_channel_mode = True

        if file_paths:
            self.is_dirty = True
            self.project_changed.emit()

    def add_imported_merge_scene(self, name: str, channels_data: List[Dict]):
        """
        Adds a scene with pre-defined channels (e.g., from Import Merge).
        channels_data: List of dicts with {'path', 'type', 'color'}
        """
        # Ensure unique name
        base_name = name
        counter = 1
        while name in self._scene_map:
            name = f"{base_name}_{counter}"
            counter += 1
            
        new_scene = SceneData(id=name, name=name)
        for ch_info in channels_data:
            # Prepare display settings dictionary
            # Default to visible=True if not provided
            display_settings = ch_info.get('display_settings', {}).copy()
            if 'visible' not in display_settings and 'visible' in ch_info:
                display_settings['visible'] = ch_info['visible']
            elif 'visible' not in display_settings:
                display_settings['visible'] = True

            new_scene.channels.append(
                ChannelDef(
                    path=os.path.normpath(ch_info['path']),
                    channel_type=ch_info['type'],
                    color=ch_info['color'],
                    display_settings=display_settings
                )
            )
            
        self.scenes.append(new_scene)
        self._scene_map[name] = new_scene
        self.is_dirty = True
        
        # Auto-detect mode
        if len(new_scene.channels) > 1:
            self.is_single_channel_mode = False
        elif len(new_scene.channels) == 1:
            self.is_single_channel_mode = True
            
        self.project_changed.emit()
        return name

    def get_scene(self, scene_id: str) -> Optional[SceneData]:
        return self._scene_map.get(scene_id)

    def add_manual_scene(self, name: str, channel_templates: Union[List[str], List[Dict]] = None) -> str:
        """Creates an empty scene manually with optional channel slots with Undo support."""
        # Ensure unique name
        base_name = name
        counter = 1
        while name in self._scene_map:
            name = f"{base_name}_{counter}"
            counter += 1
            
        from .commands import AddManualSceneCommand
        self.undo_stack.push(AddManualSceneCommand(self, name, channel_templates))
        return name

    def _add_manual_scene_internal(self, name: str, channel_templates: Union[List[str], List[Dict]] = None) -> str:
        print(f"DEBUG: [ProjectModel] _add_manual_scene_internal called. Name: {name}, Templates: {channel_templates}")
        # Ensure unique name
        base_name = name
        counter = 1
        while name in self._scene_map:
            name = f"{base_name}_{counter}"
            counter += 1
            
        new_scene = SceneData(id=name, name=name)
        
        if not channel_templates:
            # 1. Try Project Template
            if self.project_channel_template:
                for ch_def in self.project_channel_template:
                    new_scene.channels.append(
                        ChannelDef(path="", channel_type=ch_def['name'], color=ch_def['color'])
                    )
            # 2. Fallback: Inherit from last added scene (Smart Template)
            elif self.scenes:
                last_scene = self.scenes[-1]
                for ch in last_scene.channels:
                    new_scene.channels.append(
                        ChannelDef(path="", channel_type=ch.channel_type, color=ch.color)
                    )
        elif channel_templates:
            # Handle List[Dict] (Full Template)
            if isinstance(channel_templates[0], dict):
                for ch_def in channel_templates:
                    new_scene.channels.append(
                        ChannelDef(path="", channel_type=ch_def.get('name', 'Other'), color=ch_def.get('color', '#FFFFFF'))
                    )
            # Handle List[str] (Names only)
            else:
                for ch_type in channel_templates:
                    default_color = "#FFFFFF"
                    for key, (ctype, color) in self.channel_patterns.items():
                        if key == ch_type or ctype == ch_type:
                            default_color = color
                            break
                    new_scene.channels.append(ChannelDef(path="", channel_type=ch_type, color=default_color))
        
        self.scenes.append(new_scene)
        self._scene_map[name] = new_scene
        self.is_dirty = True
        self.project_changed.emit()
        return name

    def update_channel_path(self, scene_id: str, ch_index: int, new_path: str):
        """Updates the path of an existing channel slot with Undo support."""
        if scene_id in self._scene_map:
            scene = self._scene_map[scene_id]
            if 0 <= ch_index < len(scene.channels):
                old_path = scene.channels[ch_index].path
                if old_path != new_path:
                    from .commands import UpdateChannelPathCommand
                    self.undo_stack.push(UpdateChannelPathCommand(self, scene_id, ch_index, old_path, new_path))

    def _update_channel_path_internal(self, scene_id: str, ch_index: int, new_path: str):
        if scene_id in self._scene_map:
            scene = self._scene_map[scene_id]
            if 0 <= ch_index < len(scene.channels):
                if not new_path:
                    scene.channels[ch_index].path = ""
                else:
                    scene.channels[ch_index].path = os.path.normpath(new_path)
                self.is_dirty = True
                self.project_changed.emit()

    def remove_scene(self, scene_id: str):
        """Removes a scene with Undo support."""
        if scene_id in self._scene_map:
            from .commands import RemoveSceneCommand
            self.undo_stack.push(RemoveSceneCommand(self, scene_id))
            return True
        return False

    def remove_scenes(self, scene_ids: List[str]):
        """Removes multiple scenes with a single Undo command."""
        valid_ids = [sid for sid in scene_ids if sid in self._scene_map]
        if valid_ids:
            from .commands import BatchRemoveScenesCommand
            self.undo_stack.push(BatchRemoveScenesCommand(self, valid_ids))
            return True
        return False

    def _remove_scene_internal(self, scene_id: str):
        if scene_id in self._scene_map:
            scene = self._scene_map.pop(scene_id)
            if scene in self.scenes:
                self.scenes.remove(scene)
            self.is_dirty = True
            self.project_changed.emit()
            return True
        return False

    def rename_scene(self, old_id: str, new_name: str) -> bool:
        """Renames a scene with Undo support."""
        if old_id not in self._scene_map:
            return False
        if new_name in self._scene_map and new_name != old_id:
            return False
        
        from .commands import RenameSceneCommand
        self.undo_stack.push(RenameSceneCommand(self, old_id, new_name))
        return True

    def _rename_scene_internal(self, old_id: str, new_name: str):
        if old_id in self._scene_map:
            scene = self._scene_map.pop(old_id)
            scene.id = new_name
            scene.name = new_name
            self._scene_map[new_name] = scene
            self.is_dirty = True
            self.project_changed.emit()
            return True
        return False

    def _rebuild_scene_map(self):
        """Rebuilds the internal ID -> Scene map from the list."""
        self._scene_map = {s.id: s for s in self.scenes}

    def get_assigned_files(self) -> set:
        """Returns a set of all file paths currently assigned to any scene."""
        assigned = set()
        for scene in self.scenes:
            for ch in scene.channels:
                if ch.path:
                    assigned.add(os.path.normpath(ch.path))
        return assigned

    @property
    def unassigned_files(self) -> List[str]:
        assigned = self.get_assigned_files()
        return [p for p in self.pool_files if os.path.normpath(p) not in assigned]

    def add_to_pool(self, file_paths: List[str], undoable: bool = True):
        """Adds files to the pool with Undo support."""
        if not undoable:
            self._add_to_pool_internal(file_paths)
            return

        from .commands import AddFilesToPoolCommand
        self.undo_stack.push(AddFilesToPoolCommand(self, file_paths))

    def _add_to_pool_internal(self, file_paths: List[str]):
        """Internal method for adding files to pool without pushing to Undo stack."""
        # Avoid duplicates
        existing = set(self.pool_files)
        changed = False
        for p in file_paths:
            p_norm = os.path.normpath(p)
            if p_norm not in existing:
                self.pool_files.append(p_norm)
                existing.add(p_norm)
                changed = True
        
        if changed:
            self.is_dirty = True
            self.project_changed.emit()

    def remove_from_pool(self, file_path: str):
        """Removes file from pool completely with Undo support."""
        if file_path in self.pool_files:
            from .commands import RemoveFromPoolCommand
            self.undo_stack.push(RemoveFromPoolCommand(self, file_path))

    def remove_files_from_pool(self, file_paths: List[str]):
        """Removes multiple files from pool with Undo support."""
        if not file_paths:
            return
        from .commands import BatchRemoveFromPoolCommand
        self.undo_stack.push(BatchRemoveFromPoolCommand(self, file_paths))

    def _remove_from_pool_internal(self, file_path: str):
        if file_path in self.pool_files:
            self.pool_files.remove(file_path)
            self.is_dirty = True
            self.project_changed.emit()

    def add_channel_to_scene(self, scene_id: str, file_path: str, channel_type: str, color: str):
        """Adds a new channel to a scene with Undo support."""
        if scene_id in self._scene_map:
            from .commands import AddChannelToSceneCommand
            self.undo_stack.push(AddChannelToSceneCommand(self, scene_id, file_path, channel_type, color))

    def _add_channel_to_scene_internal(self, scene_id: str, file_path: str, channel_type: str, color: str):
        if scene_id in self._scene_map:
            scene = self._scene_map[scene_id]
            scene.channels.append(ChannelDef(path=os.path.normpath(file_path), channel_type=channel_type, color=color))
            self.is_dirty = True
            self.project_changed.emit()

    def add_empty_channel(self, scene_id: str):
        """Adds a new empty channel slot to a scene with Undo support."""
        if scene_id in self._scene_map:
            from .commands import AddEmptyChannelCommand
            self.undo_stack.push(AddEmptyChannelCommand(self, scene_id))

    def _add_empty_channel_internal(self, scene_id: str):
        if scene_id in self._scene_map:
            scene = self._scene_map[scene_id]
            new_idx = len(scene.channels) + 1
            name = f"New Channel {new_idx}"
            # Use a default color, maybe cycle through a palette or just grey/white
            color = "#FFFFFF" 
            scene.channels.append(ChannelDef(path="", channel_type=name, color=color))
            self.is_dirty = True
            self.project_changed.emit()

    def update_channel_color(self, scene_id: str, ch_index: int, new_color: str):
        """Updates the display color of a channel with Undo support."""
        if scene_id in self._scene_map:
            scene = self._scene_map[scene_id]
            if 0 <= ch_index < len(scene.channels):
                old_color = scene.channels[ch_index].color
                if old_color != new_color:
                    from .commands import UpdateChannelColorCommand
                    self.undo_stack.push(UpdateChannelColorCommand(self, scene_id, ch_index, old_color, new_color))

    def _update_channel_color_internal(self, scene_id: str, ch_index: int, new_color: str):
        if scene_id in self._scene_map:
            scene = self._scene_map[scene_id]
            if 0 <= ch_index < len(scene.channels):
                scene.channels[ch_index].color = new_color
                self.is_dirty = True
                self.project_changed.emit()

    def remove_channel(self, scene_id: str, ch_index: int):
        """Removes a channel from a scene with Undo support."""
        if scene_id in self._scene_map:
            scene = self._scene_map[scene_id]
            if 0 <= ch_index < len(scene.channels):
                from .commands import RemoveChannelCommand
                self.undo_stack.push(RemoveChannelCommand(self, scene_id, ch_index))

    def _remove_channel_internal(self, scene_id: str, ch_index: int):
        if scene_id in self._scene_map:
            scene = self._scene_map[scene_id]
            if 0 <= ch_index < len(scene.channels):
                scene.channels.pop(ch_index)
                self.is_dirty = True
                self.project_changed.emit()

    def _insert_channel_internal(self, scene_id: str, ch_index: int, ch_def: ChannelDef):
        if scene_id in self._scene_map:
            scene = self._scene_map[scene_id]
            scene.channels.insert(ch_index, ch_def)
            self.is_dirty = True
            self.project_changed.emit()
