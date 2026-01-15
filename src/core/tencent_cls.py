import os
import sys
import logging
import threading
from PySide6.QtCore import QSettings

class TencentCLSManager:
    """
    Manages direct log reporting to Tencent Cloud CLS (Cloud Log Service).
    Uses the official tencentcloud-cls-sdk-python.
    """
    
    # User-provided credentials (should be set via environment variables in production)
    SECRET_ID = os.environ.get("TENCENTCLOUD_SECRET_ID", "YOUR_SECRET_ID")
    SECRET_KEY = os.environ.get("TENCENTCLOUD_SECRET_KEY", "YOUR_SECRET_KEY")
    
    # Placeholder IDs - User should replace these with actual CLS Topic/Logset IDs
    REGION = "ap-guangzhou"
    LOGSET_ID = "00000000-0000-0000-0000-000000000000" 
    TOPIC_ID = os.environ.get("TENCENTCLOUD_TOPIC_ID", "00000000-0000-0000-0000-000000000000")

    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(TencentCLSManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self.settings = QSettings("FluoQuantPro", "AppSettings")
        self._initialized = True

    def send_startup_event(self, payload):
        """
        Sends a single anonymous startup event to CLS for user counting.
        """
        if self.TOPIC_ID == "00000000-0000-0000-0000-000000000000":
            print("[TencentCLS] Error: TopicId is not configured. Please set a valid TopicId in tencent_cls.py")
            return False

        def _async_report():
            try:
                import time
                import socket
                from tencentcloud.log.logclient import LogClient
                from tencentcloud.log.cls_pb2 import LogGroupList

                print(f"[TencentCLS] Using GitHub SDK v1.0.4 to report startup for UUID: {payload.get('uuid')}")
                
                # endpoint format: https://ap-guangzhou.cls.tencentcs.com
                endpoint = f'https://{self.REGION}.cls.tencentcs.com'
                
                # Use environment variables if available, otherwise fallback to class defaults
                access_id = self.SECRET_ID
                access_key = self.SECRET_KEY
                
                client = LogClient(endpoint, access_id, access_key)
                
                # Create LogGroupList (Protobuf structure)
                log_group_list = LogGroupList()
                log_group = log_group_list.logGroupList.add()
                log_group.filename = "startup_event.log"
                
                # Try to get local IP for source
                try:
                    source_ip = socket.gethostbyname(socket.gethostname())
                except:
                    source_ip = "127.0.0.1"
                log_group.source = source_ip
                
                # Add log entry
                log = log_group.logs.add()
                log.time = int(round(time.time() * 1000000))
                
                # Add contents from payload
                print(f"[TencentCLS] Payload being sent: {payload}")
                for k, v in payload.items():
                    content = log.contents.add()
                    content.key = str(k)
                    content.value = str(v)
                
                # Add a metadata tag
                tag = log_group.logTags.add()
                tag.key = "app_name"
                tag.value = "FluoQuantPro"
                
                # Send log using GitHub SDK method
                try:
                    print(f"[TencentCLS] Attempting to upload to TopicID: {self.TOPIC_ID}")
                    resp = client.put_log_raw(self.TOPIC_ID, log_group_list)
                    request_id = resp.get_request_id()
                    if request_id:
                        print(f"[TencentCLS] Upload Success. RequestID: {request_id}")
                        print(f"[TencentCLS] NOTE: If data is missing in console, check if 'Full-text Index' is ENABLED for Topic {self.TOPIC_ID}")
                    else:
                        print(f"[TencentCLS] Upload completed, but no RequestID returned. Check credentials.")
                    
                except ImportError as e:
                    print(f"[TencentCLS] SDK Import Error: {e}. Ensure tencentcloud-cls-sdk-python is installed.")
            except Exception as e:
                    print(f"[TencentCLS] Unexpected error in async report: {e}")

        # Start reporting in a background thread
        thread = threading.Thread(target=_async_report, daemon=True)
        thread.start()
        return True
            


    def get_handler(self):
        # Removed: We no longer support full logging to CLS
        return None

# Global instance
cls_manager = TencentCLSManager()
