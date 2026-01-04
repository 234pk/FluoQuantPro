import numpy as np
import cv2
from typing import List, Dict, Optional, Tuple
from src.core.data_model import ImageChannel
from src.core.roi_model import ROI
from src.core.algorithms import qpath_to_mask

class MeasureEngine:
    """
    Core engine for multi-channel ROI measurement and analysis.
    Supports raw data extraction, background subtraction, and stats calculation.
    """
    
    def __init__(self):
        pass
        
    def _create_ring_mask(self, mask: np.ndarray, width: int = 5) -> np.ndarray:
        """
        Creates a ring mask surrounding the ROI mask for local background calculation.
        """
        # Ensure mask is boolean or uint8
        if mask.dtype == bool:
            mask_uint8 = mask.astype(np.uint8) * 255
        else:
            mask_uint8 = mask
            
        # Dilate to create the outer boundary
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (width * 2 + 1, width * 2 + 1))
        dilated = cv2.dilate(mask_uint8, kernel, iterations=1)
        
        # Ring = Dilated - Original
        ring = cv2.subtract(dilated, mask_uint8)
        
        return ring > 0

    def measure_batch(self, rois: List[ROI], channels: List[ImageChannel], 
                     pixel_size: float = 1.0, 
                     bg_method: str = 'none',
                     bg_ring_width: int = 5) -> List[Dict]:
        """
        Batch measures multiple ROIs.
        Returns a list of dictionaries containing stats for each ROI.
        """
        results = []
        for roi in rois:
            # Skip non-measurable types if any (though calling code should filter)
            if roi.roi_type == 'line_scan':
                continue
                
            stats = self.measure_roi(roi, channels, pixel_size, bg_method, bg_ring_width)
            
            row_data = {
                "ROI_ID": roi.id,
                "Label": roi.label,
                "Area": stats.get('Area', 0.0)
            }
            row_data.update(stats)
            results.append(row_data)
            
        return results

    def measure_roi(self, roi: ROI, channels: List[ImageChannel], 
                   pixel_size: float = 1.0, 
                   bg_method: str = 'none',
                   bg_ring_width: int = 5) -> Dict[str, float]:
        """
        Calculates intensity statistics for an ROI across all provided channels.
        
        Args:
            roi: The ROI object.
            channels: List of ImageChannel objects (Raw 16-bit/32-bit).
            pixel_size: Physical size of one pixel (default 1.0).
            bg_method: 'none', 'global_min', 'local_ring'.
            bg_ring_width: Width of the background ring in pixels (for local_ring).
            
        Returns:
            Dictionary of stats.
        """
        if not channels:
            return {}
            
        # 1. Rasterize ROI to Mask
        # Assume all channels have same shape
        ref_shape = channels[0].shape
        mask = qpath_to_mask(roi.path, ref_shape)
        
        # Count pixels
        pixel_count = np.sum(mask)
        if pixel_count == 0:
            return {'Area': 0.0}
            
        stats = {
            'Area': float(pixel_count * (pixel_size ** 2)),
            'PixelCount': float(pixel_count)
        }
        
        # 2. Prepare Background Mask (if needed)
        bg_mask = None
        if bg_method == 'local_ring':
            bg_mask = self._create_ring_mask(mask, bg_ring_width)
            
        # 3. Iterate channels
        for i, ch in enumerate(channels):
            # Extract ROI pixels (Raw Data)
            # Ensure grayscale for RGB inputs to get consistent intensity
            data = ColocalizationEngine._ensure_grayscale(ch.raw_data)
            
            # Check if mask shape matches data shape (handle RGB vs Gray mismatch)
            # Use a local mask variable to avoid polluting the loop or causing issues
            current_mask = mask
            if current_mask.shape != data.shape:
                # Regenerate mask for this specific data shape
                try:
                    current_mask = qpath_to_mask(roi.path, data.shape)
                except Exception as e:
                    print(f"Error regenerating mask for shape {data.shape}: {e}")
                    # Fallback: if regeneration fails, we might crash next line, but better to log
            
            try:
                roi_pixels = data[current_mask]
            except IndexError:
                 print(f"IndexError in measure_roi: data {data.shape}, mask {current_mask.shape}")
                 # Last resort fallback: resize mask (slow/inaccurate but prevents crash)
                 if current_mask.shape != data.shape:
                     import cv2
                     # Convert boolean mask to uint8, resize, back to boolean
                     m_uint8 = current_mask.astype(np.uint8) * 255
                     m_resized = cv2.resize(m_uint8, (data.shape[1], data.shape[0]), interpolation=cv2.INTER_NEAREST)
                     current_mask = m_resized > 127
                     roi_pixels = data[current_mask]
                 else:
                     raise

            if roi_pixels.size == 0:
                print(f"Warning: Empty ROI pixels for channel {ch_name}")
                stats[f"{ch_name}_Mean"] = 0.0
                stats[f"{ch_name}_IntDen"] = 0.0
                stats[f"{ch_name}_Min"] = 0.0
                stats[f"{ch_name}_Max"] = 0.0
                stats[f"{ch_name}_BgMean"] = 0.0
                stats[f"{ch_name}_CorrectedMean"] = 0.0
                continue
            
            ch_name = ch.name if ch.name else f"Ch{i+1}"
            
            # Simple stats
            stats[f"{ch_name}_Mean"] = float(np.mean(roi_pixels))
            stats[f"{ch_name}_IntDen"] = float(np.sum(roi_pixels))
            stats[f"{ch_name}_Min"] = float(np.min(roi_pixels))
            stats[f"{ch_name}_Max"] = float(np.max(roi_pixels))
            
            # Background Correction
            bg_val = 0.0
            if bg_mask is not None:
                try:
                     bg_pixels = data[bg_mask]
                     if bg_pixels.size > 0:
                         bg_val = np.mean(bg_pixels)
                except:
                     pass
            
            stats[f"{ch_name}_BgMean"] = float(bg_val)
            stats[f"{ch_name}_CorrectedMean"] = float(stats[f"{ch_name}_Mean"] - bg_val)
            
        return stats

def calculate_channel_stats(data: np.ndarray) -> dict:
    """
    Calculates basic statistics for a channel's raw data.
    Used for auto-contrast and histogram.
    """
    if data is None or data.size == 0:
        return {'min': 0, 'max': 0, 'mean': 0, 'std': 0}
        
    return {
        'min': float(np.min(data)),
        'max': float(np.max(data)),
        'mean': float(np.mean(data)),
        'std': float(np.std(data))
    }

class ColocalizationEngine:
    """
    Engine for colocalization analysis between two channels.
    Calculates Pearson's Correlation Coefficient (PCC) and Mander's Overlap Coefficients (MOC).
    """
    
    @staticmethod
    def _ensure_grayscale(data: np.ndarray) -> np.ndarray:
        """Converts RGB/RGBA data to grayscale if necessary using Max Projection (No weighted mixing)."""
        if data.ndim == 3:
            # Handle RGB/RGBA via Max Projection to preserve scientific intensity integrity
            if data.shape[2] in (3, 4):
                # Using max across channels instead of weighted average (0.299R + 0.587G + 0.114B)
                # as requested for scientific rigor in fluorescence analysis.
                return np.max(data[..., :3], axis=2)
            elif data.shape[2] == 1:
                return data[..., 0]
        return data

    @staticmethod
    def calculate_pcc(ch1_data: np.ndarray, ch2_data: np.ndarray, mask: Optional[np.ndarray] = None) -> float:
        """Calculates Pearson Correlation Coefficient."""
        # Ensure grayscale for RGB inputs
        ch1_gray = ColocalizationEngine._ensure_grayscale(ch1_data)
        ch2_gray = ColocalizationEngine._ensure_grayscale(ch2_data)

        if mask is not None:
            c1 = ch1_gray[mask].astype(np.float64)
            c2 = ch2_gray[mask].astype(np.float64)
        else:
            c1 = ch1_gray.flatten().astype(np.float64)
            c2 = ch2_gray.flatten().astype(np.float64)
            
        if c1.size < 2:
            return 0.0
            
        # Pearson formula
        mu1 = np.mean(c1)
        mu2 = np.mean(c2)
        
        num = np.sum((c1 - mu1) * (c2 - mu2))
        den = np.sqrt(np.sum((c1 - mu1)**2) * np.sum((c2 - mu2)**2))
        
        if den < 1e-9:
            return 0.0
        return float(num / den)

    @staticmethod
    def calculate_manders(ch1_data: np.ndarray, ch2_data: np.ndarray, 
                          mask: Optional[np.ndarray] = None,
                          threshold1: float = 0.0, threshold2: float = 0.0) -> Tuple[float, float]:
        """
        Calculates Mander's Overlap Coefficients M1 and M2.
        M1: Fraction of Ch1 that overlaps with Ch2.
        M2: Fraction of Ch2 that overlaps with Ch1.
        """
        # Ensure grayscale for RGB inputs
        ch1_gray = ColocalizationEngine._ensure_grayscale(ch1_data)
        ch2_gray = ColocalizationEngine._ensure_grayscale(ch2_data)

        if mask is not None:
            c1 = ch1_gray[mask].astype(np.float64)
            c2 = ch2_gray[mask].astype(np.float64)
        else:
            c1 = ch1_gray.flatten().astype(np.float64)
            c2 = ch2_gray.flatten().astype(np.float64)
            
        if c1.size == 0:
            return 0.0, 0.0
            
        # Total Intensities
        sum1 = np.sum(c1)
        sum2 = np.sum(c2)
        
        if sum1 < 1e-9 or sum2 < 1e-9:
            return 0.0, 0.0
            
        # Colocalized Intensities (Above Threshold)
        # M1 = sum(C1_i if C2_i > threshold2) / sum(C1_i)
        c1_coloc = c1[c2 > threshold2]
        m1 = np.sum(c1_coloc) / sum1
        
        # M2 = sum(C2_i if C1_i > threshold1) / sum(C2_i)
        c2_coloc = c2[c1 > threshold1]
        m2 = np.sum(c2_coloc) / sum2
        
        return float(m1), float(m2)

    @staticmethod
    def generate_coloc_image(ch1_data: np.ndarray, ch2_data: np.ndarray, 
                             threshold1: float, threshold2: float) -> np.ndarray:
        """
        Generates an 8-bit image showing overlap intensity.
        Overlap appears as Yellow (Red + Green).
        """
        # Ensure grayscale for RGB inputs
        ch1_gray = ColocalizationEngine._ensure_grayscale(ch1_data)
        ch2_gray = ColocalizationEngine._ensure_grayscale(ch2_data)

        # Normalize to 0-1
        def norm(d):
            mi, ma = d.min(), d.max()
            if ma - mi < 1e-6: return np.zeros_like(d, dtype=np.float32)
            return (d.astype(np.float32) - mi) / (ma - mi)
            
        n1 = norm(ch1_gray)
        n2 = norm(ch2_gray)
        
        # Apply thresholds (masking)
        mask1 = n1 > (threshold1 / 65535.0 if ch1_data.dtype == np.uint16 else threshold1 / 255.0)
        mask2 = n2 > (threshold2 / 65535.0 if ch2_data.dtype == np.uint16 else threshold2 / 255.0)
        
        # Create RGB: R=Ch1, G=Ch2, B=0
        h, w = ch1_data.shape[:2]
        res = np.zeros((h, w, 3), dtype=np.uint8)
        
        # Show only pixels above thresholds? 
        # Usually it's better to show everything but highlight overlap.
        # Let's show everything.
        res[..., 0] = (n1 * 255).astype(np.uint8)
        res[..., 1] = (n2 * 255).astype(np.uint8)
        
        # We can use the Blue channel to specifically highlight pixels where BOTH are above threshold
        # or just let R+G = Yellow speak for itself.
        # Scientific choice: Overlap mask in Blue? 
        # colocalized_mask = mask1 & mask2
        # res[colocalized_mask, 2] = 128 # Add some blue to make it stand out as white-ish?
        
        return res

# Helper function for backward compatibility
def calculate_intensity_stats(roi: ROI, channels: List[ImageChannel]) -> Dict[str, float]:
    """
    Calculates intensity statistics for a given ROI across all visible channels.
    
    Scientific Rigor Notes:
    1. Full-Resolution Analysis: The ROI is automatically mapped from display 
       coordinates back to full-resolution space using its internal path 
       reconstruction logic. Analysis is performed on the raw_data (full-res).
    2. Sub-pixel Accuracy: Coordinate mapping uses floating-point precision 
       to ensure that ROIs drawn on downsampled displays retain their intended 
       geometry on the original data.
    3. Signal-Aware Statistics: Provides Area, Mean, Min, Max, and Integrated 
       Density (IntDen) for each channel independently.
    """
    engine = MeasureEngine()
    return engine.measure_roi(roi, channels)
