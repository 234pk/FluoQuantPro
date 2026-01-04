
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
            
        # Create logs directory if it doesn't exist
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
            
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
            
        # Generate filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = os.path.join(log_dir, f"debug_{timestamp}.log")
        
        # Configure logging
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s [%(levelname)s] [%(filename)s:%(lineno)d] %(message)s',
            handlers=[
                logging.FileHandler(log_file, encoding='utf-8'),
                logging.StreamHandler(sys.stdout)
            ]
        )
        
        # Suppress Matplotlib font manager debug logs
        logging.getLogger('matplotlib').setLevel(logging.WARNING)
        
        logging.info(f"Logging initialized. Log file: {log_file}")
        cls._instance = logging.getLogger("FluoQuantPro")
        return cls._instance

    @staticmethod
    def log(message, level=logging.INFO):
        if not Logger._instance:
            Logger.setup()
        Logger._instance.log(level, message)

    @staticmethod
    def debug(message):
        if not Logger._instance:
            Logger.setup()
        Logger._instance.debug(message)
        
    @staticmethod
    def info(message):
        if not Logger._instance:
            Logger.setup()
        Logger._instance.info(message)
        
    @staticmethod
    def warning(message):
        if not Logger._instance:
            Logger.setup()
        Logger._instance.warning(message)
        
    @staticmethod
    def error(message):
        if not Logger._instance:
            Logger.setup()
        Logger._instance.error(message)
