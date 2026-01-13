import numpy as np
import cv2
from typing import Tuple

# --- GPU Acceleration (OpenCL) Support ---
def is_opencl_enabled():
    """Checks if OpenCL is both available and enabled in OpenCV."""
    try:
        return cv2.ocl.haveOpenCL() and cv2.ocl.useOpenCL()
    except:
        return False

try:
    from skimage import exposure, restoration
    SKIMAGE_AVAILABLE = True
except Exception:
    SKIMAGE_AVAILABLE = False

class EnhanceProcessor:
    """
    Handles image enhancement operations with scientific parameter mapping.
    Designed for 16-bit fluorescence microscopy images.
    """

    @staticmethod
    def estimate_signal_size(image: np.ndarray) -> int:
        """
        Estimates typical signal size (radius) for fluorescence structures.
        Uses image dimensions as a heuristic if no segmentation is performed.
        """
        if image is None: return 10
        h, w = image.shape[:2]
        # Heuristic: ~1/50 of image width, clamped to [10, 50]
        radius = int(max(h, w) / 50)
        return max(10, min(50, radius))

    @staticmethod
    def apply_signal_stretch(image: np.ndarray, low_p: float = 2.0, high_p: float = 98.0) -> np.ndarray:
        """
        Applies Percentile-based Intensity Rescaling (Signal Stretch).
        Optimized version using histograms for speed.
        """
        if image is None:
            return image
            
        # Ensure percentiles are within 0-100
        low_p = np.clip(low_p, 0, 100)
        high_p = np.clip(high_p, 0, 100)
        
        if low_p >= high_p:
            return image
            
        # Optimization: Use histogram to find percentiles (MUCH faster than np.percentile for large arrays)
        dtype = image.dtype
        if dtype == np.uint8:
            hist = cv2.calcHist([image], [0], None, [256], [0, 256])
            cum_hist = np.cumsum(hist) / image.size * 100.0
            low = np.searchsorted(cum_hist, low_p)
            high = np.searchsorted(cum_hist, high_p)
        elif dtype == np.uint16:
            # For 16-bit, use a larger histogram
            # Finding max for exact range
            i_max = int(np.max(image))
            hist = cv2.calcHist([image], [0], None, [i_max + 1], [0, i_max + 1])
            cum_hist = np.cumsum(hist) / image.size * 100.0
            low = np.searchsorted(cum_hist, low_p)
            high = np.searchsorted(cum_hist, high_p)
        else:
            # Fallback for float or other types
            low, high = np.percentile(image, (low_p, high_p))
        
        # Fast rescaling using cv2 or numpy
        rng = high - low
        if rng < 1e-6:
            return image
            
        # Result = (image - low) / (high - low) * (orig_max - orig_min) + orig_min?
        # Actually standard rescale_intensity maps (low, high) to (min, max) of dtype
        out_min, out_max = float(image.min()), float(image.max())
        
        result = (image.astype(np.float32) - low) * ((out_max - out_min) / rng) + out_min
        return np.clip(result, out_min, out_max).astype(dtype)

    @staticmethod
    def apply_background_suppression(image: np.ndarray, strength: float = 1.0, kernel_size: int = 50) -> np.ndarray:
        """
        Applies Background Suppression (Top-Hat). Supports 'strength' for weighted blending.
        strength = 0: Original Image, 1: Full Top-Hat, >1: Over-suppression.
        """
        if image is None: return None
        
        if abs(strength) < 0.001: return image
        
        # Ensure kernel size is odd and > 1
        kernel_size = int(kernel_size) | 1
        kernel_size = max(3, kernel_size)
        
        # Top-hat requires a structural element
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
        
        # Apply Top-Hat
        suppressed = None
        if is_opencl_enabled():
            try:
                img_u = cv2.UMat(image)
                res_u = cv2.morphologyEx(img_u, cv2.MORPH_TOPHAT, kernel)
                suppressed = res_u.get()
            except Exception as e:
                suppressed = cv2.morphologyEx(image, cv2.MORPH_TOPHAT, kernel)
        else:
            suppressed = cv2.morphologyEx(image, cv2.MORPH_TOPHAT, kernel)
            
        # Weighted Blending: Result = (1 - strength)*Image + strength*Suppressed
        s = max(0.0, strength)
        if s == 1.0:
            return suppressed
            
        try:
            result = cv2.addWeighted(image, 1.0 - s, suppressed, s, 0)
        except Exception:
            result = (image.astype(np.float32) * (1.0 - s) + suppressed.astype(np.float32) * s).astype(image.dtype)
        return result

    @staticmethod
    def apply_local_contrast(image: np.ndarray, clip_limit: float = 0.01, tile_size: int = 8) -> np.ndarray:
        """
        Applies Local Contrast Enhancement (CLAHE). Supports OpenCL acceleration.
        """
        if image is None: return None
        
        # Handle Multichannel (e.g. RGB)
        if image.ndim == 3:
            # Recursively apply to each channel
            chans = cv2.split(image)
            processed_chans = [EnhanceProcessor.apply_local_contrast(c, clip_limit, tile_size) for c in chans]
            return cv2.merge(processed_chans)
        
        # Determine clip limit value
        # Standard OpenCV clipLimit ranges from 1.0 to 40.0.
        # We use a 100.0 multiplier so that 0.01 is the 1.0 baseline.
        limit_val = clip_limit * 100.0 
            
        # Create CLAHE object
        clahe = cv2.createCLAHE(clipLimit=limit_val, tileGridSize=(tile_size, tile_size))
        
        # Apply with OpenCL if available
        if is_opencl_enabled():
            try:
                img_u = cv2.UMat(image)
                res_u = clahe.apply(img_u)
                return res_u.get()
            except Exception as e:
                return clahe.apply(image)
        else:
            return clahe.apply(image)

    @staticmethod
    def apply_noise_smoothing(image: np.ndarray, sigma: float = 1.0) -> np.ndarray:
        """
        Applies Noise Smoothing (Gaussian or Bilateral).
        """
        if image is None: return None
        
        # Map sigma to Bilateral params
        # d (diameter) ~ 4*sigma
        d = int(sigma * 4) | 1 # Ensure odd
        d = max(3, d)
        
        # Sigma Color: how much intensity difference is preserved.
        sigma_color = sigma * 20.0 # Heuristic
        sigma_space = sigma * 3.0 
        
        return EnhanceProcessor.apply_bilateral_filter(image, d=d, sigma_color=sigma_color, sigma_space=sigma_space)

    @staticmethod
    def apply_gamma(image: np.ndarray, gamma: float = 1.0) -> np.ndarray:
        """
        Applies Gamma Correction. Formula: V_out = V_in ^ gamma
        Optimized using LUT for uint8/uint16.
        """
        if image is None or gamma == 1.0:
            return image
        
        dtype = image.dtype
        if dtype == np.uint8:
            # 8-bit LUT
            lut = np.array([((i / 255.0) ** gamma) * 255.0 for i in range(256)]).astype(np.uint8)
            return cv2.LUT(image, lut)
        elif dtype == np.uint16:
            # 16-bit LUT (65536 entries)
            # OpenCV's cv2.LUT only supports 8-bit. For 16-bit we use numpy indexing.
            lut = np.array([((i / 65535.0) ** gamma) * 65535.0 for i in range(65536)]).astype(np.uint16)
            return lut[image]
        else:
            # Fallback for float
            max_val = float(np.max(image)) if image.size else 1.0
            img_f = image.astype(np.float32) / max_val
            img_gamma = np.power(np.maximum(img_f, 0), gamma)
            return (img_gamma * max_val).astype(dtype)

    @staticmethod
    def apply_display_gamma(image: np.ndarray, gamma: float = 1.0) -> np.ndarray:
        """
        Applies Display Gamma.
        """
        # Re-use existing
        return EnhanceProcessor.apply_gamma(image, gamma)

    @staticmethod
    def _dtype_max(dtype) -> float:
        if dtype == np.uint16:
            return 65535.0
        if dtype == np.uint8:
            return 255.0
        return float(np.finfo(dtype).max) if np.issubdtype(dtype, np.floating) else 1.0

    @staticmethod
    def _to_float01(image: np.ndarray) -> Tuple[np.ndarray, float]:
        if image is None:
            return None, 1.0
        dtype = image.dtype
        if dtype == np.uint16:
            scale = 65535.0
        elif dtype == np.uint8:
            scale = 255.0
        else:
            max_v = float(np.max(image)) if image.size else 1.0
            scale = max(max_v, 1e-6)
        return image.astype(np.float32) / float(scale), float(scale)

    @staticmethod
    def _from_float01(image_f: np.ndarray, dtype, scale: float) -> np.ndarray:
        if image_f is None:
            return None
        img = np.clip(image_f, 0.0, 1.0) * float(scale)
        if dtype == np.uint16:
            return np.clip(img, 0, 65535).astype(np.uint16)
        if dtype == np.uint8:
            return np.clip(img, 0, 255).astype(np.uint8)
        return img.astype(dtype)

    @staticmethod
    def apply_nlm_denoising(image: np.ndarray, h: float = 10.0) -> np.ndarray:
        if image is None:
            return None
        if image.ndim == 3:
            chans = cv2.split(image)
            processed = [EnhanceProcessor.apply_nlm_denoising(c, h=h) for c in chans]
            return cv2.merge(processed)

        d_min = float(image.min())
        d_max = float(image.max())
        rng = d_max - d_min
        if rng <= 0:
            return image.copy()

        img_8u = ((image.astype(np.float32) - d_min) / rng * 255.0).astype(np.uint8)
        h_u8 = float(h) if h is not None else 10.0
        den_8u = cv2.fastNlMeansDenoising(img_8u, None, h=h_u8, templateWindowSize=7, searchWindowSize=21)
        den_f = den_8u.astype(np.float32) / 255.0 * rng + d_min
        return np.clip(den_f, 0, 65535 if image.dtype == np.uint16 else 255).astype(image.dtype)

    @staticmethod
    def apply_richardson_lucy(image: np.ndarray, psf: np.ndarray, iterations: int = 10, tv_reg: bool = False) -> np.ndarray:
        if image is None:
            return None
        if not SKIMAGE_AVAILABLE or psf is None:
            return image.copy()

        dtype = image.dtype
        image_f, scale = EnhanceProcessor._to_float01(image)
        if image_f is None:
            return None

        if image_f.ndim == 3:
            outs = []
            for i in range(image_f.shape[2]):
                deconv = restoration.richardson_lucy(image_f[..., i], psf, num_iter=max(1, int(iterations)), clip=False)
                if tv_reg:
                    deconv = restoration.denoise_tv_chambolle(deconv, weight=0.02)
                outs.append(deconv.astype(np.float32))
            out = np.stack(outs, axis=2)
        else:
            out = restoration.richardson_lucy(image_f, psf, num_iter=max(1, int(iterations)), clip=False).astype(np.float32)
            if tv_reg:
                out = restoration.denoise_tv_chambolle(out, weight=0.02).astype(np.float32)

        return EnhanceProcessor._from_float01(out, dtype, scale)

    @classmethod
    def process_realtime_pipeline(cls, image: np.ndarray, params: dict) -> np.ndarray:
        if image is None:
            return None
        if params is None:
            params = {}

        if image.ndim == 3:
            chans = cv2.split(image)
            processed = [cls.process_realtime_pipeline(c, params) for c in chans]
            return cv2.merge(processed)

        result = image.copy()

        if params.get('percentile_stretch', False):
            low_p = float(params.get('lower_percentile', 2))
            high_p = float(params.get('upper_percentile', 98))
            result = cls.apply_signal_stretch(result, low_p=low_p, high_p=high_p)

        if params.get('bilateral_filter', False):
            d = int(params.get('bilateral_d', 7))
            sigma_color = float(params.get('bilateral_sigma_color', 50))
            sigma_space = float(params.get('bilateral_sigma_space', 50))
            result = cls.apply_bilateral_filter(result, d=d, sigma_color=sigma_color, sigma_space=sigma_space)

        if params.get('wavelet_denoise', False) and SKIMAGE_AVAILABLE:
            wavelet = params.get('wavelet_base', 'db1') or 'db1'
            image_f, scale = cls._to_float01(result)
            sigma = None
            if params.get('auto_sigma', False):
                try:
                    sigma = restoration.estimate_sigma(image_f, channel_axis=None)
                except Exception:
                    sigma = None
            try:
                den = restoration.denoise_wavelet(
                    image_f,
                    wavelet=str(wavelet),
                    sigma=sigma,
                    rescale_sigma=True,
                    channel_axis=None
                ).astype(np.float32)
                result = cls._from_float01(den, result.dtype, scale)
            except Exception:
                result = cls.apply_noise_smoothing(result, sigma=1.0)

        return result

    # --- Wrapper for old Bilateral (helper) ---
    @staticmethod
    def apply_bilateral_filter(image: np.ndarray, d: int = 7, sigma_color: float = 50, sigma_space: float = 50) -> np.ndarray:
        """Applies Bilateral Filter. Supports OpenCL acceleration."""
        d_min, d_max = image.min(), image.max()
        rng = d_max - d_min
        if rng == 0: rng = 1
        
        # OpenCL Path
        if is_opencl_enabled():
            try:
                # Normalize and convert to 8u for speed on GPU
                img_u = cv2.UMat(image)
                # (img - d_min) / rng * 255
                img_8u_u = cv2.subtract(img_u, float(d_min))
                img_8u_u = cv2.multiply(img_8u_u, 255.0 / rng)
                # Use convertTo for GPU-side casting
                img_8u_u = img_8u_u.get().astype(np.uint8) # Fallback if convertTo is tricky
                # Actually, cv2.UMat doesn't have a direct convertTo in Python that's easy to use
                # but we can at least avoid one UMat creation.
                img_8u_u = cv2.UMat(img_8u_u) 
                
                filtered_8u_u = cv2.bilateralFilter(
                    img_8u_u,
                    d=d,
                    sigmaColor=sigma_color,
                    sigmaSpace=sigma_space
                )
                
                # Convert back on GPU
                res_f_u = cv2.multiply(cv2.UMat(filtered_8u_u.get().astype(np.float32)), rng / 255.0)
                res_f_u = cv2.add(res_f_u, float(d_min))
                
                return res_f_u.get().astype(image.dtype)
            except Exception as e:
                pass # CPU Fallback
        
        # CPU Fallback
        img_8u = ((image - d_min) / rng * 255).astype(np.uint8)
        filtered_8u = cv2.bilateralFilter(
            img_8u,
            d=d,
            sigmaColor=sigma_color,
            sigmaSpace=sigma_space
        )
        filtered_f = filtered_8u.astype(np.float32) / 255.0 * rng + d_min
        return filtered_f.astype(image.dtype)
        
    @staticmethod
    def estimate_auto_params(image: np.ndarray) -> dict:
        """
        Estimates 'Auto' base values for all modules.
        NOTE: This does NOT enable the features. It only calculates "if enabled, use this value".
        """
        if image is None:
            return {}
            
        # Downsample for speed (Critical for performance)
        h, w = image.shape[:2]
        # Use a smaller max dimension for estimation to be very fast
        scale = min(1.0, 256 / max(h, w)) # 256px is enough for noise/bg estimation
        if scale < 1.0:
            small = cv2.resize(image, (int(w*scale), int(h*scale)), interpolation=cv2.INTER_NEAREST)
        else:
            small = image

        # 1. Signal Stretch Auto (Percentiles)
        # Standard: 2% - 98%? Or dynamic based on histogram?
        # Let's use robust min/max (0.1% - 99.9%)
        # Actually user prompt: "Auto value * (1 + sensitivity * percent)"
        # This implies Auto is a scalar?
        # For Stretch, we need (low, high).
        # Let's define Auto Stretch as "Clip Amount" = 2.0 (meaning 2%).
        # Then percent adjusts this 2.0.
        
        # 2. Background Suppression Auto (Signal Size)
        # User: Radius = 2~3 * signal_size.
        # We estimate signal_radius.
        est_radius = EnhanceProcessor.estimate_signal_size(image)
        # Rolling ball radius should be > signal size. 
        # User says 2~3x. Diameter = 4~6x.
        bg_kernel_size = est_radius * 4
        
        # 3. Local Contrast Auto (Clip Limit)
        # Scale: 0.04 * 100 = 4.0 (Standard strong CLAHE)
        # We use a base that results in ~4.0 at 100% with the new mapping.
        auto_clip_limit = 0.03 
        # User: tile size = 2 * signal_size
        clahe_tile_size = est_radius * 2
        
        # 4. Noise Smoothing Auto (Sigma)
        # Estimate noise.
        # Use downsampled image for speed
        med = cv2.medianBlur(small if small.dtype != np.float64 else small.astype(np.float32), 3)
        diff = cv2.absdiff(small, med)
        noise_est = np.median(diff)
        max_val = 65535.0 if image.dtype == np.uint16 else 255.0
        norm_noise = noise_est / max_val
        # Map noise level to sigma. 
        # Low noise (<0.1%) -> Sigma 1.0
        # High noise (>1%) -> Sigma 3.0
        auto_sigma = 1.0 + (norm_noise * 200.0) # 0.01 * 200 = 2.0
        auto_sigma = np.clip(auto_sigma, 1.0, 5.0)
        
        # 5. Gamma Auto
        # Default 1.0.
        
        return {
            'stretch_clip': 2.0,       # 2%
            'bg_kernel': bg_kernel_size,
            'contrast_clip': auto_clip_limit, 
            'contrast_tile': clahe_tile_size,
            'noise_sigma': float(auto_sigma),
            'gamma': 1.0
        }

    @classmethod
    def apply_pipeline(cls, image: np.ndarray, params: dict, scale_factor: float = 1.0) -> np.ndarray:
        """Apply full scientific enhancement pipeline with logging."""
        if image is None: return None
        import time
        t_start = time.time()
        
        # --- Symmetry Verification Logging ---
        # We calculate mean/std of the input to compare with 0% state later
        in_mean = np.mean(image)
        in_std = np.std(image)
        
        result = image.copy()
        
        # 1. Background Suppression
        if params.get('bg_enabled', False):
            bg_s = params.get('bg_strength', 1.0)
            bg_k = int(params.get('bg_kernel', 50))
            if scale_factor < 1.0:
                bg_k = max(3, int(bg_k * scale_factor))
            print(f"DEBUG: [Enhance] Applying BG Suppression: Strength={bg_s:.4f}, Kernel={bg_k}")
            result = cls.apply_background_suppression(result, strength=bg_s, kernel_size=bg_k)
            
        # 2. Local Contrast (CLAHE)
        if params.get('contrast_enabled', False):
            c_clip = params.get('contrast_clip', 0.01)
            c_grid = int(params.get('contrast_tile', 8))
            print(f"DEBUG: [Enhance] Applying Local Contrast: Clip={c_clip:.4f}, Tile={c_grid}")
            result = cls.apply_local_contrast(result, clip_limit=c_clip, tile_size=c_grid)
            
        # 3. Noise Smoothing
        if params.get('noise_enabled', False):
            n_sigma = params.get('noise_sigma', 1.0)
            print(f"DEBUG: [Enhance] Applying Noise Reduction: Sigma={n_sigma:.4f}")
            result = cls.apply_noise_smoothing(result, sigma=n_sigma)
            
        # 4. Signal Stretch
        if params.get('stretch_enabled', False):
            s_clip = params.get('stretch_clip', 2.0)
            print(f"DEBUG: [Enhance] Applying Signal Stretch: Clip={s_clip:.4f}")
            result = cls.apply_signal_stretch(result, low_p=s_clip, high_p=100.0-s_clip)
            
        # 5. Gamma
        if params.get('gamma_enabled', False):
            g_val = params.get('gamma', 1.0)
            print(f"DEBUG: [Enhance] Applying Gamma: Val={g_val:.4f}")
            result = cls.apply_display_gamma(result, gamma=g_val)
            
        t_total = time.time() - t_start
        
        # --- Symmetry Verification Summary ---
        out_mean = np.mean(result)
        out_std = np.std(result)
        diff_mean = out_mean - in_mean
        
        if any(params.get(k, False) for k in ['bg_enabled', 'contrast_enabled', 'noise_enabled', 'stretch_enabled', 'gamma_enabled']):
            print(f"DEBUG: [Enhance] Pipeline Summary: Mean {in_mean:.2f}->{out_mean:.2f} (diff={diff_mean:+.2f}), Std {in_std:.2f}->{out_std:.2f}")
        
        if t_total > 0.01:
            print(f"[Timing] Enhance: Pipeline Total {t_total:.4f}s")
            
        return result

    @classmethod
    def process_scientific_pipeline(cls, image: np.ndarray, params: dict, scale_factor: float = 1.0) -> np.ndarray:
        """Alias for apply_pipeline with deprecation notice in logs."""
        return cls.apply_pipeline(image, params, scale_factor)
