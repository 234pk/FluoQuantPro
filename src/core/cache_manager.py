import time
from typing import Dict, List, Optional
from PySide6.QtCore import QObject, QSettings
from src.core.data_model import ImageChannel
from src.core.logger import Logger

class SceneCacheManager(QObject):
    """
    Manages caching of ImageChannel objects to prevent unnecessary reloading
    and control memory usage based on user settings.
    """
    _instance = None
    
    def __init__(self):
        super().__init__()
        self._cache: Dict[str, List[ImageChannel]] = {}
        self._current_scene_id: Optional[str] = None
        self._settings = QSettings("FluoQuantPro", "Settings")
        
    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
        
    def set_current_scene(self, scene_id: str):
        self._current_scene_id = scene_id
        
    def get_policy(self) -> str:
        # "none", "current", "recent", "all"
        return self._settings.value("display/precache_key", "current")

    def handle_low_memory(self):
        """Called when memory is critically low."""
        Logger.warning("[Cache] Low memory detected! Clearing non-current caches.")
        if self._current_scene_id:
            self.clear_all_except(self._current_scene_id)
        else:
            # If we don't know current, clear everything to be safe?
            # Or maybe just clear oldest?
            # For now, safe default: clear all.
            self.clear_all()
        
    def store_scene(self, scene_id: str, channels: List[ImageChannel]):
        """Stores a scene's channels in the cache based on policy."""
        policy = self.get_policy()
        
        if policy == "none":
            # Even if "none", we might want to ensure others are cleared
            self.clear_all()
            return
            
        if policy == "current":
            # Keep only the current one
            self.clear_all_except(scene_id)
            self._cache[scene_id] = channels
            # Logger.debug(f"[Cache] Stored scene {scene_id} (Policy: current)")
            
        elif policy == "recent":
            # Keep last 5
            # First, add/update the current one
            if scene_id in self._cache:
                del self._cache[scene_id] # Remove to re-insert at end (LRU)
            self._cache[scene_id] = channels
            
            # Trim if > 5
            max_items = 5
            if len(self._cache) > max_items:
                # Remove oldest (first keys)
                # We need to collect keys to remove first to avoid runtime error during iteration
                keys = list(self._cache.keys())
                # Keep the last 5
                to_remove = keys[:-max_items]
                
                Logger.info(f"[Cache] Policy 'recent' limit reached. Clearing: {to_remove}")
                for k in to_remove:
                    self._free_channels(self._cache[k])
                    del self._cache[k]
                    
        elif policy == "all":
            # Keep everything
            self._cache[scene_id] = channels
            Logger.info(f"[Cache] Stored scene {scene_id} (Policy: all). Total cached: {len(self._cache)}")
            
    def get_scene(self, scene_id: str) -> Optional[List[ImageChannel]]:
        """Retrieves a scene from cache if available."""
        policy = self.get_policy()
        if policy == "none":
            return None
            
        channels = self._cache.get(scene_id)
        if channels:
            Logger.info(f"[Cache] Hit for scene {scene_id}")
            # For "recent" policy, update LRU order (move to end)
            if policy == "recent":
                del self._cache[scene_id]
                self._cache[scene_id] = channels
            return channels
        return None
        
    def clear_all_except(self, keep_id: str):
        """Removes all scenes except the specified one."""
        to_remove = [k for k in list(self._cache.keys()) if k != keep_id]
        if not to_remove:
            return

        Logger.info(f"[Cache] Clearing {len(to_remove)} scenes: {to_remove}. Keeping: {keep_id}")
        for k in to_remove:
            self._free_channels(self._cache[k])
            del self._cache[k]
        
        import gc
        gc.collect()
        Logger.info(f"[Cache] Cleared {len(to_remove)} scenes.")
            
    def clear_all(self):
        """Clears the entire cache."""
        if not self._cache:
            return
            
        for channels in self._cache.values():
            self._free_channels(channels)
        self._cache.clear()
        
        import gc
        gc.collect()
        Logger.info("[Cache] All scenes cleared.")
        
    def _free_channels(self, channels: List[ImageChannel]):
        """Releases resources for a list of channels."""
        for ch in channels:
            if hasattr(ch, 'clear_cache'):
                ch.clear_cache()
            # We don't clear _raw_data here immediately because Python GC handles it,
            # but clearing caches helps.
