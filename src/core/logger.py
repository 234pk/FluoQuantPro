
import os
import sys
import logging
from datetime import datetime

class Logger:
    _instance = None
    
    @classmethod
    def setup(cls, log_dir="logs"):
        """Setup global logging configuration."""
        if cls._instance:
            return cls._instance
            
        # Determine the log directory based on the platform if default is used
        if log_dir == "logs":
            if sys.platform == 'darwin':
                # macOS: ~/Library/Logs/FluoQuantPro
                log_dir = os.path.expanduser("~/Library/Logs/FluoQuantPro")
            elif sys.platform == 'win32':
                # Windows: %APPDATA%/FluoQuantPro/logs
                appdata = os.environ.get('APPDATA')
                if appdata:
                    log_dir = os.path.join(appdata, "FluoQuantPro", "logs")
            
        # Create logs directory if it doesn't exist
        try:
            if not os.path.exists(log_dir):
                os.makedirs(log_dir, exist_ok=True)
        except Exception as e:
            # Fallback to current directory if system log path is not accessible
            print(f"[Logger] Failed to create system log dir {log_dir}: {e}")
            log_dir = "logs"
            if not os.path.exists(log_dir):
                os.makedirs(log_dir, exist_ok=True)
            
        # Cleanup old logs (older than 7 days)
        try:
            current_time = datetime.now()
            for fname in os.listdir(log_dir):
                if fname.startswith("debug_") and fname.endswith(".log"):
                    file_path = os.path.join(log_dir, fname)
                    file_modified = datetime.fromtimestamp(os.path.getmtime(file_path))
                    if (current_time - file_modified).days > 7:
                        try:
                            os.remove(file_path)
                            print(f"[Logger] Deleted old log file: {fname}")
                        except Exception as e:
                            print(f"[Logger] Failed to delete old log {fname}: {e}")
        except Exception as e:
            print(f"[Logger] Error cleaning up old logs: {e}")
            
        # Generate filenames
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        latest_log = os.path.join(log_dir, "latest.log")
        archive_log = os.path.join(log_dir, f"debug_{timestamp}.log")
        
        # If latest.log exists, rename it to archive it before starting new session
        if os.path.exists(latest_log):
            try:
                os.rename(latest_log, archive_log)
            except Exception as e:
                print(f"[Logger] Failed to archive previous log: {e}")
                # If rename fails, we'll just append or overwrite latest.log
        
        # Configure logging
        # Root logger captures everything (DEBUG level)
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG)
        
        # File Handler: DEBUG level (detailed logs for troubleshooting)
        file_handler = logging.FileHandler(latest_log, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] [%(filename)s:%(lineno)d] %(message)s'))
        
        # Console Handler: INFO level (cleaner terminal output)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
        
        # Reset handlers to avoid duplicates on reload
        root_logger.handlers = []
        root_logger.addHandler(file_handler)
        root_logger.addHandler(console_handler)
        
        # Suppress Matplotlib font manager debug logs
        logging.getLogger('matplotlib').setLevel(logging.WARNING)
        
        logging.info(f"Logging initialized. Log file: {latest_log}")
        cls._instance = logging.getLogger("FluoQuantPro")
        cls._log_dir = log_dir
        return cls._instance

    @classmethod
    def get_log_dir(cls):
        """Returns the absolute path to the log directory."""
        if not cls._instance:
            cls.setup()
        return cls._log_dir

    @staticmethod
    def log(message, level=logging.INFO):
        if not Logger._instance:
            Logger.setup()
        Logger._instance.log(level, message)

    @staticmethod
    def debug(message, **kwargs):
        if not Logger._instance:
            Logger.setup()
        Logger._instance.debug(message, **kwargs)
        
    @staticmethod
    def info(message, **kwargs):
        if not Logger._instance:
            Logger.setup()
        Logger._instance.info(message, **kwargs)
        
    @staticmethod
    def warning(message, **kwargs):
        if not Logger._instance:
            Logger.setup()
        Logger._instance.warning(message, **kwargs)
        
    @staticmethod
    def error(message, **kwargs):
        if not Logger._instance:
            Logger.setup()
        Logger._instance.error(message, **kwargs)
