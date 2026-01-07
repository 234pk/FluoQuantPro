import numpy as np
import cv2
from PySide6.QtGui import QPainterPath, QImage, QPainter, QBrush
from PySide6.QtCore import Qt

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

def magic_wand_2d(image: np.ndarray, seed_point: tuple, tolerance: float, smoothing: float = 1.0, relative: bool = False) -> np.ndarray:
    """
    Performs flood fill segmentation starting from a seed point.
    
    Args:
        image: Input image (2D or 3D numpy array).
        seed_point: (x, y) tuple.
        tolerance: Sensitivity for intensity matching.
        smoothing: Sigma for Gaussian blur before flood-filling.
        relative: If True, tolerance is treated as a percentage of the seed pixel value.
    
    Returns: Boolean numpy array (H, W).
    """
    # Handle dimensionality. If 3D (e.g. RGB or Z-stack), flatten to 2D for processing.
    if image.ndim == 3:
        # If it's RGB/RGBA (3 or 4 channels), use Max Projection instead of weighted average
        # to preserve signal integrity (scientific requirement).
        if image.shape[2] in (3, 4):
            work_img = np.max(image[..., :3], axis=2)
        else:
            # Use max projection for other multi-channel/Z-stacks
            work_img = np.max(image, axis=2)
        h, w = work_img.shape
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
    if work_img.dtype == np.uint16:
        work_img = work_img.astype(np.float32)
        
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
        lo_diff = seed_val * (tolerance / 100.0)
        up_diff = seed_val * (tolerance / 100.0)
        
    # Run floodFill
    cv2.floodFill(work_img, mask_cv, (x, y), 255, loDiff=lo_diff, upDiff=up_diff, flags=flags)
    
    # Crop mask to match image size (remove 1px border)
    mask = mask_cv[1:-1, 1:-1].astype(bool)
    
    return mask

def mask_to_qpath(mask: np.ndarray, simplify_epsilon: float = 1.0) -> QPainterPath:
    """
    Converts a boolean mask to a QPainterPath (Vector).
    Uses cv2.findContours and cv2.approxPolyDP.
    
    Args:
        mask: Boolean array or uint8 (0/255).
        simplify_epsilon: Max distance from original curve (Douglas-Peucker).
                          Higher = simpler, smoother shapes.
    """
    if mask.dtype == bool:
        mask_uint8 = mask.astype(np.uint8) * 255
    else:
        mask_uint8 = mask.astype(np.uint8)

    # Find external contours only for now (handle holes later with RETR_CCOMP if needed)
    contours, _ = cv2.findContours(mask_uint8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    path = QPainterPath()
    
    for cnt in contours:
        # Simplify contour
        if simplify_epsilon > 0:
            epsilon = simplify_epsilon
            cnt = cv2.approxPolyDP(cnt, epsilon, True)
            
        if len(cnt) < 3:
            continue
            
        # cnt has shape (N, 1, 2) -> (x, y)
        points = cnt[:, 0, :]
        
        path.moveTo(points[0][0], points[0][1])
        for i in range(1, len(points)):
            path.lineTo(points[i][0], points[i][1])
        path.closeSubpath()
        
    return path

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
