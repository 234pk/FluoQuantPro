import os
import numpy as np
from PySide6.QtCore import QThread, Signal
from src.core.logger import Logger
from src.core.data_model import ImageChannel
from src.core.image_loader import ImageLoader

class SceneLoaderWorker(QThread):
    # scene_id, index, data (numpy array or None), channel_def (object)
    channel_loaded = Signal(str, int, object, object) 
    finished_loading = Signal(str)

    def __init__(self, scene_id, channel_defs):
        super().__init__()
        self.scene_id = scene_id
        self.channel_defs = channel_defs
        self._is_running = True
        
    def preprocess_data(self, data):
        """
        Pre-process data in the worker thread to save main thread CPU time.
        Handles Max Projection for Z-stacks/Multichannel images.
        """
        if data is None: return None
        
        # Logic matched with ImageChannel.__init__
        if data.ndim == 3:
            # Case 1: (C, H, W) or (Z, H, W) where C/Z is small leading dimension
            if data.shape[0] < 10: 
                # If it's 3 or 4 channels, it might be RGB (channels-first).
                # Keep as 3D for ImageChannel to extract the correct channel based on name.
                if data.shape[0] in (3, 4):
                    return data
                # Otherwise, assume Z-stack and take Max Projection
                return np.max(data, axis=0)
            
            # Case 2: (H, W, C) where C is small trailing dimension (e.g. RGB)
            elif data.shape[2] in (3, 4):
                # RGB/RGBA - Keep as 3D for ImageChannel to handle extraction
                return data
            elif data.shape[2] < 10:
                # Multichannel -> Grayscale Max Projection
                return np.max(data, axis=2)
                
        return data

    def run(self):
        Logger.info("[Worker] Started")
        for i, ch_def in enumerate(self.channel_defs):
            if not self._is_running: return
            
            data = None
            if ch_def.path and os.path.exists(ch_def.path):
                try:
                    Logger.info(f"[Worker] Reading {os.path.basename(ch_def.path)}...")
                    # Use the robust ImageLoader instead of raw tifffile
                    data, is_rgb = ImageLoader.load_image(ch_def.path)
                    
                    # ImageLoader already handles 4D+ and basic dimension normalization
                    # We still call preprocess_data for any extra user-defined logic (like Max Projection for 3D Z-stacks)
                    if data is not None:
                        data = self.preprocess_data(data)
                        
                except Exception as e:
                    Logger.error(f"Error loading {ch_def.path}: {e}")
            
            if not self._is_running: return
            
            # Create ImageChannel object in worker thread (performs stats calculation)
            try:
                    Logger.info(f"[Worker] Creating ImageChannel {i}...")
                    # Note: ImageChannel is a data class, safe to create here if no Qt parents involved
                    ch_obj = ImageChannel(ch_def.path, ch_def.color, ch_def.channel_type, data=data, auto_contrast=False)
                    Logger.info(f"[Worker] Emitting channel_loaded {i}")
                    self.channel_loaded.emit(self.scene_id, i, ch_obj, ch_def)
            except Exception as e:
                Logger.error(f"Error creating ImageChannel in worker: {e}")
                # Fallback to passing data if object creation fails (should not happen)
                self.channel_loaded.emit(self.scene_id, i, data, ch_def)

        Logger.info("[Worker] Finished")
        self.finished_loading.emit(self.scene_id)

    def stop(self):
        self._is_running = False
        self.wait()
