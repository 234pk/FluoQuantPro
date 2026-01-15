import os
import sys
import uuid
import platform
import json
import threading
from PySide6.QtCore import QSettings, QCoreApplication
from src.core.logger import Logger

class TelemetryManager:
    """
    Handles anonymous usage statistics collection.
    Follows privacy guidelines for Windows and macOS:
    - No PII (Personally Identifiable Information) collected.
    - Persistent UUID is randomly generated and stored locally.
    - Asynchronous reporting to avoid blocking the main thread.
    - Respects user opt-out settings.
    """
    
    _instance = None
    TELEMETRY_URL = "https://api.fluoquant.pro/v1/telemetry" # Placeholder
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(TelemetryManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
            
        self.settings = QSettings("FluoQuantPro", "AppSettings")
        self._initialized = True
        self._ensure_uuid()

    def _ensure_uuid(self):
        """Ensures a persistent random UUID exists in settings."""
        if not self.settings.contains("telemetry/uuid"):
            new_uuid = str(uuid.uuid4())
            self.settings.setValue("telemetry/uuid", new_uuid)
            Logger.info(f"[Telemetry] Generated new anonymous UUID: {new_uuid}")
        
    def get_uuid(self):
        return self.settings.value("telemetry/uuid", "")

    def is_enabled(self):
        # Default to True, but allow user to disable in settings
        return self.settings.value("telemetry/enabled", True, type=bool)

    def set_enabled(self, enabled):
        self.settings.setValue("telemetry/enabled", enabled)

    def report_usage(self, event_type="startup"):
        """Sends an anonymous usage report asynchronously."""
        if not self.is_enabled():
            Logger.debug("[Telemetry] Disabled by user.")
            return

        # Check if we already reported today to avoid duplicate counting
        import datetime
        today = datetime.date.today().isoformat()
        last_report = self.settings.value("telemetry/last_report_date", "")
        
        if event_type == "startup" and last_report == today:
            Logger.debug(f"[Telemetry] Already reported startup for today ({today}). Skipping.")
            return

        thread = threading.Thread(target=self._send_report, args=(event_type, today), daemon=True)
        thread.start()

    def _send_report(self, event_type, today_str):
        """Internal method to perform the network request."""
        try:
            import time
            # Prepare anonymous payload
            payload = {
                "uuid": self.get_uuid(),
                "event": event_type,
                "platform": platform.system(),
                "os_version": platform.version(),
                "python_version": platform.python_version(),
                "app_version": "3.0.0",
                "arch": platform.machine(),
                "timestamp": time.time()
            }
            
            Logger.debug(f"[Telemetry] Sending report via Tencent CLS: {payload}")
            
            # Use Tencent CLS for reporting
            from src.core.tencent_cls import cls_manager
            success = cls_manager.send_startup_event(payload)
            
            if success:
                Logger.debug("[Telemetry] Report sent successfully to Tencent Cloud.")
                # Save the date only after successful report
                if event_type == "startup":
                    self.settings.setValue("telemetry/last_report_date", today_str)
            else:
                Logger.debug("[Telemetry] Failed to send report to Tencent Cloud.")
                    
        except Exception as e:
            # Silently fail on network errors as telemetry is not critical
            Logger.debug(f"[Telemetry] Error in reporting: {e}")

# Global instance
telemetry = TelemetryManager()
