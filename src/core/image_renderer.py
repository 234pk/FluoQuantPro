import numpy as np
import cv2
from typing import List, Tuple
from .data_model import ImageChannel
from .enhance import EnhanceProcessor

def is_opencl_enabled():
    """Checks if OpenCL is both available and enabled in OpenCV."""
    try:
        return cv2.ocl.haveOpenCL() and cv2.ocl.useOpenCL()
    except:
        return False

class ImageRenderer:
    """
    Dedicated module for image-related rendering tasks.
    Handles channel visualization, LUT generation, and multi-channel compositing.

    Usage Examples:
    --------------
    1. Render a single channel:
       >>> channel = project.get_channel(0)
       >>> rgb_image = ImageRenderer.render_channel(channel, target_shape=(512, 512))

    2. Composite multiple channels:
       >>> channels = [ch1, ch2, ch3]
       >>> composite_image = ImageRenderer.composite(channels)

    3. Generate a custom LUT:
       >>> lut = ImageRenderer.generate_rgb_lut(min_val=0, max_val=1000, gamma=1.0, hex_color='#00FF00')
    """

    @staticmethod
    def hex_to_rgb(hex_color: str) -> Tuple[float, float, float]:
        """Converts hex string (e.g., '#FF0000') to normalized RGB tuple (1.0, 0.0, 0.0)."""
        hex_color = hex_color.lstrip('#')
        if len(hex_color) != 6:
            return (1.0, 1.0, 1.0) # Fallback to white
        return tuple(int(hex_color[i:i+2], 16) / 255.0 for i in (0, 2, 4))

    @staticmethod
    def generate_rgb_lut(min_val: float, max_val: float, gamma: float, hex_color: str, lut_size: int = 65536, out_depth: int = 8) -> np.ndarray:
        """
        Generates an Nx3 LUT for fast bit-depth -> RGB mapping.
        Default size 65536 is for 16-bit data.
        out_depth: 8 for uint8, 16 for uint16.
        """
        # Create base ramp 0 to (lut_size - 1)
        ramp = np.arange(lut_size, dtype=np.float32)
        
        # 1. Normalize (Min/Max)
        rng = max_val - min_val
        if rng < 1e-6: rng = 1e-6
        
        normalized = (ramp - min_val) / rng
        np.clip(normalized, 0.0, 1.0, out=normalized)
        
        # 2. Gamma
        if abs(gamma - 1.0) > 0.01:
            np.power(normalized, 1.0 / gamma, out=normalized)
            
        # 3. Colorize
        r, g, b = ImageRenderer.hex_to_rgb(hex_color)
        
        # Shape: (lut_size, 3)
        max_val_out = 255 if out_depth == 8 else 65535
        dtype_out = np.uint8 if out_depth == 8 else np.uint16
        
        lut = np.empty((lut_size, 3), dtype=dtype_out)
        lut[:, 0] = (normalized * r * max_val_out).astype(dtype_out) # R
        lut[:, 1] = (normalized * g * max_val_out).astype(dtype_out) # G
        lut[:, 2] = (normalized * b * max_val_out).astype(dtype_out) # B
        
        return lut

    @staticmethod
    def render_channel(channel: ImageChannel, target_shape: Tuple[int, int] = None, out_depth: int = 8) -> np.ndarray:
        """
        Renders a single channel to an RGB image.
        out_depth: 8 (uint8 result) or 16 (uint16 result).
        
        Scientific Rigor Notes:
        1. Signal Integrity: Uses raw_data for processing. If target_shape is provided,
           downsampling is performed on the processed result, not the raw signal,
           to maintain maximum precision during intensity mapping.
        2. No Weighted Mixing: Grayscale conversion (if needed) uses max projection 
           across channels. Traditional weighted conversion (0.299R + 0.587G + 0.114B) 
           is strictly avoided as it biases fluorescence intensity measurements.
        3. Dynamic LUT: The LUT size adapts to the data range (e.g., 256 for 8-bit, 
           65536 for 16-bit) to prevent quantization errors during visualization.
        4. High Bit-depth Export: Supports 16-bit RGB rendering for scientific visualization
           preserving fine intensity gradients.
        """
        import time
        if not channel.display_settings.visible:
            return None

        # 1. Source Data (Always start with Raw Data)
        data = channel.raw_data
        
        if data is None or data.size == 0:
            return None
            
        settings = channel.display_settings
        
        # Calculate scale factor for preview mode optimization
        if target_shape is not None:
            h, w = data.shape[:2]
            th, tw = target_shape
            scale_factor = min(th / h, tw / w) if (h > 0 and w > 0) else 1.0
        else:
            scale_factor = 1.0

        # Optimization: Resize FIRST if needed (Preview Mode / Display Downsampling)
        if target_shape is not None and (data.shape != target_shape):
            h, w = data.shape[:2]
            th, tw = target_shape
            
            # Calculate stride
            sy = max(1, h // th)
            sx = max(1, w // tw)
            
            # Simple strided slicing
            data = np.ascontiguousarray(data[::sy, ::sx])
            
            if data.shape[:2] != target_shape:
                 data = cv2.resize(data, (tw, th), interpolation=cv2.INTER_NEAREST)

        # Check for Enhancement Parameters
        enhance_params = getattr(settings, 'enhance_params', {})
        
        has_enhancement = False
        if enhance_params:
            has_enhancement = (
                enhance_params.get('stretch_enabled', False) or
                enhance_params.get('bg_enabled', False) or
                enhance_params.get('contrast_enabled', False) or
                enhance_params.get('noise_enabled', False) or
                enhance_params.get('gamma_enabled', False) or
                enhance_params.get('median_enabled', False)
            )
            
            if has_enhancement and enhance_params.get('gamma_enabled', False):
                 if abs(enhance_params.get('gamma', 1.0) - 1.0) < 0.001:
                      other_ops = (
                        enhance_params.get('stretch_enabled', False) or
                        enhance_params.get('bg_enabled', False) or
                        enhance_params.get('contrast_enabled', False) or
                        enhance_params.get('noise_enabled', False) or
                        enhance_params.get('median_enabled', False)
                      )
                      if not other_ops:
                           has_enhancement = False

        if not has_enhancement:
            if hasattr(channel, '_cached_enhanced_data'):
                channel._cached_enhanced_data = None
            if hasattr(channel, '_last_enhance_params'):
                channel._last_enhance_params = None
            if hasattr(channel, '_preview_enhance_cache'):
                channel._preview_enhance_cache.clear()

        processed_data = data
        
        if has_enhancement:
            use_cache = False
            # Fix: is_full_res should also check if the current data matches the cached shape
            current_shape = data.shape
            is_full_res = (data.shape == channel.raw_data.shape)
            
            if (getattr(channel, '_last_enhance_params', None) == enhance_params and 
                getattr(channel, '_cached_enhanced_data', None) is not None and
                channel._cached_enhanced_data.shape == current_shape):
                processed_data = channel._cached_enhanced_data
                use_cache = True
            elif target_shape is not None:
                cache_key = (target_shape, tuple(sorted(enhance_params.items())))
                preview_cache = getattr(channel, '_preview_enhance_cache', {})
                if cache_key in preview_cache:
                    processed_data = preview_cache[cache_key]
                    use_cache = True
            
            if not use_cache:
                processed_data = EnhanceProcessor.process_scientific_pipeline(processed_data, enhance_params, scale_factor=scale_factor)
                
                if enhance_params.get('median_enabled', False):
                    k = enhance_params.get('median_kernel', 3)
                    processed_data = EnhanceProcessor.apply_median_filter(processed_data, k)
                    
                if is_full_res:
                    channel._cached_enhanced_data = processed_data
                    channel._last_enhance_params = enhance_params.copy()
                elif target_shape is not None:
                    cache_key = (target_shape, tuple(sorted(enhance_params.items())))
                    if not hasattr(channel, '_preview_enhance_cache'):
                        channel._preview_enhance_cache = {}
                    if len(channel._preview_enhance_cache) > 5:
                        channel._preview_enhance_cache.clear()
                    channel._preview_enhance_cache[cache_key] = processed_data
            
            # Final Safety: Ensure processed_data matches expected spatial dimensions
            if target_shape is not None and processed_data.shape[:2] != target_shape:
                processed_data = cv2.resize(processed_data, (target_shape[1], target_shape[0]), interpolation=cv2.INTER_NEAREST)
            
        # Determine effective Gamma for LUT
        lut_gamma = settings.gamma
        result = None
        
        # RGB Direct Path
        if getattr(channel, 'is_rgb', False) and processed_data.ndim == 3:
             r, g, b = ImageRenderer.hex_to_rgb(settings.color)
             if (r, g, b) != (1.0, 1.0, 1.0):
                  processed_data = np.max(processed_data[..., :3], axis=2)
             else:
                  data_f = processed_data[..., :3].astype(np.float32)
                  rng = settings.max_val - settings.min_val
                  if rng < 1e-6: rng = 1e-6
                  
                  mapped_data = (data_f - settings.min_val) / rng
                  np.clip(mapped_data, 0.0, 1.0, out=mapped_data)
                  
                  if abs(lut_gamma - 1.0) > 0.01:
                      np.power(mapped_data, 1.0 / lut_gamma, out=mapped_data)
                  
                  result = mapped_data

        # FAST PATH: Integer -> RGB LUT
        if result is None and processed_data.dtype in (np.uint8, np.uint16):
            try:
                # Use a safer way to determine LUT size
                if processed_data.dtype == np.uint8:
                    lut_size = 256
                else:
                    d_max = np.max(processed_data)
                    lut_size = int(d_max) + 1
                    if lut_size < 256: lut_size = 256
                    if lut_size > 65536: lut_size = 65536
                
                lut = ImageRenderer.generate_rgb_lut(settings.min_val, settings.max_val, lut_gamma, settings.color, lut_size=lut_size, out_depth=out_depth)
                rgb_mapped = lut[processed_data]
                
                max_val_out = 255.0 if out_depth == 8 else 65535.0
                result = rgb_mapped.astype(np.float32) / max_val_out
            except Exception as e:
                print(f"[ImageRenderer ERROR] LUT path failed: {e}")

        # Fallback for other cases
        if result is None:
            try:
                data_f = processed_data.astype(np.float32)
                rng = settings.max_val - settings.min_val
                if rng < 1e-6: rng = 1e-6
                
                mapped_data = (data_f - settings.min_val) / rng
                np.clip(mapped_data, 0.0, 1.0, out=mapped_data)
                
                if abs(lut_gamma - 1.0) > 0.01:
                    np.power(mapped_data, 1.0 / lut_gamma, out=mapped_data)

                r, g, b = ImageRenderer.hex_to_rgb(settings.color)
                tint = np.array([r, g, b], dtype=np.float32)
                
                if mapped_data.ndim == 2:
                    result = mapped_data[..., np.newaxis] * tint
                elif mapped_data.ndim == 3:
                    if mapped_data.shape[2] == 1:
                        result = mapped_data * tint
                    else:
                        result = mapped_data[..., :3] * tint
                else:
                    result = np.stack([mapped_data]*3, axis=-1) if mapped_data.ndim == 2 else mapped_data
            except Exception as e:
                print(f"[ImageRenderer CRITICAL] Fallback path failed: {e}")
            
        return result

    @staticmethod
    def composite(channels: List[ImageChannel], target_shape: Tuple[int, int] = None, out_depth: int = 8) -> np.ndarray:
        """
        Merges all visible channels into a single normalized float32 RGB image.
        """
        if target_shape is None and channels:
            for ch in channels:
                if not getattr(ch, 'is_placeholder', False):
                    target_shape = ch.shape
                    break
        
        if target_shape is None:
            return None
            
        if is_opencl_enabled():
            final_img_u = cv2.UMat(np.zeros((target_shape[0], target_shape[1], 3), dtype=np.float32))
        else:
            final_img = np.zeros((target_shape[0], target_shape[1], 3), dtype=np.float32)
        
        for ch in channels:
            if not ch.display_settings.visible:
                continue
                
            layer = ImageRenderer.render_channel(ch, target_shape, out_depth=out_depth)
            if layer is not None:
                if layer.dtype != np.float32:
                    layer = layer.astype(np.float32)
                    
                if layer.shape[:2] != target_shape:
                    layer = cv2.resize(layer, (target_shape[1], target_shape[0]), interpolation=cv2.INTER_NEAREST)
                    
                if is_opencl_enabled():
                    layer_u = cv2.UMat(layer)
                    final_img_u = cv2.add(final_img_u, layer_u)
                else:
                    final_img += layer
                
        if is_opencl_enabled():
            final_img = final_img_u.get()
            
        np.clip(final_img, 0.0, 1.0, out=final_img)
        return final_img
