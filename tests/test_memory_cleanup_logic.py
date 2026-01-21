
import sys
import os
import unittest
from unittest.mock import MagicMock, patch

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QUndoStack, QUndoCommand
from PySide6.QtCore import QObject

# Ensure QApplication exists
app = QApplication.instance() or QApplication(sys.argv)

from src.core.performance_monitor import PerformanceMonitor
from src.core.data_model import Session

class MockCommand(QUndoCommand):
    def __init__(self):
        super().__init__()
    def redo(self): pass
    def undo(self): pass

class MockMainWindow(QObject):
    def __init__(self):
        super().__init__()
        self.undo_stack = QUndoStack()
        # Push a dummy command so we can verify it gets cleared
        self.undo_stack.push(MockCommand()) 
        
        self.session = MagicMock()
        # Setup mock channels with clear_cache method
        channel = MagicMock()
        channel.clear_cache = MagicMock()
        self.session.channels = [channel]
        
        # Connect signal like in main.py
        self.perf_monitor = PerformanceMonitor.instance()
        self.perf_monitor.cleanup_started.connect(self.on_memory_cleanup_requested)
        
    def on_memory_cleanup_requested(self):
        # This is the logic we injected into main.py
        # We duplicate it here to verify the logic flow works as intended
        print("[MockMain] Memory cleanup requested.")
        
        if self.undo_stack:
            self.undo_stack.clear()
            
        if self.session:
            for ch in self.session.channels:
                if hasattr(ch, 'clear_cache'):
                    ch.clear_cache()

class TestMemoryCleanup(unittest.TestCase):
    def setUp(self):
        self.monitor = PerformanceMonitor.instance()
        self.window = MockMainWindow()
        
    def test_cleanup_trigger(self):
        # Verify initial state
        self.assertTrue(self.window.undo_stack.canUndo(), "Undo stack should have items initially")
        
        print("Triggering cleanup...")
        # Trigger cleanup manually
        self.monitor.trigger_cleanup()
        
        # Verify effects
        # 1. Undo stack should be empty
        self.assertFalse(self.window.undo_stack.canUndo(), "Undo stack should be cleared after cleanup")
        
        # 2. Channel cache should be cleared
        self.window.session.channels[0].clear_cache.assert_called_once()
        print("Verification successful: Undo stack cleared and channel cache cleared.")

if __name__ == '__main__':
    unittest.main()
