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
except ImportError:
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
        """
        if not SKIMAGE_AVAILABLE or image is None:
            return image
            
        # Ensure percentiles are within 0-100
        low_p = np.clip(low_p, 0, 100)
        high_p = np.clip(high_p, 0, 100)
        
        if low_p >= high_p:
            return image
            
        low, high = np.percentile(image, (low_p, high_p))
        
        return exposure.rescale_intensity(
            image,
            in_range=(low, high),
            out_range=(image.min(), image.max())
        ).astype(image.dtype)

    @staticmethod
    def apply_background_suppression(image: np.ndarray, kernel_size: int = 50) -> np.ndarray:
        """
        Applies Background Suppression using Top-Hat Transform (Rolling Ball equivalent).
        kernel_size: Radius of the rolling ball (structural element size).
        Supports OpenCL acceleration.
        """
        if image is None:
            return None
            
        # Top-hat requires a structural element
        # Elliptical kernel is better for biological features
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
        
        # Apply Top-Hat: Image - Open(Image)
        if is_opencl_enabled():
            try:
                img_u = cv2.UMat(image)
                res_u = cv2.morphologyEx(img_u, cv2.MORPH_TOPHAT, kernel)
                return res_u.get()
            except Exception as e:
                print(f"[Enhance] Top-Hat OpenCL Error: {e}")
                return cv2.morphologyEx(image, cv2.MORPH_TOPHAT, kernel)
        else:
            return cv2.morphologyEx(image, cv2.MORPH_TOPHAT, kernel)

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
        if image.dtype == np.uint16:
            limit_val = clip_limit * 1000.0 # 0.01 -> 10.0
        elif image.dtype == np.uint8:
            limit_val = clip_limit * 100.0
        else:
            # Float fallback: normalize to u16 first
            image = cv2.normalize(image, None, 0, 65535, cv2.NORM_MINMAX).astype(np.uint16)
            limit_val = clip_limit * 1000.0
            
        # Create CLAHE object
        clahe = cv2.createCLAHE(clipLimit=limit_val, tileGridSize=(tile_size, tile_size))
        
        # Apply with OpenCL if available
        if is_opencl_enabled():
            try:
                img_u = cv2.UMat(image)
                res_u = clahe.apply(img_u)
                return res_u.get()
            except Exception as e:
                print(f"[Enhance] CLAHE OpenCL Error: {e}")
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
        # Fixed relation to sigma? Or fixed?
        # Prompt says "Percent controls smoothing strength".
        # Usually we scale both spatial and color sigmas.
        # USER FEEDBACK: Effect was too subtle. Boosted parameters.
        sigma_color = sigma * 20.0 # Heuristic (was 10.0)
        sigma_space = sigma * 3.0  # (was 1.0)
        
        # Bilateral needs float32 or uint8 usually for speed/correctness in OpenCV?
        # We already have a wrapper.
        return EnhanceProcessor.apply_bilateral_filter(image, d=d, sigma_color=sigma_color, sigma_space=sigma_space)

    @staticmethod
    def apply_gamma(image: np.ndarray, gamma: float = 1.0) -> np.ndarray:
        """
        Applies Gamma Correction. Formula: V_out = V_in ^ gamma
        """
        if image is None: return None
        if gamma == 1.0: return image
        
        # Normalize to 0-1
        dtype = image.dtype
        max_val = 65535.0 if dtype == np.uint16 else 255.0
            
        img_f = image.astype(np.float32) / max_val
        img_f = np.maximum(img_f, 0)
        img_gamma = np.power(img_f, gamma)
        result = (img_gamma * max_val).astype(dtype)
        return result

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
                # Normalize and convert to 8u for speed
                img_u = cv2.UMat(image)
                # (img - d_min) / rng * 255
                img_8u_u = cv2.subtract(img_u, float(d_min))
                img_8u_u = cv2.multiply(img_8u_u, 255.0 / rng)
                img_8u_u = cv2.UMat(img_8u_u.get().astype(np.uint8)) # Cast to uint8
                
                filtered_8u_u = cv2.bilateralFilter(
                    img_8u_u,
                    d=d,
                    sigmaColor=sigma_color,
                    sigmaSpace=sigma_space
                )
                
                # Convert back
                filtered_f_u = cv2.UMat(filtered_8u_u.get().astype(np.float32))
                filtered_f_u = cv2.multiply(filtered_f_u, rng / 255.0)
                filtered_f_u = cv2.add(filtered_f_u, float(d_min))
                
                return filtered_f_u.get().astype(image.dtype)
            except Exception as e:
                print(f"[Enhance] Bilateral OpenCL Error: {e}")
        
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
        # User: 1.5 ~ 2.5
        auto_clip_limit = 1.5
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
    def process_scientific_pipeline(cls, image: np.ndarray, params: dict) -> np.ndarray:
        """
        Executes the Scientific Enhancement Pipeline.
        Order: Signal Range -> Background -> Contrast -> Noise -> Gamma
        Ref: "Recommended Minimum Pipeline: Raw -> Signal Range -> Background -> (Optional) Structure -> Display"
        """
        if image is None: return None
        
        # Optimization: Check if any enhancement is actually enabled
        has_ops = (
            params.get('stretch_enabled', False) or
            params.get('bg_enabled', False) or
            params.get('contrast_enabled', False) or
            params.get('noise_enabled', False) or
            params.get('gamma_enabled', False)
        )
        
        if not has_ops:
            return image # Zero-copy return
            
        import time
        t_start = time.time()
        
        # Debug: Print active enhancements
        # active_ops = [k for k, v in params.items() if k.endswith('_enabled') and v]
        # print(f"[Debug] Enhance Pipeline Triggered. Active: {active_ops}")
        
        result = image.copy()
        
        # 1. Signal Stretch (Percentile) - "亮度范围"
        if params.get('stretch_enabled', False):
            t0 = time.time()
            p = params.get('stretch_clip', 2.0) # e.g. 2.0 means 2% - 98%
            # Ensure symmetric or just passed as p?
            # We assume symmetric clip for simplicity: p_low=p, p_high=100-p
            result = cls.apply_signal_stretch(result, low_p=p, high_p=100.0-p)
            print(f"[Timing] Enhance: Stretch took {time.time()-t0:.4f}s")
            
        # 2. Background Suppression (Top-Hat) - "背景清除"
        if params.get('bg_enabled', False):
            t0 = time.time()
            k = int(params.get('bg_kernel', 50))
            strength = params.get('bg_strength', 1.0)
            
            if k > 0:
                suppressed = cls.apply_background_suppression(result, kernel_size=k)
                
                # Apply Strength Blending
                if abs(strength - 1.0) < 0.01:
                    result = suppressed
                else:
                    # Blend: result = original * (1-s) + suppressed * s
                    s = max(0.0, min(1.0, strength))
                    
                    # Use cv2.addWeighted for optimized blending (handles types correctly)
                    # Note: suppressed might be None if failed, but apply_background_suppression returns array
                    if suppressed is not None:
                        try:
                            result = cv2.addWeighted(result, 1.0 - s, suppressed, s, 0)
                        except Exception:
                            # Fallback for float/mismatch
                            result = (result.astype(np.float32) * (1.0 - s) + suppressed.astype(np.float32) * s).astype(result.dtype)

            print(f"[Timing] Enhance: Background took {time.time()-t0:.4f}s")
        
        # 3. Local Contrast (CLAHE) - "结构突出"
        if params.get('contrast_enabled', False):
            t0 = time.time()
            c = params.get('contrast_clip', 1.5)
            # Tile size = 2 * signal_size
            t_size = int(params.get('contrast_tile', 8))
            # Ensure valid tile size
            t_size = max(2, t_size)
            result = cls.apply_local_contrast(result, clip_limit=c, tile_size=t_size)
            print(f"[Timing] Enhance: Contrast took {time.time()-t0:.4f}s")
            
        # 4. Noise Smoothing - "噪声平滑"
        if params.get('noise_enabled', False):
            t0 = time.time()
            s = params.get('noise_sigma', 1.0)
            result = cls.apply_noise_smoothing(result, sigma=s)
            print(f"[Timing] Enhance: Noise took {time.time()-t0:.4f}s")
            
        print(f"[Timing] Enhance: Pipeline Total {time.time()-t_start:.4f}s")
        
        if params.get('gamma_enabled', False):
            g = params.get('gamma', 1.0)
            result = cls.apply_display_gamma(result, gamma=g)
            
        return result
