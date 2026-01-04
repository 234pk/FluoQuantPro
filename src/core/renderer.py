import numpy as np
import cv2
from typing import List, Tuple
from .data_model import ImageChannel
from .enhance import EnhanceProcessor

# --- GPU Acceleration (OpenCL) Initialization ---
def is_opencl_enabled():
    """Checks if OpenCL is both available and enabled in OpenCV."""
    try:
        return cv2.ocl.haveOpenCL() and cv2.ocl.useOpenCL()
    except:
        return False

# Initial check for logging
if cv2.ocl.haveOpenCL():
    print(f"[Renderer] OpenCL Hardware Acceleration: AVAILABLE (Current: {cv2.ocl.useOpenCL()})")
else:
    print(f"[Renderer] OpenCL Hardware Acceleration: NOT AVAILABLE")

class Renderer:
    """
    Static utility class to handle the conversion of raw channel data 
    into a displayable RGB image (numpy array).
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
        r, g, b = Renderer.hex_to_rgb(hex_color)
        
        # Shape: (lut_size, 3)
        max_val_out = 255 if out_depth == 8 else 65535
        dtype_out = np.uint8 if out_depth == 8 else np.uint16
        
        lut = np.empty((lut_size, 3), dtype=dtype_out)
        lut[:, 0] = (normalized * r * max_val_out).astype(dtype_out) # R
        lut[:, 1] = (normalized * g * max_val_out).astype(dtype_out) # G
        lut[:, 2] = (normalized * b * max_val_out).astype(dtype_out) # B
        
        return lut

    @staticmethod
    def render_channel(channel: ImageChannel, target_shape: Tuple[int, int] = None, out_depth: int = 8, scale_bar_settings=None, annotations: List = None) -> np.ndarray:
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
        t0 = time.time()
        
        if not channel.display_settings.visible:
            # print(f"[Renderer] Skipping {channel.name}: Not visible")
            return None

        # 1. Source Data (Prefer cached processed data from Stage 3)
        if hasattr(channel, 'cached_processed_data') and channel.cached_processed_data is not None:
            data = channel.cached_processed_data
        else:
            data = channel.raw_data
        
        if data is None or data.size == 0:
            print(f"[Renderer] Skipping {channel.name}: No data found!")
            return None
            
        settings = channel.display_settings
        
        # DEBUG LOG: Check data range
        # d_min, d_max = np.min(data), np.max(data)
        # print(f"[Renderer] Rendering {channel.name}: Data Range [{d_min}, {d_max}], Display Range [{settings.min_val}, {settings.max_val}]")
        
        # Optimization: Resize FIRST if needed (Preview Mode / Display Downsampling)
        # CRITICAL PERFORMANCE FIX: Downsample BEFORE any other processing!
        # Processing 20MP image takes seconds; processing 2MP image takes milliseconds.
        if target_shape is not None and (data.shape != target_shape):
            # Use NumPy Slicing instead of cv2.resize for extreme speed
            # cv2.resize on 20MP uint16 image can still be slow (seconds).
            # Slicing is nearly instant.
            h, w = data.shape[:2]
            th, tw = target_shape
            
            # Calculate stride
            sy = max(1, h // th)
            sx = max(1, w // tw)
            
            # Simple strided slicing (Nearest Neighbor equivalent)
            # This is O(1) view creation if strides are regular, or very fast copy.
            # CRITICAL: Convert to contiguous array immediately to avoid slow access later
            data = np.ascontiguousarray(data[::sy, ::sx])
            
            # Fix: If slicing didn't reach target size (e.g. 1.5x downsample where stride=1),
            # force resize using Nearest Neighbor (fastest).
            if data.shape[:2] != target_shape:
                 data = cv2.resize(data, (tw, th), interpolation=cv2.INTER_NEAREST)
            
            # Skip exact resizing to avoid any slow cv2 operations. 
            # Slicing is close enough for display preview.
            # if data.shape[:2] != target_shape:
            #      data = cv2.resize(data, (tw, th), interpolation=cv2.INTER_NEAREST)
            
        t_prep = time.time()

        # Check for Enhancement Parameters
        enhance_params = getattr(settings, 'enhance_params', {})
        
        # Optimization: Check if any enhancement is actually enabled
        # Default all False to avoid slow dict.get lookups if we can check existence first?
        # Actually dict.get is fast.
        
        # Check if enhance_params is empty (common case)
        if not enhance_params:
            has_enhancement = False
        else:
            has_enhancement = (
                enhance_params.get('clahe_enabled', False) or
                enhance_params.get('stretch_enabled', False) or
                enhance_params.get('bg_enabled', False) or
                enhance_params.get('contrast_enabled', False) or
                enhance_params.get('noise_enabled', False) or
                enhance_params.get('gamma_enabled', False) or
                enhance_params.get('median_enabled', False)
            )
            
            # Additional check: If Gamma is enabled but value is 1.0, ignore it
            if has_enhancement and enhance_params.get('gamma_enabled', False):
                 if abs(enhance_params.get('gamma', 1.0) - 1.0) < 0.001:
                      # If gamma is the ONLY thing enabled, disable enhancement
                      other_ops = (
                        enhance_params.get('clahe_enabled', False) or
                        enhance_params.get('stretch_enabled', False) or
                        enhance_params.get('bg_enabled', False) or
                        enhance_params.get('contrast_enabled', False) or
                        enhance_params.get('noise_enabled', False) or
                        enhance_params.get('median_enabled', False)
                      )
                      if not other_ops:
                           has_enhancement = False

        processed_data = data
        
        # --- Enhancement Pipeline ---
        # Order: CLAHE -> Stage 2 (Real-time) -> Gamma -> Median -> LUT
        
        t_enhance_start = time.time()
        
        if has_enhancement:
            # Debug Log for unexpected enhancement
            if enhance_params.get('bg_enabled', False):
                 print(f"[{time.strftime('%H:%M:%S')}] Renderer: WARNING - Background Suppression Enabled! Params: {enhance_params}")
            elif enhance_params.get('stretch_enabled', False) or enhance_params.get('contrast_enabled', False):
                 print(f"[{time.strftime('%H:%M:%S')}] Renderer: Enhancement Active. Params: {enhance_params}")
            
            # Check Caching (Only if full resolution or shape matches cached data)
            # If target_shape is defined (Preview Mode), we might skip caching or use a separate cache?
            # For now, let's cache based on raw params match.
            # Warning: If 'data' is already downsampled (in Preview), we shouldn't mix it with full-res cache.
            
            use_cache = False
            # Only cache if we are working on full raw data (not downsampled preview)
            # OR if we handle cache invalidation properly.
            # Ideally, 'channel._cached_enhanced_data' stores the FULL RES enhanced image.
            # If we are in preview mode, we should probably NOT write to that cache, or use a separate preview cache.
            # But render_channel receives 'data' which might be downsampled.
            
            is_full_res = (data.shape == channel.raw_data.shape)
            
            if is_full_res:
                if (getattr(channel, '_last_enhance_params', None) == enhance_params and 
                    getattr(channel, '_cached_enhanced_data', None) is not None):
                    processed_data = channel._cached_enhanced_data
                    use_cache = True
                    # print(f"[{time.strftime('%H:%M:%S')}] Renderer: Cache Hit for {channel.name}")
            
            if not use_cache:
                # 1. CLAHE (Local Contrast)
                if enhance_params.get('clahe_enabled', False):
                    clip = enhance_params.get('clahe_clip', 0.01)
                    tile = enhance_params.get('clahe_tile', 8)
                    processed_data = EnhanceProcessor.apply_clahe(processed_data, clip, tile)
                    
                # 2. Stage 2: Real-time Enhance (Percentile, Bilateral, Wavelet)
                # This handles Contrast Stretching, Bilateral Filter, Wavelet Denoising
                processed_data = EnhanceProcessor.process_scientific_pipeline(processed_data, enhance_params)
                
                # 3. Median Filter (Denoise)
                if enhance_params.get('median_enabled', False):
                    k = enhance_params.get('median_kernel', 3)
                    processed_data = EnhanceProcessor.apply_median_filter(processed_data, k)
                    
                # Update Cache (Only for full res)
                if is_full_res:
                    channel._cached_enhanced_data = processed_data
                    channel._last_enhance_params = enhance_params.copy()
            
        t_enhance_end = time.time()
            
        # --- Display Mapping (LUT or RGB Direct) ---
        
        # Determine effective Gamma for LUT
        lut_gamma = settings.gamma
        
        t_map_start = time.time()
        
        # RGB Direct Path (for Brightfield/Reference)
        if getattr(channel, 'is_rgb', False):
             # USER REQUEST: For fluorescence analysis/display, RGB should often be treated as intensity.
             # If a color tint is applied (not white), we assume it's a single channel encoded as RGB.
             # We convert to grayscale first to capture all intensity, then tint.
             r, g, b = Renderer.hex_to_rgb(settings.color)
             
             if (r, g, b) != (1.0, 1.0, 1.0):
                  # Convert to grayscale using Max Projection (Defect Fix: No weighted mixing)
                  if processed_data.ndim == 3 and processed_data.shape[2] in (3, 4):
                       processed_data = np.max(processed_data[..., :3], axis=2)
                       # Now it's 2D, fallback to standard intensity path below
                       # (We don't return here, let it fall through to Fallback path)
                  else:
                       # Already 2D or something else, proceed with tinting
                       pass
             
             if getattr(channel, 'is_rgb', False) and processed_data.ndim == 3:
                  # If still RGB (e.g. white tint or conversion skipped)
                  if OPENCL_AVAILABLE:
                    # Use OpenCL-friendly way to normalize and clip
                    data_u = cv2.UMat(processed_data.astype(np.float32))
                    rng = float(settings.max_val - settings.min_val)
                    if rng < 1e-6: rng = 1e-6
                    
                    # mapped = (data - min) / rng
                    mapped_data_u = cv2.subtract(data_u, float(settings.min_val))
                    mapped_data_u = cv2.multiply(mapped_data_u, 1.0 / rng)
                    
                    # Convert to numpy for clipping and gamma (OpenCL scalars are tricky in cv2)
                    mapped_data = mapped_data_u.get()
                    np.clip(mapped_data, 0.0, 1.0, out=mapped_data)
                    
                    if abs(lut_gamma - 1.0) > 0.01:
                        np.power(mapped_data, 1.0 / lut_gamma, out=mapped_data)
                    else:
                        data_f = processed_data.astype(np.float32)
                        rng = settings.max_val - settings.min_val
                        if rng < 1e-6: rng = 1e-6
                        mapped_data = (data_f - settings.min_val) / rng
                        np.clip(mapped_data, 0.0, 1.0, out=mapped_data)
                        if abs(lut_gamma - 1.0) > 0.01:
                          np.power(mapped_data, 1.0 / lut_gamma, out=mapped_data)
                      
                  # Tint
                  if (r, g, b) != (1.0, 1.0, 1.0):
                       tint = np.array([r, g, b], dtype=np.float32)
                       mapped_data = mapped_data[..., :3] * tint
                       
                  t_map_end = time.time()
                  print(f"[{time.strftime('%H:%M:%S')}] Renderer (RGB): Shape {data.shape} -> {processed_data.shape} | OpenCL: {is_opencl_enabled()} | Resize: {t_prep-t0:.4f}s | Enhance: {t_enhance_end-t_enhance_start:.4f}s | Map: {t_map_end-t_map_start:.4f}s")
                  return mapped_data
        
        # FAST PATH: Integer -> RGB LUT (uint8 or uint16)
        if processed_data.dtype in (np.uint8, np.uint16):
            # --- Defect 3 Fix: Dynamic LUT Bitdepth Adaptation ---
            # We adapt the LUT size to the actual data range to save memory 
            # and avoid truncation for high bit-depths.
            d_max = np.max(processed_data)
            lut_size = int(d_max) + 1
            
            # Safety: Ensure at least 256 for uint8/uint16 logic
            if lut_size < 256: lut_size = 256
            
            # Cap at 65536 for uint16 compatibility in many libraries
            if processed_data.dtype == np.uint16 and lut_size > 65536:
                lut_size = 65536
            
            # Generate LUT with requested depth
            lut = Renderer.generate_rgb_lut(settings.min_val, settings.max_val, lut_gamma, settings.color, lut_size=lut_size, out_depth=out_depth)
            
            # Apply LUT (Advanced Indexing) -> (H, W, 3)
            rgb_mapped = lut[processed_data]
            
            t_map_end = time.time()
            print(f"[{time.strftime('%H:%M:%S')}] Renderer (LUT): Shape {data.shape} -> {processed_data.shape} (dtype: {processed_data.dtype}, out_depth: {out_depth}) | Resize: {t_prep-t0:.4f}s | Map(LUT): {t_map_end-t_map_start:.4f}s")
            
            # Convert to float32 (normalized) for composition compatibility
            # We scale to 0-1 based on the output depth used in LUT
            max_val_out = 255.0 if out_depth == 8 else 65535.0
            return rgb_mapped.astype(np.float32) / max_val_out
            
        # Fallback for non-uint16 (Float data from filters or uint8)
        data_f = processed_data.astype(np.float32)
        rng = settings.max_val - settings.min_val
        if rng < 1e-6: rng = 1e-6
        mapped_data = (data_f - settings.min_val) / rng
        np.clip(mapped_data, 0.0, 1.0, out=mapped_data)
        
        # Apply Gamma if not done yet
        if abs(lut_gamma - 1.0) > 0.01:
            np.power(mapped_data, 1.0 / lut_gamma, out=mapped_data)

        # Colorize
        r, g, b = Renderer.hex_to_rgb(settings.color)
        tint = np.array([r, g, b], dtype=np.float32)
        
        result = None
        if mapped_data.ndim == 2:
            result = mapped_data[..., np.newaxis] * tint
        elif mapped_data.ndim == 3:
             if mapped_data.shape[2] == 1:
                 result = mapped_data * tint
             else:
                 result = mapped_data # Should have been handled by RGB path
        
        t_map_end = time.time()
        # print(f"[{time.strftime('%H:%M:%S')}] Renderer (Fallback): Shape {data.shape} -> {processed_data.shape} (dtype: {processed_data.dtype}) | Resize: {t_prep-t0:.4f}s | Enhance: {t_enhance_end-t_enhance_start:.4f}s | Map: {t_map_end-t_map_start:.4f}s")
        
        # Apply Scale Bar if enabled
        if scale_bar_settings and scale_bar_settings.enabled and result is not None:
            result = Renderer.apply_scale_bar(result, scale_bar_settings, original_size=channel.shape)
            
        # Apply Annotations if enabled
        if annotations and result is not None:
            result = Renderer.apply_annotations(result, annotations, original_size=channel.shape)
            
        # Result is already normalized float32 0-1
        return result

    @staticmethod
    def composite(channels: List[ImageChannel], target_shape: Tuple[int, int] = None, out_depth: int = 8, scale_bar_settings=None, annotations: List = None) -> np.ndarray:
        """
        Merges all visible channels into a single normalized float32 RGB image.
        out_depth: hints the renderer for individual channel rendering precision.
        """
        import time
        if target_shape is None and channels:
            for ch in channels:
                if not getattr(ch, 'is_placeholder', False):
                    target_shape = ch.shape
                    break
        
        if target_shape is None:
            return None
            
        # Accumulator
        # Use OpenCL UMat if available for faster blending
        if is_opencl_enabled():
            final_img_u = cv2.UMat(np.zeros((target_shape[0], target_shape[1], 3), dtype=np.float32))
        else:
            final_img = np.zeros((target_shape[0], target_shape[1], 3), dtype=np.float32)
        
        for ch in channels:
            if not ch.display_settings.visible:
                continue
                
            layer = Renderer.render_channel(ch, target_shape, out_depth=out_depth)
            if layer is not None:
                # Ensure layer is float32
                if layer.dtype != np.float32:
                    layer = layer.astype(np.float32)
                    
                # Ensure shape match
                if layer.shape[:2] != target_shape:
                    layer = cv2.resize(layer, (target_shape[1], target_shape[0]), interpolation=cv2.INTER_NEAREST)
                    
                if is_opencl_enabled():
                    # GPU Additive Blending
                    layer_u = cv2.UMat(layer)
                    final_img_u = cv2.add(final_img_u, layer_u)
                else:
                    # CPU Additive Blending
                    final_img += layer
                
        if is_opencl_enabled():
            final_img = final_img_u.get()
            
        # Clip to 0-1
        np.clip(final_img, 0.0, 1.0, out=final_img)
        
        # Apply Scale Bar if enabled
        if scale_bar_settings and scale_bar_settings.enabled:
            # Find original size from first valid channel
            orig_size = None
            for ch in channels:
                if not getattr(ch, 'is_placeholder', False):
                    orig_size = ch.shape
                    break
            final_img = Renderer.apply_scale_bar(final_img, scale_bar_settings, original_size=orig_size)
            
        # Apply Annotations if enabled
        if annotations:
            orig_size = None
            for ch in channels:
                if not getattr(ch, 'is_placeholder', False):
                    orig_size = ch.shape
                    break
            final_img = Renderer.apply_annotations(final_img, annotations, original_size=orig_size)
            
        return final_img

    @staticmethod
    def apply_scale_bar(image: np.ndarray, settings, original_size: Tuple[int, int] = None) -> np.ndarray:
        """
        Draws a scale bar on the image.
        image: normalized float32 RGB image (0.0 to 1.0).
        settings: ScaleBarSettings object.
        original_size: (H, W) of the original image to scale pixel_size correctly.
        """
        h, w = image.shape[:2]
        
        # Adjust pixel size if we are working on a downsampled image
        pixel_size = settings.pixel_size
        if original_size is not None:
            # Scale factor (e.g. 0.5 if image is half size)
            scale_w = w / original_size[1]
            pixel_size = pixel_size / scale_w # Effective pixel size increases as image shrinks
            
        if pixel_size <= 0: return image
        
        # Calculate bar length in pixels
        bar_len_px = int(settings.bar_length_um / pixel_size)
        if bar_len_px <= 0 or bar_len_px > w: return image
        
        # Color
        color_rgb = Renderer.hex_to_rgb(settings.color)
        
        # Position
        margin = settings.margin
        thickness = settings.thickness
        
        if "Bottom Right" in settings.position:
            x1 = w - margin - bar_len_px
            y1 = h - margin - thickness
        elif "Bottom Left" in settings.position:
            x1 = margin
            y1 = h - margin - thickness
        elif "Top Right" in settings.position:
            x1 = w - margin - bar_len_px
            y1 = margin
        elif "Top Left" in settings.position:
            x1 = margin
            y1 = margin
        else:
            x1, y1 = margin, margin
            
        x2 = x1 + bar_len_px
        y2 = y1 + thickness
        
        # Draw the bar (directly on the float32 image)
        image[y1:y2, x1:x2] = color_rgb
        
        # Draw Label
        if settings.show_label:
            label = f"{settings.bar_length_um} um"
            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = settings.font_size / 30.0
            
            # Get text size
            (tw, th), baseline = cv2.getTextSize(label, font, font_scale, 1)
            
            # Label position (centered above or below the bar)
            tx = x1 + (bar_len_px - tw) // 2
            if "Bottom" in settings.position:
                ty = y1 - 10 # Above the bar
            else:
                ty = y2 + th + 10 # Below the bar
                
            # OpenCV putText expects uint8 or float32. 
            # For float32, it expects values in 0-1 if the image is in 0-1.
            cv2.putText(image, label, (tx, ty), font, font_scale, color_rgb, 1, cv2.LINE_AA)
            
        return image

    @staticmethod
    def apply_annotations(image: np.ndarray, annotations: List, original_size: Tuple[int, int] = None) -> np.ndarray:
        """
        Draws graphic annotations on the image.
        image: normalized float32 RGB image (0.0 to 1.0).
        annotations: List of GraphicAnnotation objects.
        original_size: (H, W) of the original image to scale coordinates correctly.
        """
        if not annotations:
            return image
            
        h, w = image.shape[:2]
        
        # Scale factor if image is downsampled
        scale_x, scale_y = 1.0, 1.0
        if original_size is not None:
            scale_y = h / original_size[0]
            scale_x = w / original_size[1]
            
        for ann in annotations:
            if not ann.visible:
                continue
                
            color = Renderer.hex_to_rgb(ann.color)
            thickness = int(ann.thickness * scale_x)
            if thickness < 1: thickness = 1
            
            # Convert points from original coordinate space to current image space
            pts = []
            for px, py in ann.points:
                pts.append((int(px * scale_x), int(py * scale_y)))
                
            if not pts:
                continue
                
            if ann.type == 'arrow':
                if len(pts) >= 2:
                    start, end = pts[0], pts[1]
                    
                    # Properties
                    head_shape = ann.properties.get('arrow_head_shape', 'open')
                    head_size = float(ann.properties.get('arrow_head_size', 15.0)) * scale_x
                    
                    # Calculate geometry
                    import math
                    dx = end[0] - start[0]
                    dy = end[1] - start[1]
                    angle = math.atan2(dy, dx)
                    
                    # Draw Shaft
                    cv2.line(image, start, end, color, thickness, cv2.LINE_AA)
                    
                    # Draw Head
                    if head_shape == 'open':
                        arrow_angle = math.pi / 6
                        p1_x = end[0] - head_size * math.cos(angle - arrow_angle)
                        p1_y = end[1] - head_size * math.sin(angle - arrow_angle)
                        p2_x = end[0] - head_size * math.cos(angle + arrow_angle)
                        p2_y = end[1] - head_size * math.sin(angle + arrow_angle)
                        
                        p1 = (int(p1_x), int(p1_y))
                        p2 = (int(p2_x), int(p2_y))
                        
                        cv2.line(image, end, p1, color, thickness, cv2.LINE_AA)
                        cv2.line(image, end, p2, color, thickness, cv2.LINE_AA)
                        
                    elif head_shape == 'triangle':
                        arrow_angle = math.pi / 6
                        p1_x = end[0] - head_size * math.cos(angle - arrow_angle)
                        p1_y = end[1] - head_size * math.sin(angle - arrow_angle)
                        p2_x = end[0] - head_size * math.cos(angle + arrow_angle)
                        p2_y = end[1] - head_size * math.sin(angle + arrow_angle)
                        
                        p1 = (int(p1_x), int(p1_y))
                        p2 = (int(p2_x), int(p2_y))
                        
                        points = np.array([end, p1, p2], np.int32)
                        cv2.fillPoly(image, [points], color, lineType=cv2.LINE_AA)
                        
                    elif head_shape == 'diamond':
                        w = head_size * 0.5
                        # Back point
                        pb_x = end[0] - head_size * math.cos(angle)
                        pb_y = end[1] - head_size * math.sin(angle)
                        
                        # Mid point for width
                        pm_x = (end[0] + pb_x) / 2
                        pm_y = (end[1] + pb_y) / 2
                        
                        perp_angle = angle + math.pi/2
                        pl_x = pm_x + w * math.cos(perp_angle)
                        pl_y = pm_y + w * math.sin(perp_angle)
                        pr_x = pm_x - w * math.cos(perp_angle)
                        pr_y = pm_y - w * math.sin(perp_angle)
                        
                        p_back = (int(pb_x), int(pb_y))
                        p_left = (int(pl_x), int(pl_y))
                        p_right = (int(pr_x), int(pr_y))
                        
                        points = np.array([end, p_left, p_back, p_right], np.int32)
                        cv2.fillPoly(image, [points], color, lineType=cv2.LINE_AA)
                        
                    elif head_shape == 'circle':
                        radius = int(head_size / 2)
                        # Center at end - radius? Or center at end? 
                        # Consistent with CanvasView: Center at end
                        # Wait, CanvasView code I wrote used center at end-radius?
                        # Let's check.
                        # CanvasView: head.addEllipse(end.x() - radius, end.y() - radius, ...)
                        # That centers the circle AT `end`.
                        # So here we use `end` as center.
                        cv2.circle(image, end, radius, color, -1, cv2.LINE_AA) # -1 for fill
                        
            elif ann.type == 'line':
                if len(pts) >= 2:
                    cv2.line(image, pts[0], pts[1], color, thickness, cv2.LINE_AA)
            elif ann.type == 'rect':
                if len(pts) >= 2:
                    cv2.rectangle(image, pts[0], pts[1], color, thickness, cv2.LINE_AA)
            elif ann.type == 'circle':
                if len(pts) >= 2:
                    # pts[0] is center, pts[1] is a point on the circumference
                    import math
                    center = pts[0]
                    radius = int(math.sqrt((pts[1][0] - pts[0][0])**2 + (pts[1][1] - pts[0][1])**2))
                    cv2.circle(image, center, radius, color, thickness, cv2.LINE_AA)
            elif ann.type == 'polygon' or ann.type == 'roi_ref':
                if len(pts) >= 2:
                    pts_np = np.array(pts, np.int32).reshape((-1, 1, 2))
                    cv2.polylines(image, [pts_np], True, color, thickness, cv2.LINE_AA)
            elif ann.type == 'ellipse':
                if len(pts) >= 2:
                    # Bounding box approach: pts[0] and pts[1] are corners
                    c_x = (pts[0][0] + pts[1][0]) // 2
                    c_y = (pts[0][1] + pts[1][1]) // 2
                    axes = (abs(pts[1][0] - pts[0][0]) // 2, abs(pts[1][1] - pts[0][1]) // 2)
                    cv2.ellipse(image, (c_x, c_y), axes, 0, 0, 360, color, thickness, cv2.LINE_AA)
            elif ann.type == 'text':
                if pts and ann.text:
                    font = cv2.FONT_HERSHEY_SIMPLEX
                    font_scale = (ann.font_size / 30.0) * scale_x
                    cv2.putText(image, ann.text, pts[0], font, font_scale, color, thickness, cv2.LINE_AA)
                    
        return image
