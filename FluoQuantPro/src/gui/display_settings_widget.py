import os
import ctypes
import cv2
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QGroupBox, QRadioButton, 
                               QLabel, QHBoxLayout, QComboBox, QSizePolicy, QCheckBox)
from PySide6.QtCore import QSettings
from src.core.language_manager import LanguageManager, tr

class DisplaySettingsWidget(QWidget):
    """
    Settings widget for display quality and performance optimization.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings = QSettings("FluoQuantPro", "Settings")
        self.setup_ui()
        self.load_settings()
        LanguageManager.instance().language_changed.connect(self.retranslate_ui)

    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # 1. Image Loading Quality
        self.quality_group = QGroupBox(tr("Rendering Quality"))
        quality_layout = QVBoxLayout(self.quality_group)
        
        self.quality_combo = QComboBox()
        self.quality_combo.addItem(tr("Performance (Downsampled)"), "performance")
        self.quality_combo.addItem(tr("Balanced (Recommended)"), "balanced")
        self.quality_combo.addItem(tr("High Quality (Full Resolution)"), "high")
        quality_layout.addWidget(self.quality_combo)
        
        self.lbl_recommendation = QLabel(tr("System Analysis: Detecting..."))
        self.lbl_recommendation.setProperty("role", "description")
        quality_layout.addWidget(self.lbl_recommendation)
        
        self.desc = QLabel(tr("Higher quality requires more RAM and GPU resources. ") + 
                      tr("Performance mode is recommended for datasets > 2GB."))
        self.desc.setWordWrap(True)
        self.desc.setProperty("role", "description")
        quality_layout.addWidget(self.desc)
        
        layout.addWidget(self.quality_group)
        
        # 2. Cache Settings
        self.cache_group = QGroupBox(tr("Memory Usage"))
        cache_layout = QVBoxLayout(self.cache_group)
        
        self.cb_precache = QComboBox()
        self.cb_precache.addItem(tr("No Pre-caching"), "none")
        self.cb_precache.addItem(tr("Pre-cache current sample"), "current")
        self.cb_precache.addItem(tr("Pre-cache next 5 samples"), "next5")
        self.lbl_precache = QLabel(tr("Pre-caching Strategy:"))
        cache_layout.addWidget(self.lbl_precache)
        cache_layout.addWidget(self.cb_precache)
        
        layout.addWidget(self.cache_group)

        # 3. GPU Acceleration (OpenCL)
        self.gpu_group = QGroupBox(tr("GPU Acceleration (OpenCL)"))
        gpu_layout = QVBoxLayout(self.gpu_group)

        self.chk_opencl = QCheckBox(tr("Enable OpenCL Acceleration"))
        self.chk_opencl.setToolTip(tr("Uses GPU for faster image rendering and enhancement."))
        gpu_layout.addWidget(self.chk_opencl)

        self.lbl_gpu_info = QLabel(tr("Detecting GPU..."))
        self.lbl_gpu_info.setWordWrap(True)
        self.lbl_gpu_info.setProperty("role", "description")
        gpu_layout.addWidget(self.lbl_gpu_info)

        layout.addWidget(self.gpu_group)
        
        layout.addStretch()
        
        self.analyze_system()

    def retranslate_ui(self):
        self.quality_group.setTitle(tr("Rendering Quality"))
        
        current_quality_data = self.quality_combo.currentData()
        self.quality_combo.clear()
        self.quality_combo.addItem(tr("Performance (Downsampled)"), "performance")
        self.quality_combo.addItem(tr("Balanced (Recommended)"), "balanced")
        self.quality_combo.addItem(tr("High Quality (Full Resolution)"), "high")
        idx = self.quality_combo.findData(current_quality_data)
        if idx >= 0: self.quality_combo.setCurrentIndex(idx)
        
        self.desc.setText(tr("Higher quality requires more RAM and GPU resources. ") + 
                      tr("Performance mode is recommended for datasets > 2GB."))
        
        self.cache_group.setTitle(tr("Memory Usage"))
        self.lbl_precache.setText(tr("Pre-caching Strategy:"))
        
        current_precache_data = self.cb_precache.currentData()
        self.cb_precache.clear()
        self.cb_precache.addItem(tr("No Pre-caching"), "none")
        self.cb_precache.addItem(tr("Pre-cache current sample"), "current")
        self.cb_precache.addItem(tr("Pre-cache next 5 samples"), "next5")
        idx = self.cb_precache.findData(current_precache_data)
        if idx >= 0: self.cb_precache.setCurrentIndex(idx)
        
        self.gpu_group.setTitle(tr("GPU Acceleration (OpenCL)"))
        self.chk_opencl.setText(tr("Enable OpenCL Acceleration"))
        self.chk_opencl.setToolTip(tr("Uses GPU for faster image rendering and enhancement."))
        
        self.analyze_system()

    def analyze_system(self):
        """Analyzes hardware to provide a recommendation and detect GPU."""
        try:
            ram_gb = self._get_ram_gb()
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
        except Exception as e:
            self.lbl_recommendation.setText(tr("Recommendation: Balanced (Auto)"))

        # Detect OpenCL
        try:
            has_ocl = cv2.ocl.haveOpenCL()
            if has_ocl:
                dev = cv2.ocl.Device.getDefault()
                name = dev.name()
                ver = dev.version()
                driver = dev.driverVersion()
                info = tr("Detected: {0}\nVersion: {1}\nDriver: {2}").format(name, ver, driver)
                self.lbl_gpu_info.setText(info)
                self.chk_opencl.setEnabled(True)
            else:
                self.lbl_gpu_info.setText(tr("OpenCL Not Available: No compatible GPU detected or driver issue."))
                self.chk_opencl.setChecked(False)
                self.chk_opencl.setEnabled(False)
        except Exception as e:
            self.lbl_gpu_info.setText(tr("GPU Detection Error: {0}").format(str(e)))
            self.chk_opencl.setEnabled(False)

    def _get_ram_gb(self):
        """Cross-platform way to get total physical RAM in GB."""
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
            return stat.ullTotalPhys / (1024**3)
        else:
            # Simple fallback for linux if /proc/meminfo exists
            try:
                with open('/proc/meminfo', 'r') as f:
                    for line in f:
                        if 'MemTotal' in line:
                            return int(line.split()[1]) / (1024*1024)
            except:
                pass
        return 8.0 # Default fallback

    def load_settings(self):
        quality = self.settings.value("display/quality_key", "balanced")
        index = self.quality_combo.findData(quality)
        if index >= 0:
            self.quality_combo.setCurrentIndex(index)
        else:
            # Fallback for old settings that used text
            quality_text = self.settings.value("display/quality", "Balanced (Recommended)")
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

    def save_settings(self):
        self.settings.setValue("display/quality_key", self.quality_combo.currentData())
        self.settings.setValue("display/precache_key", self.cb_precache.currentData())
        self.settings.setValue("display/opencl_enabled", self.chk_opencl.isChecked())
        
        # Apply OpenCL setting immediately
        if cv2.ocl.haveOpenCL():
            cv2.ocl.setUseOpenCL(self.chk_opencl.isChecked())
            print(f"[DisplaySettings] OpenCL Acceleration set to: {self.chk_opencl.isChecked()}")
