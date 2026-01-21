import time
from typing import Dict, List, Optional
from PySide6.QtCore import QObject, QSettings
from src.core.data_model import ImageChannel
from src.core.logger import Logger

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

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
        
        # Check memory status
        is_memory_high = self.should_cleanup_memory()
        policy = self.get_policy()

        Logger.debug(f"[Cache] set_current_scene: {scene_id}. Memory High: {is_memory_high}. Policy: {policy}")

        # Logic Update based on User Feedback:
        # 1. If Memory is High: Force cleanup of non-current scenes regardless of policy.
        #    This prevents OOM and addresses "memory keeps rising" issue.
        # 2. If Memory is Low (Healthy): Keep caches (Soft Limit). 
        #    Even if policy is "current", we don't aggressively clear if we have plenty of RAM.
        #    This improves switching performance without penalty.
        
        if is_memory_high:
             Logger.info(f"[Cache] High memory detected while switching to {scene_id}. Triggering LRU cleanup.")
             self.handle_low_memory()
        else:
             # Memory is fine. Retain cache for fast switching.
             # We might log this for debugging user confusion.
             Logger.debug(f"[Cache] Memory healthy. Retaining background scenes for fast switching.")

    def should_cleanup_memory(self) -> bool:
        try:
            # Delegate to PerformanceMonitor which now has robust fallback logic
            from src.core.performance_monitor import PerformanceMonitor
            current_mb = PerformanceMonitor.instance()._get_current_memory_mb()
            current_gb = current_mb / 1024.0
            
            # Read threshold from settings (consistent with PerformanceMonitor)
            # Default fallback: 4GB
            threshold_gb = float(self._settings.value("performance/memory_threshold_gb", 4.0))
            
            Logger.debug(f"[Cache] Memory Check: Current={current_gb:.2f}GB, Threshold={threshold_gb:.2f}GB")
            
            if current_gb > threshold_gb:
                Logger.info(f"[Cache] Memory limit exceeded ({current_gb:.1f}GB > {threshold_gb:.1f}GB). Triggering cleanup.")
                return True
            return False
        except Exception as e:
            Logger.warning(f"[Cache] Memory check failed: {e}")
            # If check fails, assume safe to NOT clean up? Or safe to cleanup?
            # Safe default: Don't cleanup to avoid losing data on error, unless repeated OOM.
            return False

    def get_policy(self) -> str:
        # "none", "current", "recent", "all"
        return self._settings.value("display/precache_key", "current")

    def handle_low_memory(self):
        """Called when memory is critically low. Implements iterative LRU cleanup."""
        Logger.warning("[Cache] Low memory detected! Starting iterative LRU cleanup...")
        
        # Keys in self._cache are ordered by insertion (LRU = start of list)
        keys = list(self._cache.keys())
        
        # Protect current scene
        if self._current_scene_id and self._current_scene_id in keys:
            keys.remove(self._current_scene_id)
            
        if not keys:
            Logger.info("[Cache] No background scenes to clear.")
            return

        from src.core.performance_monitor import PerformanceMonitor
        monitor = PerformanceMonitor.instance()
        
        cleared_count = 0
        for scene_id in keys:
            # Evict oldest
            Logger.info(f"[Cache] Evicting oldest background scene: {scene_id}")
            if scene_id in self._cache:
                self._free_channels(self._cache[scene_id])
                del self._cache[scene_id]
                cleared_count += 1
            
            # Check if we recovered enough memory (Simple check)
            # We assume python GC will eventually reflect this, but for now we just want to stop if we are "safe"
            # Note: We don't force GC here because it's slow and handled by PerformanceMonitor async worker later.
            # But to check 'current_mb', we need at least some update.
            # We trust that removing one large scene (e.g. 500MB) is significant.
            
            current_mb = monitor._get_current_memory_mb()
            if (current_mb / 1024.0) < monitor.memory_threshold_gb:
                Logger.info(f"[Cache] Memory safe ({current_mb:.1f}MB < {monitor.memory_threshold_gb:.1f}GB). Stopping cleanup.")
                break
                
        Logger.info(f"[Cache] Cleanup finished. Evicted {cleared_count} scenes.")
        
    def store_scene(self, scene_id: str, channels: List[ImageChannel]):
        """Stores a scene's channels in the cache based on policy."""
        # Safety Check: If memory is high, ensure we enforce cleanup regardless of policy
        is_memory_high = self.should_cleanup_memory()
        Logger.debug(f"[Cache] store_scene: {scene_id}. Memory High: {is_memory_high}")
        
        if is_memory_high:
             Logger.info(f"[Cache] Memory high during storage. Enforcing cleanup.")
             self.clear_all_except(scene_id)

        policy = self.get_policy()
        
        if policy == "none":
            # Even if "none", we might want to ensure others are cleared
            self.clear_all()
            return
            
        if policy == "current":
            # Logic already handled by initial safety check + set_current_scene
            self._cache[scene_id] = channels
            
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
        current_keys = list(self._cache.keys())
        to_remove = [k for k in current_keys if k != keep_id]
        
        Logger.debug(f"[Cache] cleanup request. Cache keys: {current_keys}, Keep: {keep_id}, Remove: {to_remove}")
        
        if not to_remove:
            return

        Logger.info(f"[Cache] Clearing {len(to_remove)} scenes: {to_remove}. Keeping: {keep_id}")
        for k in to_remove:
            self._free_channels(self._cache[k])
            del self._cache[k]
        
        import gc
        gc.collect()
        Logger.info(f"[Cache] Cleared {len(to_remove)} scenes. Remaining: {list(self._cache.keys())}")
            
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
        Logger.debug(f"[Cache] Freeing {len(channels)} channels...")
        for ch in channels:
            if hasattr(ch, 'unload_raw_data'):
                ch.unload_raw_data()
            elif hasattr(ch, 'clear_cache'):
                ch.clear_cache()
            # Explicitly break references if possible
