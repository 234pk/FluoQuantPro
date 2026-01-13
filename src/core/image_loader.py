import os
import numpy as np
import tifffile
import cv2
from typing import Optional, Tuple, Union
from .channel_config import get_rgb_mapping

class ImageLoader:
    """
    Dedicated module for loading images with support for biological channel mapping.
    Handles various formats and normalizes them into raw data for analysis.
    """

    @staticmethod
    def load_image(file_path: str) -> Tuple[np.ndarray, bool]:
        """
        Loads an image from disk.
        Returns (raw_data, is_rgb).
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Image file not found: {file_path}")

        ext = os.path.splitext(file_path)[1].lower()
        try:
            if ext in (".tif", ".tiff"):
                raw_data = tifffile.imread(file_path)
            else:
                # Use cv2 for other formats, with support for Unicode paths
                img_stream = np.fromfile(file_path, dtype=np.uint8)
                raw_data = cv2.imdecode(img_stream, cv2.IMREAD_UNCHANGED)
                if raw_data is None:
                    raise IOError(f"Failed to decode image: {file_path}")
                
                # Convert BGR/BGRA to RGB/RGBA if needed
                if raw_data.ndim == 3:
                    if raw_data.shape[2] == 3:
                        raw_data = cv2.cvtColor(raw_data, cv2.COLOR_BGR2RGB)
                    elif raw_data.shape[2] == 4:
                        raw_data = cv2.cvtColor(raw_data, cv2.COLOR_BGRA2RGBA)
        except Exception as e:
            raise IOError(f"Error loading image {file_path}: {str(e)}")

        # Scientific Dimension Normalization
        # 1. Squeeze singleton dimensions (e.g., (1, 1024, 1024, 3) -> (1024, 1024, 3))
        # This is 100% safe and scientific.
        if raw_data.ndim > 2:
            original_shape = raw_data.shape
            raw_data = np.squeeze(raw_data)
            if raw_data.shape != original_shape:
                from .logger import Logger
                Logger.debug(f"ImageLoader: Squeezed dimensions from {original_shape} to {raw_data.shape}")

        # 2. Handle remaining high-dimensional data (True Z-stacks or Time-series)
        if raw_data.ndim >= 4:
            from .logger import Logger
            Logger.info(f"ImageLoader: High-dimensional data detected ({raw_data.shape}). Performing Max Intensity Projection for visualization.")
            # Default to Max Projection over the first dimension
            while raw_data.ndim > 3:
                raw_data = np.max(raw_data, axis=0)
        
        # 3. Final normalization for 3D data that should be 2D
        if raw_data.ndim == 3:
            # If it's (1, H, W) or (H, W, 1), make it 2D
            if raw_data.shape[0] == 1:
                raw_data = raw_data[0, :, :]
            elif raw_data.shape[2] == 1:
                raw_data = raw_data[:, :, 0]

        is_rgb = raw_data.ndim == 3
        return raw_data, is_rgb

    @staticmethod
    def extract_channel_data(raw_data: np.ndarray, channel_name: str) -> np.ndarray:
        """
        Extracts relevant channel data based on the channel name and RGB mapping.
        If the input is already grayscale (2D), returns it as is.
        If the input is RGB or multi-channel (3D), extracts or combines channels based on mapping.
        """
        if raw_data.ndim == 2:
            return raw_data
        
        # If ndim > 3, we have a problem (should have been handled by load_image)
        # But let's be safe and reduce it here too
        if raw_data.ndim > 3:
            while raw_data.ndim > 3:
                raw_data = np.max(raw_data, axis=0)

        # It's an RGB or Multi-channel image (3D)
        mapping = get_rgb_mapping(channel_name)
        
        # Determine (C, H, W) vs (H, W, C)
        is_ch_first = raw_data.shape[0] < raw_data.shape[2] and raw_data.shape[0] <= 4
        
        if mapping:
            # combine channels based on mapping (e.g. CY5 -> R+B)
            extracted = None
            count = 0
            for i, active in enumerate(mapping):
                if active:
                    ch_data = raw_data[i, :, :] if is_ch_first else raw_data[:, :, i]
                    if extracted is None:
                        extracted = ch_data.astype(np.float32)
                    else:
                        extracted += ch_data.astype(np.float32)
                    count += 1
            
            if extracted is not None:
                if count > 1:
                    extracted /= count
                return extracted.astype(raw_data.dtype)

        # Fallback to grayscale for unknown channels if 3D
        if raw_data.ndim == 3:
            # Determine (C, H, W) vs (H, W, C)
            is_ch_first = raw_data.shape[0] < raw_data.shape[2] and raw_data.shape[0] <= 4
            
            if is_ch_first:
                # Use Max Projection (Standard for fluorescence)
                return np.max(raw_data, axis=0)
            else:
                # Use Max Projection (Standard for fluorescence)
                return np.max(raw_data, axis=2)

        return raw_data
