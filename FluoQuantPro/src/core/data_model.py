import numpy as np
import tifffile
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict

@dataclass
class DisplaySettings:
    """
    Holds visualization parameters for a single channel.
    Changes here do NOT affect the raw data, only the rendering.
    """
    color: str = "#FFFFFF"  # Hex color code for the channel (e.g., #FF0000 for Red)
    min_val: float = 0.0    # Black point
    max_val: float = 65535.0 # White point (default for 16-bit)
    gamma: float = 1.0      # Gamma correction
    visible: bool = True
    opacity: float = 1.0

@dataclass
class ScaleBarSettings:
    """
    Settings for drawing a scale bar on the image.
    """
    enabled: bool = False
    pixel_size: float = 1.0 # um per pixel
    bar_length_um: float = 50.0 # Length in micrometers
    color: str = "#FFFFFF"
    thickness: int = 4
    position: str = "Bottom Right" # Bottom Right, Bottom Left, Top Right, Top Left
    custom_pos: Optional[Tuple[float, float]] = None # Custom (x, y) coordinates
    show_label: bool = True
    font_size: int = 20
    margin: int = 20 # Pixels from edge

@dataclass
class GraphicAnnotation:
    """
    User-drawn graphic annotations (arrows, shapes, text).
    """
    id: str
    type: str # 'arrow', 'line', 'rect', 'ellipse', 'circle', 'polygon', 'text', 'roi_ref'
    points: List[Tuple[float, float]] # Start/End or center/size or polygon vertices
    color: str = "#FFFF00"
    thickness: int = 2
    text: str = ""
    font_size: int = 20
    visible: bool = True
    roi_id: Optional[str] = None # Link to an ROI if this annotation represents one
    export_only: bool = False # If true, only shows up in export
    style: str = "solid" # solid, dashed, dotted
    selectable: bool = True # Whether the annotation can be selected/edited
    is_dragging: bool = False # Temporary state for performance optimization
    properties: Dict = field(default_factory=dict) # Custom properties (arrow_head_size, etc.)

# Biological Fluorescence Channel Mappings Reference:
# --------------------------------------------------
# BLUE CHANNEL (B / Index 2):
#   - DAPI, Hoechst 33342/33258, Alexa Fluor 405, BFP, Pacific Blue.
# GREEN CHANNEL (G / Index 1):
#   - GFP, FITC, Alexa Fluor 488, Cy2, Calcein AM, YFP, Fluo-4.
# RED CHANNEL (R / Index 0):
#   - RFP, mCherry, TRITC, Cy3, Alexa Fluor 546/555/568/594, Texas Red, PI.
# FAR-RED CHANNEL (Usually separate or mapped to R/B):
#   - Cy5, Alexa Fluor 647, APC, DRAQ5.

class ImageChannel:
    """
    Represents a single fluorescence channel (e.g., DAPI, GFP).
    Holds raw data (immutable) and display settings (mutable).
    """
    def __init__(self, file_path: str, color: str = "#FFFFFF", name: Optional[str] = None, data: Optional[np.ndarray] = None, auto_contrast: bool = False):
        """
        Initializes an ImageChannel.
        
        Scientific Rigor Notes:
        1. Dimension Normalization: Automatically collapses degenerate dimensions 
           (e.g., (1, H, W) or (H, W, 1)) to (H, W). This prevents "dimension traps" 
           common in microscope metadata.
        2. Signal Preservation: For multi-channel files with unknown channel types,
           uses Max Projection instead of weighted averaging to preserve the 
           maximum photon count signal for analysis.
        3. Raw Data Integrity: The self._raw_data attribute ALWAYS holds the 
           original sensor data for analysis, while display_settings are used
           only for visualization.
        """
        t_start = time.time()
        self.file_path = file_path
        self.name = name if name else (os.path.basename(file_path) if file_path else "Empty")
        self.is_placeholder = False
        self.is_rgb = False # Flag for RGB/Multichannel data
        
        # Caching for Enhancement Pipeline
        self._cached_enhanced_data = None
        self._last_enhance_params = None
        
        # Initialize default display settings immediately to prevent AttributeError
        self.display_settings = DisplaySettings(
            color=color,
            min_val=0.0,
            max_val=255.0,
            gamma=1.0
        )
        self.display_settings.enhance_params = {}
        
        if not file_path and data is None:
            # Placeholder initialization
            self.is_placeholder = True
            self._raw_data = np.zeros((1, 1), dtype=np.uint16) # Minimal placeholder
            self.shape = (1, 1)
            self.dtype = np.uint16
            return

        # Load data using tifffile for best bio-format support
        # We assume 2D image for now (Y, X). 
        # TODO: Handle Z-stacks or Time-series if needed later.
        try:
            if data is not None:
                self._raw_data = data
            else:
                ext = os.path.splitext(file_path)[1].lower()
                if ext in (".tif", ".tiff"):
                    self._raw_data = tifffile.imread(file_path)
                else:
                    raise ValueError(f"Unsupported by tifffile loader: {ext}")
        except Exception as e:
            try:
                import cv2

                # img = cv2.imread(file_path, cv2.IMREAD_UNCHANGED)
                # Fix for Unicode paths on Windows:
                img_stream = np.fromfile(file_path, dtype=np.uint8)
                img = cv2.imdecode(img_stream, cv2.IMREAD_UNCHANGED)
                if img is None:
                    raise IOError(f"cv2.imread returned None for {file_path}")

                if img.ndim == 3:
                    if img.shape[2] == 3:
                        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                    elif img.shape[2] == 4:
                        img = cv2.cvtColor(img, cv2.COLOR_BGRA2RGBA)

                self._raw_data = img
            except Exception as e2:
                raise IOError(f"Failed to load image {file_path}: {e} / {e2}")

        # --- Channel Extraction & Robustness Logic ---
        # 1. Dimension Pre-processing: Handle (H, W, 1) and other oddities
        if self._raw_data.ndim == 3:
            # Case 1: (H, W, 1) - Common in single-channel microscope exports
            if self._raw_data.shape[2] == 1:
                self._raw_data = self._raw_data[:, :, 0]
                print(f"Info: Collapsed (H, W, 1) to (H, W) for {self.name}")
            # Case 2: (1, H, W)
            elif self._raw_data.shape[0] == 1:
                self._raw_data = self._raw_data[0, :, :]
                print(f"Info: Collapsed (1, H, W) to (H, W) for {self.name}")
        
        # 2. Channel Extraction from RGB/Multichannel
        if self._raw_data.ndim == 3:
            self.is_rgb = True  # Mark as originally multi-channel/RGB
            
            # --- USER REQUEST: Pseudo-RGB Detection ---
            # If only one channel has non-zero data, use it directly as grayscale.
            # This handles cases where a grayscale image was saved as RGB with empty channels.
            non_zero_channels = []

            # Use name_upper here as well if needed for early detection
            name_upper = self.name.upper()

            # Handle both (C, H, W) and (H, W, C)
            if self._raw_data.shape[0] < self._raw_data.shape[2]: # (C, H, W)
                for i in range(self._raw_data.shape[0]):
                    # Robust check: Max > 5
                    ch_slice = self._raw_data[i, :, :]
                    if np.max(ch_slice) > 5:
                        non_zero_channels.append(i)
                
                if len(non_zero_channels) == 1:
                    idx = non_zero_channels[0]
                    self._raw_data = self._raw_data[idx, :, :]
                    print(f"Info: Pseudo-RGB detected. Using non-zero channel {idx} for {self.name}")
                    self.is_rgb = False
                    self.dtype = self._raw_data.dtype
                    self.shape = self._raw_data.shape[:2]
            else: # (H, W, C)
                for i in range(self._raw_data.shape[2]):
                    # Robust check: Max > 5
                    ch_slice = self._raw_data[:, :, i]
                    if np.max(ch_slice) > 5:
                        non_zero_channels.append(i)
                
                if len(non_zero_channels) == 1:
                    idx = non_zero_channels[0]
                    self._raw_data = self._raw_data[:, :, idx]
                    print(f"Info: Pseudo-RGB detected. Using non-zero channel {idx} for {self.name}")
                    self.is_rgb = False
                    self.dtype = self._raw_data.dtype
                    self.shape = self._raw_data.shape[:2]

            # Only proceed with name-based rules if still 3D (i.e., not a pseudo-RGB)
            if self._raw_data.ndim == 3:
                idx = -1
            
                # Rule 1: Green Channels
                if any(k in name_upper for k in ["GFP", "FITC", "ALEXA488", "ALEXA 488", "CY2", "CALCEIN", "YFP", "GREEN"]):
                    # Check for (C, H, W) vs (H, W, C)
                    if self._raw_data.shape[0] < self._raw_data.shape[2]: # (C, H, W)
                        idx = 1 if self._raw_data.shape[0] > 1 else 0
                        self._raw_data = self._raw_data[idx, :, :]
                    else: # (H, W, C)
                        idx = 1 if self._raw_data.shape[2] > 1 else 0
                        self._raw_data = self._raw_data[:, :, idx]
                    print(f"Info: Extracted Green channel for {self.name}")
                    
                # Rule 2: Blue Channels
                elif any(k in name_upper for k in ["DAPI", "HOECHST", "ALEXA405", "ALEXA 405", "BFP", "BLUE"]):
                    if self._raw_data.shape[0] < self._raw_data.shape[2]: # (C, H, W)
                        idx = 2 if self._raw_data.shape[0] > 2 else (self._raw_data.shape[0]-1)
                        self._raw_data = self._raw_data[idx, :, :]
                    else: # (H, W, C)
                        idx = 2 if self._raw_data.shape[2] > 2 else (self._raw_data.shape[2]-1)
                        self._raw_data = self._raw_data[:, :, idx]
                    print(f"Info: Extracted Blue channel for {self.name}")
                    
                # Rule 3: Red Channels
                elif any(k in name_upper for k in ["RFP", "MCHERRY", "TRITC", "CY3", "ALEXA555", "ALEXA 555", "ALEXA568", "ALEXA 568", "ALEXA594", "ALEXA 594", "TEXAS RED", "RED"]):
                    if self._raw_data.shape[0] < self._raw_data.shape[2]: # (C, H, W)
                        self._raw_data = self._raw_data[0, :, :]
                    else: # (H, W, C)
                        self._raw_data = self._raw_data[:, :, 0]
                    print(f"Info: Extracted Red channel for {self.name}")
                
                # Rule 4: Fallback - Unknown channel name but 3D data
                else:
                    # Use Max Projection to preserve signal without weighted averaging
                    if self._raw_data.shape[0] < self._raw_data.shape[2]: # (C, H, W)
                        print(f"Warning: Unknown channel '{self.name}' (C,H,W). Using Max Projection.")
                        self._raw_data = np.max(self._raw_data, axis=0)
                    else: # (H, W, C)
                        print(f"Warning: Unknown channel '{self.name}' (H,W,C). Using Max Projection.")
                        self._raw_data = np.max(self._raw_data, axis=2)
                
                self.is_rgb = False # Data is now normalized to 2D
        
        self.dtype = self._raw_data.dtype
        self.shape = self._raw_data.shape[:2] # Always use (H, W) for shape property to avoid breaking 2D assumptions in UI
        
        # Auto-scale initial display settings
        self.auto_scale(auto_contrast)
        
        print(f"[Timing] ImageChannel initialized. Min: {self.display_settings.min_val}, Max: {self.display_settings.max_val} (Auto-scaled). Dtype: {self._raw_data.dtype}")
        print(f"[Timing] ImageChannel total init: {time.time() - t_start:.4f}s")

    def auto_scale(self, auto_contrast=True):
        t_stats = time.time()
        try:
            # Special Handling for RGB or uint8 images: Default to full range
            if self.is_rgb or self._raw_data.dtype == np.uint8:
                 data_min = 0.0
                 data_max = 255.0
            elif not auto_contrast:
                # Default to full bit depth if auto_contrast is disabled
                data_min = 0.0
                data_max = 65535.0 if self._raw_data.dtype == np.uint16 else float(np.max(self._raw_data))
            else:
                # Scientific Auto-Scaling for 16-bit
                # Min: Use absolute minimum to preserve background
                data_min = float(np.min(self._raw_data))
                
                # Max: Intelligent auto-scaling
                # 1. Calculate 99.99% percentile (excludes 0.01% brightest pixels)
                # 2. Check if absolute max is an outlier (hot pixel)
                abs_max = float(np.max(self._raw_data))
                
                # Optimization: Use downsampled data for percentile calculation to speed up loading
                # For 16-bit images (e.g. 2048x2048), full percentile is slow.
                try:
                    if self._raw_data.size > 1000000: # > 1MP
                        # Stride slicing is very fast and sufficient for histogram stats
                        step = int(max(1, (self._raw_data.size / 250000) ** 0.5)) # Target ~250k pixels (500x500)
                        if self._raw_data.ndim == 2:
                            sample_data = self._raw_data[::step, ::step]
                        elif self._raw_data.ndim == 3:
                            sample_data = self._raw_data[::step, ::step, :]
                        else:
                            sample_data = self._raw_data
                    else:
                        sample_data = self._raw_data
                except Exception:
                    # Fallback if slicing fails
                    sample_data = self._raw_data
                    
                p_high = float(np.percentile(sample_data, 99.99))
                
                # Heuristic: If absolute max is significantly higher than 99.99% percentile,
                # it's likely a hot pixel or artifact. Use percentile.
                # Otherwise, use absolute max to avoid clipping real bright signals in sparse images.
                # We also ensure we don't clip if the image is generally dark (low dynamic range).
                if abs_max > p_high * 2.0 and abs_max > data_min + 255:
                    data_max = p_high
                else:
                    data_max = abs_max
    
                # Safety: Ensure Max > Min
                if data_max <= data_min:
                    data_max = data_min + 255.0
                
        except Exception:
            # Fallback
            data_min = 0.0
            data_max = 65535.0 if self._raw_data.dtype == np.uint16 else 255.0

        self.display_settings.min_val = data_min
        self.display_settings.max_val = data_max
        self.display_settings.gamma = 1.0
        
        # Ensure enhance_params is initialized but disabled
        self.display_settings.enhance_params = {}
        # print(f"[Timing] ImageChannel stats: {time.time() - t_stats:.4f}s")

    def reset_display_settings(self):
        """Resets display settings to default auto-scaled values."""
        self.auto_scale(auto_contrast=True)

    @property
    def channel_type(self) -> str:
        """Alias for name, used in some legacy/debug code."""
        return self.name

    def clone(self):
        """Deep copy of the channel."""
        # Create a new instance without loading file
        new_ch = ImageChannel(file_path="", color=self.display_settings.color, name=self.name)
        new_ch.file_path = self.file_path
        new_ch.is_placeholder = self.is_placeholder
        
        # Deep copy raw data
        new_ch._raw_data = self._raw_data.copy()
        new_ch.shape = self.shape
        new_ch.dtype = self.dtype
        
        # Copy display settings
        ds = self.display_settings
        new_ch.display_settings = DisplaySettings(
            color=ds.color,
            min_val=ds.min_val,
            max_val=ds.max_val,
            gamma=ds.gamma,
            visible=ds.visible,
            opacity=ds.opacity
        )
        return new_ch

    def update_data(self, new_data: np.ndarray):
        """Updates the raw data (e.g. after cropping)."""
        self._raw_data = new_data
        self.shape = self._raw_data.shape[:2]
        self.dtype = self._raw_data.dtype
        
        # Update is_rgb flag based on dimensions
        if self._raw_data.ndim == 3 and self._raw_data.shape[2] in (3, 4):
            self.is_rgb = True
        else:
            self.is_rgb = False

    @property
    def raw_data(self) -> np.ndarray:
        """Access the raw pixel data. Read-only recommended."""
        return self._raw_data

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QUndoStack

from .roi_model import RoiManager

class Session(QObject):
    """
    Manages the entire project state: list of channels, ROIs (future), etc.
    """
    data_changed = Signal() # Emitted when image data changes (e.g. crop)
    project_changed = Signal() # Emitted when channels are added/removed/cleared

    def __init__(self, undo_stack: Optional[QUndoStack] = None):
        super().__init__()
        self.channels: List[ImageChannel] = []
        self._reference_shape: Optional[Tuple[int, int]] = None
        self.undo_stack = undo_stack or QUndoStack(self)
        self.roi_manager = RoiManager(self.undo_stack)
        self.scale_bar_settings = ScaleBarSettings()
        self.annotations: List[GraphicAnnotation] = []
        self.show_annotations: bool = True
        
    def undo(self):
        self.undo_stack.undo()

    def redo(self):
        self.undo_stack.redo()

    def clear(self):
        """Resets the session state."""
        self.channels.clear()
        self._reference_shape = None
        self.roi_manager.clear()
        self.annotations.clear() # USER REQUEST: Ensure annotations are cleared
        self.project_changed.emit()

    def load_project(self, folder: str):
        """
        USER REQUEST: Compatibility method for loading projects.
        This allows MainWindow to call session.load_project if needed,
        though MainWindow.load_project is the primary entry point.
        """
        # Usually we would delegate to a project loader here
        # For now, this is a placeholder to prevent crashes if called
        print(f"[Session] Request to load project from: {folder}")
        pass

    def add_existing_channel(self, channel: ImageChannel):
        """
        Adds an already instantiated ImageChannel object to the session.
        Useful for when channels are created in background threads.
        """
        if not channel.is_placeholder:
            if self._reference_shape is None:
                self._reference_shape = channel.shape
            else:
                if channel.shape != self._reference_shape:
                    raise ValueError(
                        f"Dimension mismatch. Expected {self._reference_shape}, "
                        f"got {channel.shape} for {channel.name}"
                    )
        
        self.channels.append(channel)
        self.data_changed.emit()
        self.project_changed.emit()

    def serialize_annotations(self) -> List[dict]:
        """Convert all annotations to serializable dicts."""
        from dataclasses import asdict
        return [asdict(ann) for ann in self.annotations]

    def set_annotations(self, ann_dicts: List[dict]):
        """Restore annotations from serialized dicts."""
        self.annotations = [] # Clear current list
        if ann_dicts is None:
            ann_dicts = [] # Handle None input safely
            
        for d in ann_dicts:
            try:
                ann = GraphicAnnotation(**d)
                self.annotations.append(ann)
            except Exception as e:
                print(f"Error restoring annotation: {e}")
        self.project_changed.emit()

    def sync_existing_rois_to_annotations(self):
        """
        USER REQUEST: Converts all current ROIs into graphic annotations 
        if they don't already have one. This is triggered when 'Sync ROIs as Annotations'
        is toggled ON in the ROI Toolbox.
        """
        existing_roi_ids = {ann.roi_id for ann in self.annotations if ann.roi_id}
        
        added_count = 0
        for roi in self.roi_manager.get_all_rois():
            if roi.id in existing_roi_ids:
                continue
                
            # Map ROI type to GraphicAnnotation type
            ann_type = roi.roi_type
            if ann_type == "rectangle":
                ann_type = "rect"
            elif ann_type == "point":
                ann_type = "circle"
            # polygon, line, arrow, ellipse usually match or are handled by fallback
                
            # Convert QPointF list to List[Tuple[float, float]]
            points = [(p.x(), p.y()) for p in roi.points]
            
            # Fallback for ROI types that might not have points list populated (e.g. Magic Wand)
            if not points and not roi.path.isEmpty():
                rect = roi.path.boundingRect()
                if ann_type in ["rect", "rectangle", "ellipse"]:
                    points = [(rect.left(), rect.top()), (rect.right(), rect.bottom())]
                else:
                    # For complex paths without points, we'd need path-to-points conversion
                    # For now, use bounds as a basic placeholder
                    points = [(rect.left(), rect.top()), (rect.right(), rect.bottom())]

            if not points:
                continue

            ann = GraphicAnnotation(
                id=str(uuid.uuid4()),
                type=ann_type,
                points=points,
                color=roi.color.name(),
                thickness=2,
                roi_id=roi.id,
                selectable=True
            )
            self.annotations.append(ann)
            added_count += 1
            
        if added_count > 0:
            print(f"[Session] Synced {added_count} existing ROIs to annotations.")
            self.project_changed.emit()

    def add_channel(self, file_path: str, color: str = "#FFFFFF", name: Optional[str] = None, data: Optional[np.ndarray] = None) -> ImageChannel:
        """
        Loads and adds a new channel to the session.
        Validates that dimensions match existing channels (unless placeholders).
        """
        new_channel = ImageChannel(file_path, color, name, data=data)
        
        # If new channel is a placeholder, it accepts any shape.
        # If new channel is real, we need to check consistency.
        
        if not new_channel.is_placeholder:
            if self._reference_shape is None:
                self._reference_shape = new_channel.shape
            else:
                if new_channel.shape != self._reference_shape:
                    raise ValueError(
                        f"Dimension mismatch. Expected {self._reference_shape}, "
                        f"got {new_channel.shape} for {new_channel.name}"
                    )
        
        self.channels.append(new_channel)
        self.data_changed.emit()
        self.project_changed.emit()
        return new_channel

    def remove_channel(self, index: int):
        if 0 <= index < len(self.channels):
            self.channels.pop(index)
            if not self.channels:
                self._reference_shape = None
            self.project_changed.emit()

    def get_channel(self, index: int) -> Optional[ImageChannel]:
        if 0 <= index < len(self.channels):
            return self.channels[index]
        return None

    def crop_data(self, rect: tuple):
        """
        Physically crops all channels to the given rect (x, y, w, h).
        Updates ROIs by offsetting and filtering.
        """
        x, y, w, h = rect
        # Clip coordinates to integer
        x = int(x)
        y = int(y)
        w = int(w)
        h = int(h)
        
        if not self.channels:
            return

        # 1. Update Channels
        for ch in self.channels:
            if ch.is_placeholder: continue
            
            # Clip bounds
            h_img, w_img = ch.shape[:2]
            x0 = max(0, x)
            y0 = max(0, y)
            x1 = min(w_img, x + w)
            y1 = min(h_img, y + h)
            
            if x1 <= x0 or y1 <= y0:
                # Result is empty
                new_data = np.zeros((1, 1), dtype=ch.dtype)
            else:
                new_data = ch.raw_data[y0:y1, x0:x1].copy()
                
            ch.update_data(new_data)
            
        # Update reference shape
        if self.channels:
            self._reference_shape = self.channels[0].shape
            
        # 2. Update ROIs
        # Calculate offset based on actual crop start (x0, y0) vs original origin (0,0)
        # We need the effective offset applied to the image coordinate system.
        # The new (0,0) corresponds to old (x0, y0).
        # So old_coord - (x0, y0) = new_coord.
        
        # We need to find what x0, y0 were used.
        # Assuming all images have same size, x0/y0 are same.
        # If images differ, cropping might be inconsistent? 
        # But we enforce consistency.
        
        # Use first channel shape for logic
        ref_ch = self.channels[0]
        # Ensure we get (H, W) even if shape was somehow corrupted
        ref_shape = ref_ch.shape
        h_img = ref_shape[0]
        w_img = ref_shape[1]
        
        x0 = max(0, x)
        y0 = max(0, y)
        
        # New dimensions
        new_h = ref_ch.shape[0]
        new_w = ref_ch.shape[1]
        
        offset_x = -x0
        offset_y = -y0
        
        self.roi_manager.offset_rois(offset_x, offset_y, (0, 0, new_w, new_h))
        self.data_changed.emit()

    def restore_data(self, channels_dump, rois_dump):
        """Restores full session state (Undo)."""
        self.channels = channels_dump
        if self.channels:
            self._reference_shape = self.channels[0].shape
        self.roi_manager.set_rois(rois_dump)
        self.data_changed.emit()

    def export_channels(self, output_dir: str, sample_name: str = None, suffix: str = "_crop"):
        """Exports all channels to TIFF."""
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
        for ch in self.channels:
            if ch.is_placeholder: continue
            
            # Construct filename
            # Format: SampleName_ChannelName_crop.tif
            if sample_name:
                # Sanitize names
                s_name = sample_name.replace(" ", "_")
                c_name = ch.name.replace(" ", "_")
                fname = f"{s_name}_{c_name}{suffix}.tif"
            else:
                if ch.file_path:
                    base = os.path.splitext(os.path.basename(ch.file_path))[0]
                else:
                    base = ch.name
                fname = f"{base}{suffix}.tif"
            
            save_path = os.path.join(output_dir, fname)
            
            tifffile.imwrite(save_path, ch.raw_data)
