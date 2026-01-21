import sys
import unittest
import time
from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

# Add project root to sys.path
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.core.performance_monitor import PerformanceMonitor

class TestAsyncCleanup(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not QCoreApplication.instance():
            cls.app = QApplication([])
        else:
            cls.app = QCoreApplication.instance()

    def tearDown(self):
        PerformanceMonitor.instance().stop()

    def test_async_cleanup_trigger(self):
        monitor = PerformanceMonitor.instance()
        
        # Flag to verify signal emission
        self.cleanup_done = False
        
        def on_finished():
            self.cleanup_done = True
            
        monitor.cleanup_finished.connect(on_finished)
        
        # Trigger cleanup
        print("Triggering cleanup...")
        monitor.trigger_cleanup(current_gb=1.0)
        
        # Wait for signal (timeout 5s)
        start = time.time()
        while not self.cleanup_done and time.time() - start < 5:
            self.app.processEvents()
            time.sleep(0.1)
            
        self.assertTrue(self.cleanup_done, "Cleanup finished signal not received")
        print("Cleanup finished signal received.")
        
if __name__ == '__main__':
    unittest.main()
