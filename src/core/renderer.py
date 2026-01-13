import numpy as np
import cv2
from typing import List, Tuple
from .data_model import ImageChannel
from .image_renderer import ImageRenderer, is_opencl_enabled
from .graphics_renderer import GraphicsRenderer

class Renderer:
    """
    Facade class that maintains backward compatibility with the original Renderer API.
    Internally delegates tasks to ImageRenderer and GraphicsRenderer.
    """

    @staticmethod
    def hex_to_rgb(hex_color: str) -> Tuple[float, float, float]:
        return ImageRenderer.hex_to_rgb(hex_color)

    @staticmethod
    def generate_rgb_lut(min_val: float, max_val: float, gamma: float, hex_color: str, lut_size: int = 65536, out_depth: int = 8) -> np.ndarray:
        return ImageRenderer.generate_rgb_lut(min_val, max_val, gamma, hex_color, lut_size, out_depth)

    @staticmethod
    def generate_smooth_polygon_points(points: List[Tuple[int, int]], tension: float = 0.5, num_segments: int = 16) -> np.ndarray:
        return GraphicsRenderer.generate_smooth_polygon_points(points, tension, num_segments)

    @staticmethod
    def render_channel(channel: ImageChannel, target_shape: Tuple[int, int] = None, out_depth: int = 8, scale_bar_settings=None, annotations: List = None, dpi: int = 72, view_scale: float = 1.0, screen_dpi: float = 96.0, export_line_scans: bool = False) -> np.ndarray:
        """
        Renders a single channel to an RGB image, optionally applying scale bars and annotations.
        Maintains backward compatibility by combining ImageRenderer and GraphicsRenderer calls.
        """
        # 1. Render the core image
        result = ImageRenderer.render_channel(channel, target_shape, out_depth)
        
        if result is None:
            return None

        # 2. Apply Graphics Overlays
        # Apply Scale Bar if enabled
        if scale_bar_settings and scale_bar_settings.enabled:
            result = GraphicsRenderer.apply_scale_bar(result, scale_bar_settings, original_size=channel.shape, dpi=dpi, screen_dpi=screen_dpi)
            
        # Apply Annotations if enabled
        if annotations:
            result = GraphicsRenderer.apply_annotations(result, annotations, original_size=channel.shape, dpi=dpi, view_scale=view_scale, screen_dpi=screen_dpi)
            
        return result

    @staticmethod
    def composite(channels: List[ImageChannel], target_shape: Tuple[int, int] = None, out_depth: int = 8, scale_bar_settings=None, annotations: List = None, dpi: int = 72, view_scale: float = 1.0, screen_dpi: float = 96.0, export_line_scans: bool = False) -> np.ndarray:
        """
        Merges all visible channels and applies overlays.
        Maintains backward compatibility.
        """
        # 1. Composite the images
        final_img = ImageRenderer.composite(channels, target_shape, out_depth)
        
        if final_img is None:
            return None
            
        # Get original size from first valid channel for overlay scaling
        orig_size = None
        for ch in channels:
            if not getattr(ch, 'is_placeholder', False):
                orig_size = ch.shape
                break

        # 2. Apply Graphics Overlays
        # Apply Scale Bar if enabled
        if scale_bar_settings and scale_bar_settings.enabled:
            final_img = GraphicsRenderer.apply_scale_bar(final_img, scale_bar_settings, original_size=orig_size, dpi=dpi, screen_dpi=screen_dpi)
            
        # Apply Annotations if enabled
        if annotations:
            final_img = GraphicsRenderer.apply_annotations(final_img, annotations, original_size=orig_size, dpi=dpi, view_scale=view_scale, screen_dpi=screen_dpi)
            
        return final_img

    @staticmethod
    def apply_scale_bar(image: np.ndarray, settings, original_size: Tuple[int, int] = None, dpi: float = 300.0, screen_dpi: float = 96.0) -> np.ndarray:
        return GraphicsRenderer.apply_scale_bar(image, settings, original_size, dpi, screen_dpi)

    @staticmethod
    def apply_annotations(image: np.ndarray, annotations: List, original_size: Tuple[int, int] = None, dpi: float = 300.0, view_scale: float = 1.0, screen_dpi: float = 96.0) -> np.ndarray:
        return GraphicsRenderer.apply_annotations(image, annotations, original_size, dpi, view_scale, screen_dpi)

    @staticmethod
    def draw_dashed_line(image: np.ndarray, pt1: Tuple[int, int], pt2: Tuple[int, int], color: Tuple[float, float, float], thickness: int, dash_length: int = 10, dash_gap: int = 5):
        return GraphicsRenderer.draw_dashed_line(image, pt1, pt2, color, thickness, dash_length, dash_gap)

    @staticmethod
    def draw_dashed_polyline(image: np.ndarray, pts: np.ndarray, is_closed: bool, color: Tuple[float, float, float], thickness: int, dash_length: int = 10, dash_gap: int = 5):
        return GraphicsRenderer.draw_dashed_polyline(image, pts, is_closed, color, thickness, dash_length, dash_gap)
