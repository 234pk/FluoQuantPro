import time
import os
from PySide6.QtCore import QObject, QThread, Signal, QTimer, Qt
from src.core.logger import Logger
from src.core.language_manager import tr

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

class WatchdogThread(QThread):
    """
    Background thread that monitors the main thread's responsiveness.
    """
    freeze_detected = Signal(float) # duration in seconds
    
    def __init__(self, monitor):
        super().__init__()
        self.monitor = monitor
        self.setObjectName("PerformanceWatchdog") # Give it a name for easier debugging
        
    def run(self):
        while not self.isInterruptionRequested():
            # Use short sleeps to remain responsive to interruption
            for _ in range(10):
                if self.isInterruptionRequested():
                    return
                time.sleep(0.01) # Check every 10ms instead of 100ms sleep
            
            last_tick = self.monitor.last_tick
            current_time = time.time()
            diff = current_time - last_tick
            
            # USER REQUEST: Prevent false "lag" warnings during normal use.
            # Threshold: 10.0s (Increased from 5.0s to avoid false positives with slow heartbeats)
            if diff > 10.0:
                if not self.monitor.is_frozen:
                    self.monitor.is_frozen = True
                    self.freeze_detected.emit(diff)
            else:
                if self.monitor.is_frozen:
                    self.monitor.is_frozen = False

    def stop(self):
        """Safely stops the thread by requesting interruption and waiting."""
        self.requestInterruption()
        self.quit()
        if not self.wait(500): # Wait up to 500ms
            Logger.warning(tr("[Performance] Watchdog thread did not stop in time, terminating..."))
            self.terminate()
            self.wait() # Ensure it's dead

class MemoryCleanupWorker(QThread):
    """
    Background worker for heavy memory cleanup tasks (GC, OS Trim).
    """
    cleanup_done = Signal(int, tuple) # collected_count, pre_counts

    def run(self):
        import gc
        pre_counts = gc.get_count()
        collected = gc.collect()

        # OS Level Trim (Windows)
        import sys
        if sys.platform == 'win32':
             try:
                 import ctypes
                 # -1, -1 tells Windows to minimize the working set
                 ctypes.windll.kernel32.SetProcessWorkingSetSize(
                     ctypes.windll.kernel32.GetCurrentProcess(), 
                     -1, -1
                 )
             except Exception:
                 pass
        
        self.cleanup_done.emit(collected, pre_counts)

class PerformanceMonitor(QObject):
    """
    Central performance management system.
    """
    _instance = None
    
    # Performance Levels
    LEVEL_AUTO = "auto"
    LEVEL_ULTRA = "ultra"    # Max speed, minimal resolution
    LEVEL_HIGH = "high"      # High speed, low resolution
    LEVEL_BALANCED = "balanced" # Standard speed/quality
    LEVEL_QUALITY = "quality"   # Max quality, full resolution

    # Signals
    lag_detected = Signal(float) # Emitted when a lag spike finishes
    performance_mode_changed = Signal(bool) # True = High Performance (Lower Quality)
    violent_interaction_detected = Signal(bool) # True = High Jitter/Speed detected
    memory_status_updated = Signal(float, float, str) # current_mb, percent, display_text
    memory_threshold_exceeded = Signal(float) # current_gb
    
    cleanup_started = Signal() # Signal emitted when cleanup begins, allowing UI to release references (e.g. UndoStack)
    cleanup_finished = Signal() # Signal emitted when async cleanup completes

    def __init__(self):
        super().__init__()
        self._is_stopping = False # Flag to prevent multiple stops
        self.last_tick = time.time()
        self.is_frozen = False
        self.fps_history = []
        self.jitter_buffer = [] # To detect flickering/unstable rendering
        self.interaction_speed_history = [] # To detect rapid zoom/drag
        
        # Hardware Capabilities
        self.cpu_count = os.cpu_count() or 4
        from PySide6.QtCore import QSettings
        self._settings = QSettings("FluoQuantPro", "Settings")
        self.current_level = self._settings.value("performance/interaction_level", self.LEVEL_AUTO)
        
        if HAS_PSUTIL:
            try:
                total_mem = psutil.virtual_memory().total
            except:
                total_mem = 8 * 1024**3
        else:
            total_mem = 8 * 1024**3
            
        self.is_low_end_machine = self.cpu_count <= 4 or total_mem < 4.1 * 1024**3
        self.suppress_warnings = False # SESSION FLAG: If True, don't show popups until restart
        
        Logger.info(f"[Performance] System: {self.cpu_count} Cores, {total_mem / 1024**3:.1f} GB RAM. LowEnd={self.is_low_end_machine}")
        
        # Dynamic Settings
        self.dynamic_quality = True
        self.render_scale = 1.0
        self.use_antialiasing = not self.is_low_end_machine
        self.is_low_quality = not self.use_antialiasing
        
        # Memory Monitoring Settings
        self.auto_cleanup_enabled = self._settings.value("performance/auto_cleanup", True, type=bool)
        # Default threshold: 75% of total RAM or 6GB, whichever is lower for safety
        default_threshold = min(6.0, (total_mem / 1024**3) * 0.75)
        self.memory_threshold_gb = float(self._settings.value("performance/memory_threshold_gb", default_threshold))
        self._last_cleanup_time = 0
        
        # Start Heartbeat
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._heartbeat)
        self.timer.start(2000) # Increased frequency to 2 seconds for better responsiveness
        
        Logger.info("[Performance] PerformanceMonitor initialized and heartbeat started.")
        
        # Watchdog
        self.watchdog = WatchdogThread(self)
        self.watchdog.freeze_detected.connect(self._on_freeze)
        self.watchdog.start()
        
    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = PerformanceMonitor()
        return cls._instance
        
    def _heartbeat(self):
        """Main thread heart beat."""
        self.last_tick = time.time()
        
        # Monitor Memory
        self._check_memory()
        
    def _get_current_memory_mb(self):
        """Returns the current memory usage of the application in MB."""
        current_mb = 0.0
        try:
            # 1. Try to get process memory via psutil
            if HAS_PSUTIL:
                try:
                    process = psutil.Process()
                    try:
                        mem_info = process.memory_full_info()
                        current_mb = getattr(mem_info, 'uss', mem_info.rss) / (1024 * 1024)
                    except (AttributeError, psutil.AccessDenied, psutil.NoSuchProcess):
                        mem_info = process.memory_info()
                        current_mb = mem_info.rss / (1024 * 1024)
                except Exception:
                    pass

            # 2. Fallback to platform-specific metrics
            if current_mb < 0.1:
                # Only log this once to avoid spam
                if not getattr(self, '_fallback_logged', False):
                    Logger.debug("[Performance] psutil failed or missing. Attempting platform fallback.")
                    self._fallback_logged = True
                    
                import sys
                if sys.platform == 'darwin':
                    try:
                        import resource
                        current_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 * 1024)
                    except:
                        pass
                elif sys.platform == 'win32':
                    # Windows Fallback using ctypes
                    try:
                        import ctypes
                        from ctypes import wintypes
                        
                        # Define SIZE_T for compatibility
                        if hasattr(wintypes, 'SIZE_T'):
                            SIZE_T = wintypes.SIZE_T
                        else:
                            SIZE_T = ctypes.c_size_t

                        class PROCESS_MEMORY_COUNTERS_EX(ctypes.Structure):
                            _fields_ = [
                                ('cb', wintypes.DWORD),
                                ('PageFaultCount', wintypes.DWORD),
                                ('PeakWorkingSetSize', SIZE_T),
                                ('WorkingSetSize', SIZE_T),
                                ('QuotaPeakPagedPoolUsage', SIZE_T),
                                ('QuotaPagedPoolUsage', SIZE_T),
                                ('QuotaPeakNonPagedPoolUsage', SIZE_T),
                                ('QuotaNonPagedPoolUsage', SIZE_T),
                                ('PagefileUsage', SIZE_T),
                                ('PeakPagefileUsage', SIZE_T),
                                ('PrivateUsage', SIZE_T),
                            ]
                            
                        p = ctypes.windll.kernel32.GetCurrentProcess()
                        mem_struct = PROCESS_MEMORY_COUNTERS_EX()
                        mem_struct.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS_EX)
                        if ctypes.windll.psapi.GetProcessMemoryInfo(p, ctypes.byref(mem_struct), ctypes.sizeof(mem_struct)):
                            # Use PrivateUsage for more accurate app memory
                            current_mb = mem_struct.PrivateUsage / (1024 * 1024)
                    except Exception as e:
                        # Logger.debug(f"Windows memory fallback failed: {e}")
                        pass
                    
            if current_mb < 0.1:
                current_mb = 1.0 # Minimum value
                
        except Exception:
            current_mb = 0.0
            
        return current_mb

    def _check_memory(self):
        """Checks current memory usage and triggers cleanup if needed."""
        current_mb = self._get_current_memory_mb()
        sys_percent = 0.0
        current_gb = current_mb / 1024.0

        try:
            # Try to get system-wide memory percentage
            if HAS_PSUTIL:
                try:
                    sys_percent = psutil.virtual_memory().percent
                except:
                    pass
            
            # Final safety check and UI update
            if current_mb < 0.1 and not HAS_PSUTIL:
                self.memory_status_updated.emit(0, 0, "RAM: N/A")
                return
            
            # USER REQUEST: Clarify that the percentage is SYSTEM RAM, not APP RAM
            display_text = f"App: {current_mb:.1f}MB"
            if sys_percent > 0:
                display_text += f" (Sys: {sys_percent:.0f}%)"
                
            self.memory_status_updated.emit(current_mb, sys_percent, display_text)
            
            # Check threshold
            if hasattr(self, 'auto_cleanup_enabled') and self.auto_cleanup_enabled and current_gb > self.memory_threshold_gb:
                # Rate limit cleanup to once every 30 seconds
                if time.time() - getattr(self, '_last_cleanup_time', 0) > 30:
                    self.trigger_cleanup(current_gb)
                else:
                    # Debug log to explain why we are not cleaning up despite high memory
                    # Only log occasionally (e.g. if > 10s passed since check) to avoid spamming debug log
                    pass 
            elif current_gb > self.memory_threshold_gb:
                # Memory is high, but auto-cleanup is DISABLED or Missing
                # Log this state once in a while so we know why it's not triggering
                if time.time() - getattr(self, '_last_debug_log_time', 0) > 60:
                    Logger.debug(f"[Performance] Memory High ({current_gb:.1f}GB) but Auto-Cleanup is {getattr(self, 'auto_cleanup_enabled', 'Missing')}.")
                    self._last_debug_log_time = time.time()

                    
        except Exception as e:
            Logger.error(f"[Performance] Memory check failed: {e}")
            self.memory_status_updated.emit(0, 0, "RAM: Error")

    def trigger_cleanup(self, current_gb=None):
        """Forces a memory cleanup (Async)."""
        # Prevent multiple concurrent cleanups
        if hasattr(self, '_cleanup_worker') and self._cleanup_worker is not None and self._cleanup_worker.isRunning():
            return

        self._last_cleanup_time = time.time()
        
        # Store start memory for comparison later
        self._cleanup_start_mb = self._get_current_memory_mb()
        self._cleanup_current_gb = current_gb
        
        if current_gb is not None:
            Logger.warning(f"[Performance] Memory threshold exceeded ({current_gb:.1f} GB). Triggering async cleanup...")
        else:
            Logger.warning("[Performance] Cleanup triggered manually or by scene switch.")

        # 1. Sync Phase: Clear UI/App Caches (Must be done on Main Thread)
        self.cleanup_started.emit()
        
        from src.core.renderer import Renderer
        Renderer.clear_cache()
        Logger.info("[Performance] Renderer caches cleared.")
        
        try:
            from src.core.cache_manager import SceneCacheManager
            SceneCacheManager.instance().handle_low_memory()
        except ImportError:
            pass
            
        # 2. Async Phase: GC and OS Trim
        self._cleanup_worker = MemoryCleanupWorker()
        self._cleanup_worker.cleanup_done.connect(self._on_cleanup_done)
        self._cleanup_worker.start()

    def _on_cleanup_done(self, collected, pre_counts):
        """Called when background cleanup finishes."""
        import sys
        Logger.info(f"[Performance] Async GC collected {collected} objects. Pre-counts: {pre_counts}")
        if sys.platform == 'win32':
             Logger.info("[Performance] Windows Working Set trimmed (Async).")

        self.cleanup_finished.emit()
        self.memory_threshold_exceeded.emit(self._cleanup_current_gb or 0.0)
        
        # Check effectiveness
        end_mb = self._get_current_memory_mb()
        dropped_mb = getattr(self, '_cleanup_start_mb', end_mb) - end_mb
        
        if dropped_mb < 50 and (end_mb / 1024.0) > self.memory_threshold_gb:
            Logger.warning(f"[Performance] Cleanup ineffective (Dropped {dropped_mb:.1f} MB). Backing off for 60s.")
            self._last_cleanup_time = time.time() + 60
            
        # Clean up worker reference
        self._cleanup_worker.deleteLater()
        self._cleanup_worker = None

    def set_memory_settings(self, enabled, threshold_gb):
        """Updates memory monitoring settings."""
        self.auto_cleanup_enabled = enabled
        self.memory_threshold_gb = threshold_gb
        self._settings.setValue("performance/auto_cleanup", enabled)
        self._settings.setValue("performance/memory_threshold_gb", threshold_gb)
        Logger.info(f"[Performance] Memory settings updated: AutoCleanup={enabled}, Threshold={threshold_gb}GB")
        
    def _on_freeze(self, duration):
        # USER REQUEST: Reduce annoying lag warnings. 
        # Only log/emit if it's a significant freeze (> 10s)
        if duration > 10.0:
            Logger.warning(f"[Performance] Significant freeze detected! Duration: {duration:.2f}s")
            self.optimize_for_speed()
            self.lag_detected.emit(duration)

    def set_performance_level(self, level):
        """Manually sets the performance level."""
        if level in [self.LEVEL_AUTO, self.LEVEL_ULTRA, self.LEVEL_HIGH, self.LEVEL_BALANCED, self.LEVEL_QUALITY]:
            self.current_level = level
            self._settings.setValue("performance/interaction_level", level)
            
            # Trigger immediate quality update if needed
            is_high_perf = level in [self.LEVEL_ULTRA, self.LEVEL_HIGH]
            if level == self.LEVEL_AUTO:
                is_high_perf = self.is_low_quality
                
            self.performance_mode_changed.emit(is_high_perf)
            Logger.info(f"[Performance] Level set to: {level}")

    def get_preview_limit(self, base_limit=1024):
        """Returns a recommended resolution limit for preview rendering."""
        level = self.current_level
        
        # 1. Manual Overrides
        if level == self.LEVEL_ULTRA:
            return min(base_limit, 256)
        elif level == self.LEVEL_HIGH:
            return min(base_limit, 512)
        elif level == self.LEVEL_BALANCED:
            return min(base_limit, 1024)
        elif level == self.LEVEL_QUALITY:
            return max(base_limit, 2048) # Allow higher res for quality mode
            
        # 2. Auto Logic (Default)
        if self.is_low_end_machine:
            return min(base_limit, 384) # Lowered from 512
        
        # If we have recently detected lag, drop the limit
        if self.is_low_quality:
            return min(base_limit, 512) # Lowered from 768
            
        return base_limit

    def optimize_for_speed(self):
        """Downgrades rendering settings to recover responsiveness."""
        if self.use_antialiasing:
            Logger.info("[Performance] Disabling Antialiasing due to lag.")
            self.use_antialiasing = False
            self.is_low_quality = True
            self.performance_mode_changed.emit(True)
            
    def restore_quality(self):
        """Restores high quality settings."""
        if not self.is_low_end_machine and not self.use_antialiasing:
            Logger.info("[Performance] Restoring Antialiasing.")
            self.use_antialiasing = True
            self.is_low_quality = False
            self.performance_mode_changed.emit(False)

    def report_render_time(self, ms):
        """CanvasView calls this to report frame time."""
        self.fps_history.append(ms)
        if len(self.fps_history) > 1:
            # Calculate Jitter (difference between consecutive frame times)
            jitter = abs(ms - self.fps_history[-2])
            self.jitter_buffer.append(jitter)
            if len(self.jitter_buffer) > 20:
                self.jitter_buffer.pop(0)
                
            # Detect flickering (high jitter + high frame time)
            if len(self.jitter_buffer) >= 10:
                avg_jitter = sum(self.jitter_buffer) / len(self.jitter_buffer)
                if avg_jitter > 50 and ms > 100: # High jitter and slow rendering
                    self.violent_interaction_detected.emit(True)
                    Logger.warning(f"[Performance] Violent flickering detected! Jitter: {avg_jitter:.1f}ms")

        if len(self.fps_history) > 50:
            self.fps_history.pop(0)
            
        avg_time = sum(self.fps_history) / len(self.fps_history)
        if avg_time > 100: # < 10 FPS
            self.optimize_for_speed()
        elif avg_time < 30: # > 33 FPS
            self.restore_quality()

    def report_interaction_speed(self, speed):
        """Reports interaction speed (e.g. zoom velocity or drag delta)."""
        self.interaction_speed_history.append(speed)
        if len(self.interaction_speed_history) > 10:
            self.interaction_speed_history.pop(0)
            
        avg_speed = sum(self.interaction_speed_history) / len(self.interaction_speed_history)
        if avg_speed > 0.5: # Arbitrary threshold for "violent" interaction
            self.violent_interaction_detected.emit(True)

    def stop(self):
        """Stops the watchdog thread and timers safely."""
        if self._is_stopping:
            return
        self._is_stopping = True
        
        Logger.info("[Performance] Stopping monitor and watchdog thread...")
        
        # 1. Stop Timer first
        if hasattr(self, 'timer') and self.timer.isActive():
            self.timer.stop()
            
        # 2. Stop Thread (Blocking)
        if hasattr(self, 'watchdog'):
            if self.watchdog.isRunning():
                self.watchdog.stop()
            # Explicitly delete reference if possible, but the object is still there
            
        Logger.info("[Performance] Monitor stopped successfully.")
            
    def __del__(self):
        # Del is unreliable in Python for thread cleanup
        # but let's try one last time
        try:
            self.stop()
        except:
            pass
