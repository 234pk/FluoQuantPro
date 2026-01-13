import os
import ctypes
import cv2
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QGroupBox, QRadioButton, 
                               QLabel, QHBoxLayout, QComboBox, QSizePolicy)
from PySide6.QtCore import QSettings, QThread, Signal
from src.core.language_manager import LanguageManager, tr
from src.gui.toggle_switch import ToggleSwitch

class SystemAnalysisThread(QThread):
    """Background thread to analyze hardware without freezing UI."""
    finished = Signal(float, str, bool)

    def run(self):
        # 1. Get RAM
        ram_gb = 8.0
        try:
            if os.name == 'nt':
                class MEMORYSTATUSEX(ctypes.Structure):
                    _fields_ = [
                        ("dwLength", ctypes.c_ulong),
                        ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                    ]
                stat = MEMORYSTATUSEX()
                stat.dwLength = ctypes.sizeof(stat)
                ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
                ram_gb = stat.ullTotalPhys / (1024**3)
            else:
                with open('/proc/meminfo', 'r') as f:
                    for line in f:
                        if 'MemTotal' in line:
                            ram_gb = int(line.split()[1]) / (1024*1024)
                            break
        except:
            pass

        # 2. Get GPU Info (The slow part)
        gpu_info = ""
        ocl_available = False
        try:
            ocl_available = cv2.ocl.haveOpenCL()
            if ocl_available:
                dev = cv2.ocl.Device.getDefault()
                name = dev.name()
                ver = dev.version()
                driver = dev.driverVersion()
                gpu_info = tr("Detected: {0}\nVersion: {1}\nDriver: {2}").format(name, ver, driver)
            else:
                gpu_info = tr("OpenCL Not Available: No compatible GPU detected or driver issue.")
        except Exception as e:
            gpu_info = tr("GPU Detection Error: {0}").format(str(e))
            ocl_available = False
        
        self.finished.emit(ram_gb, gpu_info, ocl_available)

class DisplaySettingsWidget(QWidget):
    """
    Settings widget for display quality and performance optimization.
    """
    _cached_ram = None
    _cached_gpu_info = None
    _cached_ocl_available = None

    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings = QSettings("FluoQuantPro", "Settings")
        self.setup_ui()
        self.load_settings()
        LanguageManager.instance().language_changed.connect(self.retranslate_ui)

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(15)

        # 1. Rendering Quality Group
        self.quality_group = QGroupBox(tr("Rendering Quality"))
        q_layout = QVBoxLayout(self.quality_group)
        
        h_q = QHBoxLayout()
        h_q.addWidget(QLabel(tr("Preset:")))
        self.quality_combo = QComboBox()
        self.quality_combo.addItem(tr("1K (Performance)"), "performance")
        self.quality_combo.addItem(tr("2.5K (Balanced)"), "balanced")
        self.quality_combo.addItem(tr("4K (Ultra High)"), "4k")
        self.quality_combo.addItem(tr("Original"), "high")
        h_q.addWidget(self.quality_combo)
        q_layout.addLayout(h_q)
        
        self.lbl_recommendation = QLabel()
        self.lbl_recommendation.setWordWrap(True)
        self.lbl_recommendation.setStyleSheet("font-style: italic; color: gray;")
        q_layout.addWidget(self.lbl_recommendation)
        
        h_pre = QHBoxLayout()
        h_pre.addWidget(QLabel(tr("Caching Strategy:")))
        self.cb_precache = QComboBox()
        self.cb_precache.addItem(tr("No Pre-caching"), "none")
        self.cb_precache.addItem(tr("Pre-cache current sample"), "current")
        self.cb_precache.addItem(tr("Aggressive Pre-cache (All)"), "all")
        h_pre.addWidget(self.cb_precache)
        q_layout.addLayout(h_pre)
        
        layout.addWidget(self.quality_group)

        # 2. GPU Acceleration Group
        self.gpu_group = QGroupBox(tr("GPU Acceleration"))
        gpu_layout = QVBoxLayout(self.gpu_group)
        
        h_ocl = QHBoxLayout()
        self.lbl_gpu_toggle = QLabel(tr("Enable OpenCL Acceleration"))
        h_ocl.addWidget(self.lbl_gpu_toggle)
        h_ocl.addStretch()
        self.chk_opencl = ToggleSwitch()
        h_ocl.addWidget(self.chk_opencl)
        gpu_layout.addLayout(h_ocl)
        
        self.lbl_gpu_info = QLabel(tr("Detecting GPU..."))
        self.lbl_gpu_info.setWordWrap(True)
        self.lbl_gpu_info.setStyleSheet("font-size: 10px; color: #888;")
        gpu_layout.addWidget(self.lbl_gpu_info)
        
        layout.addWidget(self.gpu_group)
        
        # 3. Interpolation Method Group
        self.interpolation_group = QGroupBox(tr("Scaling Clarity"))
        interp_layout = QVBoxLayout(self.interpolation_group)
        
        h_interp = QHBoxLayout()
        h_interp.addWidget(QLabel(tr("Algorithm:")))
        self.interp_combo = QComboBox()
        self.interp_combo.addItem(tr("Nearest Neighbor (Fastest)"), "nearest")
        self.interp_combo.addItem(tr("Bilinear (Smooth)"), "bilinear")
        self.interp_combo.addItem(tr("Bicubic (Sharper)"), "bicubic")
        self.interp_combo.addItem(tr("Lanczos (Best Quality)"), "lanczos")
        h_interp.addWidget(self.interp_combo)
        interp_layout.addLayout(h_interp)
        
        self.lbl_interp_info = QLabel(tr("Controls the image quality when zooming. Higher quality may impact performance."))
        self.lbl_interp_info.setWordWrap(True)
        self.lbl_interp_info.setStyleSheet("font-style: italic; color: gray;")
        interp_layout.addWidget(self.lbl_interp_info)
        
        layout.addWidget(self.interpolation_group)
        
        layout.addStretch()
        
        # Only run analysis if not cached
        self.analyze_system()

    def retranslate_ui(self):
        self.quality_group.setTitle(tr("Rendering Quality"))
        self.quality_combo.setItemText(0, tr("1K (Performance)"))
        self.quality_combo.setItemText(1, tr("2.5K (Balanced)"))
        self.quality_combo.setItemText(2, tr("4K (Ultra High)"))
        self.quality_combo.setItemText(3, tr("Original"))
        
        self.cb_precache.setItemText(0, tr("No Pre-caching"))
        self.cb_precache.setItemText(1, tr("Pre-cache current sample"))
        self.cb_precache.setItemText(2, tr("Aggressive Pre-cache (All)"))
        
        self.gpu_group.setTitle(tr("GPU Acceleration"))
        self.lbl_gpu_toggle.setText(tr("Enable OpenCL Acceleration"))
        self.chk_opencl.setToolTip(tr("Uses GPU for faster image rendering and enhancement."))
        
        self.interpolation_group.setTitle(tr("Scaling Clarity"))
        self.interp_combo.setItemText(0, tr("Nearest Neighbor (Fastest)"))
        self.interp_combo.setItemText(1, tr("Bilinear (Smooth)"))
        self.interp_combo.setItemText(2, tr("Bicubic (Sharper)"))
        self.interp_combo.setItemText(3, tr("Lanczos (Best Quality)"))
        self.lbl_interp_info.setText(tr("Controls the image quality when zooming. Higher quality may impact performance."))
        
        if hasattr(self, '_analysis_thread') and self._analysis_thread.isRunning():
            self.lbl_recommendation.setText(tr("Analyzing system performance..."))
            self.lbl_gpu_info.setText(tr("Detecting GPU acceleration support..."))
        else:
            self.update_system_info_labels()
        
        # Do NOT call analyze_system() here, just update text if needed
        self.update_system_info_labels()

    def update_system_info_labels(self):
        """Update labels using cached or detected system info."""
        if self._cached_ram is not None:
            ram_gb = self._cached_ram
            if ram_gb < 8:
                rec = tr("Performance")
                reason = tr("Low RAM detected ({0:.1f} GB)").format(ram_gb)
            elif ram_gb < 16:
                rec = tr("Balanced")
                reason = tr("Moderate RAM detected ({0:.1f} GB)").format(ram_gb)
            else:
                rec = tr("High Quality")
                reason = tr("Sufficient RAM detected ({0:.1f} GB)").format(ram_gb)
            self.lbl_recommendation.setText(tr("Recommendation: {0} (Reason: {1})").format(rec, reason))

        if self._cached_gpu_info:
            self.lbl_gpu_info.setText(self._cached_gpu_info)
        
        if self._cached_ocl_available is not None:
            self.chk_opencl.setEnabled(self._cached_ocl_available)

    def analyze_system(self):
        """Analyzes hardware once and caches results."""
        # Check if already analyzing or cached
        if hasattr(self, '_analysis_thread') and self._analysis_thread.isRunning():
            return
            
        if DisplaySettingsWidget._cached_ram is not None and DisplaySettingsWidget._cached_gpu_info is not None:
            self.update_system_info_labels()
            return

        # Start background analysis
        self.lbl_recommendation.setText(tr("Analyzing system performance..."))
        self.lbl_gpu_info.setText(tr("Detecting GPU acceleration support..."))
        
        self._analysis_thread = SystemAnalysisThread()
        self._analysis_thread.finished.connect(self._on_analysis_finished)
        self._analysis_thread.start()

    def _on_analysis_finished(self, ram_gb, gpu_info, ocl_available):
        """Callback when background analysis is complete."""
        DisplaySettingsWidget._cached_ram = ram_gb
        DisplaySettingsWidget._cached_gpu_info = gpu_info
        DisplaySettingsWidget._cached_ocl_available = ocl_available
        
        self.update_system_info_labels()
        
        # Clean up thread
        self._analysis_thread.deleteLater()

    def _get_ram_gb(self):
        # This is now handled in the thread, but kept for compatibility if needed
        return DisplaySettingsWidget._cached_ram or 8.0

    def load_settings(self):
        # Migrate old 4K setting if quality_key is not set yet
        has_quality_key = self.settings.contains("display/quality_key")
        mode_4k = self.settings.value("display/mode_4k", False, type=bool)
        
        if not has_quality_key and mode_4k:
            quality = "4k"
        else:
            quality = self.settings.value("display/quality_key", "balanced")
            
        index = self.quality_combo.findData(quality)
        if index >= 0:
            self.quality_combo.setCurrentIndex(index)
        else:
            # Fallback for old settings that used text
            quality_text = self.settings.value("display/quality", "2.5K (Balanced)")
            index = self.quality_combo.findText(quality_text)
            if index >= 0:
                self.quality_combo.setCurrentIndex(index)
            
        precache = self.settings.value("display/precache_key", "current")
        index = self.cb_precache.findData(precache)
        if index >= 0:
            self.cb_precache.setCurrentIndex(index)
        else:
            # Fallback for old settings that used text
            precache_text = self.settings.value("display/precache", "Pre-cache current sample")
            index = self.cb_precache.findText(precache_text)
            if index >= 0:
                self.cb_precache.setCurrentIndex(index)

        opencl_enabled = self.settings.value("display/opencl_enabled", True, type=bool)
        if self.chk_opencl.isEnabled():
            self.chk_opencl.setChecked(opencl_enabled)

        interpolation = self.settings.value("display/interpolation", "bicubic")
        index = self.interp_combo.findData(interpolation)
        if index >= 0:
            self.interp_combo.setCurrentIndex(index)

    def save_settings(self):
        quality = self.quality_combo.currentData()
        self.settings.setValue("display/quality_key", quality)
        
        # Define resolution limits for each quality mode
        limits = {
            "performance": 1024,
            "balanced": 2560,
            "4k": 3840,
            "high": -1  # -1 indicates no limit
        }
        self.settings.setValue("display/resolution_limit", limits.get(quality, 2560))
        
        self.settings.setValue("display/precache_key", self.cb_precache.currentData())
        self.settings.setValue("display/opencl_enabled", self.chk_opencl.isChecked())
        
        # 4K mode is now part of quality setting
        mode_4k = (quality == "4k")
        self.settings.setValue("display/mode_4k", mode_4k)
        
        interpolation = self.interp_combo.currentData()
        self.settings.setValue("display/interpolation", interpolation)
        
        # Apply OpenCL setting immediately
        if cv2.ocl.haveOpenCL():
            cv2.ocl.setUseOpenCL(self.chk_opencl.isChecked())
            print(f"[DisplaySettings] OpenCL Acceleration set to: {self.chk_opencl.isChecked()}")
            
        if mode_4k:
             print("[DisplaySettings] 4K Ultra quality enabled. High-DPI optimizations applied.")
