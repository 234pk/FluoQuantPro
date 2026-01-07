import sys
import time
import ctypes
import multiprocessing
import matplotlib
matplotlib.use('QtAgg') # 显式设置后端，避免 macOS 上尝试使用 TkAgg 导致挂起
import numpy as np
from PySide6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QWidget, 
                               QHBoxLayout, QLabel, QFileDialog, QDockWidget, QMenu, QMessageBox, QScrollArea, QFrame, QToolButton, QSizePolicy)
from PySide6.QtGui import QAction, QDesktopServices, QColor
from PySide6.QtCore import Qt, QTimer, QUrl, QSettings, QSize
import csv
import cv2
from src.core.logger import Logger  # Import Logger
from src.core.data_model import Session, ImageChannel, GraphicAnnotation
from src.core.enums import DrawingMode
from src.core.renderer import Renderer
from src.gui.multi_view import MultiViewWidget
from src.gui.tools import MagicWandTool, PolygonSelectionTool, CropTool, RectangleSelectionTool, EllipseSelectionTool, PointCounterTool, LineScanTool, TextTool, BatchSelectionTool
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
except Exception:
    ColocalizationPanel = None
from src.gui.adjustment_panel import AdjustmentPanel
from src.gui.annotation_panel import AnnotationPanel
from src.gui.measurement_dialog import MeasurementSettingsDialog
from src.gui.calibration_dialog import CalibrationDialog
from src.gui.export_settings_dialog import ExportSettingsDialog
from src.gui.auto_save_dialog import AutoSaveSettingsDialog
from src.gui.settings_dialog import SettingsDialog
import tifffile
import os

from src.gui.icon_manager import IconManager, get_icon
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
        return os.path.join(sys._MEIPASS, relative_path)
    
    # 2. 对于 macOS Bundle 结构，资源可能在 ../Resources (如果是从 MacOS 目录运行)
    exe_dir = os.path.dirname(sys.executable)
    macos_bundle_res = os.path.join(exe_dir, "..", "Resources", relative_path)
    if os.path.exists(macos_bundle_res):
        return os.path.normpath(macos_bundle_res)
        
    # 3. 默认回退到开发环境路径
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), relative_path)

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
        print(f"[{time.strftime('%H:%M:%S')}] Worker: Started")
        for i, ch_def in enumerate(self.channel_defs):
            if not self._is_running: return
            
            data = None
            if ch_def.path and os.path.exists(ch_def.path):
                try:
                    print(f"[{time.strftime('%H:%M:%S')}] Worker: Reading {os.path.basename(ch_def.path)}...")
                    try:
                        data = tifffile.imread(ch_def.path)
                    except Exception:
                        # Fallback to OpenCV for non-TIFF formats
                        import cv2
                        # data = cv2.imread(ch_def.path, cv2.IMREAD_UNCHANGED)
                        # Fix for Unicode paths:
                        data_stream = np.fromfile(ch_def.path, dtype=np.uint8)
                        data = cv2.imdecode(data_stream, cv2.IMREAD_UNCHANGED)
                        if data is not None:
                            if data.ndim == 3 and data.shape[2] == 3:
                                data = cv2.cvtColor(data, cv2.COLOR_BGR2RGB)
                            elif data.ndim == 3 and data.shape[2] == 4:
                                data = cv2.cvtColor(data, cv2.COLOR_BGRA2RGBA)
                    
                    # Offload preprocessing (e.g. Max Projection) to thread
                    if data is not None:
                        data = self.preprocess_data(data)
                        
                except Exception as e:
                    print(f"Error loading {ch_def.path}: {e}")
            
            if not self._is_running: return
            
            # Create ImageChannel object in worker thread (performs stats calculation)
            try:
                    print(f"[{time.strftime('%H:%M:%S')}] Worker: Creating ImageChannel {i}...")
                    # Note: ImageChannel is a data class, safe to create here if no Qt parents involved
                    ch_obj = ImageChannel(ch_def.path, ch_def.color, ch_def.channel_type, data=data, auto_contrast=False)
                    print(f"[{time.strftime('%H:%M:%S')}] Worker: Emitting channel_loaded {i}")
                    self.channel_loaded.emit(self.scene_id, i, ch_obj, ch_def)
            except Exception as e:
                print(f"Error creating ImageChannel in worker: {e}")
                # Fallback to passing data if object creation fails (should not happen)
                self.channel_loaded.emit(self.scene_id, i, data, ch_def)

        print(f"[{time.strftime('%H:%M:%S')}] Worker: Finished")
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
        
        self.setWindowTitle("FluoQuant Pro")
        self.setWindowIcon(get_icon("wand")) # Using wand as app icon
        self.resize(1600, 900)
        
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

        # Auto-Save Setup
        self.settings = QSettings("FluoQuantPro", "AppSettings")
        self._last_titlebar_style = None
        self.auto_save_timer = QTimer(self)
        self.auto_save_timer.timeout.connect(self.auto_save_project)
        self.setup_auto_save()
        
        # OpenCL Initialization
        self.init_opencl()
        
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
            'CorrectedMean': False
        }
        
        # UI Setup
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)
        self.layout.setContentsMargins(0, 0, 0, 0)
        # Main Layout - Central Widget (Canvas Only)
        # Left: MultiView (Canvas)
        self.multi_view = MultiViewWidget(self.session)
        self.layout.addWidget(self.multi_view)
        
        # Connect Empty State signals
        self.multi_view.new_project_requested.connect(self.new_project)
        self.multi_view.open_project_requested.connect(self.open_project)
        self.multi_view.open_recent_requested.connect(self.load_project) # Connect recent project signal
        self.multi_view.import_folder_requested.connect(self.import_folder_auto)
        self.multi_view.import_merge_requested.connect(self.on_import_merge)
        
        # --- Sidebar: Sample List ---
        self.sample_dock = QDockWidget("Project Samples", self)
        self.sample_dock.setObjectName("SampleDock") # Important for state saving
        self.sample_dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        self.sample_dock.setMinimumWidth(250)
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
        
        # --- Right Sidebar: Tabbed Control Panel ---
        self.right_dock = QDockWidget("Controls", self)
        self.right_dock.setObjectName("ControlDock")
        self.right_dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        self.right_dock.setMinimumWidth(0) # Allow free resizing (User request)
        # Ensure resizing features are enabled
        self.right_dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable | 
                                    QDockWidget.DockWidgetFeature.DockWidgetFloatable | 
                                    QDockWidget.DockWidgetFeature.DockWidgetClosable)
        
        # Tabs
        from PySide6.QtWidgets import QTabWidget, QStyle
        self.control_tabs = QTabWidget()
        # USER REQUEST: Use Corner Widgets for Tab Navigation (Previous/Next)
        self.control_tabs.setUsesScrollButtons(True) # Enable scrolling for shrinking
        Logger.debug("[Main] Control Tabs configured to allow scrolling (shrinkable)")

        # Create Navigation Buttons
        self.btn_tab_prev = QToolButton(self.control_tabs)
        self.btn_tab_prev.setObjectName("nav_btn")
        # Use Standard Icon to ensure visibility (Red Circle fix)
        self.btn_tab_prev.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowLeft)) 
        self.btn_tab_prev.setToolTip(tr("Previous Tab"))
        self.btn_tab_prev.setIconSize(QSize(12, 12)) 
        self.btn_tab_prev.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_tab_prev.clicked.connect(self._on_prev_tab_clicked)

        self.btn_tab_next = QToolButton(self.control_tabs)
        self.btn_tab_next.setObjectName("nav_btn")
        # Use Standard Icon for consistency
        self.btn_tab_next.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowRight))
        self.btn_tab_next.setToolTip(tr("Next Tab"))
        self.btn_tab_next.setIconSize(QSize(12, 12)) 
        self.btn_tab_next.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_tab_next.clicked.connect(self._on_next_tab_clicked)

        # Set as Corner Widgets
        self.control_tabs.setCornerWidget(self.btn_tab_prev, Qt.Corner.TopLeftCorner)
        self.control_tabs.setCornerWidget(self.btn_tab_next, Qt.Corner.TopRightCorner)

        self.right_dock.setWidget(self.control_tabs)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.right_dock)
        
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
        self.annotation_panel.annotation_updated.connect(self.on_annotation_updated)
        
        # Menu Bar
        self.create_actions()
        
        # Inject action into colocalization panel after actions are created
        if self.colocalization_panel:
            self.colocalization_panel.set_line_scan_action(self.action_line_scan)
        
        # Now create the toolbox widget since actions exist
        self.roi_toolbox = RoiToolbox(self)
        
        # Connect MultiView signals
        self.multi_view.connect_signals(self)
        
        # Connect session signals (Combined)
        manager = self.session.roi_manager
        
        # Cleanup any existing connections to these slots to prevent duplicates
        try:
            manager.roi_added.disconnect(self.on_roi_added)
            manager.roi_removed.disconnect(self.on_roi_removed)
            manager.roi_updated.disconnect(self.on_roi_updated)
            manager.selection_changed.disconnect(self.on_roi_selection_changed)
        except:
            pass # Not connected yet
            
        manager.roi_added.connect(self.on_roi_added)
        manager.roi_removed.connect(self.on_roi_removed)
        manager.roi_updated.connect(self.on_roi_updated)
        manager.selection_changed.connect(self.on_roi_selection_changed)
        
        # Connect toolbox to manager signals
        if hasattr(self, 'roi_toolbox'):
            try:
                manager.roi_added.disconnect(self.roi_toolbox.update_counts_summary)
                manager.roi_removed.disconnect(self.roi_toolbox.update_counts_summary)
                manager.roi_updated.disconnect(self.roi_toolbox.update_counts_summary)
            except:
                pass
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
        self.statusBar().addWidget(self.lbl_status)
        
        # Connect Adjustment Panel -> MultiView selection sync
        # Use channel_activated which is defined in AdjustmentPanel
        if hasattr(self.adjustment_panel, 'channel_activated'):
            self.adjustment_panel.channel_activated.connect(self.multi_view.select_channel)
        else:
            print("WARNING: AdjustmentPanel has no 'channel_activated' signal")

        # Connect Channel Selection
        self.multi_view.channel_selected.connect(self.on_channel_selected)
        self.multi_view.channel_selected.connect(self.adjustment_panel.set_active_channel)
        self.multi_view.channel_selected.connect(self.enhance_panel.set_active_channel)
        
        self.multi_view.channel_file_dropped.connect(self.handle_channel_file_drop)
        self.multi_view.mouse_moved_on_view.connect(self.update_status_mouse_info)
        self.multi_view.annotation_created.connect(self.on_annotation_created)
        self.multi_view.annotation_modified.connect(self.on_annotation_modified)
        self.multi_view.tool_cancelled.connect(self.on_tool_cancelled)
        
        # Connect Empty State Import Action
        if hasattr(self.multi_view, 'import_requested'):
            self.multi_view.import_requested.connect(lambda: self.sample_list.load_images_to_pool())
        
        # Connect Enhance Panel -> MultiView selection sync
        self.enhance_panel.channel_activated.connect(self.multi_view.select_channel)
        
        # Tools
        self.wand_tool = MagicWandTool(self.session)
        self.wand_tool.preview_changed.connect(self.multi_view.update_all_previews)
        self.wand_tool.tolerance_changed.connect(self.handle_wand_tolerance_changed)
        self.wand_tool.committed.connect(lambda msg: self.lbl_status.setText(msg))
        
        self.polygon_tool = PolygonSelectionTool(self.session)
        self.polygon_tool.preview_changed.connect(self.multi_view.update_all_previews)
        self.polygon_tool.committed.connect(lambda msg: self.lbl_status.setText(msg))
        
        self.rect_tool = RectangleSelectionTool(self.session)
        self.rect_tool.preview_changed.connect(self.multi_view.update_all_previews)
        self.rect_tool.committed.connect(lambda msg: self.lbl_status.setText(msg))
        
        self.ellipse_tool = EllipseSelectionTool(self.session)
        self.ellipse_tool.preview_changed.connect(self.multi_view.update_all_previews)
        self.ellipse_tool.committed.connect(lambda msg: self.lbl_status.setText(msg))
        
        self.count_tool = PointCounterTool(self.session)
        self.count_tool.preview_changed.connect(self.multi_view.update_all_previews)
        self.count_tool.committed.connect(lambda msg: self.lbl_status.setText(msg))
        
        self.line_scan_tool = LineScanTool(self.session)
        self.line_scan_tool.preview_changed.connect(self.multi_view.update_all_previews)
        if self.colocalization_panel:
            self.line_scan_tool.line_updated.connect(self.colocalization_panel.on_line_updated)
        self.line_scan_tool.committed.connect(lambda msg: self.lbl_status.setText(msg))
        
        self.crop_tool = CropTool(self.session)
        
        self.text_tool = TextTool(self.session)
        self.text_tool.preview_changed.connect(self.multi_view.update_all_previews)
        self.text_tool.committed.connect(lambda msg: self.lbl_status.setText(msg))
        self.text_tool.committed.connect(lambda: self.annotation_panel.update_annotation_list())
        self.text_tool.committed.connect(lambda: self.multi_view.set_annotations(self.session.annotations))

        self.batch_tool = BatchSelectionTool(self.session)
        self.batch_tool.preview_changed.connect(self.multi_view.update_all_previews)
        self.batch_tool.selection_made.connect(self.on_batch_selection_made)

        # Apply Modern Interactivity Stylesheet
        self.apply_stylesheet()
        
        # Connect Language Change
        LanguageManager.instance().language_changed.connect(self.retranslate_ui)
        
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
        self.setWindowTitle(tr("FluoQuant Pro"))
        
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
        visible_tabs_str = settings.value("interface/visible_tabs", "toolbox,adjustments,enhance,colocalization,annotation,results")
        visible_tabs_list = visible_tabs_str.split(',')
        
        # Handle backward compatibility
        if "overlay" in visible_tabs_list and "annotation" not in visible_tabs_list:
            visible_tabs_list.append("annotation")
        
        # Clear all tabs
        self.control_tabs.clear()
        
        # Add only visible ones
        for tab_id, widget, label in self.all_tabs_data:
            if tab_id in visible_tabs_list:
                self.control_tabs.addTab(widget, label)

    def on_annotation_tool_selected(self, mode):
        """Handles graphic annotation tool selection."""
        print(f"\n\nDEBUG: [Main] on_annotation_tool_selected called with mode: {mode} (FORCE LOG)\n")
        
        # 1. 检查是否正在进行 ROI 工具切换（状态锁）
        if getattr(self, '_is_switching_roi_tool', False) and mode == 'none':
            print("DEBUG: [Main] Ignoring annotation reset because we are currently switching ROI tools.")
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
                    print(f"DEBUG: [Main] Ignoring annotation reset because an ROI tool is checked.")
                    return

                # --- 优化：不再武断地切回手型工具 ---
                # 即使没有 ROI 工具，我们也只是清理当前视图的工具状态，而不是强制选中 action_pan
                # 这样可以避免信号回环导致的“抢夺焦点”问题
                print("DEBUG: [Main] Mode is none, clearing view tools (NOT forcing Pan)")
                self.multi_view.set_tool(None)
                return

            # Map annotation mode to ROI tools (The "Nuclear Option")
            tool_to_use = None
            
            if mode == 'rect':
                tool_to_use = self.rect_tool
            elif mode == 'ellipse' or mode == 'circle':
                 tool_to_use = self.ellipse_tool
            elif mode == 'polygon':
                 tool_to_use = self.polygon_tool
            elif mode == 'arrow' or mode == 'line':
                 # Use LineScanTool for lines and arrows
                 if hasattr(self, 'line_scan_tool'):
                     tool_to_use = self.line_scan_tool
                 else:
                     print("ERROR: [Main] line_scan_tool not found!")
            elif mode == 'text':
                 # Fallback to TextTool for text (no ROI equivalent)
                 tool_to_use = self.text_tool
            
            elif mode == 'batch_select':
                 # Use BatchSelectionTool
                 if hasattr(self, 'batch_tool'):
                     tool_to_use = self.batch_tool
                 
            if tool_to_use:
                print(f"DEBUG: [Main] Activating tool: {tool_to_use}")
                # Set the pending mode so on_roi_added knows to convert it
                self.pending_annotation_mode = mode
                
                # Force tool setting
                self.multi_view.set_tool(tool_to_use)
                
                # Check if tool was actually set in views
                # We can't easily check all views here, but we trust set_tool
                
                # Uncheck main toolbar tools to reflect state
                if self.tools_action_group.checkedAction():
                    self.tools_action_group.setExclusive(False)
                    self.tools_action_group.checkedAction().setChecked(False)
                    self.tools_action_group.setExclusive(True)
                    
                self.lbl_status.setText(tr("Annotation Mode: {0}").format(mode.capitalize()))
            else:
                print(f"DEBUG: [Main] No tool found for mode: {mode}")
        except Exception as e:
            print(f"ERROR: [Main] Exception in on_annotation_tool_selected: {e}")
            import traceback
            traceback.print_exc()
        
    def on_annotation_created(self, ann):
        """Handles new graphic annotation creation."""
        self.session.annotations.append(ann)
        self.annotation_panel.update_annotation_list()
        self.multi_view.set_annotations(self.session.annotations)
        print(f"DEBUG: Annotation created and added to session: {ann.type}")
        
    def on_annotation_updated(self):
        """Handles updates to existing annotations."""
        self.multi_view.set_annotations(self.session.annotations)

    def on_overlay_settings_changed(self):
        """Handles changes to scale bar or global annotation settings."""
        self.multi_view.update_scale_bar(self.session.scale_bar_settings)
        # Update annotations too, in case visibility was toggled
        self.multi_view.set_annotations(self.session.annotations)
        
        # Sync properties to TextTool
        if hasattr(self, 'text_tool') and hasattr(self, 'annotation_panel'):
            props = self.annotation_panel.get_current_properties()
            self.text_tool.color = props.get('color', '#FFFF00')
            self.text_tool.font_size = props.get('arrow_head_size', 12)

    def on_roi_added(self, roi):
        """Sync ROI to annotations if enabled OR convert to annotation if in annotation mode."""
        print(f"CRITICAL_DEBUG: Entering Main.on_roi_added for ROI {roi.id}")
        import sys
        sys.stdout.flush()
        from src.core.logger import Logger
        Logger.debug(f"[Main.on_roi_added] ENTER - ROI: {roi.label} ({roi.id})")
        
        try:
            # 1. Check if we are in "Annotation Mode" (Hijacking ROI tools)
            if getattr(self, 'pending_annotation_mode', None):
                mode = self.pending_annotation_mode
                print(f"DEBUG: Converting ROI {roi.id} to Annotation ({mode})")
                
                # Convert ROI points to annotation points
                points = [(p.x(), p.y()) for p in roi.points]
                if not points and roi.line_points:
                    p1, p2 = roi.line_points
                    points = [(p1.x(), p1.y()), (p2.x(), p2.y())]
                
                # Create UUID
                import uuid
                ann_id = str(uuid.uuid4())
                
                # Map mode to annotation type
                ann_type = mode # 'rect', 'ellipse', 'arrow', 'line', 'polygon'
                
                # User Request: "Dual Attributes" - ROI should also have the specific type
                # so RoiGraphicsItem can render it correctly (e.g. arrow head).
                roi.roi_type = ann_type
                
                # Get properties from Annotation Panel
                props = self.annotation_panel.get_current_properties()
                
                # Create Annotation
                ann = GraphicAnnotation(
                    id=ann_id,
                    type=ann_type,
                    points=points,
                    color=props.get('color', "#FFFF00"), 
                    thickness=props.get('thickness', 2),
                    visible=True
                )
                
                # Apply additional properties (style, arrow size)
                ann.style = props.get('style', 'solid')
                ann.export_only = props.get('export_only', False)
                if ann_type == 'arrow':
                    # Scale default size (15.0) by display scale so it looks correct on screen
                    scale = 1.0
                    if hasattr(self, 'multi_view'):
                        active_view = self.multi_view.views.get(self.multi_view.active_channel_id)
                        if active_view:
                            scale = active_view.display_scale
                        elif self.multi_view.views:
                            scale = next(iter(self.multi_view.views.values())).display_scale
                    
                    base_size = props.get('arrow_head_size', 15.0)
                    if scale > 0:
                        ann.properties['arrow_head_size'] = base_size / scale
                    else:
                        ann.properties['arrow_head_size'] = base_size
                
                # 【核心修复】避免重影：隐藏原始 ROI 并建立关联
                roi.visible = False
                ann.roi_id = roi.id
                ann.roi = roi 
                
                self.session.annotations.append(ann)
                self.annotation_panel.update_annotation_list()
                self.multi_view.set_annotations(self.session.annotations)
                
                # 触发 ROI 状态更新信号
                self.session.roi_manager.roi_updated.emit(roi.id)
                Logger.debug(f"[Main.on_roi_added] ROI converted to annotation successfully")
                return

            if getattr(self, '_suppress_roi_annotation_sync', False):
                return

            # 2. Normal ROI Sync (if enabled)
            if hasattr(self, 'roi_toolbox') and self.roi_toolbox.chk_sync_rois.isChecked():
                # Don't sync point ROIs if they are part of point counter (they are too many)
                if roi.roi_type == "point":
                    return
                # Convert ROI points to annotation points
                points = [(p.x(), p.y()) for p in roi.points]
                if not points and roi.line_points:
                    p1, p2 = roi.line_points
                    points = [(p1.x(), p1.y()), (p2.x(), p2.y())]
                
                # Map ROI types to annotation types
                ann_type = 'roi_ref'
                if roi.roi_type == 'rectangle': ann_type = 'rect'
                elif roi.roi_type == 'ellipse': ann_type = 'ellipse'
                elif roi.roi_type == 'line_scan' or roi.roi_type == 'line': ann_type = 'line'
                elif roi.roi_type == 'polygon': ann_type = 'polygon'
                elif roi.roi_type == 'arrow': ann_type = 'arrow'
                elif roi.roi_type == 'point': ann_type = 'circle'
                elif roi.roi_type == 'circle': ann_type = 'circle'
                
                # Special handling for points
                if roi.roi_type == 'point' and len(points) == 1:
                    p1 = points[0]
                    points = [p1, (p1[0] + 5, p1[1] + 5)]
                
                ann = GraphicAnnotation(
                    id=f"ann_{roi.id}",
                    type=ann_type,
                    points=points,
                    color=roi.color.name(),
                    thickness=2,
                    roi_id=roi.id
                )
                ann.roi = roi
                
                if hasattr(roi, 'properties'):
                    ann.properties.update(roi.properties)
                
                self.session.annotations.append(ann)
                self.annotation_panel.update_annotation_list()
                self.multi_view.set_annotations(self.session.annotations)
                Logger.debug(f"[Main.on_roi_added] ROI synced to annotation successfully")
                
        except Exception as e:
            Logger.error(f"[Main.on_roi_added] Error processing ROI addition: {e}")
            import traceback
            Logger.error(traceback.format_exc())
        
        Logger.debug(f"[Main.on_roi_added] EXIT")
        
    def on_roi_removed(self, roi_id):
        """Remove linked annotation if ROI is removed."""
        self.session.annotations = [a for a in self.session.annotations if a.roi_id != roi_id]
        self.annotation_panel.update_annotation_list()
        self.multi_view.update_all_previews()

    def on_roi_updated(self, roi_or_id):
        """Update linked annotation if ROI is updated."""
        # 修复：区分传入的是对象还是 ID 字符串
        if isinstance(roi_or_id, str):
            roi_id = roi_or_id
            roi = self.session.roi_manager.get_roi(roi_id)
            if not roi:
                return # 没找到，忽略
        else:
            roi = roi_or_id # 假设它是对象
            
        if getattr(self, '_suppress_roi_annotation_sync', False):
             return
             
        for ann in self.session.annotations:
            if ann.roi_id == roi.id:
                # 【核心修复】确保内存引用始终有效
                ann.roi = roi 
                
                # Update geometry
                # 修复循环更新：检查坐标误差
                new_points = [(p.x(), p.y()) for p in roi.points]
                if not new_points and roi.line_points:
                    p1, p2 = roi.line_points
                    new_points = [(p1.x(), p1.y()), (p2.x(), p2.y())]
                
                # 计算差异
                has_changed = False
                if len(ann.points) != len(new_points):
                    has_changed = True
                else:
                    for p1, p2 in zip(ann.points, new_points):
                        if abs(p1[0] - p2[0]) > 0.1 or abs(p1[1] - p2[1]) > 0.1:
                            has_changed = True
                            break
                
                if not has_changed:
                    # 坐标未变，无需触发后续更新循环
                    continue
                    
                ann.points = new_points
                
                # Update color
                ann.color = roi.color.name()
                
                # Update type if it changed (e.g. from generic to specific)
                ann_type = 'roi_ref'
                if roi.roi_type == 'rectangle': ann_type = 'rect'
                elif roi.roi_type == 'ellipse': ann_type = 'ellipse'
                elif roi.roi_type == 'line_scan' or roi.roi_type == 'line': ann_type = 'line'
                elif roi.roi_type == 'polygon': ann_type = 'polygon'
                elif roi.roi_type == 'arrow': ann_type = 'arrow' # Support arrow
                elif roi.roi_type == 'point': ann_type = 'circle'
                elif roi.roi_type == 'circle': ann_type = 'circle'
                ann.type = ann_type
                
                # Special handling for points
                if roi.roi_type == 'point' and len(ann.points) == 1:
                    p1 = ann.points[0]
                    ann.points = [p1, (p1[0] + 5, p1[1] + 5)]
                
                # Update properties
                if hasattr(roi, 'properties'):
                    ann.properties.update(roi.properties)
                
                self.annotation_panel.update_annotation_list()
                # Optimized sync: Update single annotation instead of full reload
                self.multi_view.sync_annotation(ann)
                break

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

            pair = sorted([str(roi1.id), str(roi2.id)])
            entry_id = f"overlap_{pair[0]}_{pair[1]}"
            self.result_widget.add_overlap_entry(sample_name, roi1.id, entry_id, display_data)
            self.result_widget.add_overlap_entry(sample_name, roi2.id, entry_id, display_data)
            
        except Exception as e:
            Logger.error(f"[Main] Overlap analysis failed: sample={sample_name} roi1={roi1.id} roi2={roi2.id} err={e}")

    def on_annotation_modified(self, update_data):
        """Handles updates from direct interaction with annotation items."""
        ann_id = update_data.get('id')
        new_points = update_data.get('points')
        
        # DEBUG: Track modification
        # print(f"DEBUG: [Main] on_annotation_modified id={ann_id}")

        found = False
        for ann in self.session.annotations:
            if ann.id == ann_id:
                found = True
                if new_points:
                    # print(f"DEBUG: [Main] Updating Annotation {ann_id} points: {ann.points} -> {new_points}")
                    Logger.info(f"Updated Annotation {ann.id} points: {ann.points} -> {new_points}")
                    ann.points = new_points
                    # print(f"DEBUG: [Main] Persisted annotation move for {ann.id}. New points: {ann.points}")
                
                # If we had properties to update
                if 'properties' in update_data:
                    ann.properties.update(update_data['properties'])
                
                # Update dragging state for performance optimization
                ann.is_dragging = update_data.get('is_dragging', False)
                    
                # If linked to ROI, should we update ROI?
                # Ideally yes, but ROI model is strict about shape.
                # If we moved an 'roi_ref' annotation, we should update the ROI.
                if ann.roi_id and self.session.roi_manager:
                    # Sync back to ROI
                    # We need to map annotation points back to ROI points.
                    # Since Scene Coordinates are Full Resolution, and ROI expects Full Resolution,
                    # we can use them directly (as QPointF).
                    
                    try:
                        roi = self.session.roi_manager.get_roi(ann.roi_id)
                        if roi:
                            # print(f"DEBUG: Syncing Annotation {ann.id} back to ROI {roi.id}")
                            
                            # Convert tuples back to QPointF
                            qpoints = [QPointF(p[0], p[1]) for p in ann.points]
                            
                            # Update ROI geometry
                            # Note: roi.reconstruct_from_points handles type-specific logic (e.g. line_scan vs polygon)
                            # But we need to pass the correct type if we want to enforce it.
                            # Usually roi.roi_type is already set.
                            roi.reconstruct_from_points(qpoints)
                            
                            # IMPORTANT: We must update the manager to trigger signals?
                            # Or just update the object?
                            # Ideally, calling roi_manager.update_roi(roi) is best.
                            # But update_roi might trigger on_roi_updated which triggers on_annotation_modified... LOOP?
                            
                            # Let's check canvas_view._on_roi_updated.
                            # It checks 'is_dragging'.
                            # But here we are DRAGGING the ANNOTATION item. The ROI item is hidden (due to our previous fix).
                            # So ROI item won't be dragging.
                            
                            # If we trigger update_roi -> on_roi_updated -> updates ROI item path.
                            # And on_roi_updated -> updates annotation (in main.py)?
                            # Yes, main.py has on_roi_updated which updates annotation points.
                            
                            # We need to suppress the loop.
                            # We can set a flag on main_window?
                            self._suppress_roi_annotation_sync = True
                            self.session.roi_manager.roi_updated.emit(roi)
                            self._suppress_roi_annotation_sync = False
                            
                    except Exception as e:
                        print(f"ERROR: Failed to sync Annotation back to ROI: {e}")
                
                self.annotation_panel.update_annotation_list()
                
                # Sync changes to all views (efficiently)
                if hasattr(self.multi_view, 'sync_annotation'):
                    self.multi_view.sync_annotation(ann)
                else:
                    self.multi_view.set_annotations(self.session.annotations)
                
                break
        
    def on_clear_annotations(self):
        """Clears all graphic annotations."""
        from PySide6.QtWidgets import QMessageBox
        if not self.session.annotations:
            return
            
        ret = QMessageBox.question(
            self, tr("Clear Annotations"),
            tr("Are you sure you want to clear all graphic annotations?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if ret == QMessageBox.StandardButton.Yes:
            self.session.annotations = []
            self.annotation_panel.update_annotation_list()
            self.multi_view.set_annotations([]) # Force clear in view
            # Also clear previews if needed? set_annotations([]) handles it.

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

    def on_fixed_size_toggled(self, checked):
        """Callback for ROI fixed size checkbox."""
        if hasattr(self, 'rect_tool'):
            self.rect_tool.set_fixed_size_mode(checked)
            # Update toolbox inputs enabled state
            self.roi_toolbox.spin_width.setEnabled(checked)
            self.roi_toolbox.spin_height.setEnabled(checked)

    def _on_prev_tab_clicked(self):
        """Switch to previous tab."""
        count = self.control_tabs.count()
        if count > 0:
            current = self.control_tabs.currentIndex()
            # Wrap around or stop? Standard is wrap.
            new_idx = (current - 1) % count
            self.control_tabs.setCurrentIndex(new_idx)

    def _on_next_tab_clicked(self):
        """Switch to next tab."""
        count = self.control_tabs.count()
        if count > 0:
            current = self.control_tabs.currentIndex()
            new_idx = (current + 1) % count
            self.control_tabs.setCurrentIndex(new_idx)

    def on_tab_changed(self, index):
        """Handle tab switching events."""
        tab_text = self.control_tabs.tabText(index)
        
        # Trigger lazy loading for Enhance Panel
        current_widget = self.control_tabs.widget(index)
        if current_widget == self.enhance_panel:
            self.enhance_panel.on_panel_shown()
            
        # If switching AWAY from Toolbox, default to Hand/Pan tool
        if tab_text != tr("Toolbox"):
            # Check if current tool is a TextTool OR if we are in hijacked annotation mode
            is_annotation = isinstance(self.multi_view.current_tool, TextTool) or (getattr(self, 'pending_annotation_mode', None) is not None)
            
            # If we are in Annotation Mode, DO NOT switch to Pan tool.
            # Only switch if we are in a regular ROI tool mode.
            if not is_annotation and self.multi_view.current_tool is not None:
                # Trigger Pan action (which is a toggle, so if it's not checked, check it)
                if hasattr(self, 'action_pan'):
                    self.action_pan.setChecked(True) 
                    if self.action_pan.isChecked():
                        self.multi_view.set_tool(None)
        
        # If switching TO Overlay (Annotation) tab, ensure we don't accidentally clear tool
        # unless it was an ROI tool.
        if tab_text == tr("Annotation"):
             # Maybe we want to keep the current annotation tool active?
             pass
                        
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
        self.menu_view.addAction(self.action_toggle_theme)
        
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
                self.multi_view.update_all_previews()

    def open_auto_save_settings(self):
        """Opens the Auto Save configuration dialog."""
        dlg = AutoSaveSettingsDialog(self)
        if dlg.exec():
            self.setup_auto_save()

    def apply_stylesheet(self):
        """Applies a professional theme (Dark or Light) with high interactivity."""
        theme = self.settings.value("ui_theme", "light")
        
        # Clear icon cache to force regeneration with new theme colors
        IconManager._cache.clear()
        
        if theme == "dark":
            bg_color = "#2b2b2b"
            text_color = "#dcdcdc"
            header_bg = "#333333"
            header_text = "#dcdcdc"
            toolbar_bg = "#333333"
            border_color = "#1a1a1a"
            item_hover = "#444444"
            input_bg = "#1e1e1e"
            group_border = "#555555"
            accent_color = "#4a90e2"
            tab_bg = "#333333"
            tab_selected = "#2b2b2b"
            button_bg = "#3c3c3c"
            button_hover = "#505050"
        else:
            # PPT / Office Style Light Theme
            bg_color = "#f3f3f3"
            text_color = "#202020"
            accent_color = "#C43E1C" # PowerPoint Orange/Red
            header_bg = "#E0E0E0" # Grey Header (User Request)
            header_text = "#333333"
            toolbar_bg = "#ffffff"
            border_color = "#d0d0d0"
            item_hover = "#e6e6e6"
            input_bg = "#ffffff"
            group_border = "#c0c0c0"
            tab_bg = "#f0f0f0"
            tab_selected = "#ffffff"
            button_bg = "#ffffff"
            button_hover = "#fdfdfd"

        # Update application palette for system-aware widgets and IconManager
        palette = QApplication.palette()
        palette.setColor(palette.ColorGroup.All, palette.ColorRole.Window, QColor(bg_color))
        palette.setColor(palette.ColorGroup.All, palette.ColorRole.WindowText, QColor(text_color))
        palette.setColor(palette.ColorGroup.All, palette.ColorRole.Base, QColor(input_bg))
        palette.setColor(palette.ColorGroup.All, palette.ColorRole.Text, QColor(text_color))
        palette.setColor(palette.ColorGroup.All, palette.ColorRole.Button, QColor(header_bg))
        palette.setColor(palette.ColorGroup.All, palette.ColorRole.ButtonText, QColor(header_text))
        palette.setColor(palette.ColorGroup.All, palette.ColorRole.Highlight, QColor(accent_color))
        QApplication.setPalette(palette)

        qss = f"""
        /* Main Window and General */
        QMainWindow, QDialog, QWidget {{{{
            background-color: {bg_color};
            color: {text_color};
            font-family: "Segoe UI", "Roboto", "Helvetica Neue", sans-serif;
        }}}}
        
        /* Modern Border for Main Window */
        QMainWindow {{{{
            border: 1px solid {border_color};
        }}}}
        
        QLabel {{{{
            background-color: transparent; /* Remove background shading from text */
        }}}}
        
        /* Menu Bar */
        QMenuBar {{{{
            background-color: {header_bg};
            color: {header_text};
            border-bottom: none;
            padding: 4px;
        }}}}
        QMenuBar::item {{{{
            background-color: transparent;
            padding: 6px 12px;
            border-radius: 4px;
            color: {header_text};
        }}}}
        QMenuBar::item:selected {{{{
            background-color: rgba(255, 255, 255, 0.2);
            color: {header_text};
        }}}}
        QMenuBar::item:pressed {{{{
            background-color: rgba(0, 0, 0, 0.1);
            color: {header_text};
        }}}}

        /* Menu dropdown */
        QMenu {{{{
            background-color: {bg_color};
            border: 1px solid {border_color};
            padding: 4px;
        }}}}
        QMenu::item {{{{
            padding: 6px 28px 6px 28px;
            border-radius: 4px;
            color: {text_color};
        }}}}
        QMenu::item:selected {{{{
            background-color: {accent_color};
            color: white;
        }}}}
        QMenu::separator {{{{
            height: 1px;
            background-color: {border_color};
            margin: 4px 8px;
        }}}}
        QMenu::icon {{{{
            padding-left: 10px;
        }}}}
        
        /* ToolBar */
        QToolBar {{{{
            background-color: {toolbar_bg};
            border-bottom: 1px solid {border_color};
            border-right: 1px solid {border_color};
            spacing: 8px;
            padding: 4px;
        }}}}
        QToolBar QToolButton {{{{
            background-color: transparent;
            border: 1px solid transparent;
            border-radius: 4px;
            width: 28px;
            height: 28px;
            padding: 0px;
            color: {text_color};
        }}}}
        QToolBar QToolButton:hover {{{{
            background-color: {item_hover};
            border: 1px solid {accent_color};
        }}}}
        QToolBar QToolButton:checked {{{{
            background-color: {accent_color};
            border: 1px solid {accent_color};
            color: white;
        }}}}
        QToolBar QToolButton:pressed {{{{
            background-color: {border_color};
        }}}}
        
        /* Dock Widgets */
        QDockWidget {{{{
            color: {text_color};
            font-weight: bold;
            border: none;
        }}}}
        QDockWidget::title {{{{
            background-color: {bg_color};
            padding: 6px 8px;
            text-align: left;
            border-bottom: 1px solid {border_color};
            color: {accent_color}; /* Brand color for dock titles */
        }}}}
        
        /* Splitter */
        QSplitter::handle {{{{
            background-color: {border_color};
            margin: 1px;
        }}}}
        QSplitter::handle:horizontal {{{{ width: 1px; }}}}
        QSplitter::handle:vertical {{{{ height: 1px; }}}}
        QSplitter::handle:hover {{{{ background-color: {accent_color}; }}}}

        /* Tool Buttons (General) */
        QToolButton {{{{
            background-color: {button_bg};
            border: 1px solid {group_border};
            border-radius: 4px;
            width: 28px;
            height: 28px;
            padding: 0px;
            margin: 1px;
            color: {text_color};
        }}}}
        QToolButton:hover {{{{
            background-color: {button_hover};
            border: 1px solid {accent_color};
        }}}}
        QToolButton:pressed {{{{
            background-color: {border_color};
        }}}}
        QToolButton:checked {{{{
            background-color: {accent_color};
            color: white;
            border: 1px solid {accent_color};
        }}}}
        QToolButton:disabled {{{{
            opacity: 0.3;
        }}}}
        
        /* Specific Tool Button IDs for corner actions - Cleaner look */
        #undo_btn, #redo_btn, #save_btn, #settings_btn, #theme_btn, #action_btn {{{{
            border: none;
            padding: 4px;
            background: transparent;
            min-width: 28px;
            min-height: 28px;
            border-radius: 4px;
        }}}}
        #undo_btn:hover, #redo_btn:hover, #save_btn:hover, #settings_btn:hover, #theme_btn:hover, #action_btn:hover {{{{
            background-color: {item_hover};
        }}}}
        
        /* Specialized Hero/Action Button (High Emphasis) */
        QPushButton#action_btn {{{{
            background-color: {accent_color};
            color: white;
            border: 1px solid {accent_color};
            border-radius: 4px;
            padding: 6px 16px;
            font-weight: bold;
        }}}}
        QPushButton#action_btn:hover {{{{
            background-color: {accent_color};
            border: 1px solid {accent_color};
            opacity: 0.85;
        }}}}
        QPushButton#action_btn:pressed {{{{
            background-color: {border_color};
        }}}}
        QPushButton#action_btn:disabled {{{{
            background-color: {border_color};
            color: {group_border};
            border: 1px solid {border_color};
        }}}}
        
        /* Tab Widget */
        QTabWidget::pane {{{{
            border: 1px solid {border_color};
            background-color: {bg_color};
            border-radius: 4px;
            top: -1px;
        }}}}
        QTabBar::tab {{{{
            background-color: {tab_bg};
            color: {text_color};
            padding: 8px 16px;
            border: 1px solid {border_color};
            border-bottom: none;
            border-top-left-radius: 4px;
            border-top-right-radius: 4px;
            margin-right: 2px;
        }}}}
        QTabBar::tab:selected {{{{
            background-color: {bg_color};
            border-bottom: 2px solid {accent_color};
            font-weight: bold;
            color: {accent_color};
        }}}}
        QTabBar::tab:hover:!selected {{{{
            background-color: {item_hover};
        }}}}
        /* Hide default scroll buttons */
        QTabBar::scroller {{{{
            width: 0px;
            height: 0px;
        }}}}

        /* Tooltip */
        QToolTip {{{{
            background-color: {bg_color};
            color: {text_color};
            border: 1px solid {accent_color};
            padding: 4px;
            border-radius: 4px;
        }}}}

        /* Tree and List Widgets */
        QTreeWidget, QListWidget {{{{
            background-color: {input_bg};
            border: 1px solid {border_color};
            border-radius: 4px;
            outline: none;
        }}}}
        QTreeWidget::item, QListWidget::item {{{{
            padding: 4px;
            border: none;
            color: {text_color};
        }}}}
        QTreeWidget::item:hover, QListWidget::item:hover {{{{
            background-color: {item_hover};
        }}}}
        QTreeWidget::item:selected, QListWidget::item:selected {{{{
            background-color: {accent_color};
            color: white;
        }}}}

        /* ScrollBar - Minimalist */
        QScrollBar:vertical {{{{
            border: none;
            background: {bg_color};
            width: 10px;
            margin: 0px;
        }}}}
        QScrollBar::handle:vertical {{{{
            background: {group_border};
            min-height: 20px;
            border-radius: 5px;
        }}}}
        QScrollBar::handle:vertical:hover {{{{
            background: {accent_color};
        }}}}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{{{
            height: 0px;
        }}}}
        QScrollBar:horizontal {{{{
            border: none;
            background: {bg_color};
            height: 10px;
            margin: 0px;
        }}}}
        QScrollBar::handle:horizontal {{{{
            background: {group_border};
            min-width: 20px;
            border-radius: 5px;
        }}}}
        QScrollBar::handle:horizontal:hover {{{{
            background: {accent_color};
        }}}}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{{{
            width: 0px;
        }}}}
        
        QFrame#menu_sep {{{{
            background-color: {border_color};
            margin: 6px 4px;
            width: 1px;
        }}}}

        /* Input Fields */
        QDoubleSpinBox, QSpinBox, QLineEdit, QComboBox, QPushButton {{{{
            background-color: {input_bg};
            border: 1px solid {group_border};
            border-radius: 4px;
            padding: 6px;
            color: {text_color};
        }}}}
        QPushButton:hover {{{{
            background-color: {button_hover};
            border: 1px solid {accent_color};
        }}}}
        QPushButton:pressed {{{{
            background-color: {border_color};
        }}}}
        QDoubleSpinBox:focus, QSpinBox:focus, QLineEdit:focus, QComboBox:focus, QPushButton:focus {{{{
            border: 1px solid {accent_color};
        }}}}
        
        /* Sliders */
        QSlider::groove:horizontal {{{{
            border: 1px solid {border_color};
            height: 4px;
            background: {group_border};
            margin: 2px 0;
            border-radius: 2px;
        }}}}
        QSlider::handle:horizontal {{{{
            background: {accent_color};
            border: 1px solid {accent_color};
            width: 14px;
            height: 14px;
            margin: -6px 0;
            border-radius: 7px;
        }}}}

        /* Group Boxes - Refined Style */
        QGroupBox {{{{
            border: 1px solid {group_border};
            border-radius: 6px;
            margin-top: 4px;
            padding: 4px;
            font-weight: normal;
            color: {accent_color};
            background-color: {bg_color};
        }}}}
        QGroupBox::title {{{{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            padding: 0 5px;
            left: 6px;
            font-size: 12px;
            font-weight: normal;
            background-color: {bg_color};
        }}}}

        /* Card Style for Panels */
        QWidget#card, QWidget[role="card"] {{{{
            background-color: {bg_color};
            border: 1px solid {border_color};
            border-radius: 8px;
            padding: 10px;
        }}}}

        /* Label Roles */
        QLabel[role="title"] {{{{
            font-weight: bold;
            font-size: 14px;
            color: {accent_color};
        }}}}
        QLabel[role="subtitle"] {{{{
            font-weight: bold;
            font-size: 12px;
            color: {text_color};
            opacity: 0.8;
        }}}}

        /* Status Indicators */
        QLabel[role="status"] {{{{
            padding: 4px 8px;
            border-radius: 4px;
            font-weight: bold;
            background-color: {input_bg};
            border: 1px solid {border_color};
        }}}}
        QLabel[role="success"] {{{{
            color: #27ae60;
            background-color: rgba(46, 204, 113, 0.15);
            border: 1px solid #2ecc71;
        }}}}
        QLabel[role="warning"] {{{{
            color: #e67e22;
            background-color: rgba(230, 126, 34, 0.15);
            border: 1px solid #e67e22;
        }}}}
        QLabel[role="error"] {{{{
            color: #e74c3c;
            background-color: rgba(231, 76, 60, 0.15);
            border: 1px solid #e74c3c;
        }}}}

        /* Hero Buttons (Large Action Buttons) */
        QPushButton[role="hero"] {{{{
            background-color: {accent_color};
            color: white;
            border-radius: 8px;
            padding: 12px 24px;
            font-size: 15px;
            font-weight: bold;
            border: none;
            min-width: 220px;
        }}}}
        QPushButton[role="hero"]:hover {{{{
            background-color: {button_hover};
            border: 1px solid {accent_color};
        }}}}

        /* Recent Projects List */
        QListWidget[role="recent"] {{{{
            background-color: transparent;
            border: 1px solid {border_color};
            border-radius: 4px;
            color: {text_color};
        }}}}
        QListWidget[role="recent"]::item {{{{
            padding: 8px;
            border-bottom: 1px solid {border_color};
        }}}}
        QListWidget[role="recent"]::item:hover {{{{
            background-color: {input_bg};
            color: {accent_color};
        }}}}

        /* Loading Overlay */
        QLabel[role="overlay"] {{{{
            background-color: rgba(0, 0, 0, 180);
            color: white;
            font-size: 24px;
            font-weight: bold;
        }}}}
        
        /* Preview Overlay */
        QLabel[role="preview"] {{{{
            border: 2px solid {accent_color};
            background-color: black;
        }}}}
        QPushButton[role="hero"]:pressed {{{{
            background-color: {border_color};
        }}}}

        /* Tabs Style */
        QTabWidget::pane {{{{
            border: 1px solid {border_color};
            background-color: {bg_color};
            border-radius: 4px;
        }}}}
        QTabBar::tab {{{{
            background: {input_bg};
            border: 1px solid {border_color};
            border-bottom-color: {border_color};
            border-top-left-radius: 4px;
            border-top-right-radius: 4px;
            padding: 4px 10px;
            min-width: 60px;
            color: {text_color};
        }}}}
        QTabBar::tab:hover {{{{
            background: {button_hover};
        }}}}
        QTabBar::tab:selected {{{{
            background: {bg_color};
            border-bottom-color: {bg_color};
            font-weight: bold;
            color: {accent_color};
        }}}}

        /* Tool Buttons */
        QToolButton {{{{
            border: 1px solid {border_color};
            border-radius: 4px;
            background-color: {input_bg};
            padding: 2px;
        }}}}
        QToolButton:hover {{{{
            background-color: {button_hover};
            border: 1px solid {accent_color};
        }}}}
        QToolButton:pressed {{{{
            background-color: {border_color};
        }}}}
        QToolButton#nav_btn {{{{
            border: 1px solid {border_color};
            border-radius: 4px;
            background-color: {input_bg};
            padding: 2px;
        }}}}
        QToolButton#nav_btn:hover {{{{
            background-color: {button_hover};
            border: 1px solid {accent_color};
        }}}}

        /* Splitter Style */
        QSplitter::handle {{{{
            background-color: {border_color};
        }}}}

        /* Label Roles */
        QLabel[role="accent"] {{{{
            color: {accent_color};
            font-weight: bold;
        }}}}
        QLabel[role="description"] {{{{
            color: {text_color};
            opacity: 0.6;
            font-size: 11px;
            padding-left: 20px;
        }}}}

        /* Color Pickers / Color Indicator Buttons */
        QPushButton[role="color_picker"], QToolButton[role="color_picker"] {{{{
            border: 1px solid {border_color};
            border-radius: 4px;
            min-width: 20px;
            min-height: 20px;
            max-width: 20px;
            max-height: 20px;
        }}}}
        QPushButton[role="color_picker"]:hover, QToolButton[role="color_picker"]:hover {{{{
            border: 1px solid {accent_color};
        }}}}
        
        /* Separator */
        QFrame[frameShape="4"], QFrame[frameShape="5"] {{{{
            color: {border_color};
            background-color: {border_color};
            max-height: 1px;
            opacity: 0.3;
        }}}}

        /* Navigation Toolbar (Matplotlib) */
        [class*="NavigationToolbar"] {{{{
            background-color: transparent;
            border: none;
        }}}}

        /* Tooltips */
        QToolTip, PreviewPopup {{{{
            background-color: {input_bg};
            color: {text_color};
            border: 1px solid {border_color};
            padding: 4px;
            border-radius: 4px;
        }}}}

        /* Tree Widget */
        QTreeWidget {{{{
            border: 1px solid {border_color};
            background-color: {bg_color};
            border-radius: 4px;
        }}}}
        QTreeWidget::item {{{{
            padding: 4px;
            border-bottom: 1px solid {group_border};
        }}}}
        QTreeWidget::item:selected {{{{
            background-color: {button_hover};
            color: {accent_color};
        }}}}

        /* Specific Tool Button Roles */
        QToolButton[role="subtle"] {{{{
            border: none;
            background: transparent;
            color: {text_color};
            font-size: 11px;
            padding: 2px 5px;
            border-radius: 4px;
        }}}}
        QToolButton[role="subtle"]:hover {{{{
            background-color: {button_hover};
            color: {accent_color};
        }}}}
        QToolButton[role="accent"] {{{{
            color: {accent_color};
            font-weight: bold;
        }}}}
        QToolButton:checked {{{{
            background-color: {accent_color};
            color: white;
            border: 1px solid {accent_color};
        }}}}
        """
        self.setStyleSheet(qss)
        if hasattr(self, 'menu_actions_widget'):
            self.menu_actions_widget.setStyleSheet(qss)
        self._last_titlebar_style = (header_bg, border_color, header_text)
        if self.isVisible():
            self._apply_windows_titlebar_style(header_bg, border_color, header_text)
        else:
            QTimer.singleShot(0, lambda: self._apply_windows_titlebar_style(header_bg, border_color, header_text))

    def showEvent(self, event):
        super().showEvent(event)
        if self._last_titlebar_style:
            header_bg, border_color, header_text = self._last_titlebar_style
            QTimer.singleShot(0, lambda: self._apply_windows_titlebar_style(header_bg, border_color, header_text))

    def _apply_windows_titlebar_style(self, caption_hex: str, border_hex: str, text_hex: str):
        try:
            if sys.platform != "win32":
                return

            hwnd = int(self.winId())

            def to_colorref(hex_color: str) -> int:
                s = (hex_color or "").strip()
                if s.startswith("#"):
                    s = s[1:]
                if len(s) != 6:
                    return 0
                r = int(s[0:2], 16)
                g = int(s[2:4], 16)
                b = int(s[4:6], 16)
                return (b << 16) | (g << 8) | r

            dwmapi = ctypes.windll.dwmapi
            set_attr = dwmapi.DwmSetWindowAttribute

            DWMWA_BORDER_COLOR = 34
            DWMWA_CAPTION_COLOR = 35
            DWMWA_TEXT_COLOR = 36

            caption = ctypes.c_uint(to_colorref(caption_hex))
            border = ctypes.c_uint(to_colorref(border_hex))
            text = ctypes.c_uint(to_colorref(text_hex))

            set_attr(hwnd, DWMWA_CAPTION_COLOR, ctypes.byref(caption), ctypes.sizeof(caption))
            set_attr(hwnd, DWMWA_BORDER_COLOR, ctypes.byref(border), ctypes.sizeof(border))
            set_attr(hwnd, DWMWA_TEXT_COLOR, ctypes.byref(text), ctypes.sizeof(text))

            Logger.debug(f"[Main] Windows titlebar styled: caption={caption_hex} border={border_hex} text={text_hex}")
        except Exception as e:
            Logger.debug(f"[Main] Windows titlebar styling skipped: {e}")

    def toggle_theme(self):
        """Toggles between dark and light themes."""
        current = self.settings.value("ui_theme", "dark")
        new_theme = "light" if current == "dark" else "dark"
        self.settings.setValue("ui_theme", new_theme)
        self.apply_stylesheet()
        self.lbl_status.setText(tr("Theme switched to {0}").format(new_theme.capitalize()))


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

    def closeEvent(self, event):
        if not self.check_unsaved_changes():
            event.ignore()
        else:
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
            self.multi_view.initialize_views()
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
        self.multi_view.initialize_views()
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
            self.multi_view.initialize_views() # Re-init views (clears images)
            
            # Optionally, select the next available scene?
            # SampleList might handle selection of next item, which triggers load_scene.
            # But if no items left, we are clear.
            
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
                self.multi_view.update_view(ch_index)

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
            self.setWindowTitle("FluoQuantPro")

    def load_project(self, folder):
        """Internal helper to load a project folder."""
        if not folder or not os.path.exists(folder):
            return False
            
        json_path = os.path.join(folder, "project.json")
        if not os.path.exists(json_path):
            # NEW LOGIC: Auto-initialize if missing (Restore "Open Folder -> Auto Read" workflow)
            reply = QMessageBox.question(self, tr("Initialize Project"), 
                                         tr("No project.json found. Initialize new project and import images from this folder?"),
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
            self.multi_view.initialize_views()
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
            
        # Check for existing project.json
        if os.path.exists(os.path.join(folder, "project.json")):
             res = QMessageBox.warning(self, tr("Existing Project"), 
                                      tr("This folder already contains a project. Overwrite?"),
                                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
             if res == QMessageBox.StandardButton.No:
                 return False
        
        self.project_model.set_root_path(folder)
        return self.save_project()

    def save_project(self) -> bool:
        """Saves project structure and current scene state."""
        if not self.project_model.root_path:
            # If no root path (e.g. started without project), ask to save as new
            return self.save_project_as()

        # 1. Capture Current Scene State
        if self.current_scene_id:
            # Always sync current ROIs to ProjectModel memory first
            # (ProjectModel.save_project will decide whether to write them to disk based on flag)
            rois = self.session.roi_manager.serialize_rois()
            
            # Get Display Settings
            display_settings = []
            for ch in self.session.channels:
                s = ch.display_settings
                s_dict = {
                    "min_val": s.min_val,
                    "max_val": s.max_val,
                    "gamma": s.gamma,
                    "visible": s.visible,
                    "color": s.color
                }
                if hasattr(s, 'enhance_params'):
                     pass # USER REQUEST: Do NOT save enhance params. Temporary only.
                     # s_dict['enhance_params'] = s.enhance_params
                display_settings.append(s_dict)
                
            annotations = self.session.serialize_annotations()
            self.project_model.save_scene_state(self.current_scene_id, rois, display_settings, annotations=annotations)
        
        # 2. Save to JSON
        try:
            # Check persistence setting for DISK storage
            settings = QSettings("FluoQuantPro", "AppSettings")
            save_on_close = settings.value("roi/save_on_close", False, type=bool)
            
            self.project_model.save_project(include_rois=save_on_close)
            self.add_to_recent_projects(self.project_model.root_path)
            self.lbl_status.setText(tr("Project Saved to {0}").format(self.project_model.root_path))
            return True
        except Exception as e:
            QMessageBox.critical(self, tr("Error"), tr("Failed to save project: {0}").format(e))
            return False

    def handle_scene_deletion(self, scene_id):
        """Clears the view if the deleted scene was the current one."""
        if self.current_scene_id == scene_id:
            self.current_scene_id = None
            self.session.clear()
            self.multi_view.initialize_views()
            self.lbl_status.setText(tr("Scene {0} deleted and view cleared.").format(scene_id))
        else:
            self.lbl_status.setText(tr("Scene {0} removed from project.").format(scene_id))

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
        self.multi_view.flash_channel(channel_index)
        self.multi_view.fit_views()

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
                    # Load data
                    data = None
                    if file_path.lower().endswith(('.tif', '.tiff')):
                        data = tifffile.imread(file_path)
                    else:
                        # data = cv2.imread(file_path, cv2.IMREAD_UNCHANGED)
                        # Fix for Unicode paths:
                        data_stream = np.fromfile(file_path, dtype=np.uint8)
                        data = cv2.imdecode(data_stream, cv2.IMREAD_UNCHANGED)
                        
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
                        ch.reset_display_settings() 
                        
                        Logger.info(f"[Main] Data loaded for channel {ch_index}. Triggering view update.")
                        self.session.data_changed.emit() 
                        
                        # Also refresh the view explicitly to ensure update
                        self.multi_view.update_view(ch_index)
                        
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
            # Check ROI persistence settings
            settings = QSettings("FluoQuantPro", "AppSettings")
            save_rois_on_switch = settings.value("roi/save_on_switch", False, type=bool)
            
            if save_rois_on_switch:
                rois = self.session.roi_manager.serialize_rois()
            else:
                # USER REQUEST: Best not to save previous ROIs (persist only annotations)
                # We pass empty list for ROIs so they are cleared in the project model (or not saved)
                rois = [] 
                
            annotations = self.session.serialize_annotations()
            
            # Get Display Settings
            display_settings = []
            for ch in self.session.channels:
                s = ch.display_settings
                s_dict = {
                    "min_val": s.min_val,
                    "max_val": s.max_val,
                    "gamma": s.gamma,
                    "visible": s.visible,
                    "color": s.color
                }
                if hasattr(s, 'enhance_params'):
                     pass # USER REQUEST: Do NOT save enhance params. Temporary only.
                     # s_dict['enhance_params'] = s.enhance_params
                display_settings.append(s_dict)
                
            self.project_model.save_scene_state(self.current_scene_id, rois, display_settings, annotations=annotations)
        
        self.current_scene_id = scene_id
        
        # --- Prepare to Load New Scene ---
        scene_data = self.project_model.get_scene(scene_id)
        if not scene_data:
             return

        self.session.clear()
        
        # Reset View (Empty)
        self.multi_view.initialize_views()
        self.multi_view.show_loading(tr("Loading {0}...").format(scene_id)) # Show overlay
        self.lbl_status.setText(tr("Loading scene: {0}...").format(scene_id))
        
        # Start Async Loader
        self.loader_worker = SceneLoaderWorker(scene_id, scene_data.channels)
        self.loader_worker.channel_loaded.connect(self.on_channel_loaded)
        self.loader_worker.finished_loading.connect(self.on_scene_loading_finished)
        self.loader_worker.start()

    def on_channel_loaded(self, scene_id, index, data_or_obj, ch_def):
        """Called when a single channel finishes loading in background."""
        print(f"[{time.strftime('%H:%M:%S')}] UI: Received channel_loaded signal for index {index}")
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
                # USER REQUEST: Do not restore enhance params from disk.
                # Just ensure they are reset.
                ch.display_settings.enhance_percents = {} 
                ch.display_settings.enhance_params = {}
                # print(f"[{time.strftime('%H:%M:%S')}] UI: Reset enhancements to OFF (Policy: No Persistence).")

            # Restore ROIs & Annotations ONLY when the first channel is loaded (to set reference shape)
            scene_data = self.project_model.get_scene(scene_id)
            if index == 0:
                # USER REQUEST: Best not to save/restore previous ROIs.
                # if scene_data.rois:
                #    self.session.roi_manager.set_rois(scene_data.rois)
                settings = QSettings("FluoQuantPro", "AppSettings")
                save_rois_on_switch = settings.value("roi/save_on_switch", False, type=bool)
                if save_rois_on_switch and scene_data.rois:
                    self._suppress_roi_annotation_sync = True
                    try:
                        self.session.roi_manager.set_rois(scene_data.rois)
                    finally:
                        self._suppress_roi_annotation_sync = False
                if scene_data.annotations:
                    self.session.set_annotations(scene_data.annotations)
                    self.annotation_panel.update_annotation_list()
            
            # Update UI incrementally
            # We initialize views for every channel to ensure the layout updates (1-view, 2-view, etc.)
            # and to ensure the view objects exist for rendering.
            self.multi_view.initialize_views()
            
            if index == 0:
                print(f"[{time.strftime('%H:%M:%S')}] UI: Initializing first channel view...")
                self.multi_view.fit_views()
                self.multi_view.select_channel(0)
            
            # Trigger immediate render for this channel
            # Note: initialize_views() already calls render_all(), but we call it again 
            # if we want to be absolutely sure the latest session data is used.
            self.refresh_display()
            
            # Update overlay text (shows progress)
            self.multi_view.show_loading(tr("Loading... ({0}/{1})").format(index+1, len(scene_data.channels))) 
            self.lbl_status.setText(tr("Loaded channel {0}/{1}").format(index+1, len(scene_data.channels)))
            
            print(f"[{time.strftime('%H:%M:%S')}] UI: on_channel_loaded done for index {index}")
            
        except Exception as e:
            print(f"Error in on_channel_loaded for index {index}: {e}")
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
        print(f"[{time.strftime('%H:%M:%S')}] UI: Scene loading finished signal received")
        
        try:
            # Final refresh: Initialize views with ALL loaded channels
            print(f"[{time.strftime('%H:%M:%S')}] UI: Final view initialization...")
            self.multi_view.initialize_views()
            self.multi_view.fit_views()
            print(f"[{time.strftime('%H:%M:%S')}] UI: Final view initialization done")
            
            # Update Tool Targets
            self.update_point_counter_targets()
            
            # Update Overlays
            self.multi_view.update_scale_bar(self.session.scale_bar_settings)
            self.multi_view.set_annotations(self.session.annotations)
        except Exception as e:
            print(f"Error in on_scene_loading_finished: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.multi_view.hide_loading() # Hide overlay
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
        
        print(f"DEBUG: [Main] on_batch_selection_made with rect: {rect}, channel_idx: {channel_index}")
        
        active_view = None
        
        # 1. Try to get view from channel_index
        if channel_index >= 0:
            # MultiView uses "Ch{index+1}" as key for channel views
            view_id = f"Ch{channel_index + 1}"
            if view_id in self.multi_view.views:
                active_view = self.multi_view.views[view_id]
        elif channel_index == -1:
             # Merge view
             if "Merge" in self.multi_view.views:
                 active_view = self.multi_view.views["Merge"]
        
        # 2. Fallback
        if not active_view:
             if self.multi_view.active_channel_id:
                 active_view = self.multi_view.views.get(self.multi_view.active_channel_id)
             elif self.multi_view.views:
                 active_view = next(iter(self.multi_view.views.values()))
                 
        if active_view:
             path = QPainterPath()
             path.addRect(rect)
             
             # Get items in the rect (this uses QGraphicsScene logic)
             items = active_view.scene.items(path, Qt.ItemSelectionMode.IntersectsItemShape)
             print(f"DEBUG: [Main] Found {len(items)} items in selection rect")
             
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
             print(f"DEBUG: [Main] Selected {count} valid ROI items: {selected_ids}")
             
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
        self.multi_view.set_tool(None)
        self.multi_view.set_annotation_mode('none')
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
                print(f"DEBUG: [Main.on_tool_toggled] Toggling toolbox for action: {tool_action.text() if tool_action else 'None'}")
                import sys
                sys.stdout.flush()
                
                self.roi_toolbox.set_active_tool(tool_action)
                
                # AUTO-SWITCH TAB: If an ROI tool is selected, switch to ROI Toolbox tab
                for i in range(self.control_tabs.count()):
                    tab_text = self.control_tabs.tabText(i)
                    is_toolbox_tab = False
                    for tab_id, _, title in self.all_tabs_data:
                        if tab_id == "toolbox" and title == tab_text:
                            is_toolbox_tab = True
                            break
                    
                    if is_toolbox_tab:
                        self.control_tabs.setCurrentIndex(i)
                        print(f"DEBUG: [Main.on_tool_toggled] Switched to tab {i} ({tab_text})")
                        break
                sys.stdout.flush()

            # Clear annotation tool selection if a regular ROI tool is selected
            if hasattr(self, 'annotation_panel'):
                self.annotation_panel.clear_tool_selection()
                
            # Reset pending annotation mode to prevent "hijacking"
            self.pending_annotation_mode = None 
        finally:
            # --- 释放锁 ---
            self._is_switching_roi_tool = False

        if tool_action == self.action_wand:
            self.lbl_status.setText("Mode: Magic Wand (Click to Auto-Select, Drag horizontally to adjust tolerance)")
            # Sync settings from UI
            self.wand_tool.base_tolerance = self.roi_toolbox.spin_wand_tol.value()
            self.wand_tool.smoothing = self.roi_toolbox.spin_wand_smooth.value()
            self.wand_tool.relative = self.roi_toolbox.chk_wand_relative.isChecked()
            self.multi_view.set_tool(self.wand_tool)
        elif tool_action == self.action_polygon:
            self.lbl_status.setText("Mode: Polygon Lasso (Left Click to Add, Right Click to Finish")
            self.multi_view.set_tool(self.polygon_tool)
            # Sync fixed size state
            if hasattr(self.polygon_tool, 'set_fixed_size_mode'):
                self.polygon_tool.set_fixed_size_mode(self.roi_toolbox.chk_fixed_size.isChecked())
        elif tool_action == self.action_rect:
            self.lbl_status.setText("Mode: Rectangle Selection (Drag to Draw")
            self.multi_view.set_tool(self.rect_tool)
            # Sync fixed size state
            self.rect_tool.set_fixed_size_mode(self.roi_toolbox.chk_fixed_size.isChecked())
        elif tool_action == self.action_ellipse:
            self.lbl_status.setText("Mode: Ellipse Selection (Drag to Draw")
            self.multi_view.set_tool(self.ellipse_tool)
            # Sync fixed size state
            self.ellipse_tool.set_fixed_size_mode(self.roi_toolbox.chk_fixed_size.isChecked())
        elif tool_action == self.action_count:
            self.lbl_status.setText("Mode: Point Counter (Click to count spots in current channel or merge view)")
            self.count_tool.radius = self.roi_toolbox.spin_count_radius.value()
            self.multi_view.set_tool(self.count_tool)
        elif tool_action == self.action_line_scan:
            self.lbl_status.setText("Mode: Line Scan (Drag to Draw Line for Colocalization)")
            self.multi_view.set_tool(self.line_scan_tool)
            # Sync fixed size state
            if hasattr(self.line_scan_tool, 'set_fixed_size_mode'):
                self.line_scan_tool.set_fixed_size_mode(self.roi_toolbox.chk_fixed_size.isChecked())
            # Switch to Colocalization tab automatically
            if self.colocalization_panel:
                self.control_tabs.setCurrentWidget(self.colocalization_panel)
        elif tool_action == self.action_batch_select:
            self.lbl_status.setText("Mode: Batch Select (Drag to select multiple items)")
            self.multi_view.set_tool(self.batch_tool)
        elif tool_action == self.action_pan:
            self.lbl_status.setText("Mode: Pan/Hand (Drag to Move View/ROI)")
            self.multi_view.set_tool(None) # Setting tool to None enables Pan mode in CanvasView
        else:
            self.multi_view.set_tool(None)
            self.lbl_status.setText("Mode: View/Pan")

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
            self.multi_view.flash_channel(index)
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
            self.multi_view.select_channel(channel_index)
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
        """Updates tool fixed size mode."""
        self.rect_tool.set_fixed_size_mode(checked)
        self.ellipse_tool.set_fixed_size_mode(checked)
        if hasattr(self.line_scan_tool, 'set_fixed_size_mode'):
            self.line_scan_tool.set_fixed_size_mode(checked)
        if hasattr(self.polygon_tool, 'set_fixed_size_mode'):
            self.polygon_tool.set_fixed_size_mode(checked)

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
        print("DEBUG: [Main] crop_to_selection called")
        rois = self.session.roi_manager.get_all_rois()
        if not rois:
            self.lbl_status.setText(tr("No selection to crop."))
            QMessageBox.information(self, tr("Crop"), tr("Please select an area (ROI) first."))
            return
            
        # Use the LAST ROI
        roi = rois[-1]
        print(f"DEBUG: [Main] Cropping to ROI: {roi.label}, Type: {roi.roi_type}")
        
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
                print(f"DEBUG: [Main] Extracted {len(points)} points from ROI path (overriding insufficient roi.points).")
        
        
        src_pts_ordered = None
        dst_pts = None
        M = None
        w, h = 0, 0
        x, y = 0, 0
        
        if len(points) < 3:
             # Fallback to simple bounding rect if not enough points
             print("DEBUG: [Main] Not enough points for advanced crop. Using bounding rect.")
             rect = roi.path.boundingRect()
             x, y, w, h = int(rect.x()), int(rect.y()), int(rect.width()), int(rect.height())
        else:
             pts_array = np.array(points, dtype=np.float32)
             
             # 2. Minimum Bounding Rectangle (Rotated)
             rect_rotated = cv2.minAreaRect(pts_array)
             (center, (w_rot, h_rot), angle) = rect_rotated
             
             print(f"DEBUG: [Main] MBR Center: {center}, Size: {w_rot:.2f}x{h_rot:.2f}, Angle: {angle:.2f}")
             
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
             print(f"DEBUG: [Main] Perspective Matrix:\n{M}")
             
        # Check bounds
        if w < 1 or h < 1:
            print("DEBUG: [Main] Invalid crop dimensions.")
            return
            
        # Prepare Mask (for Polygons/Irregular shapes)
        # If M is present, we warp the polygon to create the mask in destination coordinates
        mask = None
        if M is not None and (roi.roi_type == 'polygon' or roi.roi_type == 'freehand'):
            try:
                # Transform original points to crop coordinates
                pts_reshaped = pts_array.reshape(-1, 1, 2)
                warped_pts = cv2.perspectiveTransform(pts_reshaped, M)
                
                # Create mask (white on black)
                mask = np.zeros((h, w), dtype=np.uint8)
                cv2.fillPoly(mask, [np.int32(warped_pts)], 255)
                print("DEBUG: [Main] Polygon mask generated.")
            except Exception as e:
                print(f"ERROR: [Main] Failed to generate mask: {e}")
            
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
                    'visible': ch.display_settings.visible
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
        
        # Determine Output Directory
        custom_path = options.get("export_path", "").strip()
        if custom_path:
            output_dir = custom_path
            try:
                os.makedirs(output_dir, exist_ok=True)
            except OSError as e:
                QMessageBox.warning(self, tr("Export Error"), tr("Cannot create custom export directory:\n{0}\nUsing default instead.").format(output_dir))
                output_dir = self.project_model.get_export_path()
        else:
            output_dir = self.project_model.get_export_path()
        
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

        total_exported = 0
        
        try:
            import tifffile
            from src.core.renderer import Renderer

            for i, scene_data in enumerate(scenes_to_export):
                if progress.wasCanceled():
                    break
                
                progress.setLabelText(tr("Exporting sample: {0} ({1}/{2})").format(scene_data.id, i+1, len(scenes_to_export)))
                progress.setValue(i)
                QApplication.processEvents() # Keep UI responsive

                # Get annotations for this scene (if including them)
                if include_ann:
                    if scene_data.id == self.current_scene_id:
                        # For current scene, use the active session's visibility states
                        export_annotations = [ann for ann in self.session.annotations if ann.visible]
                    else:
                        # For other scenes, use their saved annotations
                        # Note: visibility might need to be checked in serialized data too
                        export_annotations = []
                        for ann_dict in scene_data.annotations:
                            if ann_dict.get('visible', True):
                                try:
                                    from src.core.data_model import GraphicAnnotation
                                    export_annotations.append(GraphicAnnotation(**ann_dict))
                                except: pass
                else:
                    export_annotations = []

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
                        
                        for ch in channels:
                            if not ch.display_settings.visible or ch.is_placeholder:
                                continue
                                
                            rgb = Renderer.render_channel(ch, out_depth=out_depth, annotations=export_annotations)
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
                    comp = Renderer.composite(channels, out_depth=out_depth, annotations=export_annotations)
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
                QMessageBox.information(self, tr("Export Successful"), tr("Exported {0} images to:\n{1}").format(total_exported, output_dir))
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
        self.multi_view.render_all()
        if fit:
            self.multi_view.fit_views()

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
                
            self.lbl_status.setText("  ".join(info_parts))
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
                self.control_tabs.addTab(widget, label)
                
        # Restore index if the tab is still visible
        if current_tab_name:
            for i in range(self.control_tabs.count()):
                widget = self.control_tabs.widget(i)
                # Find which key this widget corresponds to
                for key, w, label in self.all_tabs_data:
                    if w == widget and key == current_tab_name:
                        self.control_tabs.setCurrentIndex(i)
                        break

    def on_display_settings_changed(self):
        """Triggers a re-render without resetting view (for adjustment sliders)."""
        if not self.session.channels:
            return
            
        # UI Feedback
        self.lbl_status.setText(tr("Processing Enhancement..."))
        Logger.debug("[Main] Display settings changed -> preview render")
        QApplication.processEvents()
        
        # Use preview mode (downsampling) for responsive slider adjustments
        self.multi_view.render_all(preview=True)
        try:
            self.multi_view.flash_channel(getattr(self, 'active_channel_idx', -1))
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
            self.result_widget.remove_results_for_rois(current_roi_ids)
            
            # 2.1 Remove any OLD virtual overlap results to avoid duplicates
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
            
            with open(file_path, 'w', newline='') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                
                writer.writeheader()
                for data in current_data:
                    writer.writerow(data)
                    
            self.lbl_status.setText(tr("Results saved to {0}").format(file_path))
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
            success = self.save_project()
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
            "<p>Version: 2.0.8</p>"
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
                
                with open(file_path, 'w') as f:
                    json.dump(report, f, indent=4)
                    
            else:
                # CSV Matrix (IoU by default, or ask?)
                # We'll save IoU matrix
                import csv
                with open(file_path, 'w', newline='') as f:
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
    
    app = QApplication(sys.argv)
    
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
