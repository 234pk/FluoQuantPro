import os
import sys
from pathlib import Path
import multiprocessing

import time
import ctypes
import multiprocessing
import matplotlib
matplotlib.use('QtAgg')
import numpy as np
import cv2
import tifffile

from PySide6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QWidget, 
                               QHBoxLayout, QLabel, QFileDialog, QDockWidget, QMenu, QMessageBox, QScrollArea, QFrame, QToolButton, QSizePolicy,
                               QGraphicsDropShadowEffect, QPushButton, QStackedWidget)
from PySide6.QtGui import QAction, QDesktopServices, QColor, QPalette
from PySide6.QtCore import Qt, QTimer, QUrl, QSettings, QSize, QPropertyAnimation, QEasingCurve, QRect, QEvent, QPoint

from src.core.language_manager import LanguageManager, tr

# --- Splash Helper ---
def update_splash(text=None, progress=None, close=False):
    try:
        import pyi_splash
        if text:
            pyi_splash.update_text(text)
        if progress is not None:
            pyi_splash.update_progress(progress)
        if close:
            pyi_splash.close()
    except (ImportError, AttributeError, RuntimeError):
        pass

# Ensure the project root is in sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

import time
import ctypes
import multiprocessing
import matplotlib
matplotlib.use('QtAgg')
import numpy as np
import cv2
import tifffile

# 更新进度
update_splash(tr("Loading GUI Components..."), 40)

from PySide6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QWidget, 
                               QHBoxLayout, QLabel, QFileDialog, QDockWidget, QMenu, QMessageBox, QScrollArea, QFrame, QToolButton, QSizePolicy,
                               QGraphicsDropShadowEffect, QPushButton, QStackedWidget)
from PySide6.QtGui import QAction, QDesktopServices, QColor, QPalette
from PySide6.QtCore import Qt, QTimer, QUrl, QSettings, QSize, QPropertyAnimation, QEasingCurve, QRect, QEvent, QPoint

class HoverEffectFilter(QFrame):
    """
    Event filter to provide advanced hover/press effects for buttons:
    - Scaling (105% hover, 98% press)
    - Dynamic Shadows (Blur/Opacity)
    - Elastic Animations
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self._animations = {}
        self._shadows = {}

    def eventFilter(self, obj, event):
        # Strict type checking to avoid interfering with CanvasView or other widgets
        if type(obj) not in (QPushButton, QToolButton):
            return False

        # Only handle basic mouse/hover events for buttons
        if not obj.isEnabled():
            return False

        if event.type() == QEvent.Type.Enter:
            self._apply_hover_effect(obj, True)
        elif event.type() == QEvent.Type.Leave:
            self._apply_hover_effect(obj, False)
        elif event.type() == QEvent.Type.MouseButtonPress:
            self._apply_press_effect(obj, True)
        elif event.type() == QEvent.Type.MouseButtonRelease:
            self._apply_press_effect(obj, False)
            
        return False # IMPORTANT: Never return True, always let the original widget handle the event

    def _apply_hover_effect(self, btn, hovering):
        # 1. Scaling Animation - Subtler scaling
        scale = 1.02 if hovering else 1.0
        self._animate_geometry(btn, scale, tilt=hovering)
        
        # 2. Shadow Effect - Subtler shadow
        if hovering:
            shadow = QGraphicsDropShadowEffect(btn)
            shadow.setBlurRadius(10) # Reduced spread
            shadow.setOffset(0, 3) # Reduced offset
            shadow.setColor(QColor(0, 0, 0, 40)) # Lighter shadow
            btn.setGraphicsEffect(shadow)
            self._shadows[btn] = shadow
        else:
            btn.setGraphicsEffect(None)
            if btn in self._shadows:
                del self._shadows[btn]

    def _apply_press_effect(self, btn, pressed):
        scale = 0.98 if pressed else 1.02
        self._animate_geometry(btn, scale, tilt=not pressed)

    def _animate_geometry(self, btn, scale_factor, tilt=False):
        base_geo = btn.property("base_geometry")
        if base_geo is None:
            base_geo = btn.geometry()
            btn.setProperty("base_geometry", base_geo)

        center = base_geo.center()
        
        # Add very slight offset for dynamic feel
        if tilt:
            center += QPoint(0, -1) # Move up only 1px on hover
            
        new_w = int(base_geo.width() * scale_factor)
        new_h = int(base_geo.height() * scale_factor)
        
        target_geo = QRect(0, 0, new_w, new_h)
        target_geo.moveCenter(center)

        anim = self._animations.get(btn)
        if anim:
            anim.stop()
        else:
            anim = QPropertyAnimation(btn, b"geometry")
            self._animations[btn] = anim

        anim.setDuration(150) # Faster transition (150ms)
        anim.setStartValue(btn.geometry())
        anim.setEndValue(target_geo)
        
        # Use smoother curves without overshoot
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            
        anim.start()
import csv
from src.core.logger import Logger  # Import Logger
from src.core.data_model import Session, ImageChannel  
from src.core.enums import DrawingMode
from src.core.renderer import Renderer
from src.core.performance_monitor import PerformanceMonitor
from src.gui.multi_view import MultiViewWidget
from src.gui.filmstrip_view import FilmstripWidget
from src.gui.tools import MagicWandTool, PolygonTool, CropTool, PointCounterTool, LineScanTool, BatchSelectionTool, DrawToolFactory, BaseDrawTool
from src.gui.import_dialog import FluorophoreAssignmentDialog
from src.gui.project_dialog import ProjectSetupDialog
from src.core.project_model import ProjectModel
from src.core.overlap_analyzer import ROIOverlapAnalyzer
from src.gui.sample_list import SampleListWidget
from src.gui.roi_toolbox import RoiToolbox
from src.gui.result_widget import MeasurementResultWidget
from src.gui.enhance_panel import EnhancePanel
try:
    from src.gui.colocalization_panel import ColocalizationPanel
except Exception as e:
    import traceback
    print(f"CRITICAL ERROR: Failed to import ColocalizationPanel: {e}")
    traceback.print_exc()
    ColocalizationPanel = None
from src.gui.adjustment_panel import AdjustmentPanel
from src.gui.annotation_panel import AnnotationPanel
from src.gui.measurement_dialog import MeasurementSettingsDialog
from src.gui.calibration_dialog import CalibrationDialog
from src.gui.export_settings_dialog import ExportSettingsDialog
from src.gui.auto_save_dialog import AutoSaveSettingsDialog
from src.gui.settings_dialog import SettingsDialog
import os

# 更新进度
update_splash(tr("Loading Resources..."), 70)

from src.gui.icon_manager import IconManager, get_icon
from src.gui.toggle_switch import ToggleSwitch
from src.gui.theme_manager import ThemeManager
from src.core.language_manager import LanguageManager, tr

from PySide6.QtCore import QThread, Signal
from PySide6.QtCore import QPointF

import os
import sys

# Get absolute path to resources
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
def get_resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    # 1. 优先检查 PyInstaller 的临时解压目录
    if hasattr(sys, '_MEIPASS'):
        path = os.path.join(sys._MEIPASS, relative_path)
        if os.path.exists(path):
            return path
    
    # 2. 检查可执行文件同级目录 (针对手动复制的文件)
    exe_dir = os.path.dirname(sys.executable)
    exe_path = os.path.join(exe_dir, relative_path)
    if os.path.exists(exe_path):
        return os.path.normpath(exe_path)

    # 3. 对于 macOS Bundle 结构
    macos_bundle_res = os.path.join(exe_dir, "..", "Resources", relative_path)
    if os.path.exists(macos_bundle_res):
        return os.path.normpath(macos_bundle_res)
        
    # 4. 默认回退到开发环境路径
    dev_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), relative_path)
    return dev_path

class SceneLoaderWorker(QThread):
    # scene_id, index, data (numpy array or None), channel_def (object)
    channel_loaded = Signal(str, int, object, object) 
    finished_loading = Signal(str)

    def __init__(self, scene_id, channel_defs):
        super().__init__()
        self.scene_id = scene_id
        self.channel_defs = channel_defs
        self._is_running = True
        
    def preprocess_data(self, data):
        """
        Pre-process data in the worker thread to save main thread CPU time.
        Handles Max Projection for Z-stacks/Multichannel images.
        """
        if data is None: return None
        
        # Logic matched with ImageChannel.__init__
        if data.ndim == 3:
            # Case 1: (C, H, W) or (Z, H, W) where C/Z is small leading dimension
            if data.shape[0] < 10: 
                # If it's 3 or 4 channels, it might be RGB (channels-first).
                # Keep as 3D so ImageChannel can extract the correct channel based on name.
                if data.shape[0] in (3, 4):
                    return data
                # Otherwise, assume Z-stack and take Max Projection
                return np.max(data, axis=0)
            
            # Case 2: (H, W, C) where C is small trailing dimension (e.g. RGB)
            elif data.shape[2] in (3, 4):
                # RGB/RGBA - Keep as 3D for ImageChannel to handle extraction
                return data
            elif data.shape[2] < 10:
                # Multichannel -> Grayscale Max Projection
                return np.max(data, axis=2)
                
        return data

    def run(self):
        Logger.info("[Worker] Started")
        for i, ch_def in enumerate(self.channel_defs):
            if not self._is_running: return
            
            data = None
            if ch_def.path and os.path.exists(ch_def.path):
                try:
                    Logger.info(f"[Worker] Reading {os.path.basename(ch_def.path)}...")
                    # Use the robust ImageLoader instead of raw tifffile
                    from src.core.image_loader import ImageLoader
                    data, is_rgb = ImageLoader.load_image(ch_def.path)
                    
                    # ImageLoader already handles 4D+ and basic dimension normalization
                    # We still call preprocess_data for any extra user-defined logic (like Max Projection for 3D Z-stacks)
                    if data is not None:
                        data = self.preprocess_data(data)
                        
                except Exception as e:
                    Logger.error(f"Error loading {ch_def.path}: {e}")
            
            if not self._is_running: return
            
            # Create ImageChannel object in worker thread (performs stats calculation)
            try:
                    Logger.info(f"[Worker] Creating ImageChannel {i}...")
                    # Note: ImageChannel is a data class, safe to create here if no Qt parents involved
                    ch_obj = ImageChannel(ch_def.path, ch_def.color, ch_def.channel_type, data=data, auto_contrast=False)
                    Logger.info(f"[Worker] Emitting channel_loaded {i}")
                    self.channel_loaded.emit(self.scene_id, i, ch_obj, ch_def)
            except Exception as e:
                Logger.error(f"Error creating ImageChannel in worker: {e}")
                # Fallback to passing data if object creation fails (should not happen)
                self.channel_loaded.emit(self.scene_id, i, data, ch_def)

        Logger.info("[Worker] Finished")
        self.finished_loading.emit(self.scene_id)

    def stop(self):
        self._is_running = False
        self.wait()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        # Initialize Logger
        Logger.setup()
        Logger.info("Application starting...")
        
        self.setWindowTitle(tr("FluoQuant Pro v3.0"))
        self.setWindowIcon(get_icon("wand")) # Using wand as app icon
        
        # Adaptive UI: Set initial size based on screen geometry
        screen = QApplication.primaryScreen()
        if screen:
            # Use availableGeometry to respect taskbar
            available_geo = screen.availableGeometry()
            
            # Use 90% of available space for a generous but safe default
            width = int(available_geo.width() * 0.9)
            height = int(available_geo.height() * 0.9)
            
            # Ensure it doesn't exceed available screen space
            width = min(width, available_geo.width())
            height = min(height, available_geo.height())
            
            # Minimum reasonable size
            width = max(1024, width)
            height = max(720, height)
            
            self.resize(width, height)
            
            # Center within the available workspace
            self.move(
                available_geo.x() + (available_geo.width() - width) // 2,
                available_geo.y() + (available_geo.height() - height) // 2
            )
            
            # On small screens (e.g. 1366x768), default to maximized for better UX
            if available_geo.width() <= 1366:
                QTimer.singleShot(0, self.showMaximized)
        else:
            self.resize(1280, 800)
        
        self.loader_worker = None
        self.current_project_path = None
        
        # Undo Stack
        from PySide6.QtGui import QUndoStack
        self.undo_stack = QUndoStack(self)
        
        # Data Models
        self.session = Session(undo_stack=self.undo_stack)
        self.session.main_window = self
        Logger.debug("[Main] Session main_window reference set")
        self.drawing_mode = DrawingMode.NONE
        self.session.data_changed.connect(self.refresh_display)
        self.project_model = ProjectModel(undo_stack=self.undo_stack)

        # Initialize Hover Effect Filter
        self.hover_filter = HoverEffectFilter(self)
        QApplication.instance().installEventFilter(self.hover_filter)

        # Auto-Save Setup
        self.settings = QSettings("FluoQuantPro", "AppSettings")
        self.auto_save_timer = QTimer(self)
        self.auto_save_timer.timeout.connect(self.auto_save_project)
        self.setup_auto_save()
        
        # Performance Monitor
        self.perf_monitor = PerformanceMonitor.instance()
        self.perf_monitor.lag_detected.connect(self.show_recovery_dialog)
        self.perf_monitor.performance_mode_changed.connect(self.on_performance_mode_changed)

        # OpenCL Initialization
        self.init_opencl()
        
        # 更新进度到完成
        update_splash(tr("Finalizing UI..."), 100)
        
        # Debounce Timer for Display Refresh
        # Prevents excessive re-rendering during rapid parameter changes
        self.refresh_debounce_timer = QTimer(self)
        self.refresh_debounce_timer.setSingleShot(True)
        self.refresh_debounce_timer.setInterval(50) # 50ms debounce for smooth but responsive updates
        self.refresh_debounce_timer.timeout.connect(self._perform_refresh_display)
        self._pending_fit_view = False
        
        # Store accumulated measurements for all scenes
        # List of Dicts, with 'Scene' key added
        self.all_measurements = [] 
        self.current_scene_id = None
        
        # Default Measurement Settings
        self.measurement_settings = {
            'Area': True,
            'Mean': True,
            'IntDen': True,
            'Min': True,
            'Max': True,
            'BgMean': False,
            'CorrectedMean': False,
            'Accumulate': True
        }
        
        # UI Setup
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)
        # Add a small bottom margin to ensure status bar is always visible
        # and not covered by any floating or expanding widgets.
        self.layout.setContentsMargins(0, 0, 0, 10) 
        # Main Layout - Central Widget (Canvas Only)
        # We use a StackedWidget to toggle between Grid View and Filmstrip View
        self.view_stack = QStackedWidget()
        self.layout.addWidget(self.view_stack)

        # 1. Grid View (Original MultiView)
        self.multi_view = MultiViewWidget(self.session)
        self.view_stack.addWidget(self.multi_view)

        # 2. Filmstrip View
        self.filmstrip_view = FilmstripWidget(self.session)
        self.view_stack.addWidget(self.filmstrip_view)

        # List of all view containers for agnostic operations
        self.view_containers = [self.multi_view, self.filmstrip_view]

        # Default to Grid View
        self.view_stack.setCurrentWidget(self.multi_view)
        
        # Connect Empty State signals for ALL view containers
        for container in self.view_containers:
            container.new_project_requested.connect(self.new_project)
            container.open_project_requested.connect(self.open_project)
            container.open_recent_requested.connect(self.load_project)
            container.import_folder_requested.connect(self.import_folder_auto)
            container.import_merge_requested.connect(self.on_import_merge)
            if hasattr(container, 'import_requested'):
                container.import_requested.connect(lambda: self.sample_list.load_images_to_pool())
        
        # --- Sidebar: Sample List ---
        self.sample_dock = QDockWidget(tr("Project Samples"), self)
        self.sample_dock.setObjectName("SampleDock") # Important for state saving
        self.sample_dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        self.sample_dock.setMinimumWidth(50) # Unified minimum width for compression
        self.sample_list = SampleListWidget(self.project_model)
        self.sample_list.scene_selected.connect(self.load_scene)
        self.sample_list.channel_selected.connect(self.on_sample_channel_selected)
        self.sample_list.scene_deleted.connect(self.handle_scene_deletion)
        self.sample_list.channel_color_changed.connect(self.update_active_channel_color)
        if hasattr(self.sample_list, "channel_file_assigned"):
            self.sample_list.channel_file_assigned.connect(self.on_channel_file_assigned)
        if hasattr(self.sample_list, "channel_cleared"):
            self.sample_list.channel_cleared.connect(self.on_channel_cleared)
        if hasattr(self.sample_list, "channel_removed"):
            self.sample_list.channel_removed.connect(self.on_channel_removed)
        self.sample_dock.setWidget(self.sample_list)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.sample_dock)
        
        # Unified minimum width for docks to allow extreme compression
        self.sample_dock.setMinimumWidth(50)
        
        # --- Right Sidebar: Tabbed Control Panel ---
        self.right_dock = QDockWidget(tr("Controls"), self)
        self.right_dock.setObjectName("ControlDock")
        self.right_dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        self.right_dock.setMinimumWidth(0) # Allow free resizing (User request)
        # Ensure resizing features are enabled
        self.right_dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable | 
                                    QDockWidget.DockWidgetFeature.DockWidgetFloatable | 
                                    QDockWidget.DockWidgetFeature.DockWidgetClosable)
        
        # Sidebar Panel
        from src.gui.sidebar_panel import RightSidebarControlPanel
        self.control_tabs = RightSidebarControlPanel()
        self.control_tabs.setMinimumWidth(0)
        Logger.debug("[Main] Control Tabs replaced with RightSidebarControlPanel")

        self.right_dock.setWidget(self.control_tabs)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.right_dock)

        # Adaptive Right Dock Initial Width
        if screen:
             # Initially allocate around 20% for controls if screen is large
             initial_right_width = int(width * 0.22)
             self.resizeDocks([self.right_dock], [initial_right_width], Qt.Horizontal)
        
        self.right_dock.setMinimumWidth(50) # Unified minimum width for compression
        
        # 1. Toolbox Tab
        self.roi_toolbox = None # Initialized later when actions are ready
        
        # 2. Adjustment Tab
        self.adjustment_panel = AdjustmentPanel(self.session)
        self.adjustment_panel.settings_changed.connect(self.on_display_settings_changed)
        
        # 3. Enhance Tab
        self.enhance_panel = EnhancePanel(self.session)
        self.enhance_panel.settings_changed.connect(self.on_display_settings_changed)
        
        # 4. Colocalization (Line Scan) Tab
        self.colocalization_panel = ColocalizationPanel(self.session) if ColocalizationPanel else None
        
        # 5. Annotation Tab
        self.annotation_panel = AnnotationPanel(self.session)
        self.annotation_panel.settings_changed.connect(self.on_overlay_settings_changed)
        self.annotation_panel.annotation_tool_selected.connect(self.on_annotation_tool_selected)
        self.annotation_panel.clear_annotations_requested.connect(self.on_clear_annotations)
        #self.annotation_panel.annotation_updated.connect(self.on_annotation_updated)
        self.annotation_panel.annotation_selected.connect(self.select_view_annotation) # Forward Association
        
        # Menu Bar
        self.create_actions()
        
        # Inject action into colocalization panel after actions are created
        if self.colocalization_panel:
            self.colocalization_panel.set_line_scan_action(self.action_line_scan)
        
        # Now create the toolbox widget since actions exist
        self.roi_toolbox = RoiToolbox(self)
        
        # Close splash screen if present (PyInstaller)
        update_splash(close=True)
        
        # Connect session signals (Combined)
        manager = self.session.roi_manager
        
        # 稳固连接信号，不再尝试 disconnect（因为此时是初始化阶段）
        manager.roi_added.connect(self.on_roi_added)
        manager.roi_removed.connect(self.on_roi_removed)
        manager.roi_updated.connect(self.on_roi_updated)
        manager.selection_changed.connect(self.on_roi_selection_changed)
        
        # Connect toolbox to manager signals
        if hasattr(self, 'roi_toolbox') and self.roi_toolbox:
            manager.roi_added.connect(self.roi_toolbox.update_counts_summary)
            manager.roi_removed.connect(self.roi_toolbox.update_counts_summary)
            manager.roi_updated.connect(self.roi_toolbox.update_counts_summary)
        
        # Connect ColocalizationPanel to session changes
        if self.colocalization_panel:
            self.session.data_changed.connect(self.colocalization_panel.refresh_channels)
            self.session.project_changed.connect(self.colocalization_panel.refresh_channels)
        
        # Connect OverlayPanel to session changes
        self.session.data_changed.connect(self.annotation_panel.refresh_from_session)
        self.session.project_changed.connect(self.annotation_panel.refresh_from_session)
        
        # Wrap in ScrollArea for visibility on small screens (Toolbox)
        toolbox_scroll = QScrollArea()
        toolbox_scroll.setWidget(self.roi_toolbox)
        toolbox_scroll.setWidgetResizable(True)
        toolbox_scroll.setMinimumWidth(0)
        toolbox_scroll.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        
        # Wrap Annotation Panel in ScrollArea (Content can be tall)
        annotation_scroll = QScrollArea()
        annotation_scroll.setWidget(self.annotation_panel)
        annotation_scroll.setWidgetResizable(True)
        annotation_scroll.setMinimumWidth(0)
        annotation_scroll.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        
        # Wrap Adjustment Panel in ScrollArea
        adjustment_scroll = QScrollArea()
        adjustment_scroll.setWidget(self.adjustment_panel)
        adjustment_scroll.setWidgetResizable(True)
        adjustment_scroll.setMinimumWidth(0)
        adjustment_scroll.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        
        # Wrap Enhance Panel in ScrollArea
        enhance_scroll = QScrollArea()
        enhance_scroll.setWidget(self.enhance_panel)
        enhance_scroll.setWidgetResizable(True)
        enhance_scroll.setMinimumWidth(0)
        enhance_scroll.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        
        # Wrap Colocalization Panel in ScrollArea
        colocalization_scroll = None
        if self.colocalization_panel:
            colocalization_scroll = QScrollArea()
            colocalization_scroll.setWidget(self.colocalization_panel)
            colocalization_scroll.setWidgetResizable(True)
            colocalization_scroll.setMinimumWidth(0)
            colocalization_scroll.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        
        # 4. Measure Results Tab
        self.result_widget = MeasurementResultWidget()
        
        # Store tabs for visibility management
        self.all_tabs_data = [
            ("toolbox", toolbox_scroll, tr("Toolbox")),
            ("adjustments", adjustment_scroll, tr("Adjustments")),
            ("enhance", enhance_scroll, tr("Enhance")),
            ("annotation", annotation_scroll, tr("Annotations")),
            ("results", self.result_widget, tr("Measure Results"))
        ]
        if self.colocalization_panel:
            self.all_tabs_data.insert(3, ("colocalization", colocalization_scroll, tr("Colocalization")))
        
        # Initial visibility update
        self.update_tab_visibility()
        
        # Connect Tab Change Signal
        self.control_tabs.currentChanged.connect(self.on_tab_changed)
        
        # Connect Fixed Size Checkbox
        self.roi_toolbox.chk_fixed_size.toggled.connect(self.on_fixed_size_toggled)
        
        # Connect ROI changes to update counts summary
        self.session.roi_manager.roi_added.connect(self.roi_toolbox.update_counts_summary)
        self.session.roi_manager.roi_removed.connect(lambda _: self.roi_toolbox.update_counts_summary())

        self.setup_menu()
        
        # Status Bar
        self.setStatusBar(self.statusBar())
        self.lbl_status = QLabel(tr("Ready"))
        self.statusBar().addWidget(self.lbl_status, 1) # Stretch factor 1 to take available space
        
        # Zoom Label
        self.lbl_zoom = QLabel("100%")
        self.lbl_zoom.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.lbl_zoom.setMinimumWidth(60)
        # Add to status bar as a permanent widget (right side)
        self.statusBar().addPermanentWidget(self.lbl_zoom)

        # Memory Label
        self.lbl_memory = QLabel(tr("RAM: 0 MB"))
        self.lbl_memory.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.lbl_memory.setMinimumWidth(120)
        self.lbl_memory.setStyleSheet("margin-right: 10px; color: #666;")
        self.statusBar().addPermanentWidget(self.lbl_memory)

        # Connect Performance Monitor Signals
        self.perf_monitor.memory_status_updated.connect(self.update_memory_label)
        self.perf_monitor.memory_threshold_exceeded.connect(self.on_memory_warning)

        # Connect Adjustment Panel -> MultiView selection sync
        # Use channel_activated which is defined in AdjustmentPanel
        if hasattr(self.adjustment_panel, 'channel_activated'):
            self.adjustment_panel.channel_activated.connect(self.select_view_channel)
        else:
            print("WARNING: AdjustmentPanel has no 'channel_activated' signal")

        # Connect View Container Signals
        for container in self.view_containers:
            container.channel_selected.connect(self.on_channel_selected)
            container.channel_selected.connect(self.adjustment_panel.set_active_channel)
            container.channel_selected.connect(self.enhance_panel.set_active_channel)
            container.channel_file_dropped.connect(self.handle_channel_file_drop)
            container.mouse_moved_on_view.connect(self.update_status_mouse_info)
            container.tool_cancelled.connect(self.on_tool_cancelled)
            container.zoom_changed.connect(self.update_zoom_label)
            if hasattr(container, 'import_requested'):
                container.import_requested.connect(lambda: self.sample_list.load_images_to_pool())
        
        # Connect Enhance Panel -> MultiView selection sync
        self.enhance_panel.channel_activated.connect(self.select_view_channel)
        
        # Tools
        self.wand_tool = MagicWandTool(self.session)
        self.wand_tool.preview_changed.connect(self.on_tool_preview_changed)
        self.wand_tool.tolerance_changed.connect(self.handle_wand_tolerance_changed)
        self.wand_tool.committed.connect(lambda msg: self.lbl_status.setText(msg))
        
        self.polygon_tool = PolygonTool(self.session)
        self.polygon_tool.preview_changed.connect(self.on_tool_preview_changed)
        self.polygon_tool.committed.connect(lambda msg: self.lbl_status.setText(msg))
        
        self.rect_tool = DrawToolFactory.create(self.session, "rect")
        self.rect_tool.preview_changed.connect(self.on_tool_preview_changed)
        self.rect_tool.committed.connect(lambda msg: self.lbl_status.setText(msg))
        
        self.ellipse_tool = DrawToolFactory.create(self.session, "ellipse")
        self.ellipse_tool.preview_changed.connect(self.on_tool_preview_changed)
        self.ellipse_tool.committed.connect(lambda msg: self.lbl_status.setText(msg))
        
        self.count_tool = PointCounterTool(self.session)
        self.count_tool.preview_changed.connect(self.on_tool_preview_changed)
        self.count_tool.committed.connect(lambda msg: self.lbl_status.setText(msg))
        
        self.line_scan_tool = LineScanTool(self.session)
        self.line_scan_tool.preview_changed.connect(self.on_tool_preview_changed)
        if self.colocalization_panel:
            self.line_scan_tool.line_updated.connect(self.colocalization_panel.on_line_updated)
        self.line_scan_tool.committed.connect(self._on_tool_committed)
        
        self.crop_tool = CropTool(self.session)
        
        self.text_tool = DrawToolFactory.create(self.session, "text")
        self.text_tool.preview_changed.connect(self.on_tool_preview_changed)
        self.text_tool.committed.connect(self._on_tool_committed)

        self.arrow_tool = DrawToolFactory.create(self.session, "arrow")
        self.arrow_tool.preview_changed.connect(self.on_tool_preview_changed)
        self.arrow_tool.committed.connect(self._on_tool_committed)

        self.batch_tool = BatchSelectionTool(self.session)
        self.batch_tool.preview_changed.connect(self.on_tool_preview_changed)
        self.batch_tool.selection_made.connect(self.on_batch_selection_made)

        # Apply Modern Interactivity Stylesheet
        self.apply_stylesheet()
        
        # Connect Language Change
        LanguageManager.instance().language_changed.connect(self.retranslate_ui)
        
        # Connect Theme Change
        ThemeManager.instance().theme_changed.connect(self.on_theme_changed)
        
        # Restore UI State (Geometry, Docks, Splitters)
        self.restore_ui_state()
        
    def on_annotation_selected_on_canvas(self, ann_id):
        """Callback when an annotation is selected on the canvas (CanvasView)."""
        # Switch to Annotation tab if not already there? 
        # Maybe optional, but user expects property panel access.
        # self.control_tabs.setCurrentIndex(4) # Switch to Annotation tab
        self.annotation_panel.select_annotation_by_id(ann_id)

    def retranslate_ui(self):
        """Update all UI text when language changes."""
        self.setWindowTitle(tr("FluoQuant Pro v1.1"))
        
        # Update Dock Titles
        self.sample_dock.setWindowTitle(tr("Project Samples"))
        self.right_dock.setWindowTitle(tr("Controls"))
        
        # Update Tab Titles
        # Check if tabs exist (they should be created in __init__)
        if self.control_tabs.count() >= 6:
            self.control_tabs.setTabText(0, tr("Toolbox"))
            self.control_tabs.setTabText(1, tr("Adjustments"))
            self.control_tabs.setTabText(2, tr("Enhance"))
            self.control_tabs.setTabText(3, tr("Colocalization"))
            self.control_tabs.setTabText(4, tr("Annotation"))
            self.control_tabs.setTabText(5, tr("Measure Results"))
            
        # Update Status Bar
        if self.lbl_status.text() == "Ready" or self.lbl_status.text() == tr("Ready"):
            self.lbl_status.setText(tr("Ready"))

        # Update Actions
        self.action_new_project.setText(tr("New Project..."))
        self.action_new_project.setStatusTip(tr("Create a new project in a selected folder"))
        self.action_new_project.setToolTip(tr("Create a new project in a selected folder"))
        
        self.action_open_project.setText(tr("Open Project..."))
        self.action_open_project.setStatusTip(tr("Open an existing project folder"))
        self.action_open_project.setToolTip(tr("Open an existing project folder"))
        
        self.recent_projects_menu.setTitle(tr("Recent Projects"))
        self.update_recent_projects_menu() # Refresh items with translated text
        
        # Menu Titles
        self.menu_file.setTitle(tr("File"))
        self.menu_import.setTitle(tr("Import"))
        self.menu_edit.setTitle(tr("Edit"))
        self.menu_view.setTitle(tr("View"))
        self.menu_analysis.setTitle(tr("Analysis"))
        self.menu_export.setTitle(tr("Export"))
        self.menu_help.setTitle(tr("Help"))
        
        self.action_save_project.setText(tr("Save Project"))
        self.action_save_project.setStatusTip(tr("Save all changes to the project"))
        self.action_save_project.setToolTip(tr("Save all changes to the project"))
        
        self.action_save_project_as.setText(tr("Save Project As..."))
        self.action_save_project_as.setStatusTip(tr("Save the current project to a new folder"))
        self.action_save_project_as.setToolTip(tr("Save the current project to a new folder"))
        
        self.action_settings.setText(tr("Application Settings..."))
        self.action_settings.setStatusTip(tr("Configure global application preferences"))
        self.action_settings.setToolTip(tr("Configure global application preferences"))
        
        self.action_auto_save_settings.setText(tr("Auto Save Settings..."))
        self.action_auto_save_settings.setStatusTip(tr("Configure project auto-save behavior"))
        self.action_auto_save_settings.setToolTip(tr("Configure project auto-save behavior"))
        
        self.action_import.setText(tr("Import Images to Pool..."))
        self.action_import.setStatusTip(tr("Select individual images to add to the image pool"))
        self.action_import.setToolTip(tr("Select individual images to add to the image pool"))
        
        self.action_import_folder.setText(tr("Import Folder (Auto-Group)..."))
        self.action_import_folder.setStatusTip(tr("Import all images in a folder and group by metadata/name"))
        self.action_import_folder.setToolTip(tr("Import all images in a folder and group by metadata/name"))
        
        self.action_import_merge.setText(tr("Import Merge (RGB Split)..."))
        self.action_import_merge.setStatusTip(tr("Import an RGB merge image and split into fluorophore channels"))
        self.action_import_merge.setToolTip(tr("Import an RGB merge image and split into fluorophore channels"))
        
        self.action_exit.setText(tr("Exit"))
        self.action_exit.setStatusTip(tr("Close the application"))
        self.action_exit.setToolTip(tr("Close the application"))
        
        self.action_undo.setText(tr("Undo"))
        self.action_undo.setStatusTip(tr("Undo the last action"))
        self.action_undo.setToolTip(tr("Undo the last action"))
        
        self.action_redo.setText(tr("Redo"))
        self.action_redo.setStatusTip(tr("Redo the last undone action"))
        self.action_redo.setToolTip(tr("Redo the last undone action"))
        
        # --- Toolbar Setup ---
        # Explicitly create main toolbar if not already present (usually done in setup_ui but missing here)
        self.main_toolbar = self.findChild(QToolBar, "MainToolBar")
        if not self.main_toolbar:
            self.main_toolbar = self.addToolBar(tr("Main Toolbar"))
            self.main_toolbar.setObjectName("MainToolBar")
        
        # UI OPTIMIZATION: Icon only, fixed size, and move to left
        self.main_toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.main_toolbar.setIconSize(QSize(20, 20))
        self.addToolBar(Qt.ToolBarArea.LeftToolBarArea, self.main_toolbar)
        self.main_toolbar.setMovable(False)
        self.main_toolbar.setFloatable(False)
            
        # Add Undo/Redo/Export to Toolbar
        # Check if already added to avoid duplicates
        actions = self.main_toolbar.actions()
        if self.action_undo not in actions:
            self.main_toolbar.addAction(self.action_undo)
            self.main_toolbar.addAction(self.action_redo)
            self.main_toolbar.addSeparator()
            self.main_toolbar.addAction(self.action_export_images)

        self.action_clear.setText(tr("Clear ROIs"))
        self.action_clear.setStatusTip(tr("Remove all ROIs from the current scene"))
        self.action_clear.setToolTip(tr("Remove all ROIs from the current scene"))
        
        self.action_wand.setText(tr("Magic Wand"))
        self.action_wand.setStatusTip(tr("Select a region based on color/intensity similarity"))
        self.action_wand.setToolTip(tr("Select a region based on color/intensity similarity"))
        
        self.action_polygon.setText(tr("Polygon Lasso"))
        self.action_polygon.setStatusTip(tr("Draw a multi-sided region of interest"))
        self.action_polygon.setToolTip(tr("Draw a multi-sided region of interest"))
        
        self.action_rect.setText(tr("Rectangle"))
        self.action_rect.setStatusTip(tr("Draw a rectangular region of interest"))
        self.action_rect.setToolTip(tr("Draw a rectangular region of interest"))
        
        self.action_ellipse.setText(tr("Ellipse"))
        self.action_ellipse.setStatusTip(tr("Draw an elliptical region of interest"))
        self.action_ellipse.setToolTip(tr("Draw an elliptical region of interest"))
        
        self.action_count.setText(tr("Point Counter"))
        self.action_count.setStatusTip(tr("Interactively count fluorescent points across channels"))
        self.action_count.setToolTip(tr("Interactively count fluorescent points across channels"))
        
        self.action_line_scan.setText(tr("Line Scan"))
        self.action_line_scan.setStatusTip(tr("Draw a line to perform colocalization analysis"))
        self.action_line_scan.setToolTip(tr("Draw a line to perform colocalization analysis"))
        
        self.action_pan.setText(tr("Hand (Pan)"))
        self.action_pan.setStatusTip(tr("Pan the view and move existing ROIs"))
        self.action_pan.setToolTip(tr("Pan the view and move existing ROIs"))
        
        self.action_crop.setText(tr("Crop to Selection"))
        self.action_crop.setStatusTip(tr("Crop the current scene to the selected ROI"))
        self.action_crop.setToolTip(tr("Crop the current scene to the selected ROI"))
        
        self.action_measure.setText(tr("Measure"))
        self.action_measure.setStatusTip(tr("Run intensity measurements on all ROIs and calculate overlaps"))
        self.action_measure.setToolTip(tr("Run intensity measurements on all ROIs and calculate overlaps"))
        
        self.action_measure_settings.setText(tr("Measurement Settings..."))
        self.action_measure_settings.setStatusTip(tr("Select which metrics to calculate"))
        self.action_measure_settings.setToolTip(tr("Select which metrics to calculate"))
        
        self.action_export.setText(tr("Export Results (CSV)"))
        self.action_export.setStatusTip(tr("Save measurements to a CSV file"))
        self.action_export.setToolTip(tr("Save measurements to a CSV file"))
        
        self.action_export_images.setText(tr("Export Images"))
        self.action_export_images.setStatusTip(tr("Export current views as high-resolution images"))
        self.action_export_images.setToolTip(tr("Export current views as high-resolution images"))
        
        self.action_export_settings.setText(tr("Export Settings..."))
        self.action_export_settings.setStatusTip(tr("Configure export paths and formats"))
        self.action_export_settings.setToolTip(tr("Configure export paths and formats"))
        
        self.action_toggle_sidebar.setText(tr("Show/Hide Sidebar"))
        self.action_toggle_sidebar.setStatusTip(tr("Toggle the visibility of the Project Samples sidebar"))
        self.action_toggle_sidebar.setToolTip(tr("Toggle the visibility of the Project Samples sidebar"))
        
        self.action_toggle_controls.setText(tr("Show/Hide Controls"))
        self.action_toggle_controls.setStatusTip(tr("Toggle the visibility of the Controls panel"))
        self.action_toggle_controls.setToolTip(tr("Toggle the visibility of the Controls panel"))
        
        self.action_toggle_theme.setText(tr("Switch Theme"))
        self.action_toggle_theme.setStatusTip(tr("Toggle between Dark and Light UI themes"))
        self.action_toggle_theme.setToolTip(tr("Toggle between Dark and Light UI themes"))
        
        self.action_about.setText(tr("About FluoQuant Pro"))
        self.action_about.setStatusTip(tr("Show information about this application"))
        self.action_about.setToolTip(tr("Show information about this application"))
        
        self.action_shortcuts.setText(tr("Keyboard Shortcuts"))
        self.action_shortcuts.setStatusTip(tr("View available keyboard shortcuts"))
        self.action_shortcuts.setToolTip(tr("View available keyboard shortcuts"))
        
        self.action_manual.setText(tr("User Manual"))
        self.action_manual.setStatusTip(tr("Open the User Manual"))
        self.action_manual.setToolTip(tr("Open the User Manual"))
        
        # Update Dock Widget Titles
        self.sample_dock.setWindowTitle(tr("Project Samples"))
        self.right_dock.setWindowTitle(tr("Controls"))
        
        # Update Tab Titles
        if self.control_tabs.count() >= 6:
            self.control_tabs.setTabText(0, tr("Toolbox"))
            self.control_tabs.setTabText(1, tr("Adjustments"))
            self.control_tabs.setTabText(2, tr("Enhance"))
            self.control_tabs.setTabText(3, tr("Colocalization"))
            self.control_tabs.setTabText(4, tr("Annotation"))
            self.control_tabs.setTabText(5, tr("Measure Results"))
        
        # Update Status Bar
        self.lbl_status.setText(tr("Ready"))

    def update_tab_visibility(self):
        """Updates control panel tab visibility based on settings."""
        settings = QSettings("FluoQuantPro", "AppSettings")
        # Change 'overlay' to 'annotation' in default string to match new panel name
        visible_tabs_str = settings.value("interface/visible_tabs", "toolbox,adjustments,enhance,colocalization,annotation,results")
        visible_list = visible_tabs_str.split(",")
        
        # Remember current index to restore it if possible
        current_tab_name = None
        current_idx = self.control_tabs.currentIndex()
        if current_idx >= 0:
            # Find the key for the current widget
            current_widget = self.control_tabs.widget(current_idx)
            for key, widget, label in self.all_tabs_data:
                if widget == current_widget:
                    current_tab_name = key
                    break
        
        # Clear all tabs
        self.control_tabs.clear()
        
        # Add only visible ones
        for key, widget, label in self.all_tabs_data:
            if key in visible_list:
                self.control_tabs.add_tab(key, widget, label)
                
        # Restore index if the tab is still visible
        if current_tab_name:
            for i in range(self.control_tabs.count()):
                widget = self.control_tabs.widget(i)
                # Find which key this widget corresponds to
                for key, w, label in self.all_tabs_data:
                    if w == widget and key == current_tab_name:
                        self.control_tabs.setCurrentIndex(i)
                        break

    def on_annotation_tool_selected(self, mode):
        """Handles graphic annotation tool selection."""
        Logger.debug(f"[Main] on_annotation_tool_selected called with mode: {mode}")
        
        # 1. 检查是否正在进行 ROI 工具切换（状态锁）
        if getattr(self, '_is_switching_roi_tool', False) and mode == 'none':
            Logger.debug("[Main] Ignoring annotation reset because we are currently switching ROI tools.")
            return

        try:
            # Reset any pending annotation mode
            if mode != 'none':
                self.pending_annotation_mode = None
            
            if mode == 'none':
                # 2. 检查是否有任何 ROI 工具正处于选中状态
                is_any_roi_tool_active = False
                for act in self.tools_action_group.actions():
                    if act != self.action_pan and act.isChecked():
                        is_any_roi_tool_active = True
                        break
                
                # 如果当前有 ROI 工具，不要退回到 Pan
                if is_any_roi_tool_active:
                    Logger.debug(f"[Main] Ignoring annotation reset because an ROI tool is checked.")
                    return

                # --- 优化：不再武断地切回手型工具 ---
                # 即使没有 ROI 工具，我们也只是清理当前视图的工具状态，而不是强制选中 action_pan
                # 这样可以避免信号回环导致的“抢夺焦点”问题
                Logger.debug("[Main] Mode is none, clearing view tools (NOT forcing Pan)")
                self.set_view_tool(None)
                return

            # Annotation 模式仅保留箭头/文字，其它形状通过 ROI 工具
            tool_to_use = None
            from src.gui.tools import DrawToolFactory
            if mode in ['arrow', 'text']:
                # 直接进入注解上下文，由视图创建工具
                self.set_view_annotation_mode(mode)
                self.pending_annotation_mode = None
                tool_to_use = None
                
                # Uncheck main toolbar tools to reflect state
                if self.tools_action_group.checkedAction():
                    self.tools_action_group.setExclusive(False)
                    self.tools_action_group.checkedAction().setChecked(False)
                    self.tools_action_group.setExclusive(True)
            elif mode == 'batch_select':
                if hasattr(self, 'batch_tool'):
                    tool_to_use = self.batch_tool
            else:
                # 其它类型不在注解面板中创建
                self.set_view_annotation_mode('none')
                tool_to_use = None
                 
            if tool_to_use:
                Logger.debug(f"[Main] Activating batch selection tool")
                self.pending_annotation_mode = None
                self.set_view_tool(tool_to_use)
                # Uncheck main toolbar tools to reflect state
                if self.tools_action_group.checkedAction():
                    self.tools_action_group.setExclusive(False)
                    self.tools_action_group.checkedAction().setChecked(False)
                    self.tools_action_group.setExclusive(True)
                self.lbl_status.setText(tr("Annotation Mode: {0}").format(mode.capitalize()))
            else:
                # Arrow/Text 已在上面设置；其它类型维持 ROI 面板
                self.lbl_status.setText(tr("Annotation Mode: {0}").format(mode.capitalize()))
        except Exception as e:
            Logger.error(f"[Main] Exception in on_annotation_tool_selected: {e}", exc_info=True)
    
    def _on_tool_committed(self, msg: str):
        self.lbl_status.setText(msg)
        self.annotation_panel.update_annotation_list()
        
    def on_overlay_settings_changed(self):
        """Handles changes to scale bar or global annotation settings."""
        self.update_all_scale_bars(self.session.scale_bar_settings)
        
        # Sync properties to TextTool
        if hasattr(self, 'text_tool') and hasattr(self, 'annotation_panel'):
            props = self.annotation_panel.get_current_properties()
            self.text_tool.color = props.get('color', '#FFFF00')
            self.text_tool.font_size = props.get('arrow_head_size', 12)


    def on_roi_added(self, roi):
        """Handle new ROI addition."""
        Logger.debug(f"[Main.on_roi_added] ROI added: {roi.label}")
        
    def on_roi_removed(self, roi_id):
        """Handle ROI removal."""
        Logger.debug(f"[Main.on_roi_removed] ROI removed: {roi_id}")

    def on_roi_updated(self, roi_or_id):
        """Handle ROI updates."""
        roi_id = roi_or_id if isinstance(roi_or_id, str) else roi_or_id.id
        Logger.debug(f"[Main.on_roi_updated] ROI updated: {roi_id}")
        
        # Propagate to ALL view containers to keep them in sync
        for container in self.view_containers:
            if hasattr(container, '_on_roi_updated'):
                container._on_roi_updated(roi_or_id)

    def on_roi_selection_changed(self):
        """
        Handles ROI selection changes.
        Previous interactive overlap analysis has been moved to 'Measure' button action.
        This method now primarily handles UI updates related to selection.
        """
        # print("DEBUG: [Main] on_roi_selection_changed triggered")
        
        # We can keep the selection sync if needed, but overlap calculation is removed.
        # Just ensure the table selection syncs if implemented.
        pass


    def _run_overlap_analysis(self, sample_name: str, roi1, roi2):
        """Helper to run analysis between two ROIs and add result."""
        Logger.debug(f"[Main] Overlap analyze: sample={sample_name} roi1={roi1.id} roi2={roi2.id}")
        # Prepare data for analyzer
        roi1_data = {
            'path': roi1.path, 
            'label': roi1.label, 
            'area': roi1.stats.get('Area', 0)
        }
        roi2_data = {
            'path': roi2.path, 
            'label': roi2.label, 
            'area': roi2.stats.get('Area', 0)
        }
        
        # Perform analysis
        try:
            # Use session channels and pixel size
            channels = self.session.channels
            pixel_size = self.session.scale_bar_settings.pixel_size
            
            result = ROIOverlapAnalyzer.calculate_overlap(roi1_data, roi2_data, channels=channels, pixel_size=pixel_size)
            
            # Filter trivial overlaps (e.g. IoU < 0.01 or 0 overlap) to reduce noise in 1-vs-All mode
            if result['overlap_area'] <= 0:
                return
            
            label_1 = result.get('label_1', 'A')
            label_2 = result.get('label_2', 'B')
            
            display_data = {
                'Label': result['label'],
                'Area': result['union_area'],
                'Intersection_Area': result['overlap_area'],
                f'{label_1}_Only_Area': result['area1_only'],
                f'{label_2}_Only_Area': result['area2_only'],
                'Metrics_Mean': result['iou'],        # Mean col -> IoU
                'Metrics_IntDen': result['overlap_ratio'] # IntDen col -> Ratio
            }

            intersection_stats = result.get("intersection_stats") or {}
            for key, val in intersection_stats.items():
                if key in ["Area", "PixelCount"]:
                    continue
                if "_" in key:
                    ch_name, metric = key.rsplit("_", 1)
                    display_data[f"Intersection ({ch_name})_{metric}"] = val

            # Add "Only" stats for each ROI
            area1_only_stats = result.get("area1_only_stats") or {}
            for key, val in area1_only_stats.items():
                if key in ["Area", "PixelCount"] or "_" not in key:
                    continue
                ch_name, metric = key.rsplit("_", 1)
                display_data[f"{label_1}_Only ({ch_name})_{metric}"] = val

            area2_only_stats = result.get("area2_only_stats") or {}
            for key, val in area2_only_stats.items():
                if key in ["Area", "PixelCount"] or "_" not in key:
                    continue
                ch_name, metric = key.rsplit("_", 1)
                display_data[f"{label_2}_Only ({ch_name})_{metric}"] = val

            pair = sorted([str(roi1.id), str(roi2.id)])
            entry_id = f"overlap_{pair[0]}_{pair[1]}"
            self.result_widget.add_overlap_entry(sample_name, roi1.id, entry_id, display_data)
            self.result_widget.add_overlap_entry(sample_name, roi2.id, entry_id, display_data)
            
        except Exception as e:
            Logger.error(f"[Main] Overlap analysis failed: sample={sample_name} roi1={roi1.id} roi2={roi2.id} err={e}")

    def on_annotation_modified(self, update_data):
        """Deprecated."""
        pass

    def on_clear_annotations(self):
        """Clears all ROIs (Unified Model)."""
        from PySide6.QtWidgets import QMessageBox
        
        rois = self.session.roi_manager.get_all_rois()
        if not rois:
            return

        ret = QMessageBox.question(
            self, tr("Clear ROIs"),
            tr("Are you sure you want to clear all ROIs/Annotations?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if ret == QMessageBox.StandardButton.Yes:
            self.session.roi_manager.clear()

    def create_actions(self):
        """Initialize all actions with icons, shortcuts, and status tips."""
        # File Actions
        self.action_new_project = QAction(tr("New Project..."), self)
        self.action_new_project.setShortcut("Ctrl+N")
        self.action_new_project.setStatusTip(tr("Create a new project in a selected folder"))
        self.action_new_project.setIcon(get_icon("new", "document-new"))
        self.action_new_project.triggered.connect(self.new_project)

        self.action_open_project = QAction(tr("Open Project..."), self)
        self.action_open_project.setShortcut("Ctrl+O")
        self.action_open_project.setStatusTip(tr("Open an existing project folder"))
        self.action_open_project.setIcon(get_icon("open", "document-open"))
        self.action_open_project.triggered.connect(self.open_project)

        # Recent Projects Menu
        self.recent_projects_menu = QMenu(tr("Recent Projects"), self)
        self.recent_projects_menu.setIcon(get_icon("recent", "document-open-recent"))
        self.update_recent_projects_menu()

        self.action_save_project = QAction(tr("Save Project"), self)
        self.action_save_project.setShortcut("Ctrl+S")
        self.action_save_project.setStatusTip(tr("Save all changes to the project"))
        self.action_save_project.setIcon(get_icon("save", "document-save"))
        self.action_save_project.triggered.connect(self.save_project)

        self.action_save_project_as = QAction(tr("Save Project As..."), self)
        self.action_save_project_as.setShortcut("Ctrl+Shift+S")
        self.action_save_project_as.setStatusTip(tr("Save the current project to a new folder"))
        self.action_save_project_as.setIcon(get_icon("save_as", "document-save-as"))
        self.action_save_project_as.triggered.connect(self.save_project_as)

        self.action_settings = QAction(tr("Application Settings..."), self)
        self.action_settings.setShortcut("Ctrl+,")
        self.action_settings.setStatusTip(tr("Configure global application preferences"))
        self.action_settings.setIcon(get_icon("settings", "preferences-system"))
        self.action_settings.triggered.connect(self.open_settings)

        self.action_auto_save_settings = QAction(tr("Auto Save Settings..."), self)
        self.action_auto_save_settings.setStatusTip(tr("Configure project auto-save behavior"))
        self.action_auto_save_settings.triggered.connect(self.open_auto_save_settings)

        self.action_import = QAction(tr("Import Images to Pool..."), self)
        self.action_import.setStatusTip(tr("Select individual images to add to the image pool"))
        self.action_import.setIcon(get_icon("import", "document-import"))
        self.action_import.triggered.connect(lambda: self.sample_list.load_images_to_pool())

        self.action_import_folder = QAction(tr("Import Folder (Auto-Group)..."), self)
        self.action_import_folder.setStatusTip(tr("Import all images in a folder and group by metadata/name"))
        self.action_import_folder.setIcon(get_icon("folder", "folder-open"))
        self.action_import_folder.triggered.connect(self.import_folder_auto)

        self.action_import_merge = QAction(tr("Import Merge (RGB Split)..."), self)
        self.action_import_merge.setStatusTip(tr("Import an RGB merge image and split into fluorophore channels"))
        self.action_import_merge.setIcon(get_icon("import", "document-import"))
        self.action_import_merge.triggered.connect(self.on_import_merge)
        
        self.action_exit = QAction(tr("Exit"), self)
        self.action_exit.setShortcut("Alt+F4")
        self.action_exit.setStatusTip(tr("Close the application"))
        self.action_exit.setIcon(get_icon("exit", "application-exit"))
        self.action_exit.triggered.connect(self.close)

        # Edit/ROI Actions
        self.action_undo = QAction(tr("Undo"), self)
        self.action_undo.setShortcut("Ctrl+Z")
        self.action_undo.setStatusTip(tr("Undo the last action"))
        self.action_undo.setIcon(get_icon("undo", "edit-undo"))
        self.action_undo.triggered.connect(lambda: self.session.undo())
        self.session.undo_stack.canUndoChanged.connect(self.action_undo.setEnabled)
        self.action_undo.setEnabled(self.session.undo_stack.canUndo())
        
        self.action_redo = QAction(tr("Redo"), self)
        self.action_redo.setShortcuts(["Ctrl+Y", "Ctrl+Shift+Z"])
        self.action_redo.setStatusTip(tr("Redo the last undone action"))
        self.action_redo.setIcon(get_icon("redo", "edit-redo"))
        self.action_redo.triggered.connect(lambda: self.session.redo())
        self.session.undo_stack.canRedoChanged.connect(self.action_redo.setEnabled)
        self.action_redo.setEnabled(self.session.undo_stack.canRedo())

        self.action_clear = QAction(tr("Clear ROIs"), self)
        self.action_clear.setShortcut("Ctrl+Del")
        self.action_clear.setStatusTip(tr("Remove all ROIs from the current scene"))
        self.action_clear.setIcon(get_icon("clear", "edit-clear"))
        self.action_clear.triggered.connect(lambda: self.session.roi_manager.clear(undoable=True))

        self.action_select_all = QAction(tr("Select All"), self)
        self.action_select_all.setShortcut("Ctrl+A")
        self.action_select_all.setStatusTip(tr("Select all ROIs and Annotations"))
        self.action_select_all.setIcon(get_icon("select_all", "edit-select-all"))
        self.action_select_all.triggered.connect(self.select_all_rois)

        # Tools (Checkable)
        self.action_wand = QAction(tr("Magic Wand"), self)
        self.action_wand.setObjectName("action_wand")
        self.action_wand.setCheckable(True)
        self.action_wand.setShortcut("W")
        self.action_wand.setStatusTip(tr("Select a region based on color/intensity similarity"))
        self.action_wand.setIcon(get_icon("wand", "edit-select-magic-wand"))
        self.action_wand.toggled.connect(lambda c: self.on_tool_toggled(self.action_wand, c))
        
        self.action_polygon = QAction(tr("Polygon Lasso"), self)
        self.action_polygon.setObjectName("action_polygon")
        self.action_polygon.setCheckable(True)
        self.action_polygon.setShortcut("P")
        self.action_polygon.setStatusTip(tr("Draw a multi-sided region of interest"))
        self.action_polygon.setIcon(get_icon("polygon", "draw-polygon"))
        self.action_polygon.toggled.connect(lambda c: self.on_tool_toggled(self.action_polygon, c))
        
        self.action_rect = QAction(tr("Rectangle"), self)
        self.action_rect.setObjectName("action_rect")
        self.action_rect.setCheckable(True)
        self.action_rect.setShortcut("R")
        self.action_rect.setStatusTip(tr("Draw a rectangular region of interest"))
        self.action_rect.setIcon(get_icon("rect", "draw-rectangle"))
        self.action_rect.toggled.connect(lambda c: self.on_tool_toggled(self.action_rect, c))

        self.action_ellipse = QAction(tr("Ellipse"), self)
        self.action_ellipse.setObjectName("action_ellipse")
        self.action_ellipse.setCheckable(True)
        self.action_ellipse.setShortcut("E")
        self.action_ellipse.setStatusTip(tr("Draw an elliptical region of interest"))
        self.action_ellipse.setIcon(get_icon("ellipse", "draw-ellipse"))
        self.action_ellipse.toggled.connect(lambda c: self.on_tool_toggled(self.action_ellipse, c))

        self.action_count = QAction(tr("Point Counter"), self)
        self.action_count.setObjectName("action_count")
        self.action_count.setCheckable(True)
        self.action_count.setShortcut("C")
        self.action_count.setStatusTip(tr("Interactively count fluorescent points across channels"))
        self.action_count.setIcon(get_icon("count", "crosshair"))
        self.action_count.toggled.connect(lambda c: self.on_tool_toggled(self.action_count, c))

        self.action_line_scan = QAction(tr("Line Scan"), self)
        self.action_line_scan.setObjectName("action_line_scan")
        self.action_line_scan.setCheckable(True)
        self.action_line_scan.setShortcut("L")
        self.action_line_scan.setStatusTip(tr("Draw a line to perform colocalization analysis"))
        self.action_line_scan.setIcon(get_icon("line", "draw-line"))
        self.action_line_scan.toggled.connect(lambda c: self.on_tool_toggled(self.action_line_scan, c))

        # Pan / Hand Tool
        self.action_pan = QAction(tr("Hand (Pan)"), self)
        self.action_pan.setObjectName("action_pan")
        self.action_pan.setCheckable(True)
        self.action_pan.setShortcut("H")
        self.action_pan.setStatusTip(tr("Pan the view and move existing ROIs"))
        self.action_pan.setIcon(get_icon("hand", "cursor-hand"))
        self.action_pan.toggled.connect(lambda c: self.on_tool_toggled(self.action_pan, c))

        # Batch Selection Tool
        self.action_batch_select = QAction(tr("Batch Select"), self)
        self.action_batch_select.setObjectName("action_batch_select")
        self.action_batch_select.setCheckable(True)
        self.action_batch_select.setShortcut("B")
        self.action_batch_select.setStatusTip(tr("Drag to select multiple ROIs/Annotations"))
        self.action_batch_select.setIcon(get_icon("select", "edit-select-all"))
        self.action_batch_select.toggled.connect(lambda c: self.on_tool_toggled(self.action_batch_select, c))

        # Crop
        self.action_crop = QAction(tr("Crop to Selection"), self)
        self.action_crop.setShortcut("Ctrl+X")
        self.action_crop.setStatusTip(tr("Crop the current scene to the selected ROI"))
        self.action_crop.setIcon(get_icon("crop", "transform-crop-symbolic"))
        self.action_crop.triggered.connect(self.crop_to_selection)

        # Tool Group
        from PySide6.QtGui import QActionGroup
        self.tools_action_group = QActionGroup(self)
        self.tools_action_group.addAction(self.action_wand)
        self.tools_action_group.addAction(self.action_polygon)
        self.tools_action_group.addAction(self.action_rect)
        self.tools_action_group.addAction(self.action_ellipse)
        self.tools_action_group.addAction(self.action_count)
        self.tools_action_group.addAction(self.action_line_scan)
        self.tools_action_group.addAction(self.action_pan)
        self.tools_action_group.addAction(self.action_batch_select)
        self.tools_action_group.setExclusive(True) # 启用互斥，防止多个工具同时选中

        # Analysis Actions
        self.action_measure = QAction(tr("Measure"), self)
        self.action_measure.setShortcut("Ctrl+M")
        self.action_measure.setStatusTip(tr("Run intensity measurements on all ROIs"))
        self.action_measure.setIcon(get_icon("measure", "view-statistics"))
        self.action_measure.triggered.connect(self.measure_all_rois)
        
        self.action_measure_settings = QAction(tr("Measurement Settings..."), self)
        self.action_measure_settings.setStatusTip(tr("Select which metrics to calculate"))
        self.action_measure_settings.setIcon(get_icon("stats", "view-list-details"))
        self.action_measure_settings.triggered.connect(self.open_measure_settings)

        self.action_set_scale = QAction(tr("Set Scale..."), self)
        self.action_set_scale.setStatusTip(tr("Calibrate pixel size using a known distance"))
        self.action_set_scale.setIcon(get_icon("scale", "measure-length")) 
        self.action_set_scale.triggered.connect(self.open_set_scale_dialog)

        self.action_export = QAction(tr("Export Results (CSV)"), self)
        self.action_export.setShortcut("Ctrl+E")
        self.action_export.setStatusTip(tr("Save measurements to a CSV file"))
        self.action_export.setIcon(get_icon("export", "document-export"))
        self.action_export.triggered.connect(self.export_results)
        
        self.action_export_images = QAction(tr("Export Images"), self)
        self.action_export_images.setStatusTip(tr("Export current views as high-resolution images"))
        self.action_export_images.setIcon(get_icon("export_img", "image-x-generic"))
        self.action_export_images.triggered.connect(self.export_images)

        self.action_export_overlap = QAction(tr("Export Overlap Report..."), self)
        self.action_export_overlap.setStatusTip(tr("Export ROI overlap matrix and analysis report"))
        self.action_export_overlap.setIcon(get_icon("export", "document-export"))
        self.action_export_overlap.triggered.connect(self.export_overlap_report)

        self.action_export_settings = QAction(tr("Export Settings..."), self)
        self.action_export_settings.setStatusTip(tr("Configure export paths and formats"))
        self.action_export_settings.setIcon(get_icon("export_settings", "preferences-system"))
        self.action_export_settings.triggered.connect(self.open_export_settings)

        self.action_refresh = QAction(tr("Refresh Display"), self)
        self.action_refresh.setShortcut("F5")
        self.action_refresh.setStatusTip(tr("Force a re-render of all views"))
        self.action_refresh.setIcon(get_icon("refresh", "view-refresh"))
        self.action_refresh.triggered.connect(lambda: self.refresh_display())

        # View Actions
        self.action_toggle_sidebar = self.sample_dock.toggleViewAction()
        self.action_toggle_sidebar.setShortcut("Ctrl+B")
        self.action_toggle_sidebar.setStatusTip(tr("Toggle the visibility of the Project Samples sidebar"))
        
        self.action_toggle_controls = self.right_dock.toggleViewAction()
        self.action_toggle_controls.setShortcut("F12")
        self.action_toggle_controls.setStatusTip(tr("Toggle the visibility of the Controls panel"))

        self.action_toggle_theme = QAction(tr("Switch Theme"), self)
        self.action_toggle_theme.setShortcut("Ctrl+T")
        self.action_toggle_theme.setStatusTip(tr("Toggle between Dark and Light UI themes"))
        self.action_toggle_theme.setIcon(get_icon("theme", "preferences-desktop-theme"))
        self.action_toggle_theme.triggered.connect(self.toggle_theme)

        self.action_fit_width = QAction(tr("Fit Width"), self)
        self.action_fit_width.setStatusTip(tr("Zoom to fit image width to viewport"))
        self.action_fit_width.setIcon(get_icon("fit_width", "zoom-fit-width"))
        self.action_fit_width.triggered.connect(self.on_fit_to_width)

        self.action_fit_height = QAction(tr("Fit Height"), self)
        self.action_fit_height.setStatusTip(tr("Zoom to fit image height to viewport"))
        self.action_fit_height.setIcon(get_icon("fit_height", "zoom-fit-height"))
        self.action_fit_height.triggered.connect(self.on_fit_to_height)

        # View Mode Actions
        self.view_mode_group = QActionGroup(self)
        self.view_mode_group.setExclusive(True)

        self.action_grid_view = QAction(tr("Grid View"), self)
        self.action_grid_view.setCheckable(True)
        self.action_grid_view.setChecked(True)
        self.action_grid_view.setIcon(get_icon("grid", "view-grid"))
        self.action_grid_view.triggered.connect(lambda: self.switch_view_mode("grid"))
        self.view_mode_group.addAction(self.action_grid_view)

        self.action_filmstrip_view = QAction(tr("Filmstrip View"), self)
        self.action_filmstrip_view.setCheckable(True)
        self.action_filmstrip_view.setIcon(get_icon("filmstrip", "view-filmstrip"))
        self.action_filmstrip_view.triggered.connect(lambda: self.switch_view_mode("filmstrip"))
        self.view_mode_group.addAction(self.action_filmstrip_view)

        # Help Actions
        self.action_about = QAction(tr("About FluoQuant Pro"), self)
        self.action_about.setStatusTip(tr("Show information about this application"))
        self.action_about.setIcon(get_icon("info", "help-about"))
        self.action_about.triggered.connect(self.show_about)

        self.action_shortcuts = QAction(tr("Keyboard Shortcuts"), self)
        self.action_shortcuts.setShortcut("F1")
        self.action_shortcuts.setStatusTip(tr("View available keyboard shortcuts"))
        self.action_shortcuts.setIcon(get_icon("shortcuts", "help-contents"))
        self.action_shortcuts.triggered.connect(self.show_shortcuts)
        
        self.action_manual = QAction(tr("User Manual"), self)
        self.action_manual.setShortcut("F1")
        self.action_manual.setStatusTip(tr("Open the User Manual"))
        self.action_manual.setIcon(get_icon("help", "help-browser"))
        self.action_manual.triggered.connect(self.open_manual)
        
        # Shortcuts changed to Ctrl+F1 to avoid conflict with Manual (standard F1)
        self.action_shortcuts.setShortcut("Ctrl+F1")

    def get_active_view_container(self):
        """Returns the currently visible view container (MultiView or Filmstrip)."""
        return self.view_stack.currentWidget()

    def get_active_canvas_view(self):
        """Returns the currently active CanvasView for interaction."""
        container = self.get_active_view_container()
        if container and hasattr(container, 'get_active_view'):
            return container.get_active_view()
        return None

    def switch_view_mode(self, mode):
        """Switches between Grid View and Filmstrip View."""
        if mode == "grid":
            self.view_stack.setCurrentWidget(self.multi_view)
            self.action_grid_view.setChecked(True)
        else:
            self.view_stack.setCurrentWidget(self.filmstrip_view)
            self.action_filmstrip_view.setChecked(True)
            # Ensure filmstrip is initialized/rendered
            if self.session.channels:
                self.initialize_all_views()
                self.update_all_view_containers()

    def on_filmstrip_channel_selected(self, index):
        """DEPRECATED: Use on_channel_selected instead."""
        self.on_channel_selected(index)

    def on_tab_changed(self, index):
        """Handle tab switching events."""
        self._is_switching_tab = True
        try:
            tab_text = self.control_tabs.tabText(index)
            
            # Trigger lazy loading for Enhance Panel
            current_widget = self.control_tabs.widget(index)
            if current_widget == self.enhance_panel:
                self.enhance_panel.on_panel_shown()
                
            # If switching AWAY from Toolbox, maybe we want to default to Hand/Pan tool?
            # --- USER REQUEST: No longer automatically switch to Pan tool when switching tabs ---
            # This prevents "jumping back" and allows using tools while adjusting settings in other tabs.
            """
            if tab_text != tr("Toolbox"):
                ...
            """
            pass
            
            # If switching TO Overlay (Annotation) tab, ensure we don't accidentally clear tool
            # unless it was an ROI tool.
            if tab_text == tr("Annotation"):
                 # Maybe we want to keep the current annotation tool active?
                 pass
        finally:
            self._is_switching_tab = False
                        
    def setup_menu(self):
        menu_bar = self.menuBar()
        
        # File Menu
        self.menu_file = menu_bar.addMenu(tr("File"))
        self.menu_file.addAction(self.action_new_project)
        self.menu_file.addAction(self.action_open_project)
        self.menu_file.addMenu(self.recent_projects_menu) # Add Recent Projects submenu
        self.menu_file.addSeparator()
        self.menu_file.addAction(self.action_save_project)
        self.menu_file.addAction(self.action_save_project_as)
        self.menu_file.addSeparator()
        
        self.menu_import = self.menu_file.addMenu(tr("Import"))
        self.menu_import.setIcon(get_icon("import", "document-import"))
        self.menu_import.addAction(self.action_import_folder)
        self.menu_import.addAction(self.action_import)
        self.menu_import.addAction(self.action_import_merge)
        
        self.menu_file.addSeparator()
        self.menu_file.addAction(self.action_settings)
        self.menu_file.addAction(self.action_auto_save_settings)
        self.menu_file.addSeparator()
        self.menu_file.addAction(self.action_exit)
        
        # Edit Menu
        self.menu_edit = menu_bar.addMenu(tr("Edit"))
        self.menu_edit.addAction(self.action_undo)
        self.menu_edit.addAction(self.action_redo)
        self.menu_edit.addSeparator()
        self.menu_edit.addAction(self.action_clear)
        self.menu_edit.addSeparator()
        self.menu_edit.addAction(self.action_crop)
        
        # View Menu
        self.menu_view = menu_bar.addMenu(tr("View"))
        self.menu_view.addAction(self.action_toggle_sidebar)
        self.menu_view.addAction(self.action_toggle_controls)
        self.menu_view.addSeparator()
        self.menu_view.addAction(self.action_fit_width)
        self.menu_view.addAction(self.action_fit_height)
        self.menu_view.addSeparator()
        self.menu_view.addAction(self.action_toggle_theme)
        
        self.menu_view.addSeparator()
        self.menu_view.addAction(self.action_refresh)
        self.menu_view.addSeparator()
        self.menu_view.addAction(self.action_grid_view)
        self.menu_view.addAction(self.action_filmstrip_view)
        
        # Analysis Menu
        self.menu_analysis = menu_bar.addMenu(tr("Analysis"))
        self.menu_analysis.addAction(self.action_measure)
        self.menu_analysis.addAction(self.action_measure_settings)
        self.menu_analysis.addAction(self.action_set_scale)
        self.menu_analysis.addSeparator()
        
        self.menu_export = self.menu_analysis.addMenu(tr("Export"))
        self.menu_export.setIcon(get_icon("export", "document-export"))
        self.menu_export.addAction(self.action_export)
        self.menu_export.addAction(self.action_export_images)
        self.menu_export.addSeparator()
        self.menu_export.addAction(self.action_export_settings)
        
        # Help Menu
        self.menu_help = menu_bar.addMenu(tr("Help"))
        self.menu_help.addAction(self.action_manual)
        self.menu_help.addAction(self.action_shortcuts)
        self.menu_help.addSeparator()
        self.menu_help.addAction(self.action_about)

        # --- USER REQUEST: Add Undo/Redo Buttons near Menu Bar ---
        # We use a corner widget or a small toolbar at the top right of the menu bar area
        
        # Create a container widget for the menu-aligned buttons
        self.menu_actions_widget = QWidget()
        menu_actions_layout = QHBoxLayout(self.menu_actions_widget)
        menu_actions_layout.setContentsMargins(10, 0, 10, 0)
        menu_actions_layout.setSpacing(4)

        # Undo/Redo Group
        btn_undo = QToolButton()
        btn_undo.setObjectName("undo_btn")
        btn_undo.setDefaultAction(self.action_undo)
        btn_undo.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        btn_undo.setIconSize(QSize(20, 20))
        btn_undo.setFixedSize(28, 28)
        menu_actions_layout.addWidget(btn_undo)

        btn_redo = QToolButton()
        btn_redo.setObjectName("redo_btn")
        btn_redo.setDefaultAction(self.action_redo)
        btn_redo.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        btn_redo.setIconSize(QSize(20, 20))
        btn_redo.setFixedSize(28, 28)
        menu_actions_layout.addWidget(btn_redo)
        
        # Fit Width (Refresh) Button
        self.btn_fit = QToolButton()
        self.btn_fit.setObjectName("fit_btn")
        # Connect to a custom lambda to both refresh display and fit width
        self.btn_fit.clicked.connect(lambda: (self.refresh_display(), self.on_fit_to_width()))
        self.btn_fit.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.btn_fit.setIconSize(QSize(20, 20))
        self.btn_fit.setFixedSize(28, 28)
        self.btn_fit.setToolTip(tr("Refresh Display and Fit Width"))
        # Change icon to a refresh/reload style if available, otherwise use fit_width
        self.btn_fit.setIcon(get_icon("refresh", "view-refresh")) 
        menu_actions_layout.addWidget(self.btn_fit)
        
        # Export Button (Requested by User)
        btn_export = QToolButton()
        btn_export.setObjectName("export_btn")
        btn_export.setDefaultAction(self.action_export_images)
        btn_export.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        btn_export.setIconSize(QSize(20, 20))
        btn_export.setFixedSize(28, 28)
        menu_actions_layout.addWidget(btn_export)
        
        # Add a small vertical separator
        sep1 = QFrame()
        sep1.setObjectName("menu_sep")
        sep1.setFrameShape(QFrame.VLine)
        sep1.setFrameShadow(QFrame.Plain) # Use plain for cleaner look
        sep1.setFixedWidth(1)
        menu_actions_layout.addWidget(sep1)
        
        # Save Button
        btn_save = QToolButton()
        btn_save.setObjectName("save_btn")
        btn_save.setDefaultAction(self.action_save_project)
        btn_save.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        btn_save.setIconSize(QSize(20, 20))
        btn_save.setFixedSize(28, 28)
        menu_actions_layout.addWidget(btn_save)

        # Settings Button
        btn_settings = QToolButton()
        btn_settings.setObjectName("settings_btn")
        btn_settings.setDefaultAction(self.action_settings)
        btn_settings.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        btn_settings.setIconSize(QSize(20, 20))
        btn_settings.setFixedSize(28, 28)
        menu_actions_layout.addWidget(btn_settings)

        # View Mode Toggle Group
        menu_actions_layout.addSpacing(10)
        
        btn_grid = QToolButton()
        btn_grid.setDefaultAction(self.action_grid_view)
        btn_grid.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        btn_grid.setIconSize(QSize(20, 20))
        btn_grid.setFixedSize(28, 28)
        menu_actions_layout.addWidget(btn_grid)
        
        btn_filmstrip = QToolButton()
        btn_filmstrip.setDefaultAction(self.action_filmstrip_view)
        btn_filmstrip.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        btn_filmstrip.setIconSize(QSize(20, 20))
        btn_filmstrip.setFixedSize(28, 28)
        menu_actions_layout.addWidget(btn_filmstrip)

        # Add to MenuBar as a Corner Widget (Right side)
        menu_bar.setCornerWidget(self.menu_actions_widget, Qt.Corner.TopRightCorner)


    def setup_auto_save(self):
        """Configures the auto-save timer based on settings."""
        enabled = self.settings.value("auto_save_enabled", True, type=bool)
        interval = self.settings.value("auto_save_interval", 3, type=int)
        
        if enabled and interval > 0:
            ms = interval * 60 * 1000
            self.auto_save_timer.start(ms)
            print(f"Auto-save enabled: every {interval} minutes.")
        else:
            self.auto_save_timer.stop()
            print("Auto-save disabled.")

    def init_opencl(self):
        """Initializes OpenCL acceleration based on saved settings."""
        # Note: We use "Settings" group for display settings to match DisplaySettingsWidget
        display_settings = QSettings("FluoQuantPro", "Settings")
        enabled = display_settings.value("display/opencl_enabled", True, type=bool)
        
        if cv2.ocl.haveOpenCL():
            cv2.ocl.setUseOpenCL(enabled)
            status = "ENABLED" if enabled else "DISABLED"
            print(f"[Main] OpenCL Hardware Acceleration: {status}")
            
            if enabled:
                dev = cv2.ocl.Device.getDefault()
                print(f"[Main] Using GPU: {dev.name()}")
        else:
            print("[Main] OpenCL Hardware Acceleration: NOT AVAILABLE")

    def open_measure_settings(self):
        """Opens the measurement metrics selection dialog."""
        dlg = MeasurementSettingsDialog(self, self.measurement_settings)
        if dlg.exec():
            self.measurement_settings = dlg.get_settings()
            # Update the results widget if it exists
            self.result_widget.update_settings(self.measurement_settings)

    def open_set_scale_dialog(self):
        """Opens the Set Scale dialog for pixel calibration."""
        # Get current pixel size
        current_pixel_size = self.session.scale_bar_settings.pixel_size
        
        # Get selected ROI to determine if it's a line for calibration
        selected_line_length = None
        selected_ids = self.session.roi_manager.get_selected_ids()
        if len(selected_ids) == 1:
            roi = self.session.roi_manager._rois.get(selected_ids[0])
            if roi and (roi.roi_type == "line_scan" or roi.roi_type == "line"):
                # Calculate length in pixels
                if roi.line_points:
                    p1, p2 = roi.line_points
                    dx = p2.x() - p1.x()
                    dy = p2.y() - p1.y()
                    selected_line_length = (dx*dx + dy*dy)**0.5
                elif roi.path:
                     # Estimate from path
                     selected_line_length = roi.path.length()
        
        dlg = CalibrationDialog(current_pixel_size, selected_line_length, self)
        if dlg.exec():
            new_pixel_size = dlg.get_result()
            if new_pixel_size is not None:
                self.session.scale_bar_settings.pixel_size = new_pixel_size
                self.lbl_status.setText(tr("Scale set to {0:.4f} um/px").format(new_pixel_size))
                # Refresh views (scale bar)
                self.update_all_scale_bars(self.session.scale_bar_settings)

    def open_auto_save_settings(self):
        """Opens the Auto Save configuration dialog."""
        dlg = AutoSaveSettingsDialog(self)
        if dlg.exec():
            self.setup_auto_save()

    def apply_stylesheet(self):
        """Sets the application stylesheet based on the current theme."""
        ThemeManager.instance().apply_theme(self)

    def on_theme_changed(self, new_theme):
        """Callback when theme is changed via settings or toggle."""
        # Refresh all icons to match new theme colors
        self.refresh_icons()
        
        # 额外刷新各个面板的图标
        if hasattr(self, 'roi_toolbox') and self.roi_toolbox:
            self.roi_toolbox.refresh_icons()
        if hasattr(self, 'annotation_panel') and self.annotation_panel:
            self.annotation_panel.refresh_icons()
        if hasattr(self, 'adjustment_panel') and self.adjustment_panel:
            self.adjustment_panel.refresh_icons()
        if hasattr(self, 'enhance_panel') and self.enhance_panel:
            self.enhance_panel.refresh_icons()
        
        # Update status bar
        theme_display_names = ThemeManager.instance().THEMES
        self.lbl_status.setText(tr("Theme switched to {0}").format(theme_display_names.get(new_theme, new_theme)))

    def refresh_icons(self):
        """Re-sets icons for all major buttons to match the current theme."""
        # Update Main Toolbar/Actions
        self.action_undo.setIcon(get_icon("undo"))
        self.action_redo.setIcon(get_icon("redo"))
        self.action_fit_width.setIcon(get_icon("fit-width"))
        self.action_export_images.setIcon(get_icon("export"))
        self.action_save_project.setIcon(get_icon("save"))
        self.action_toggle_theme.setIcon(get_icon("theme"))
        self.action_settings.setIcon(get_icon("settings"))
        
        if hasattr(self, 'btn_fit'):
            self.btn_fit.setIcon(get_icon("refresh", "view-refresh"))
        
        # Update other icons if necessary...
        # Note: retranslate_ui also sets some text, but refresh_icons focuses on colors.
        
    def showEvent(self, event):
        super().showEvent(event)
        # Ensure titlebar style is applied after window is shown
        theme = ThemeManager.instance()
        if theme._last_titlebar_style:
            header_bg, border_color, header_text = theme._last_titlebar_style
            QTimer.singleShot(0, lambda: theme.apply_windows_titlebar_style(self, header_bg, border_color, header_text))

    def toggle_theme(self):
        """Toggles through all available UI themes."""
        ThemeManager.instance().toggle_theme()



    def check_unsaved_changes(self) -> bool:
        """Checks for unsaved changes and prompts user. Returns True if safe to proceed (Saved or Discarded)."""
        if self.project_model.is_dirty:
            reply = QMessageBox.question(self, tr('Unsaved Changes'),
                                         tr("You have unsaved changes. Do you want to save them?"),
                                         QMessageBox.StandardButton.Yes | 
                                         QMessageBox.StandardButton.No | 
                                         QMessageBox.StandardButton.Cancel)

            if reply == QMessageBox.StandardButton.Yes:
                return self.save_project()
            elif reply == QMessageBox.StandardButton.No:
                return True
            elif reply == QMessageBox.StandardButton.Cancel:
                return False
        return True

    def show_recovery_dialog(self, duration):
        """
        Triggered when PerformanceMonitor detects a UI freeze > 500ms.
        Offers the user options to optimize performance.
        """
        # USER REQUEST: Check suppression flag
        if getattr(self.perf_monitor, 'suppress_warnings', False):
            Logger.debug(f"[Performance] Freeze of {duration:.2f}s detected but suppressed by user.")
            return

        msg = f"System recovered from a {duration:.2f}s freeze."
        Logger.warning(msg)
        
        if duration > 2.0:
             # Severe freeze
             msg_box = QMessageBox(self)
             msg_box.setIcon(QMessageBox.Icon.Warning)
             msg_box.setWindowTitle(tr("Performance Alert"))
             msg_box.setText(tr("The application stopped responding for {0:.1f} seconds.\n\n"
                                "Do you want to enable 'High Performance Mode' (reduces visual quality) "
                                "to prevent further lags?").format(duration))
             
             msg_box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
             msg_box.setDefaultButton(QMessageBox.StandardButton.Yes)
             
             # USER REQUEST: Add "No longer pop up" toggle switch
             container = QWidget()
             layout = QHBoxLayout(container)
             layout.setContentsMargins(10, 0, 10, 0)
             lbl = QLabel(tr("Don't show again this session"))
             cb = ToggleSwitch()
             layout.addWidget(lbl)
             layout.addStretch()
             layout.addWidget(cb)
             msg_box.layout().addWidget(container, msg_box.layout().rowCount(), 0, 1, msg_box.layout().columnCount())
             
             reply = msg_box.exec()
             
             if cb.isChecked():
                 self.perf_monitor.suppress_warnings = True
                 Logger.info("[Performance] User chose to suppress further warnings for this session.")
             
             if reply == QMessageBox.StandardButton.Yes:
                 self.perf_monitor.optimize_for_speed()
        else:
            # Minor freeze - Auto-optimize silently or just log
            # But user said "Pop up... when > 500ms"
            # Maybe a small toast is better than a blocking box for 500ms lag.
            self.lbl_status.setText(tr("Performance Warning: Lag detected ({0:.1f}s). Optimizing...").format(duration))
            # Auto-optimize if not already
            if self.perf_monitor.dynamic_quality:
                self.perf_monitor.optimize_for_speed()

    def on_performance_mode_changed(self, high_perf_mode):
        if high_perf_mode:
            self.lbl_status.setText(tr("High Performance Mode Enabled: Antialiasing Disabled."))
        else:
            self.lbl_status.setText(tr("High Quality Mode Restored."))
        
        # Optimization: Don't force a global refresh immediately if we just entered high-performance mode.
        # This prevents a "lag -> optimize -> refresh -> more lag" loop.
        # The next render (either from user action or auto-refresh) will use the new setting.
        if not high_perf_mode:
            self.refresh_display()

    def closeEvent(self, event):
        if not self.check_unsaved_changes():
            event.ignore()
        else:
            # --- Stop Performance Monitor (Ensure Threads Exit) ---
            from src.core.performance_monitor import PerformanceMonitor
            PerformanceMonitor.instance().stop()
            
            # --- Save UI State (Geometry, Docks, Splitters) ---
            settings = QSettings("FluoQuantPro", "Window")
            settings.setValue("geometry", self.saveGeometry())
            settings.setValue("windowState", self.saveState())
            
            # Save SampleList Splitter (if exists)
            if hasattr(self, 'sample_list') and hasattr(self.sample_list, 'splitter'):
                 settings.setValue("sampleListSplitter", self.sample_list.splitter.saveState())
            
            event.accept()

    def new_project(self):
        """Resets the project and opens the setup dialog."""
        if not self.check_unsaved_changes():
            return

        # 1. Ask for Project Folder
        folder = QFileDialog.getExistingDirectory(self, tr("Select New Project Folder"))
        if not folder:
            return
            
        # Check if folder is empty or allow overwrite?
        # For now, just warn if it contains project.json
        if os.path.exists(os.path.join(folder, "project.json")):
            res = QMessageBox.warning(self, tr("Existing Project"), 
                                      tr("This folder already contains a project. Overwrite?"),
                                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if res == QMessageBox.StandardButton.No:
                return

        dialog = ProjectSetupDialog(self)
        if dialog.exec():
            # Clear existing data
            self.project_model.clear()
            self.session.clear()
            
            # Set Root Path
            self.project_model.set_root_path(folder)
            
            self.sample_list.refresh_list()
            self.sample_list.refresh_pool_list()
            self.initialize_all_views()
            self.result_widget.clear()
            
            # Set new template
            template = dialog.get_template()
            print(f"DEBUG: [Main] new_project - dialog.get_template() returned: {template}")
            if not template:
                QMessageBox.warning(
                    self,
                    tr("Template"),
                    tr("No channels were selected in the template. New samples may have no channel slots.")
                )
            self.project_model._set_project_template_internal(template)
            print(f"DEBUG: [Main] new_project - model.project_channel_template is now: {self.project_model.project_channel_template}")
            if template and not self.project_model.project_channel_template:
                warnings = [str(w) for w in getattr(self.project_model, "last_template_warnings", []) if w]
                QMessageBox.warning(
                    self,
                    tr("Template Warning"),
                    tr("Channel template could not be applied and was normalized to empty.\n\nDetails:\n{0}").format("\n".join(warnings) if warnings else tr("Unknown reason"))
                )
            
            # Initial Save
            self.project_model.save_project()
            
            # Check for existing images in the new project folder (Enhancement)
            settings = QSettings("FluoQuantPro", "AppSettings")
            recursive = settings.value("import/recursive", False, type=bool)
            files = self.project_model.scan_folder(folder, recursive=recursive)
            if files:
                 reply = QMessageBox.question(self, tr("Import Images"), 
                                              tr("Found {0} images in the selected folder. Import them automatically?").format(len(files)),
                                              QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                 if reply == QMessageBox.StandardButton.Yes:
                     self.project_model.add_files(files)
                     self.project_model.save_project()
                     self.sample_list.refresh_list()
                     self.sample_list.refresh_pool_list()
            
            self.lbl_status.setText(tr("New Project Created in {0}").format(folder))

    def update_recent_projects_menu(self):
        """Updates the recent projects menu items from QSettings."""
        self.recent_projects_menu.clear()
        recent_files = self.settings.value("recentProjects", [])
        
        if not recent_files:
            empty_action = self.recent_projects_menu.addAction(tr("No Recent Projects"))
            empty_action.setEnabled(False)
            return

        for fpath in recent_files:
            if os.path.exists(fpath):
                action = self.recent_projects_menu.addAction(os.path.basename(fpath))
                action.setData(fpath)
                action.setToolTip(fpath)
                action.triggered.connect(lambda checked=False, p=fpath: self.load_project(p))
            
        self.recent_projects_menu.addSeparator()
        clear_action = self.recent_projects_menu.addAction(tr("Clear Recent Projects"))
        clear_action.triggered.connect(self.clear_recent_projects)

    def add_to_recent_projects(self, fpath):
        """Adds a project file path to the recent projects list."""
        recent_files = self.settings.value("recentProjects", [])
        if not isinstance(recent_files, list):
            recent_files = []
            
        if fpath in recent_files:
            recent_files.remove(fpath)
        recent_files.insert(0, fpath)
        
        # Keep only last 10
        recent_files = recent_files[:10]
        self.settings.setValue("recentProjects", recent_files)
        self.update_recent_projects_menu()

    def clear_recent_projects(self):
        """Clears the recent projects list."""
        self.settings.setValue("recentProjects", [])
        self.update_recent_projects_menu()



    def update_ui_after_load(self):
        """Updates all UI components after a project is loaded."""
        self.sample_list.refresh_list()
        self.sample_list.refresh_pool_list()
        self.initialize_all_views()
        self.update_window_title()

    def handle_scene_deletion(self, scene_id):
        """
        Handles scene deletion.
        If the deleted scene is the current one, clear the view.
        """
        Logger.info(f"[Main] Scene deleted: {scene_id}")
        
        # If the deleted scene was the current one
        if self.current_scene_id == scene_id:
            Logger.info(f"[Main] Deleted active scene {scene_id}. Clearing views.")
            self.current_scene_id = None
            self.session.clear() # Clear session data
            self.initialize_all_views() # Re-init views (clears images)
            self.lbl_status.setText(tr("Scene {0} deleted and view cleared.").format(scene_id))
        else:
            self.lbl_status.setText(tr("Scene {0} removed from project.").format(scene_id))
            
    def on_channel_cleared(self, scene_id, ch_index):
        """
        Callback when a channel is cleared (e.g. via 'Clear' button in SampleList).
        """
        Logger.info(f"[Main] Channel cleared: scene={scene_id}, ch={ch_index}")
        if self.current_scene_id == scene_id:
            if 0 <= ch_index < len(self.session.channels):
                ch = self.session.channels[ch_index]
                ch.file_path = ""
                ch.update_data(np.zeros((1, 1), dtype=np.uint16))
                ch.is_placeholder = True
                ch.stats = {}
                self.session.data_changed.emit()
                self.update_all_view_containers(ch_index)

    def on_channel_removed(self, scene_id, ch_index):
        """
        Callback when a channel slot is removed entirely.
        """
        Logger.info(f"[Main] Channel removed: scene={scene_id}, ch={ch_index}")
        if self.current_scene_id == scene_id:
            # Full reload needed because channel indices shift
            self.load_scene(scene_id, force=True)

    def update_window_title(self):
        """Updates window title with current project name."""
        if self.current_project_path:
            pname = os.path.basename(self.current_project_path)
            self.setWindowTitle(tr("FluoQuantPro - {0}").format(pname))
        else:
            self.setWindowTitle(tr("FluoQuantPro"))

    def load_project(self, folder):
        """Internal helper to load a project folder."""
        if not folder or not os.path.exists(folder):
            return False
            
        json_path = os.path.join(folder, "project.fluo")
        if not os.path.exists(json_path):
            json_path = os.path.join(folder, "project.json") # Fallback
            
        if not os.path.exists(json_path):
            # NEW LOGIC: Auto-initialize if missing (Restore "Open Folder -> Auto Read" workflow)
            reply = QMessageBox.question(self, tr("Initialize Project"), 
                                         tr("No project file found. Initialize new project and import images from this folder?"),
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            
            if reply == QMessageBox.StandardButton.Yes:
                self.project_model.clear()
                self.session.clear()
                self.project_model.set_root_path(folder)
                
                # Scan folder for images
                settings = QSettings("FluoQuantPro", "AppSettings")
                recursive = settings.value("import/recursive", False, type=bool)
                files = self.project_model.scan_folder(folder, recursive=recursive)
                if files:
                    # Use add_files to group them into scenes immediately (Auto Read)
                    self.project_model.add_files(files)
                    self.lbl_status.setText(tr("Initialized project with {0} images.").format(len(files)))
                else:
                    self.lbl_status.setText(tr("Initialized empty project."))
                
                # Save immediately to establish project structure
                self.project_model.save_project()
                
                self.current_project_path = folder
                self.update_ui_after_load()
                self.add_to_recent_projects(folder)
                self.update_window_title()
                return True
            else:
                return False

        # Existing load logic
        self.project_model.clear()  # Uses default clear_undo=True to reset undo stack for new project
        self.session.clear()
        
        # Load
        if self.project_model.load_project(folder):
            self.current_project_path = folder
            self.sample_list.refresh_list()
            self.sample_list.refresh_pool_list()
            self.initialize_all_views()
            self.add_to_recent_projects(folder)
            self.lbl_status.setText(tr("Project Loaded: {0}").format(folder))
            self.update_window_title()
            if getattr(self.project_model, "last_template_warnings", None):
                warnings = [str(w) for w in self.project_model.last_template_warnings if w]
                if warnings:
                    QMessageBox.warning(
                        self,
                        tr("Template Warning"),
                        tr("Project channel template has irregularities and has been automatically normalized.\nWe recommend checking the channel template settings to avoid inheritance issues.\n\nDetails:\n{0}").format("\n".join(warnings))
                    )
            return True
        else:
            QMessageBox.critical(self, tr("Error"), tr("Failed to load project file."))
            return False

    def open_project(self):
        """Opens an existing project folder."""
        if not self.check_unsaved_changes():
            return

        folder = QFileDialog.getExistingDirectory(self, tr("Open Project Folder"))
        if folder:
            # Check if current project is empty (no root path set). If so, load in place.
            # Otherwise, launch a new instance.
            if not self.project_model.root_path:
                self.load_project(folder)
            else:
                # Launch new instance
                import subprocess
                try:
                    subprocess.Popen([sys.executable, __file__, folder])
                    self.lbl_status.setText(tr("Opening project in new window..."))
                except Exception as e:
                    QMessageBox.warning(self, tr("Error"), tr("Failed to launch new window: {0}").format(e))
                    # Fallback to loading in place
                    self.load_project(folder)

    def save_project_as(self) -> bool:
        """Prompts for a new folder and saves the project there."""
        folder = QFileDialog.getExistingDirectory(self, tr("Select Project Folder to Save As"))
        if not folder:
            return False
            
        # Check for existing project file
        if os.path.exists(os.path.join(folder, "project.fluo")) or os.path.exists(os.path.join(folder, "project.json")):
             res = QMessageBox.warning(self, tr("Existing Project"), 
                                      tr("This folder already contains a project file. Overwrite?"),
                                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
             if res == QMessageBox.StandardButton.No:
                 return False
        
        self.project_model.set_root_path(folder)
        return self.save_project()

    def save_project(self, manual: bool = True) -> bool:
        """
        Saves project structure and current scene state.
        
        Args:
            manual: If True (default), forces ROI persistence regardless of settings.
                   If False (e.g. auto-save or save-on-close), respects user settings.
        """
        if not self.project_model.root_path:
            return self.save_project_as()

        # 1. Determine if we should capture ROIs based on settings/manual flag
        include_rois = True
        if not manual:
            settings = QSettings("FluoQuantPro", "AppSettings")
            save_on_close = settings.value("roi/save_on_close", False, type=bool)
            save_on_switch = settings.value("roi/save_on_switch", False, type=bool)
            include_rois = save_on_close or save_on_switch

        # 2. Capture Current Scene State (Update in-memory ProjectModel)
        if self.current_scene_id:
            # If include_rois is False, we might want to preserve annotations anyway
            # or just skip updating ROIs in memory for this save.
            if include_rois:
                rois = self.session.roi_manager.serialize_rois()
            else:
                # USER REQUEST: Persist only annotations even if measurement ROIs are not auto-saved
                all_rois = self.session.roi_manager.get_all_rois()
                annotation_types = ['arrow', 'text', 'line_scan', 'line', 'polygon', 'general', 'point', 'circle', 'rectangle', 'rect', 'ellipse', 'magic_wand']
                persistent_rois = [r for r in all_rois if r.roi_type in annotation_types]
                
                from src.core.roi_model import RoiManager
                temp_manager = RoiManager()
                for r in persistent_rois:
                    temp_manager.add_roi(r)
                rois = temp_manager.serialize_rois()
                
            # Get Display Settings
            display_settings = []
            for ch in self.session.channels:
                s = ch.display_settings
                s_dict = {
                    "min_val": s.min_val,
                    "max_val": s.max_val,
                    "gamma": s.gamma,
                    "visible": s.visible,
                    "color": s.color,
                    "enhance_percents": getattr(s, 'enhance_percents', {}),
                    "enhance_params": getattr(s, 'enhance_params', {})
                }
                display_settings.append(s_dict)
                
            # Update memory state
            self.project_model.save_scene_state(self.current_scene_id, rois, display_settings)
        
        # 3. Save to JSON
        try:
            self.project_model.save_project()
            self.add_to_recent_projects(self.project_model.root_path)
            
            if manual:
                self.lbl_status.setText(tr("Project Saved to {0}").format(self.project_model.root_path))
            return True
        except Exception as e:
            QMessageBox.critical(self, tr("Error"), tr("Failed to save project: {0}").format(e))
            return False

    def update_active_channel_color(self, scene_id, ch_index, new_color):
        """
        Updates the color of a channel in the active session if it matches the modified scene.
        Ensures real-time rendering update without reloading the file.
        """
        if self.current_scene_id == scene_id:
            if 0 <= ch_index < len(self.session.channels):
                ch = self.session.channels[ch_index]
                if ch.display_settings.color != new_color:
                    ch.display_settings.color = new_color
                    self.session.data_changed.emit()
                    print(f"[Main] Updated active channel {ch_index} color to {new_color}")
                    
                    # Trigger re-render to update Merge View immediately
                    self.refresh_display()

    def import_folder_auto(self):
        """Redirects to sample list's auto-group import folder."""
        self.sample_list.import_folder_auto()

    def on_import_merge(self):
        """
        Implementation of Import Merge:
        1. Select RGB image.
        2. Split into R, G, B.
        3. Assign fluorophores via dialog.
        4. Add as a new individual scene (doesn't affect project template).
        """
        if not self.project_model.root_path:
            QMessageBox.warning(self, tr("No Project"), tr("Please create or open a project first."))
            return

        file_path, _ = QFileDialog.getOpenFileName(
            self, tr("Select RGB Merge Image"), "", tr("Images (*.tif *.tiff *.png *.jpg *.jpeg);;All Files (*)")
        )
        if not file_path:
            return

        # 1. Show assignment dialog
        filename = os.path.basename(file_path)
        dlg = FluorophoreAssignmentDialog(self, filename)
        if not dlg.exec():
            return

        assignments = dlg.get_assignments()
        
        # 2. Split RGB and save
        try:
            img = tifffile.imread(file_path)
            if img.ndim < 3 or img.shape[-1] < 3:
                QMessageBox.critical(self, tr("Error"), tr("Selected image is not a standard RGB image."))
                return
            
            # Handle potential (C, H, W) vs (H, W, C)
            if img.shape[0] <= 4: # Likely (C, H, W)
                r, g, b = img[0], img[1], img[2]
            else: # Likely (H, W, C)
                r, g, b = img[:,:,0], img[:,:,1], img[:,:,2]
            
            # Create subfolder for imported channels
            import_dir = os.path.join(self.project_model.root_path, "imported_merge", os.path.splitext(filename)[0])
            os.makedirs(import_dir, exist_ok=True)
            
            channels_to_add = []
            for color_name, data in [("Red", r), ("Green", g), ("Blue", b)]:
                assignment = assignments.get(color_name)

                if not assignment:
                    continue

                ch_filename = f"{os.path.splitext(filename)[0]}_{color_name}.tif"
                ch_path = os.path.join(import_dir, ch_filename)
                tifffile.imwrite(ch_path, data.astype(img.dtype))

                channels_to_add.append({
                    "path": ch_path,
                    "type": assignment['fluorophore'],
                    "color": assignment['color'],
                    "visible": True
                })

            if not channels_to_add:
                QMessageBox.information(self, tr("Import Merge"), tr("No channels were selected for import."))
                return

            # 3. Add to Project Model (Individual case, doesn't use template)
            scene_name = os.path.splitext(filename)[0]
            scene_id = self.project_model.add_imported_merge_scene(scene_name, channels_to_add)
            
            # 4. Update UI
            self.sample_list.refresh_list()
            self.lbl_status.setText(tr("Imported Merge: {0}").format(scene_name))
            
            # Optional: Select the new scene
            self.load_scene(scene_id)
            
        except Exception as e:
            QMessageBox.critical(self, tr("Import Error"), tr("Failed to split and import image:\n{0}").format(str(e)))

    def handle_channel_file_drop(self, file_path: str, channel_index: int):
        """
        Handles file drop on a specific channel view.
        Updates the ProjectModel and reloads the scene.
        """
        if not self.current_scene_id:
            return
            
        Logger.info(f"[Main] File dropped on View: Assigning {file_path} to Channel {channel_index} in Scene {self.current_scene_id}")
        
        # 1. Update Project Model (Persistence)
        self.project_model.update_channel_path(self.current_scene_id, channel_index, file_path)
        
        # 2. Refresh Sample List UI (to show filled slot)
        self.sample_list.refresh_list()
        self.sample_list.refresh_pool_list()
        
        # 3. Update Session & View (Immediate Visual Feedback)
        self.on_channel_file_assigned(self.current_scene_id, channel_index, file_path)
        
        # 4. Final Polish
        self.lbl_status.setText(tr("Assigned {0} to channel {1}").format(os.path.basename(file_path), channel_index + 1))
        self.flash_view_channel(channel_index)
        self.fit_all_views()

    def on_channel_file_assigned(self, scene_id, ch_index, file_path):
        """
        Callback when a file is dropped onto a channel slot in SampleListWidget.
        Logic:
          1. If dropping onto the CURRENT active scene, reload that channel immediately.
          2. If dropping onto another scene, just update model (already done by SampleList),
             but do NOT reload current view.
        """
        Logger.debug(f"[Main] on_channel_file_assigned: scene={scene_id}, ch={ch_index}, file={file_path}")
        
        # Check if we are currently viewing this scene
        if self.current_scene_id == scene_id:
            Logger.info(f"[Main] Dropped file on CURRENT scene {scene_id}. Reloading channel {ch_index}...")
            
            # 1. Update Session channel info
            if 0 <= ch_index < len(self.session.channels):
                try:
                    # Use robust ImageLoader instead of raw imread
                    from src.core.image_loader import ImageLoader
                    data, is_rgb = ImageLoader.load_image(file_path)
                    
                    if data is not None:
                            if data.ndim == 3 and data.shape[2] == 3:
                                data = cv2.cvtColor(data, cv2.COLOR_BGR2RGB)
                            elif data.ndim == 3 and data.shape[2] == 4:
                                data = cv2.cvtColor(data, cv2.COLOR_BGRA2RGBA)

                    if data is not None:
                        # Handle preprocessing (Max Projection)
                        if data.ndim == 3 and data.shape[0] < 10:
                             data = np.max(data, axis=0) # Z-stack max proj
                        elif data.ndim == 3 and data.shape[2] < 10 and data.shape[2] not in (3,4):
                             data = np.max(data, axis=2)
                             
                        # Update Session Channel
                        ch = self.session.channels[ch_index]
                        ch.file_path = file_path
                        ch.update_data(data)
                        ch.is_placeholder = False
                        
                        from src.core.analysis import calculate_channel_stats
                        ch.stats = calculate_channel_stats(data)
                        
                        # INHERIT SETTINGS: Check if this file has existing settings in the project model pool
                        pool_settings = self.project_model.pool_display_settings.get(os.path.normpath(file_path))
                        if pool_settings:
                            Logger.info(f"[Main] Inheriting display settings for {os.path.basename(file_path)}")
                            ch.display_settings.min_val = pool_settings.get('min_val', ch.display_settings.min_val)
                            ch.display_settings.max_val = pool_settings.get('max_val', ch.display_settings.max_val)
                            ch.display_settings.gamma = pool_settings.get('gamma', ch.display_settings.gamma)
                        else:
                            ch.reset_display_settings() 
                        
                        Logger.info(f"[Main] Data loaded for channel {ch_index}. Triggering view update.")
                        self.session.data_changed.emit() 
                        
                        # Also refresh the view explicitly to ensure update
                        self.update_all_view_containers(ch_index)
                        
                except Exception as e:
                    Logger.error(f"[Main] Error reloading channel {ch_index}: {e}")
                    QMessageBox.warning(self, tr("Load Error"), str(e))
        else:
            Logger.debug(f"[Main] Dropped file on background scene {scene_id}. No immediate view refresh needed.")

    def load_scene(self, scene_id, force=False):
        """Called when user clicks a scene in the sample list."""
        if not scene_id: return
        
        # Optimization: Do not reload if it's already the current scene
        if self.current_scene_id == scene_id and not force:
           return
        
        # Stop any existing loader
        if self.loader_worker and self.loader_worker.isRunning():
            self.loader_worker.stop()
            self.loader_worker = None
        
        # --- Save Previous Scene State (In-Memory) ---
        if self.current_scene_id and self.current_scene_id != scene_id:
            # We use save_project(manual=False) to handle persistence logic 
            # (respecting settings like save_on_switch).
            # This avoids redundant serialization code here.
            self.save_project(manual=False)
        
        self.current_scene_id = scene_id
        
        # --- Prepare to Load New Scene ---
        scene_data = self.project_model.get_scene(scene_id)
        if not scene_data:
             return

        self.session.clear()

        # Auto-detect Mode (Must be set AFTER clear, as clear() resets it)
        if len(scene_data.channels) == 1:
            self.session.is_single_channel_mode = True
        else:
            self.session.is_single_channel_mode = False
        
        # Reset View (Empty)
        self.initialize_all_views()
        self.show_view_loading(tr("Loading {0}...").format(scene_id)) # Show overlay
        self.lbl_status.setText(tr("Loading scene: {0}...").format(scene_id))
        
        # Start Async Loader
        self.loader_worker = SceneLoaderWorker(scene_id, scene_data.channels)
        self.loader_worker.channel_loaded.connect(self.on_channel_loaded)
        self.loader_worker.finished_loading.connect(self.on_scene_loading_finished)
        self.loader_worker.start()

    def on_channel_loaded(self, scene_id, index, data_or_obj, ch_def):
        """Called when a single channel finishes loading in background."""
        Logger.info(f"[UI] Received channel_loaded signal for index {index}")
        if scene_id != self.current_scene_id:
            return # Ignore old signals
            
        try:
            # Add to session
            if isinstance(data_or_obj, ImageChannel):
                 self.session.add_existing_channel(data_or_obj)
                 ch = data_or_obj
            else:
                 # Fallback for legacy or error cases
                 # add_channel arguments: file_path, color, name, data
                 ch = self.session.add_channel(ch_def.path, ch_def.color, ch_def.channel_type, data=data_or_obj)
            
            # Apply saved settings if any
            if ch_def.display_settings:
                ds = ch_def.display_settings
                ch.display_settings.min_val = ds.get("min_val", ch.display_settings.min_val)
                ch.display_settings.max_val = ds.get("max_val", ch.display_settings.max_val)
                ch.display_settings.gamma = ds.get("gamma", ch.display_settings.gamma)
                ch.display_settings.visible = ds.get("visible", True)
                ch.display_settings.color = ds.get("color", ch.display_settings.color)
                
                # Restore Enhance Params
                ch.display_settings.enhance_percents = ds.get("enhance_percents", {})
                ch.display_settings.enhance_params = ds.get("enhance_params", {})
                
                if ch.display_settings.enhance_percents:
                    Logger.info(f"[UI] Restored enhancement parameters for channel {index}")

            # Restore ROIs & Annotations ONLY when the first channel is loaded (to set reference shape)
            scene_data = self.project_model.get_scene(scene_id)
            if index == 0:
                # USER REQUEST: Always restore ROIs if present in project data
                # settings = QSettings("FluoQuantPro", "AppSettings")
                # save_rois_on_switch = settings.value("roi/save_on_switch", False, type=bool)
                
                if scene_data.rois:
                    self._suppress_roi_annotation_sync = True
                    try:
                        self.session.roi_manager.set_rois(scene_data.rois)
                    finally:
                        self._suppress_roi_annotation_sync = False
                
                # Sync ROI selection state
                if hasattr(self.session, 'roi_manager'):
                    self.session.roi_manager.selection_changed.emit()
            
            # Update UI incrementally
            # We initialize views for every channel to ensure the layout updates (1-view, 2-view, etc.)
            # and to ensure the view objects exist for rendering.
            self.initialize_all_views()
            
            if index == 0:
                Logger.info("[UI] Initializing first channel view...")
                self.fit_all_views()
                self.select_view_channel(0)
            
            # Trigger immediate render for this channel
            # Note: initialize_views() already calls render_all(), but we call it again 
            # if we want to be absolutely sure the latest session data is used.
            self.refresh_display()
            
            # Update overlay text (shows progress)
            self.show_view_loading(tr("Loading... ({0}/{1})").format(index+1, len(scene_data.channels))) 
            self.lbl_status.setText(tr("Loaded channel {0}/{1}").format(index+1, len(scene_data.channels)))
            
            Logger.info(f"[UI] on_channel_loaded done for index {index}")
            
        except Exception as e:
            Logger.error(f"Error in on_channel_loaded for index {index}: {e}")
            import traceback
            traceback.print_exc()
            
            # User Feedback for Dimension Mismatch
            if "Dimension mismatch" in str(e):
                QMessageBox.warning(
                    self, 
                    tr("Load Error"), 
                    tr("Failed to load channel {0}: Image dimensions must match the first loaded channel.").format(index+1) + 
                    f"\n\n{str(e)}"
                )
            
            self.lbl_status.setText(tr("Error loading channel {0}: {1}").format(index+1, e))

    def on_scene_loading_finished(self, scene_id):
        if scene_id != self.current_scene_id: return
        Logger.info("[UI] Scene loading finished signal received")
        
        try:
            # Final refresh: Initialize views with ALL loaded channels
            Logger.info("[UI] Final view initialization...")
            self.initialize_all_views()
            self.fit_all_views()
            Logger.info("[UI] Final view initialization done")
            
            # Update Tool Targets
            self.update_point_counter_targets()
            
            # Update Overlays
            self.update_all_scale_bars(self.session.scale_bar_settings)
            
            # Ensure Annotation Panel is in sync
            if hasattr(self, 'annotation_panel'):
                self.annotation_panel.update_annotation_list()
            
        except Exception as e:
            print(f"Error in on_scene_loading_finished: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.hide_view_loading()
            self.lbl_status.setText(tr("Scene loaded: {0}").format(scene_id))

    def update_point_counter_targets(self):
        """Populates the point counter channel combo with current session channels."""
        if not hasattr(self, 'roi_toolbox'):
            return
            
        # Ensure point counter widgets are initialized
        # If the point counter group hasn't been created yet, this attribute won't exist.
        if not hasattr(self.roi_toolbox, 'combo_count_target'):
            self.roi_toolbox.refresh_point_counter_channels()

        if hasattr(self.roi_toolbox, 'combo_count_target'):
            combo = self.roi_toolbox.combo_count_target
            combo.blockSignals(True) # Prevent triggering signals during update
            combo.clear()
            combo.addItem(tr("Auto (Current View)"), -1)
            
            for i, ch in enumerate(self.session.channels):
                combo.addItem(tr("Channel {0}: {1}").format(i+1, ch.name), i)
            combo.blockSignals(False)

    def on_scene_renamed(self, old_id, new_id):
        """Handle scene rename to keep state consistent."""
        if self.current_scene_id == old_id:
            self.current_scene_id = new_id
            self.lbl_status.setText(tr("Scene renamed to: {0}").format(new_id))
            # No need to reload images as the SceneData object is the same in memory (just ID changed)
            # But we might need to update any labels referring to the scene name
            


    def handle_wand_tolerance_changed(self, tolerance):
        """Updates status bar with current magic wand tolerance during dragging."""
        mode = tr("%") if self.wand_tool.relative else tr("units")
        self.lbl_status.setText(tr("Magic Wand: Adjusting Tolerance... {0:.1f} {1}").format(tolerance, mode))

    def on_batch_selection_made(self, rect, channel_index=-1):
        """Selects all items within the given rect in the active view."""
        from PySide6.QtGui import QPainterPath
        from PySide6.QtWidgets import QGraphicsItem
        
        Logger.debug(f"[Main] on_batch_selection_made with rect: {rect}, channel_idx: {channel_index}")
        
        active_view = self.get_active_canvas_view()
        
        if active_view:
             path = QPainterPath()
             path.addRect(rect)
             
             # Get items in the rect (this uses QGraphicsScene logic)
             items = active_view.scene.items(path, Qt.ItemSelectionMode.IntersectsItemShape)
             Logger.debug(f"[Main] Found {len(items)} items in selection rect")
             
             # Clear current selection first
             active_view.scene.clearSelection()
             
             count = 0
             selected_ids = []
             for item in items:
                 if item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable:
                     # Select ROI items
                     if hasattr(item, 'roi_id'):
                         item.setSelected(True)
                         selected_ids.append(item.roi_id)
                         count += 1
                     # Select Annotation items
                     elif hasattr(item, 'ann_id'):
                         item.setSelected(True)
                         count += 1
                     
             self.lbl_status.setText(tr("Selected {0} items.").format(count))
             Logger.debug(f"[Main] Selected {count} valid ROI items: {selected_ids}")
             
             # Force update RoiManager selection state immediately
             # This is critical because QGraphicsScene selectionChanged might be async or blocked
             if self.session and self.session.roi_manager:
                 self.session.roi_manager.set_selected_ids(selected_ids)


    def on_tool_cancelled(self):
        """Called when ESC is pressed in CanvasView."""
        # Uncheck all ROI tools (switch to Pan)
        self._suppress_tool_toggled = True
        for act in self.tools_action_group.actions():
            if act != self.action_pan:
                act.setChecked(False)
        self.action_pan.setChecked(True)
        self._suppress_tool_toggled = False
        
        # Clear annotation tool selection
        if hasattr(self, 'annotation_panel'):
            self.annotation_panel.clear_tool_selection()
            
        # Reset mode
        self.pending_annotation_mode = None
        self.set_view_tool(None)
        self.set_view_annotation_mode('none')
        self.lbl_status.setText(tr("Ready"))

    def on_tool_toggled(self, tool_action, checked):
        # Check suppression flag
        if getattr(self, '_suppress_tool_toggled', False):
            return

        # --- 状态锁：开始切换 ROI 工具 ---
        self._is_switching_roi_tool = True
        
        try:
            # Manual Exclusivity Logic
            if checked:
                # Uncheck all other tools
                self._suppress_tool_toggled = True
                for act in self.tools_action_group.actions():
                    if act != tool_action:
                        act.setChecked(False)
                self._suppress_tool_toggled = False
                
                # FORCE: If we are selecting something other than Pan, ensure Pan is NOT checked
                if tool_action != self.action_pan:
                    self.action_pan.setChecked(False)
            else:
                # If unchecked, and NO other tool is checked, switch to Pan (Default)
                if not any(a.isChecked() for a in self.tools_action_group.actions()):
                    # Fix: If we are in Annotation Mode (pending_annotation_mode is set),
                    # do NOT fallback to Pan, because the Annotation tool is active but not represented in this action group.
                    if getattr(self, 'pending_annotation_mode', None):
                        return

                    if tool_action != self.action_pan:
                         # Switch to Pan
                         self.action_pan.setChecked(True)
                         return 
                    else:
                         # Pan was unchecked. Re-check it.
                         self._suppress_tool_toggled = True
                         self.action_pan.setChecked(True)
                         self._suppress_tool_toggled = False
                         return

            if not checked:
                return
                
            # Update Drawing Mode
            self.drawing_mode = DrawingMode.ROI
                
            # Update toolbox UI
            if hasattr(self, 'roi_toolbox'):
                Logger.debug(f"[Main.on_tool_toggled] Toggling toolbox for action: {tool_action.text() if tool_action else 'None'}")
                
                self.roi_toolbox.set_active_tool(tool_action)
                
                # AUTO-SWITCH TAB: If an ROI tool is selected, switch to ROI Toolbox tab
                # USER REQUEST: Do NOT switch for LineScan
                # Also do NOT switch if we are already in the process of switching tabs (avoids loops)
                if tool_action != self.action_line_scan and not getattr(self, '_is_switching_tab', False):
                    for i in range(self.control_tabs.count()):
                        tab_text = self.control_tabs.tabText(i)
                        is_toolbox_tab = False
                        for tab_id, _, title in self.all_tabs_data:
                            if tab_id == "toolbox" and title == tab_text:
                                is_toolbox_tab = True
                                break
                        
                        if is_toolbox_tab:
                            self.control_tabs.setCurrentIndex(i)
                            Logger.debug(f"[Main.on_tool_toggled] Switched to tab {i} ({tab_text})")
                            break

            # Clear annotation tool selection if a regular ROI tool is selected
            if hasattr(self, 'annotation_panel'):
                self.annotation_panel.clear_tool_selection()
                
            # Reset pending annotation mode to prevent "hijacking"
            self.pending_annotation_mode = None 
        finally:
            # --- 释放锁 ---
            self._is_switching_roi_tool = False

        if tool_action == self.action_wand:
            self.lbl_status.setText(tr("Mode: Magic Wand (Click to Auto-Select, Drag horizontally to adjust tolerance)"))
            # Sync settings from UI
            self.wand_tool.base_tolerance = self.roi_toolbox.spin_wand_tol.value()
            self.wand_tool.smoothing = self.roi_toolbox.spin_wand_smooth.value()
            self.wand_tool.relative = self.roi_toolbox.chk_wand_relative.isChecked()
            if hasattr(self.roi_toolbox, 'chk_wand_largest'):
                self.wand_tool.keep_largest = self.roi_toolbox.chk_wand_largest.isChecked()
            if hasattr(self.roi_toolbox, 'chk_wand_split'):
                self.wand_tool.split_regions = self.roi_toolbox.chk_wand_split.isChecked()
            if hasattr(self.roi_toolbox, 'chk_wand_polygon'):
                self.wand_tool.convert_to_polygon = self.roi_toolbox.chk_wand_polygon.isChecked()
            if hasattr(self.roi_toolbox, 'chk_wand_smooth_contour'):
                self.wand_tool.contour_smoothing = self.roi_toolbox.chk_wand_smooth_contour.isChecked()
            
            self.set_view_tool(self.wand_tool)
        elif tool_action == self.action_polygon:
            self.lbl_status.setText(tr("Mode: Polygon Lasso (Left Click to Add, Right Click to Finish)"))
            self.set_view_tool(self.polygon_tool)
            # Sync fixed size state
            if hasattr(self.polygon_tool, 'set_fixed_size_mode'):
                self.polygon_tool.set_fixed_size_mode(self.roi_toolbox.chk_fixed_size.isChecked())
        elif tool_action == self.action_rect:
            self.lbl_status.setText(tr("Mode: Rectangle Selection (Drag to Draw)"))
            self.set_view_tool(self.rect_tool)
            # Sync fixed size state
            self.rect_tool.set_fixed_size_mode(self.roi_toolbox.chk_fixed_size.isChecked())
        elif tool_action == self.action_ellipse:
            self.lbl_status.setText(tr("Mode: Ellipse Selection (Drag to Draw)"))
            self.set_view_tool(self.ellipse_tool)
            # Sync fixed size state
            self.ellipse_tool.set_fixed_size_mode(self.roi_toolbox.chk_fixed_size.isChecked())
        elif tool_action == self.action_count:
            self.lbl_status.setText(tr("Mode: Point Counter (Click to count spots in current channel or merge view)"))
            self.count_tool.radius = self.roi_toolbox.spin_count_radius.value()
            self.set_view_tool(self.count_tool)
        elif tool_action == self.action_line_scan:
            self.lbl_status.setText(tr("Mode: Line Scan (Drag to Draw Line for Colocalization)"))
            self.set_view_tool(self.line_scan_tool)
            # Sync fixed size state
            if hasattr(self.line_scan_tool, 'set_fixed_size_mode'):
                self.line_scan_tool.set_fixed_size_mode(self.roi_toolbox.chk_fixed_size.isChecked())
            # Switch to Colocalization tab automatically
            if self.colocalization_panel:
                self.control_tabs.setCurrentWidget(self.colocalization_panel)
        elif tool_action == self.action_batch_select:
            self.lbl_status.setText(tr("Mode: Batch Select (Drag to select multiple items)"))
            self.set_view_tool(self.batch_tool)
        elif tool_action == self.action_pan:
            self.lbl_status.setText(tr("Mode: Pan/Hand (Drag to Move View/ROI)"))
            self.set_view_tool(None) # Setting tool to None enables Pan mode in CanvasView
        else:
            self.set_view_tool(None)
            self.lbl_status.setText(tr("Mode: View/Pan"))

    def on_channel_selected(self, index):
        """Syncs the selected channel across the UI and tools."""
        self.active_channel_idx = index
        try:
            if index is not None and index >= 0 and index < len(self.session.channels):
                ch_name = self.session.channels[index].name
                self.lbl_status.setText(tr("Selected: {0}").format(ch_name))
            elif index == -1:
                self.lbl_status.setText(tr("Selected: Merge"))
                    
            Logger.debug(f"[Main] Channel selected: {index}")
            
            # Update visual state in ALL view containers
            self.flash_view_channel(index)
            self.select_view_channel(index)
            
            # Also sync to sample list for visual feedback
            if hasattr(self, 'sample_list'):
                self.sample_list.set_active_channel(index)
                
        except Exception as e:
            Logger.debug(f"[Main] Channel selected UI feedback failed: {e}")
        
        # Update tools with the currently selected channel for Merge view drawing
        for tool in [self.wand_tool, self.polygon_tool, self.rect_tool, self.ellipse_tool, self.count_tool, self.line_scan_tool]:
            if hasattr(tool, 'set_active_channel'):
                tool.set_active_channel(index)

    def on_sample_channel_selected(self, scene_id, channel_index):
        """Called when a specific channel is clicked in the sample list."""
        if scene_id == self.current_scene_id:
            # Just switch the view if it's the same scene
            print(f"DEBUG: Switching to channel {channel_index} in scene {scene_id} without reload")
            self.select_view_channel(channel_index)
            # Also sync with panels
            self.adjustment_panel.set_active_channel(channel_index)
            self.enhance_panel.set_active_channel(channel_index)
        else:
            # Different scene, reload
            print(f"DEBUG: Reloading scene {scene_id} for channel {channel_index}")
            self.load_scene(scene_id)
            # After load, select channel (SceneLoaderWorker emits channel_loaded which might handle this,
            # but let's ensure it's set if loader skips it)
            # Actually, load_scene sets up a worker. We should tell the worker which channel to focus on.
            self.active_channel_idx = channel_index # This will be used when rendering finishes


    def on_fixed_size_toggled(self, checked):
        """Updates tool fixed size mode and toolbox UI state."""
        # Update toolbox inputs enabled state
        if hasattr(self, 'roi_toolbox'):
            self.roi_toolbox.spin_width.setEnabled(checked)
            self.roi_toolbox.spin_height.setEnabled(checked)
            
        # Update all applicable tools
        for tool in [self.rect_tool, self.ellipse_tool, self.line_scan_tool, self.polygon_tool]:
            if hasattr(tool, 'set_fixed_size_mode'):
                tool.set_fixed_size_mode(checked)

    def select_all_rois(self):
        """Selects all ROIs in the current session."""
        if self.session and self.session.roi_manager:
            self.session.roi_manager.select_all()
        
    def crop_to_selection(self):
        """
        Crops the image to the current ROI selection.
        Creates a NEW sample with the cropped data instead of overwriting.
        Supports MBR and Perspective Transform for rotated ROIs, with Masking for Polygons.
        """
        Logger.debug("[Main] crop_to_selection called")
        rois = self.session.roi_manager.get_all_rois()
        if not rois:
            self.lbl_status.setText(tr("No selection to crop."))
            QMessageBox.information(self, tr("Crop"), tr("Please select an area (ROI) first."))
            return
            
        # Use the LAST ROI
        roi = rois[-1]
        Logger.debug(f"[Main] Cropping to ROI: {roi.label}, Type: {roi.roi_type}")
        
        # --- Advanced Crop Logic (MBR + Perspective + Mask) ---
        import cv2
        import numpy as np
        
        # 1. Get ROI Points
        # Prefer explicit points if available and sufficient (>= 3 for polygon/rotated rect)
        points = []
        if roi.points and len(roi.points) >= 3:
            points = [[p.x(), p.y()] for p in roi.points]
            
        # If points are insufficient (e.g. 2 points for Rect), try extracting from Path
        # This handles rotated rectangles where roi.points might only be [TL, BR] but path is rotated.
        if len(points) < 3 and roi.path:
            path_points = []
            for i in range(roi.path.elementCount()):
                e = roi.path.elementAt(i)
                # Check for MoveTo or LineTo to get vertices
                if e.isMoveTo() or e.isLineTo():
                    # Check if point is already in list (to avoid duplicates from closed loops)
                    pt = [e.x, e.y]
                    if not path_points or (abs(path_points[-1][0] - pt[0]) > 0.01 or abs(path_points[-1][1] - pt[1]) > 0.01):
                        path_points.append(pt)
            
            # Use path points if they define a shape (>= 3 points)
            if len(path_points) >= 3:
                points = path_points
                Logger.debug(f"[Main] Extracted {len(points)} points from ROI path (overriding insufficient roi.points).")
        
        
        src_pts_ordered = None
        dst_pts = None
        M = None
        w, h = 0, 0
        x, y = 0, 0
        
        # 2. Determine Crop Strategy based on ROI Type
        # User Feedback: "Polygon crop sometimes distorts coordinates."
        # Cause: minAreaRect + Warp rotates the image, which is unexpected for generic polygons.
        # Fix: Use Axis-Aligned Bounding Rect for Polygons/Freehand/Rectangles.
        #      Only use minAreaRect (Rotation) for explicitly Rotated Rectangles (if implemented).
        
        use_rotation = False
        # If we had a specific 'rotated_rect' type, we would set use_rotation = True
        # Currently, 'rectangle', 'polygon', 'freehand', 'magic_wand', 'ellipse' 
        # are best served by Axis-Aligned Crop + Mask.
        
        if len(points) < 3:
             # Fallback to simple bounding rect if not enough points
             Logger.debug("[Main] Not enough points for advanced crop. Using bounding rect.")
             rect = roi.path.boundingRect()
             # Use floor/ceil to ensure we capture the full area and avoid 1px shifts
             x_f, y_f, w_f, h_f = rect.x(), rect.y(), rect.width(), rect.height()
             x, y = int(np.floor(x_f)), int(np.floor(y_f))
             w, h = int(np.ceil(x_f + w_f)) - x, int(np.ceil(y_f + h_f)) - y
        
        elif not use_rotation:
             # Axis-Aligned Strategy
             Logger.debug(f"[Main] Using Axis-Aligned Crop for ROI Type: {roi.roi_type}")
             pts_array = np.array(points, dtype=np.float32)
             x_min, y_min, w_val, h_val = cv2.boundingRect(pts_array)
             # Robust integer conversion
             x, y = int(np.floor(x_min)), int(np.floor(y_min))
             w, h = int(np.ceil(x_min + w_val)) - x, int(np.ceil(y_min + h_val)) - y
             
             # No perspective transform needed
             M = None
             
             # Destination points are just 0..w, 0..h (implicit)
             # We need to shift polygon points for the mask
             # (Handled in mask generation below: subtract x,y)
             
        else:
             # Rotated Strategy (Original Logic)
            pts_array = np.array(points, dtype=np.float32)
             
             # 2. Minimum Bounding Rectangle (Rotated)
            rect_rotated = cv2.minAreaRect(pts_array)
            (center, (w_rot, h_rot), angle) = rect_rotated
             
            Logger.debug(f"[Main] MBR Center: {center}, Size: {w_rot:.2f}x{h_rot:.2f}, Angle: {angle:.2f}")
             
             # Check aspect ratio to ensure consistent orientation
            if w_rot < h_rot:
                w_rot, h_rot = h_rot, w_rot
                angle += 90
             
            w, h = int(w_rot), int(h_rot)
             
             # 3. Source Points (The 4 corners of the rotated rect)
            box = cv2.boxPoints(rect_rotated)
            src_pts = np.float32(box)
             
             # 4. Destination Points
             # Sort src_pts
            s = src_pts.sum(axis=1)
            diff = np.diff(src_pts, axis=1)
             
            tl = src_pts[np.argmin(s)]
            br = src_pts[np.argmax(s)]
            tr_ = src_pts[np.argmin(diff)]
            bl = src_pts[np.argmax(diff)]
             
            src_pts_ordered = np.float32([tl, tr_, br, bl])
             
             # Destination: (0,0), (w,0), (w,h), (0,h)
            dst_pts = np.float32([
                 [0, 0],
                 [w - 1, 0],
                 [w - 1, h - 1],
                 [0, h - 1]
            ])
             
             # Calculate Transform Matrix
            M = cv2.getPerspectiveTransform(src_pts_ordered, dst_pts)
            Logger.debug(f"[Main] Perspective Matrix:\n{M}")
             
        # Check bounds
        img_h, img_w = 0, 0
        for ch in self.session.channels:
            if ch.raw_data is not None:
                img_h, img_w = ch.raw_data.shape[:2]
                break
        
        if img_h > 0 and img_w > 0:
            # Clip x, y to [0, img_w/img_h]
            orig_x, orig_y = x, y
            x = max(0, min(img_w - 1, x))
            y = max(0, min(img_h - 1, y))
            # Clip w, h so x+w, y+h stay within bounds
            w = max(1, min(img_w - x, w + (orig_x - x)))
            h = max(1, min(img_h - y, h + (orig_y - y)))
            Logger.debug(f"[Main] Clipped Crop Rect: x={x}, y={y}, w={w}, h={h}")

        if w < 1 or h < 1:
            Logger.debug("[Main] Invalid crop dimensions.")
            return
            
        # Prepare Mask (for Polygons/Irregular shapes)
        mask = None
        if roi.roi_type in ['polygon', 'freehand', 'magic_wand', 'ellipse']:
            try:
                mask = np.zeros((h, w), dtype=np.uint8)
                
                if roi.roi_type == 'ellipse':
                    # Special handling for Ellipse: Use cv2.ellipse
                    center_x, center_y = (w / 2), (h / 2)
                    axes = (w // 2, h // 2)
                    # For ellipse, we fill the entire bounding box with an oval mask
                    cv2.ellipse(mask, (int(center_x), int(center_y)), axes, 0, 0, 360, 255, -1)
                    print("DEBUG: [Main] Ellipse mask generated.")
                elif M is not None:
                    # Transform original points to crop coordinates using Perspective Matrix
                    pts_reshaped = pts_array.reshape(-1, 1, 2)
                    warped_pts = cv2.perspectiveTransform(pts_reshaped, M)
                    cv2.fillPoly(mask, [np.int32(warped_pts)], 255)
                    print("DEBUG: [Main] Warped Polygon mask generated.")
                elif 'pts_array' in locals():
                    # Simple Translation (x, y are top-left of crop)
                    # Shift points by -x, -y
                    shifted_pts = pts_array - [x, y]
                    cv2.fillPoly(mask, [np.int32(shifted_pts)], 255)
                    print("DEBUG: [Main] Translated Polygon mask generated.")
                else:
                    # Fallback for ROI with path but no points array
                    print(f"WARNING: [Main] Mask requested for {roi.roi_type} but pts_array is missing.")
            except Exception as e:
                print(f"ERROR: [Main] Failed to generate mask for {roi.roi_type}: {e}")
            
        # Prepare new sample name
        current_name = self.current_scene_id
        if not current_name:
            current_name = "Sample"
            
        # Ensure export directory exists
        export_dir = self.project_model.get_export_path()
        cropped_dir = os.path.join(export_dir, "cropped")
        os.makedirs(cropped_dir, exist_ok=True)
        
        index = 1
        while True:
            new_sample_name = f"{current_name}_Cropped_{index:03d}"
            sample_dir = os.path.join(cropped_dir, new_sample_name)
            if self.project_model.get_scene(new_sample_name) is None and not os.path.exists(sample_dir):
                break
            index += 1
        sample_dir = os.path.join(cropped_dir, new_sample_name)
        os.makedirs(sample_dir, exist_ok=True)
        
        channels_data = []
        
        try:
            import tifffile
        except ImportError:
            QMessageBox.critical(self, tr("Error"), tr("tifffile library is missing. Cannot save cropped images."))
            return

        # Crop and Save each channel
        for i, ch in enumerate(self.session.channels):
            # Crop Data
            raw = ch.raw_data
            cropped = None
            
            # Helper to warp/mask a single 2D plane
            def process_plane(img_2d):
                 if M is not None:
                     res = cv2.warpPerspective(img_2d, M, (w, h))
                 else:
                     # Simple slice
                     res = img_2d[y:y+h, x:x+w]
                 
                 # Apply Mask if exists
                 if mask is not None:
                     # Bitwise AND
                     # Handle types: img might be uint16, mask is uint8
                     # cv2.bitwise_and supports mask argument
                     res = cv2.bitwise_and(res, res, mask=mask)
                 return res

            try:
                if raw.ndim == 2:
                    cropped = process_plane(raw)
                elif raw.ndim == 3:
                     # (H, W, C) usually
                     if raw.shape[2] in [3, 4]:
                         # RGB - Warp all channels at once (cv2 handles 3 channels)
                         # But process_plane logic for mask applies to all channels?
                         # cv2.warpPerspective works on 3-channel.
                         # cv2.bitwise_and works on 3-channel with single channel mask.
                         cropped = process_plane(raw)
                     else:
                         # (Z, H, W) or Multi-channel stack
                         # Iterate and process each slice
                         # Assuming first dim is Z/C
                         slices = []
                         for z in range(raw.shape[0]):
                             slices.append(process_plane(raw[z]))
                         cropped = np.array(slices)
                
                if cropped is None:
                    print(f"WARNING: [Main] Failed to crop channel {i}")
                    continue

                # Save to disk
                ch_name = ch.name if ch.name else f"Ch{i+1}"
                ch_name = "".join(c for c in ch_name if c.isalnum() or c in (' ', '_', '-')).strip()
                filename = f"{ch_name}.tif"
                save_path = os.path.join(sample_dir, filename)
                
                tifffile.imwrite(save_path, cropped)
                
                # Prepare metadata for import
                channels_data.append({
                    'path': save_path,
                    'type': ch.channel_type,
                    'color': ch.display_settings.color,
                    'display_settings': {
                        'min_val': ch.display_settings.min_val,
                        'max_val': ch.display_settings.max_val,
                        'gamma': ch.display_settings.gamma,
                        'visible': ch.display_settings.visible,
                        'opacity': ch.display_settings.opacity,
                        'enhance_percents': getattr(ch.display_settings, 'enhance_percents', {}),
                        'enhance_params': getattr(ch.display_settings, 'enhance_params', {})
                    }
                })
            except Exception as e:
                print(f"ERROR: [Main] Error processing channel {i}: {e}")
                import traceback
                traceback.print_exc()
            
        # Create new scene in ProjectModel
        if channels_data:
            final_name = self.project_model.add_imported_merge_scene(new_sample_name, channels_data)
            # Switch to new scene
            self.load_scene(final_name)
            self.lbl_status.setText(tr("Created new cropped sample: {0}").format(final_name))
        else:
             self.lbl_status.setText(tr("Crop failed: No channels processed."))

    def _burn_rois_to_array(self, array, rois):
        """Helper to draw ROIs onto a numpy array using QPainter."""
        from PySide6.QtGui import QImage, QPainter, QPen, QColor, QFont
        from PySide6.QtCore import Qt
        import numpy as np
        
        h, w = array.shape[:2]
        is_16bit = (array.dtype == np.uint16)
        
        if is_16bit:
            # QImage doesn't support 3-channel 16-bit easily for QPainter.
            # We convert to 4-channel RGBA64 (16-bit per component)
            rgba64 = np.zeros((h, w, 4), dtype=np.uint16)
            rgba64[..., :3] = array
            rgba64[..., 3] = 65535 # Alpha
            
            # Format_RGBA64 uses 8 bytes per pixel (16 bits * 4 channels)
            qimg = QImage(rgba64.data, w, h, w * 8, QImage.Format.Format_RGBA64)
            
            painter = QPainter(qimg)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            
            for roi in rois:
                color = QColor(roi.color)
                # For 16-bit, we don't need to do anything special for QColor,
                # QPainter will handle the mapping to RGBA64.
                pen = QPen(color, 2, Qt.PenStyle.SolidLine)
                painter.setPen(pen)
                
                if roi.path:
                    painter.drawPath(roi.path)
                
                if roi.label:
                    painter.setFont(QFont("Arial", 12, QFont.Weight.Bold))
                    if roi.points:
                        painter.drawText(roi.points[0], roi.label)
            
            painter.end()
            # Convert back to 3-channel uint16
            return rgba64[..., :3].copy()
        else:
            # Standard 8-bit path
            # Create QImage from array. Ensure it's contiguous.
            if not array.flags['C_CONTIGUOUS']:
                array = np.ascontiguousarray(array)
                
            qimg = QImage(array.data, w, h, w * 3, QImage.Format.Format_RGB888)
            
            painter = QPainter(qimg)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            
            for roi in rois:
                color = QColor(roi.color)
                pen = QPen(color, 2, Qt.PenStyle.SolidLine)
                painter.setPen(pen)
                
                if roi.path:
                    painter.drawPath(roi.path)
                
                if roi.label:
                    painter.setFont(QFont("Arial", 12, QFont.Weight.Bold))
                    if roi.points:
                        painter.drawText(roi.points[0], roi.label)
            
            painter.end()
            return array

    def export_images(self):
        """
        Export channel images based on global settings.
        
        Scientific Rigor Notes:
        1. Parameter Synchronization: Forces a sync of UI parameters (Min/Max/Gamma/LUT) 
        2. Full-Resolution Rendering: Unlike the display canvas which may use 
        3. ROI Burn-in: Optional burning of ROIs onto rendered images uses 
        """
        if not self.project_model.scenes:
            self.lbl_status.setText(tr("No samples in project to export."))
            QMessageBox.warning(self, tr("Export"), tr("No samples loaded in the project."))
            return

        # Get settings
        options = ExportSettingsDialog.get_current_options()
        
        # Determine Suggested Output Directory
        suggested_dir = options.get("export_path", "").strip() or self.project_model.get_export_path()
        
        # --- USER REQUEST: Always use standard dialog for safety ---
        output_dir = QFileDialog.getExistingDirectory(
            self, 
            tr("Select Export Folder"), 
            suggested_dir
        )
        
        if not output_dir:
            self.lbl_status.setText(tr("Export cancelled."))
            return
        
        # Ask user: Current sample or All samples?
        if len(self.project_model.scenes) > 1:
            reply = QMessageBox.question(
                self, tr("Export Images"), 
                tr("Export all {0} samples in the project?\n\n(Click 'No' to export only the current sample)").format(len(self.project_model.scenes)),
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel
            )
            if reply == QMessageBox.Cancel:
                return
            export_all = (reply == QMessageBox.Yes)
        else:
            export_all = False

        scenes_to_export = self.project_model.scenes if export_all else []
        if not export_all:
            if not self.current_scene_id:
                QMessageBox.warning(self, tr("Export"), tr("No current sample selected."))
                return
            current_scene = self.project_model.get_scene(self.current_scene_id)
            if current_scene:
                scenes_to_export = [current_scene]

        if not scenes_to_export:
            return

        # Progress Dialog
        from PySide6.QtWidgets import QProgressDialog
        progress = QProgressDialog(tr("Exporting images..."), tr("Cancel"), 0, len(scenes_to_export), self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.show()

        # --- USER REQUEST: Sync UI Parameters before export ---
        # This ensures that any pending changes in sliders (not yet debounced) are applied.
        if hasattr(self, 'adjustment_panel'):
            self.adjustment_panel._apply_display_settings()
        if hasattr(self, 'enhance_panel'):
            self.enhance_panel.calculate_and_apply_params()

        # --- USER REQUEST: Annotations & ROIs ---
        # The visibility of annotations is now controlled by the user in the Overlay Panel
        # and the global export setting in the dialog.
        include_ann = options.get("export_include_ann", False)
        include_scale_bar = options.get("export_include_scale_bar", True)
        export_line_scans = options.get("export_line_scans", True)

        total_exported = 0
        
        try:
            import tifffile
            from src.core.renderer import Renderer
            from PySide6.QtWidgets import QApplication

            # --- USER REQUEST: Physical Consistency (WYSIWYG) ---
            # Get screen logical DPI to pass to renderer
            # Logic: UI uses logical pixels (e.g. 2px line). 
            # 96 DPI is the standard baseline for 100% scaling.
            screen = QApplication.primaryScreen()
            screen_dpi = screen.logicalDotsPerInch() if screen else 96.0

            for i, scene_data in enumerate(scenes_to_export):
                if progress.wasCanceled():
                    break
                
                progress.setLabelText(tr("Exporting sample: {0} ({1}/{2})").format(scene_data.id, i+1, len(scenes_to_export)))
                progress.setValue(i)
                QApplication.processEvents() # Keep UI responsive

                # Get scale bar settings
                if scene_data.id == self.current_scene_id:
                    scale_bar_settings = self.session.scale_bar_settings if include_scale_bar else None
                else:
                    # For batch export, we use the current scale bar settings
                    # since pixel size might be different per scene, we should ideally
                    # use the scene's own scale bar settings if available.
                    # But for now, using the global one is common.
                    scale_bar_settings = self.session.scale_bar_settings if include_scale_bar else None

                # Get annotations for this scene (if including them)
                export_annotations = []
                if include_ann:
                    if scene_data.id == self.current_scene_id:
                        # For current scene, use the active session's ROI manager
                        # Unified Model: Filter ROIs that are visible
                        all_rois = self.session.roi_manager.get_all_rois()
                        export_annotations = []
                        for r in all_rois:
                            if not r.visible: continue
                            if not export_line_scans and r.roi_type == 'line_scan': continue
                            export_annotations.append(r)
                    else:
                        # For other scenes, we need to load their ROIs from serialized data
                        rois_data = getattr(scene_data, 'rois', [])
                        
                        try:
                            from src.core.roi_model import ROI
                            
                            for r_dict in rois_data:
                                if r_dict.get('visible', True):
                                    if not export_line_scans and r_dict.get('roi_type') == 'line_scan':
                                        continue
                                    try:
                                        # Use standard reconstruction logic
                                        r = ROI.from_dict(r_dict)
                                        export_annotations.append(r)
                                    except Exception as e:
                                        Logger.error(f"[Main.export_images] Failed to reconstruct ROI: {e}")
                                        pass
                        except ImportError:
                            pass

                # --- Scientific Rigor: Parameter Synchronization ---
                # We ensure that the Rendered export uses the EXACT same parameters (Min/Max/Gamma/LUT)
                # as currently displayed on screen. No default parameters are allowed.
                if scene_data.id == self.current_scene_id:
                    # Current scene: Use the active session (guaranteed to have latest UI parameters)
                    channels = self.session.channels
                else:
                    # Other scenes: Load them and apply their saved display settings.
                    # If settings are missing, we should ideally fallback to the current UI settings 
                    # for batch consistency, but here we prefer the scene's own saved state.
                    temp_session = Session()
                    for ch_def in scene_data.channels:
                        if not ch_def.path or not os.path.exists(ch_def.path):
                            continue
                        try:
                            from src.core.data_model import ImageChannel
                            ch = ImageChannel(ch_def.path, ch_def.color, ch_def.channel_type)
                            if ch_def.display_settings:
                                ds = ch_def.display_settings
                                ch.display_settings.min_val = ds.get("min_val", ch.display_settings.min_val)
                                ch.display_settings.max_val = ds.get("max_val", ch.display_settings.max_val)
                                ch.display_settings.gamma = ds.get("gamma", ch.display_settings.gamma)
                                ch.display_settings.visible = ds.get("visible", True)
                                ch.display_settings.color = ds.get("color", ch.display_settings.color)
                                # Also sync LUT size and enhancement params if they exist
                                if "lut_size" in ds: ch.display_settings.lut_size = ds["lut_size"]
                                if "enhance_params" in ds: ch.display_settings.enhance_params = ds["enhance_params"]
                            temp_session.add_existing_channel(ch)
                        except Exception as e:
                            print(f"Failed to load channel for export: {e}")
                    channels = temp_session.channels

                if not channels:
                    continue

                sample_name = scene_data.id
                
                # Calculate View Scale based on Display Quality Setting
                quality = self.settings.value("display/quality_key", "balanced")
                if quality == "performance":
                     max_view_dim = 1024 # 1024p
                elif quality == "balanced":
                     max_view_dim = 2560 # 2.5K
                elif quality == "4k":
                     max_view_dim = 3840 # 4K
                else: # "high" or legacy "High Quality (Full Resolution)"
                     max_view_dim = 32768 # Effectively Full Resolution (System Limit)
                
                # Determine original width from first valid channel
                orig_w = 1920 # Default fallback
                for ch in channels:
                    if not getattr(ch, 'is_placeholder', False):
                        if ch.shape and len(ch.shape) > 1:
                            orig_w = ch.shape[1]
                            break
                
                # The "View Width" is the width of the image as seen in the software's viewport (downsampled)
                view_w = min(orig_w, max_view_dim)
                view_scale = orig_w / view_w if view_w > 0 else 1.0

                # 1. Export Single Channels
                if options["export_channels"]:
                    if options["export_raw"]:
                        # Raw 16-bit Grayscale TIFF (Preserves signal integrity)
                        for ch in channels:
                            if ch.is_placeholder: continue
                            s_name = sample_name.replace(" ", "_")
                            c_name = ch.name.replace(" ", "_")
                            fname = tr("{0}_{1}_raw.tif").format(s_name, c_name)
                            save_path = os.path.join(output_dir, fname)
                            tifffile.imwrite(save_path, ch.raw_data)
                            total_exported += 1
                            
                    if options["export_rendered"]:
                        # Rendered RGB TIFF (WYSIWYG: What You See Is What You Get)
                        # We do NOT pass target_shape here to force full-resolution rendering.
                        out_depth = options.get("bit_depth", 8)
                        dpi = options.get("dpi", 600)
                        
                        for ch in channels:
                            if not ch.display_settings.visible or ch.is_placeholder:
                                continue
                                
                            rgb = Renderer.render_channel(
                                ch, 
                                out_depth=out_depth, 
                                scale_bar_settings=scale_bar_settings, 
                                annotations=export_annotations, 
                                dpi=dpi, 
                                view_scale=view_scale, 
                                screen_dpi=screen_dpi
                            )
                            if rgb is not None:
                                # Scale to requested bit depth
                                if out_depth == 16:
                                    rgb_final = (rgb * 65535).astype('uint16')
                                else:
                                    rgb_final = (rgb * 255).astype('uint8')
                                
                                # (Handled by Renderer now)
                                
                                fname = tr("{0}_{1}_rendered.tif").format(sample_name, ch.name)
                                save_path = os.path.join(output_dir, fname)
                                dpi = options.get("dpi", 600)
                                tifffile.imwrite(save_path, rgb_final, photometric='rgb', resolutionunit='inch', resolution=(dpi, dpi))
                                total_exported += 1
                
                # 2. Export Merge
                if options["export_merge"]:
                    out_depth = options.get("bit_depth", 8)
                    dpi = options.get("dpi", 600)
                    comp = Renderer.composite(
                        channels, 
                        out_depth=out_depth, 
                        scale_bar_settings=scale_bar_settings, 
                        annotations=export_annotations, 
                        dpi=dpi, 
                        view_scale=view_scale, 
                        screen_dpi=screen_dpi
                    )
                    if comp is not None:
                        # Scale to requested bit depth
                        if out_depth == 16:
                            comp_final = (comp * 65535).astype('uint16')
                        else:
                            comp_final = (comp * 255).astype('uint8')
                        
                        # (Handled by Renderer now)
                            
                        fname = tr("{0}_Merge.tif").format(sample_name)
                        save_path = os.path.join(output_dir, fname)
                        dpi = options.get("dpi", 600)
                        # Fixed resolution unit for merge export
                        tifffile.imwrite(save_path, comp_final, photometric='rgb', resolutionunit='inch', resolution=(dpi, dpi), metadata={'Spacing': 1/dpi})
                        total_exported += 1

            progress.setValue(len(scenes_to_export))
            
            if total_exported > 0:
                self.lbl_status.setText(tr("Exported {0} images.").format(total_exported))
                
                msg_box = QMessageBox(self)
                msg_box.setWindowTitle(tr("Export Successful"))
                msg_box.setText(tr("Exported {0} images to:\n{1}").format(total_exported, output_dir))
                msg_box.setIcon(QMessageBox.Icon.Information)
                
                open_btn = msg_box.addButton(tr("Open Folder"), QMessageBox.ButtonRole.ActionRole)
                msg_box.addButton(QMessageBox.StandardButton.Ok)
                
                msg_box.exec()
                
                if msg_box.clickedButton() == open_btn:
                    from PySide6.QtCore import QUrl
                    QDesktopServices.openUrl(QUrl.fromLocalFile(output_dir))
            else:
                 self.lbl_status.setText(tr("Nothing exported (check settings/visibility)."))
                 
        except Exception as e:
            self.lbl_status.setText(tr("Error exporting images: {0}").format(e))
            print(f"Export Error: {e}")
            import traceback
            traceback.print_exc()

    def open_export_settings(self):
        """Opens the global export configuration dialog (Redirected to Unified Settings)."""
        self.open_settings()

    def open_import_dialog(self):
        # Redirect to sidebar's auto-group import folder
        self.sample_list.import_folder_auto()

    def load_dummy_data(self):
        """Feature removed."""
        pass
    def open_settings(self):
        """
        打开设置对话框，并处理设置更新
        """
        # 1. 准备要传给对话框的数据
        # 这里的 'self.measurement_settings' 是假设你在 MainWindow 里保存测量设置的变量名
        # 如果你的变量名不同，请替换成你实际使用的变量名，或者直接传 None
        current_settings = getattr(self, 'measurement_settings', None)

        # 2. 实例化你写的对话框
        # 注意：这里必须传递 parent=self，否则对话框可能不显示或报错
        dialog = SettingsDialog(self, current_measurement_settings=current_settings)

        # 3. 显示对话框并等待用户操作
        # dialog.exec() 会阻塞主窗口，直到用户点击 OK 或 Cancel
        if dialog.exec():
            # --- 用户点击了 OK (Accepted) ---
            
            # 你的 save_and_accept 方法已经处理了 AutoSave 和 Export 的保存
            
            # 现在需要从对话框获取更新后的测量设置
            new_measurement_settings = dialog.get_measurement_settings()
            
            # 4. 更新 MainWindow 中的状态
            self.measurement_settings = new_measurement_settings
            
            # 5. 更新界面显示 (选项卡可见性等)
            self.update_tab_visibility()
            
            # Update View Layout (Handle "Show Merge" toggle)
            self.initialize_all_views()
            
            # 6. 刷新显示 (以应用画质等设置)
            self.refresh_display()
            
            # 可选：打印日志查看结果
            print("设置已保存，并已刷新显示。")
            
        else:
            # --- 用户点击了 Cancel (Rejected) ---
            print("用户取消了设置")

    def refresh_display(self, fit=False):
        """Triggers a re-render. If fit=True, also fits views (for new images)."""
        if not self.session.channels:
            return
        
        # Debounce: Stop previous timer if running, update pending state, and restart
        if fit:
            self._pending_fit_view = True
        
        self.refresh_debounce_timer.start() # Restart timer (50ms)
        self.lbl_status.setText(tr("Refreshing views..."))

    def _perform_refresh_display(self):
        """Performs the actual refresh after the debounce interval."""
        if not self.session.channels:
            return
        
        # Update ALL view containers to keep them in sync
        self.update_all_view_containers()
        
        if self._pending_fit_view:
            self.fit_all_views()
            self._pending_fit_view = False
        
        self.lbl_status.setText(tr("Ready"))

    def update_zoom_label(self, scale):
        """Updates the zoom label in the status bar."""
        percentage = int(scale * 100)
        self.lbl_zoom.setText(f"{percentage}%")

    def update_memory_label(self, current_mb, sys_percent, display_text):
        """Updates the RAM usage display in status bar."""
        self.lbl_memory.setText(display_text)
        
        # USER REQUEST: Smarter color coding. 
        # Don't show warning just because other apps are using RAM (sys_percent).
        # Only warn if the APP itself is high, or if SYSTEM is critical.
        
        threshold_gb = getattr(self.perf_monitor, 'memory_threshold_gb', 8.0)
        app_gb = current_mb / 1024.0
        app_percent = (app_gb / threshold_gb) * 100.0 if threshold_gb > 0 else 0
        
        if app_percent > 90 or sys_percent > 98:
            self.lbl_memory.setStyleSheet("color: #ff4d4d; font-weight: bold; margin-right: 10px;")
        elif app_percent > 70 or sys_percent > 90:
            self.lbl_memory.setStyleSheet("color: #ffa500; margin-right: 10px;")
        else:
            self.lbl_memory.setStyleSheet("color: #666; margin-right: 10px;")

    def on_memory_warning(self, current_gb):
        """Shows a temporary warning message when memory is high."""
        self.lbl_status.setText(tr(f"Memory high ({current_gb:.1f} GB), cache cleared automatically."))
        # Reset after 5 seconds
        QTimer.singleShot(5000, lambda: self.lbl_status.setText(tr("Ready")))

    def update_status_mouse_info(self, x, y, channel_index):
        """Updates status bar with coordinates and intensity values."""
        if not self.session.channels:
            return
            
        # Check bounds using the first valid channel
        ref_ch = None
        for ch in self.session.channels:
            if ch.raw_data is not None:
                ref_ch = ch
                break
        
        if not ref_ch:
            return
            
        h, w = ref_ch.shape
        if 0 <= x < w and 0 <= y < h:
            info_parts = [f"X: {x}, Y: {y}"]
            
            # Get intensity for all channels
            intensities = []
            for i, ch in enumerate(self.session.channels):
                if ch.raw_data is not None:
                    try:
                        # raw_data could be 2D (H, W)
                        val = ch.raw_data[y, x]
                        intensities.append(f"{ch.name}: {val}")
                    except:
                        pass
            
            if intensities:
                info_parts.append(" | ".join(intensities))
                
            self.lbl_status.setText(tr("  ").join(info_parts))
        else:
            self.lbl_status.setText(tr("Ready"))

    def update_tab_visibility(self):
        """Updates control panel tab visibility based on settings."""
        settings = QSettings("FluoQuantPro", "AppSettings")
        # Change 'overlay' to 'annotation' in default string to match new panel name
        visible_tabs_str = settings.value("interface/visible_tabs", "toolbox,adjustments,enhance,colocalization,annotation,results")
        visible_list = visible_tabs_str.split(",")
        
        # Remember current index to restore it if possible
        current_tab_name = None
        current_idx = self.control_tabs.currentIndex()
        if current_idx >= 0:
            # Find the key for the current widget
            current_widget = self.control_tabs.widget(current_idx)
            for key, widget, label in self.all_tabs_data:
                if widget == current_widget:
                    current_tab_name = key
                    break
        
        # Clear all tabs
        self.control_tabs.clear()
        
        # Add only visible ones
        for key, widget, label in self.all_tabs_data:
            if key in visible_list:
                self.control_tabs.add_tab(key, widget, label)
                
        # Restore index if the tab is still visible
        if current_tab_name:
            for i in range(self.control_tabs.count()):
                widget = self.control_tabs.widget(i)
                # Find which key this widget corresponds to
                for key, w, label in self.all_tabs_data:
                    if w == widget and key == current_tab_name:
                        self.control_tabs.setCurrentIndex(i)
                        break

    def set_view_tool(self, tool):
        """Sets the active tool on ALL view containers."""
        for container in self.view_containers:
            if hasattr(container, 'set_tool'):
                container.set_tool(tool)

    def set_view_annotation_mode(self, mode):
        """Sets the annotation mode on ALL view containers."""
        for container in self.view_containers:
            if hasattr(container, 'set_annotation_mode'):
                container.set_annotation_mode(mode)

    def initialize_all_views(self):
        """Initializes views on ALL view containers."""
        for container in self.view_containers:
            if hasattr(container, 'initialize_views'):
                container.initialize_views()

    def fit_all_views(self):
        """Fits views on ALL view containers."""
        for container in self.view_containers:
            if hasattr(container, 'fit_views'):
                container.fit_views()

    def update_all_view_containers(self, channel_index=None):
        """Updates views on ALL view containers."""
        for container in self.view_containers:
            if channel_index is not None:
                if hasattr(container, 'update_view'):
                    container.update_view(channel_index)
            else:
                if hasattr(container, 'render_all'):
                    container.render_all()

    def show_view_loading(self, message):
        """Shows loading overlay on the active view container."""
        container = self.get_active_view_container()
        if container and hasattr(container, 'show_loading'):
            container.show_loading(message)

    def hide_view_loading(self):
        """Hides loading overlay on the active view container."""
        container = self.get_active_view_container()
        if container and hasattr(container, 'hide_loading'):
            container.hide_loading()

    def flash_view_channel(self, index):
        """Flashes the specified channel on the active view container."""
        container = self.get_active_view_container()
        if container and hasattr(container, 'flash_channel'):
            container.flash_channel(index)

    def select_view_channel(self, index):
        """Selects the specified channel on ALL view containers."""
        for container in self.view_containers:
            if hasattr(container, 'select_channel'):
                container.select_channel(index)

    def update_all_scale_bars(self, settings):
        """Updates the scale bar on ALL view containers."""
        for container in self.view_containers:
            if hasattr(container, 'update_scale_bar'):
                container.update_scale_bar(settings)

    def select_view_annotation(self, ann_id):
        """Selects the specified annotation on ALL view containers."""
        for container in self.view_containers:
            if hasattr(container, 'select_annotation'):
                container.select_annotation(ann_id)

    def on_tool_preview_changed(self):
        """Called when a tool's preview needs updating."""
        container = self.get_active_view_container()
        if hasattr(container, 'update_all_previews'):
            container.update_all_previews()

    def on_fit_to_width(self):
        container = self.get_active_view_container()
        if hasattr(container, 'fit_to_width'):
            container.fit_to_width()

    def on_fit_to_height(self):
        container = self.get_active_view_container()
        if hasattr(container, 'fit_to_height'):
            container.fit_to_height()

    def on_fit_to_view(self):
        container = self.get_active_view_container()
        if hasattr(container, 'fit_views'):
            container.fit_views()

    def on_display_settings_changed(self):
        """Triggers a re-render without resetting view (for adjustment sliders)."""
        if not self.session.channels:
            return
            
        # UI Feedback
        self.lbl_status.setText(tr("Processing Enhancement..."))
        Logger.debug("[Main] Display settings changed -> preview render")
        QApplication.processEvents()
        
        # PERSIST SETTINGS
        for ch in self.session.channels:
            if ch.file_path:
                norm_path = os.path.normpath(ch.file_path)
                self.project_model.pool_display_settings[norm_path] = {
                    'min_val': ch.display_settings.min_val,
                    'max_val': ch.display_settings.max_val,
                    'gamma': ch.display_settings.gamma
                }
        
        # --- AUTOMATIC: Refresh Active View Container ---
        container = self.get_active_view_container()
        if hasattr(container, 'render_all'):
            container.render_all(preview=True)

        try:
            active_idx = getattr(self, 'active_channel_idx', -1)
            if hasattr(container, 'flash_channel'):
                container.flash_channel(active_idx)
        except Exception as e:
            Logger.debug(f"[Main] flash_channel skipped: {e}")
        
        self.lbl_status.setText(tr("Enhancement Applied."))

    def measure_all_rois(self):
        """Iterate all ROIs and populate the result tree."""
        print("DEBUG: measure_all_rois triggered")
        
        # Check Channels
        if not self.session.channels:
             QMessageBox.warning(self, tr("Measure"), tr("No images loaded. Please load an image first."))
             return

        # Check ROIs (Pre-check)
        rois = self.session.roi_manager.get_all_rois()
        if not rois:
            self.lbl_status.setText(tr("No ROIs to measure."))
            QMessageBox.information(self, tr("Info"), tr("No ROIs defined. Please draw an ROI first."))
            return

        try:
            from src.core.analysis import MeasureEngine
            print("DEBUG: MeasureEngine imported")
        except ImportError as e:
            QMessageBox.critical(self, tr("Error"), tr("Failed to import Analysis Engine. Missing dependencies?\n{0}").format(e))
            return

        try:
            engine = MeasureEngine()
            
            # --- UPSERT MODE: Update existing, Append new, Keep history ---
            # 1. Identify which ROIs we are about to measure
            current_roi_ids = set(r.id for r in rois)
            
            # 2. Remove any OLD results for these specific ROIs (to prevent duplicates)
            # This allows "Refresh" behavior for the active ROIs, but preserves
            # history for ROIs that were deleted from the canvas.
            accumulate = self.measurement_settings.get('Accumulate', True)
            if not accumulate:
                self.result_widget.remove_results_for_rois(current_roi_ids)
            
            # 2.1 Remove any OLD virtual overlap results to avoid duplicates
            if not accumulate:
                existing_ids = self.result_widget.tree.get_existing_roi_ids()
                virtual_ids = [rid for rid in existing_ids if str(rid).startswith("virtual_overlap_")]
                if virtual_ids:
                     print(f"DEBUG: [Main] Removing {len(virtual_ids)} old virtual overlap results")
                     self.result_widget.remove_results_for_rois(virtual_ids)
            
            if not rois:
                self.lbl_status.setText(tr("No ROIs selected to measure."))
                return

            # Get Sample Name (or current scene ID)
            sample_name = tr("Current Scene")
            # Try to find current item in sample list
            if hasattr(self.sample_list, 'tree_widget'):
                # We want the name of the current scene (parent of the selected channel or the scene itself)
                # But actually, measure_all_rois is usually run on the CURRENTLY LOADED scene
                if self.current_scene_id:
                    # Get display name from ProjectModel
                    scene = self.project_model.get_scene(self.current_scene_id)
                    if scene:
                        sample_name = scene.name
                    else:
                        sample_name = self.current_scene_id
            elif self.current_scene_id:
                sample_name = self.current_scene_id
            
            # Prepare Data List for ALL selected items
            roi_data_list = []
            count_summary = {} # {channel_name: count}
            
            # --- STRICT MEASUREMENT SCOPE CONTROL ---
            # Filter ROIs to exclude Line Scans and Annotations
            measurable_rois = []
            for roi in rois:
                # 1. Exclude Line Scans
                if roi.roi_type == 'line_scan':
                    continue
                
                # 2. Exclude Annotations (if any crept into ROI manager, though unlikely)
                if roi.roi_type == 'annotation':
                    continue
                    
                measurable_rois.append(roi)
                
                # Special handling for Point ROIs: Add to count summary
                if roi.label.startswith("Point_"):
                    # Extract channel name: Point_{ChannelName}_{Index}
                    name_part = roi.label[6:]
                    if "_" in name_part:
                        ch_name = name_part.rsplit("_", 1)[0]
                        count_summary[ch_name] = count_summary.get(ch_name, 0) + 1
                    else:
                        count_summary[tr("Unknown")] = count_summary.get(tr("Unknown"), 0) + 1

            if not measurable_rois:
                self.lbl_status.setText(tr("No measurable ROIs found (Line Scans excluded)."))
                return

            # Batch Measure using Encapsulated Engine
            roi_data_list = engine.measure_batch(
                measurable_rois, 
                self.session.channels, 
                bg_method='local_ring'
            )
                
            # Update Result Widget
            self.result_widget.add_sample_results(sample_name, roi_data_list, self.measurement_settings, count_summary=count_summary)
            if not self.measurement_settings.get('Accumulate', True):
                self.result_widget.clear_overlap_groups(sample_name)
                Logger.debug(f"[Main] Overlap groups cleared: sample={sample_name}")
            
            # --- AUTOMATIC OVERLAP ANALYSIS (All ROIs) ---
            if len(measurable_rois) >= 2:
                print(f"DEBUG: [Main] Calculating overlap for {len(measurable_rois)} ROIs")
                
                # 1. Prepare data
                rois_data = []
                for r in measurable_rois:
                    rois_data.append({
                        'path': r.path,
                        'label': r.label,
                        'area': r.stats.get('Area', 0),
                        'id': r.id
                    })
                
                try:
                    channels = self.session.channels
                    pixel_size = self.session.scale_bar_settings.pixel_size
                    
                    # 2. Calculate Common Intersection (Multi-Overlap)
                    result = ROIOverlapAnalyzer.calculate_multi_overlap(rois_data, channels, pixel_size)
                    
                    if result and result.get('overlap_area', 0) > 0:
                        display_data = {
                            'Label': result['label'],
                            'Area': result['union_area'],
                            'Intersection_Area': result['overlap_area'],
                            'Non_Common_Area': result.get('non_overlap_area', 0)
                        }
                        
                        # Add stats
                        def map_stats(stats_dict, region_name):
                            if not stats_dict: return
                            for key, val in stats_dict.items():
                                if key in ['Area', 'PixelCount']: continue
                                if '_' in key:
                                    ch_name, metric = key.rsplit('_', 1)
                                    new_key = f"{region_name} ({ch_name})_{metric}"
                                    display_data[new_key] = val
                        
                        map_stats(result.get('intersection_stats'), 'Intersection')
                        for r in measurable_rois:
                            self.result_widget.add_overlap_entry(sample_name, r.id, "overlap_all", display_data)
                        Logger.debug(f"[Main] Multi-overlap added: sample={sample_name} rois={len(measurable_rois)}")
                        
                    # 3. Calculate Pairwise Overlaps (Matrix approach)
                    # We can iterate all pairs and add significant overlaps
                    # To avoid clutter, maybe only add pairs with IoU > 0.01
                    for i in range(len(measurable_rois)):
                        for j in range(i + 1, len(measurable_rois)):
                            roi1 = measurable_rois[i]
                            roi2 = measurable_rois[j]
                            
                            # Quick bbox check
                            if not roi1.path.boundingRect().intersects(roi2.path.boundingRect()):
                                continue

                            self._run_overlap_analysis(sample_name, roi1, roi2)
                            
                except Exception as e:
                    print(f"Error in automatic overlap analysis: {e}")
                    import traceback
                    traceback.print_exc()
            
            # Switch to Results Tab
            self.control_tabs.setCurrentWidget(self.result_widget)
                
            self.lbl_status.setText(tr("Measured {0} ROIs. Overlap analysis complete.").format(len(rois)))
            
        except Exception as e:
            print(f"DEBUG: Exception in measurement: {e}")
            self.lbl_status.setText(tr("Measurement Error: {0}").format(e))
            QMessageBox.critical(self, tr("Measurement Error"), tr("An error occurred during measurement:\n{0}").format(e))
            import traceback
            traceback.print_exc()

    def open_measure_settings(self):
        """Opens the measurement settings dialog."""
        dialog = MeasurementSettingsDialog(self, self.measurement_settings)
        if dialog.exec():
            self.measurement_settings = dialog.get_settings()
            # Update result widget visibility
            self.result_widget.update_settings(self.measurement_settings)
            self.lbl_status.setText(tr("Measurement settings updated."))
            
    def export_results(self):
        """Save current measurements to CSV."""
        # Retrieve data directly from the widget (source of truth)
        current_data = self.result_widget.get_all_data()
        
        if not current_data:
            self.lbl_status.setText(tr("No measurements to export. Run Measure first."))
            return
            
        default_path = os.path.join(self.project_model.get_export_path(), "results.csv")
        file_path, _ = QFileDialog.getSaveFileName(
            self, 
            tr("Save Results"), 
            default_path, 
            tr("CSV Files (*.csv);;All Files (*)")
        )
        
        if not file_path:
            return
            
        target_path = Path(file_path)
        
        # Double check parent directory exists
        if not target_path.parent.exists():
            QMessageBox.warning(self, tr("Path Error"), tr("Target directory does not exist!"))
            return

        try:
            # Determine all unique fieldnames across all records
            all_keys = set()
            for data in current_data:
                all_keys.update(data.keys())
            
            # Sort fieldnames for consistent column order
            # Desired order: Sample, ROI_Label, Channel, Area, Count, then others
            base_order = ['Sample', 'ROI_Label', 'Channel', 'Area', 'Count']
            fieldnames = [k for k in base_order if k in all_keys]
            fieldnames += sorted([k for k in all_keys if k not in base_order])
            
            with target_path.open('w', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                
                writer.writeheader()
                for data in current_data:
                    writer.writerow(data)
                    
            self.lbl_status.setText(tr("Results saved to {0}").format(file_path))
            
            # --- USER REQUEST: Add Open Folder button to CSV export success ---
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle(tr("Export Successful"))
            msg_box.setText(tr("Measurements exported to:\n{0}").format(file_path))
            msg_box.setIcon(QMessageBox.Icon.Information)
            
            open_btn = msg_box.addButton(tr("Open Folder"), QMessageBox.ButtonRole.ActionRole)
            msg_box.addButton(QMessageBox.StandardButton.Ok)
            
            msg_box.exec()
            
            if msg_box.clickedButton() == open_btn:
                from PySide6.QtCore import QUrl
                export_dir = os.path.dirname(file_path)
                QDesktopServices.openUrl(QUrl.fromLocalFile(export_dir))
        except Exception as e:
            self.lbl_status.setText(tr("Error saving CSV: {0}").format(e))
            print(f"Export Error: {e}")

    def auto_save_project(self):
        """Automatically saves the project if a path is set."""
        if not self.project_model.root_path:
            return
            
        if not self.project_model.is_dirty:
            return
            
        try:
            success = self.save_project(manual=False)
            if success:
                self.lbl_status.setText(tr("Auto-Saved Project to {0}").format(self.project_model.root_path))
        except Exception as e:
            print(f"Auto-save failed: {e}")

    def open_manual(self):
        """Opens the user manual (manual.html) in the default web browser."""
        manual_path = get_resource_path("manual.html")
        if os.path.exists(manual_path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(manual_path))
        else:
            # Fallback to local dir if not in resources (for dev)
            local_manual = os.path.join(os.path.dirname(os.path.abspath(__file__)), "manual.html")
            if os.path.exists(local_manual):
                QDesktopServices.openUrl(QUrl.fromLocalFile(local_manual))
            else:
                QMessageBox.warning(self, tr("Manual Not Found"), tr("Could not find manual at {0}").format(manual_path))

    def show_about(self):
        """Shows the About dialog."""
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.about(self, tr("About FluoQuant Pro"), 
            tr("<h3>FluoQuant Pro</h3>"
            "<p>A professional tool for fluorescence image analysis and point counting.</p>"
            "<p>TongJi University XueLab</p>"
            "<p>Version: 1.1.0</p>"
            "<p>Developed By PK</p>"))

    def show_shortcuts(self):
        """Shows the Keyboard Shortcuts dialog."""
        from PySide6.QtWidgets import QMessageBox
        shortcuts = tr(
            "<b>General:</b><br>"
            "Ctrl+N: New Project<br>"
            "Ctrl+O: Open Project<br>"
            "Ctrl+S: Save Project<br>"
            "Ctrl+,: Settings<br>"
            "Alt+F4: Exit<br><br>"
            "<b>Tools:</b><br>"
            "W: Magic Wand<br>"
            "P: Polygon Lasso<br>"
            "R: Rectangle<br>"
            "E: Ellipse<br>"
            "C: Point Counter<br>"
            "H: Hand (Pan)<br>"
            "Ctrl+Z: Undo<br>"
            "Ctrl+Y: Redo<br>"
            "Ctrl+Del: Clear ROIs<br> "
            "Ctrl+X: Crop to Selection<br><br>"
            "<b>Analysis:</b><br>"
            "Ctrl+M: Measure (Intensity & Overlap)<br>"
            "Ctrl+E: Export Results<br><br>"
            "<b>View:</b><br>"
            "Ctrl+B: Toggle Sidebar<br>"
            "F12: Toggle Controls<br>"
            "Ctrl+T: Switch Theme<br>"
            "F1: User Manual<br>"
            "Ctrl+F1: Keyboard Shortcuts"
        )
        QMessageBox.information(self, tr("Keyboard Shortcuts"), shortcuts)

    def restore_ui_state(self):
        """Restores window geometry, dock positions, and splitter states."""
        settings = QSettings("FluoQuantPro", "Window")
        
        # Restore Geometry (Size & Position)
        geometry = settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)
            
        # Restore State (Docks & Toolbars)
        state = settings.value("windowState")
        if state:
            self.restoreState(state)
            
        # Restore SampleList Splitter
        if hasattr(self, 'sample_list') and hasattr(self.sample_list, 'splitter'):
             splitter_state = settings.value("sampleListSplitter")
             if splitter_state:
                 self.sample_list.splitter.restoreState(splitter_state)

    def export_overlap_report(self):
        """Exports ROI overlap analysis report (Matrix & Details)."""
        import json
        
        # 1. Gather ROIs
        rois = self.session.roi_manager.get_all_rois()
        measurable_rois = [r for r in rois if r.roi_type not in ['line_scan', 'annotation']]
        
        if len(measurable_rois) < 2:
            QMessageBox.warning(self, tr("Export Overlap"), tr("Need at least 2 ROIs for overlap analysis."))
            return
            
        # 2. Prepare Data
        rois_data = []
        for r in measurable_rois:
            rois_data.append({
                'id': r.id,
                'label': r.label,
                'path': r.path,
                'area': r.stats.get('Area', 0)
            })
            
        # 3. Calculate Matrix
        try:
            labels, iou_matrix, ratio_matrix = ROIOverlapAnalyzer.calculate_overlap_matrix(rois_data)
        except Exception as e:
            QMessageBox.critical(self, tr("Error"), tr("Failed to calculate overlap matrix:\n{0}").format(e))
            return
            
        # 4. Save Dialog
        default_path = os.path.join(self.project_model.get_export_path(), "overlap_report.json")
        file_path, filter_str = QFileDialog.getSaveFileName(
            self, 
            tr("Save Overlap Report"), 
            default_path, 
            tr("JSON Report (*.json);;CSV Matrix (*.csv)")
        )
        
        if not file_path:
            return
            
        target_path = Path(file_path)
        
        # Double check parent directory exists
        if not target_path.parent.exists():
            QMessageBox.warning(self, tr("Path Error"), tr("Target directory does not exist!"))
            return

        try:
            if file_path.endswith(".json"):
                # Structured JSON Report
                report = {
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "sample": self.current_scene_id or "Unknown",
                    "rois": [r['label'] for r in rois_data],
                    "matrix_iou": iou_matrix.tolist(),
                    "matrix_overlap_ratio": ratio_matrix.tolist(),
                    "details": []
                }
                
                # Add pairwise details (optional, but good for "structured report")
                # For now, just matrix is the main requirement.
                
                with target_path.open('w', encoding='utf-8') as f:
                    json.dump(report, f, indent=4)
                    
            else:
                # CSV Matrix (IoU by default, or ask?)
                # We'll save IoU matrix
                import csv
                with target_path.open('w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    # Header
                    writer.writerow(["ROI"] + labels)
                    for i, label in enumerate(labels):
                        row = [label] + [f"{val:.4f}" for val in iou_matrix[i]]
                        writer.writerow(row)
                        
                # Optionally save Ratio matrix to a separate file?
                # For simplicity, just IoU matrix in CSV.
                
            self.lbl_status.setText(tr("Overlap report saved to {0}").format(file_path))
            
        except Exception as e:
            QMessageBox.critical(self, tr("Export Error"), tr("Failed to save report:\n{0}").format(e))

def main():
    # Enable High DPI scaling and pixmaps for Qt6 (mostly default, but explicit is better)
    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"
    os.environ["QT_USE_HIGHDPI_PIXMAPS"] = "1"
    
    # Set rounding policy for fractional scaling BEFORE creating QApplication
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    
    app = QApplication(sys.argv)
    
    # 进度反馈逻辑
    update_splash(tr("Initializing Core Modules..."), 10)
    
    # Initialize Icon Manager
    IconManager.init(get_resource_path("resources"))
    
    # Set Application Icon
    app.setWindowIcon(get_icon("icon", "applications-science"))
    
    window = MainWindow()
    
    # Check for command line arguments (Project Path)
    if len(sys.argv) > 1:
        project_path = sys.argv[1]
        if os.path.isdir(project_path):
            # Use QTimer to load after UI init
            QTimer.singleShot(100, lambda: window.load_project(project_path))
            
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    multiprocessing.freeze_support() # 必须调用，防止 PyInstaller 打包后的进程递归
    main()
