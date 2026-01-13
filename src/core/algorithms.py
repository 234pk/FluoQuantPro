import numpy as np
import cv2
from PySide6.QtGui import QPainterPath, QImage, QPainter, QBrush
from PySide6.QtCore import Qt
from typing import Optional, List, Tuple

def qpath_to_mask(path: QPainterPath, shape: tuple) -> np.ndarray:
    """
    Rasterizes a QPainterPath into a boolean numpy mask.
    
    Args:
        path: The vector path.
        shape: (H, W) tuple of the target image dimensions.
    """
    h, w = shape
    if w <= 0 or h <= 0:
        return np.zeros((0, 0), dtype=bool)

    # Format_Grayscale8 is 1 byte per pixel
    img = QImage(w, h, QImage.Format.Format_Grayscale8)
    if img.isNull():
        from src.core.logger import Logger
        Logger.error(f"Failed to allocate QImage of size {w}x{h}")
        return np.zeros(shape, dtype=bool)
        
    img.fill(0)
    
    painter = QPainter(img)
    if not painter.isActive():
        from src.core.logger import Logger
        Logger.error("Failed to start QPainter on mask image")
        return np.zeros(shape, dtype=bool)

    # Disable Antialiasing for strict binary mask (center rule usually)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(Qt.GlobalColor.white))
    painter.drawPath(path)
    painter.end()
    
    # Convert to numpy
    # constBits() returns a pointer to the first pixel data
    # IMPORTANT: We must ensure img stays alive while we access ptr
    ptr = img.constBits()
    bpl = img.bytesPerLine()
    
    # Create numpy array from the buffer
    # We make an immediate copy to avoid lifetime issues with the QImage buffer
    try:
        # Create a view first, then copy
        arr = np.array(ptr).reshape((h, bpl)).copy()
    except Exception as e:
        from src.core.logger import Logger
        Logger.error(f"Error converting QImage to numpy: {e}")
        return np.zeros(shape, dtype=bool)
    
    # Crop padding if bytes_per_line > width
    if bpl > w:
        arr = arr[:, :w]
        
    return arr > 127

def magic_wand_2d(image: np.ndarray, seed_point: tuple, tolerance: float, smoothing: float = 1.0, relative: bool = False, channel_name: Optional[str] = None) -> np.ndarray:
    """
    Performs flood fill segmentation starting from a seed point.
    
    Args:
        image: Input image (2D or 3D numpy array).
        seed_point: (x, y) tuple.
        tolerance: Sensitivity for intensity matching.
        smoothing: Sigma for Gaussian blur before flood-filling.
        relative: If True, tolerance is treated as a percentage of the seed pixel value.
        channel_name: Optional biological channel name for mapping-aware grayscale conversion.
    
    Returns: Boolean numpy array (H, W).
    """
    # Handle dimensionality. If 3D (e.g. RGB or Z-stack), optionally flatten or keep as RGB.
    if image.ndim == 3:
        # Use mapping-aware extraction if channel name is provided
        if channel_name:
            from src.core.image_loader import ImageLoader
            work_img = ImageLoader.extract_channel_data(image, channel_name)
        else:
            # Fallback: If it's a standard RGB, we can either keep it or flatten it.
            # OpenCV's floodFill supports 3-channel images.
            # However, for consistency with single-channel tools, we might still want to flatten
            # UNLESS the user explicitly wants RGB-based segmentation.
            # User requested "Use RGB data", which might mean using the 3-channel info.
            if image.shape[2] in (3, 4):
                # Keep as RGB (3 channels) if it's a display array
                work_img = image[..., :3].copy()
            else:
                # Z-stack or other 3D: Use Max Projection
                work_img = np.max(image, axis=2)
        
        h, w = work_img.shape[:2]
    else:
        h, w = image.shape
        work_img = image.copy()

    x, y = seed_point
    
    if x < 0 or x >= w or y < 0 or y >= h:
        return np.zeros((h, w), dtype=bool)
        
    mask_cv = np.zeros((h + 2, w + 2), dtype=np.uint8)
    
    # 4 connectivity (4) | Fixed range (FLOODFILL_FIXED_RANGE) | Mask only (FLOODFILL_MASK_ONLY)
    flags = 4 | cv2.FLOODFILL_FIXED_RANGE | cv2.FLOODFILL_MASK_ONLY | (255 << 8)
    
    # Ensure data type is compatible with OpenCV floodFill (uint8, uint16, float32)
    # OpenCV floodFill supports 8-bit and 32-bit float images.
    if work_img.dtype == np.uint16:
        work_img = work_img.astype(np.float32)
    elif work_img.dtype == bool:
        work_img = work_img.astype(np.uint8) * 255
        
    # Apply smoothing
    if smoothing > 0:
        kernel_size = int(2 * round(3 * smoothing) + 1)
        if kernel_size % 2 == 0: kernel_size += 1
        work_img = cv2.GaussianBlur(work_img, (kernel_size, kernel_size), smoothing)
    
    # Calculate absolute diffs
    lo_diff = tolerance
    up_diff = tolerance
    
    if relative:
        seed_val = work_img[y, x]
        # For RGB, seed_val is an array. lo_diff/up_diff will also be arrays.
        lo_diff = seed_val * (tolerance / 100.0)
        up_diff = seed_val * (tolerance / 100.0)
    
    # If RGB, lo_diff/up_diff must be a scalar or a tuple/list of length 3
    if work_img.ndim == 3 and not isinstance(lo_diff, (list, tuple, np.ndarray)):
        lo_diff = (lo_diff, lo_diff, lo_diff)
        up_diff = (up_diff, up_diff, up_diff)
        
    # Run floodFill
    # Note: loDiff/upDiff can be scalars or tuples
    cv2.floodFill(work_img, mask_cv, (x, y), 255, loDiff=lo_diff, upDiff=up_diff, flags=flags)
    
    # Crop mask to match image size (remove 1px border)
    mask = mask_cv[1:-1, 1:-1].astype(bool)
    
    return mask

def mask_to_qpath(mask: np.ndarray, simplify_epsilon: float = 1.0, smooth: bool = False) -> QPainterPath:
    """
    Converts a boolean mask to a QPainterPath (Vector).
    Uses cv2.findContours and cv2.approxPolyDP.
    
    Args:
        mask: Boolean array or uint8 (0/255).
        simplify_epsilon: Max distance from original curve (Douglas-Peucker).
                          Higher = simpler, smoother shapes.
        smooth: If True, uses cubic splines for even smoother appearance.
    """
    if mask.dtype == bool:
        mask_uint8 = mask.astype(np.uint8) * 255
    else:
        mask_uint8 = mask.astype(np.uint8)

    # SMOOTHING: To make graphics more "round" and less jagged (staircase effect)
    # We apply a small blur and threshold to the mask itself before contour extraction
    if simplify_epsilon < 1.0 or smooth:
        # For small epsilon (high detail), staircase effects are very visible.
        # A tiny blur helps "round" the corners.
        k_size = 3 if not smooth else 5
        mask_uint8 = cv2.GaussianBlur(mask_uint8, (k_size, k_size), 0)
        _, mask_uint8 = cv2.threshold(mask_uint8, 128, 255, cv2.THRESH_BINARY)

    # Find external contours only for now
    contours, _ = cv2.findContours(mask_uint8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    path = QPainterPath()
    
    # If smooth is requested, we might need the smooth path generator
    # To avoid circular imports, we'll implement a simple version here or import locally
    smooth_func = None
    if smooth:
        try:
            from src.core.roi_model import create_smooth_path_from_points
            smooth_func = create_smooth_path_from_points
        except ImportError:
            pass

    for cnt in contours:
        # Simplify contour
        if simplify_epsilon > 0:
            cnt = cv2.approxPolyDP(cnt, simplify_epsilon, True)
            
        if len(cnt) < 3:
            continue
            
        # cnt has shape (N, 1, 2) -> (x, y)
        points = cnt[:, 0, :]
        
        if smooth and smooth_func:
            from PySide6.QtCore import QPointF
            qpoints = [QPointF(float(p[0]), float(p[1])) for p in points]
            sub_path = smooth_func(qpoints, closed=True)
            path.addPath(sub_path)
        else:
            path.moveTo(float(points[0][0]), float(points[0][1]))
            for i in range(1, len(points)):
                path.lineTo(float(points[i][0]), float(points[i][1]))
            path.closeSubpath()
        
    return path

def mask_to_qpaths(mask: np.ndarray, simplify_epsilon: float = 1.0, smooth: bool = False) -> list:
    if mask.dtype == bool:
        mask_uint8 = mask.astype(np.uint8) * 255
    else:
        mask_uint8 = mask.astype(np.uint8)

    # Apply smoothing if requested
    if simplify_epsilon < 1.0 or smooth:
        k_size = 3 if not smooth else 5
        mask_uint8 = cv2.GaussianBlur(mask_uint8, (k_size, k_size), 0)
        _, mask_uint8 = cv2.threshold(mask_uint8, 128, 255, cv2.THRESH_BINARY)

    contours, _ = cv2.findContours(mask_uint8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    paths = []
    
    smooth_func = None
    if smooth:
        try:
            from src.core.roi_model import create_smooth_path_from_points
            smooth_func = create_smooth_path_from_points
        except ImportError:
            pass

    for cnt in contours:
        if simplify_epsilon > 0:
            cnt = cv2.approxPolyDP(cnt, simplify_epsilon, True)
        if len(cnt) < 3:
            continue
            
        points = cnt[:, 0, :]
        path = QPainterPath()
        
        if smooth and smooth_func:
            from PySide6.QtCore import QPointF
            qpoints = [QPointF(float(p[0]), float(p[1])) for p in points]
            path = smooth_func(qpoints, closed=True)
        else:
            path.moveTo(float(points[0][0]), float(points[0][1]))
            for i in range(1, len(points)):
                path.lineTo(float(points[i][0]), float(points[i][1]))
            path.closeSubpath()
            
        paths.append(path)
    return paths

def bilinear_interpolate_numpy(img, x, y):
    """
    Vectorized bilinear interpolation for an array of (x, y) coordinates.
    """
    x0 = np.floor(x).astype(int)
    x1 = x0 + 1
    y0 = np.floor(y).astype(int)
    y1 = y0 + 1

    x0 = np.clip(x0, 0, img.shape[1] - 1)
    x1 = np.clip(x1, 0, img.shape[1] - 1)
    y0 = np.clip(y0, 0, img.shape[0] - 1)
    y1 = np.clip(y1, 0, img.shape[0] - 1)

    Ia = img[y0, x0]
    Ib = img[y1, x0]
    Ic = img[y0, x1]
    Id = img[y1, x1]

    wa = (x1 - x) * (y1 - y)
    wb = (x1 - x) * (y - y0)
    wc = (x - x0) * (y1 - y)
    wd = (x - x0) * (y - y0)

    return Ia * wa + Ib * wb + Ic * wc + Id * wd

def sample_line_profile(img, p1, p2, num_points=None):
    """
    Samples image intensity along a line from p1 to p2 using vectorized bilinear interpolation.
    p1, p2 are (x, y) coordinates.
    """
    if num_points is None:
        num_points = int(np.hypot(p2[0] - p1[0], p2[1] - p1[1])) + 1
    
    if num_points < 2:
        # Correctly handle boundary case
        y, x = int(np.clip(p1[1], 0, img.shape[0]-1)), int(np.clip(p1[0], 0, img.shape[1]-1))
        return np.array([img[y, x]])

    x_coords = np.linspace(p1[0], p2[0], num_points)
    y_coords = np.linspace(p1[1], p2[1], num_points)
    
    # Use vectorized version
    return bilinear_interpolate_numpy(img, x_coords, y_coords)
