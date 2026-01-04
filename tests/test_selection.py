import sys
import unittest
import os

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

try:
    from PySide6.QtWidgets import QApplication
    from src.core.roi_model import ROI, RoiManager
except ImportError:
    print("Skipping tests: PySide6 or src modules not found.")
    sys.exit(0)

class TestSelection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not QApplication.instance():
            cls.app = QApplication(sys.argv)
            
    def setUp(self):
        self.manager = RoiManager()
        self.roi1 = ROI(label="ROI1")
        self.roi2 = ROI(label="ROI2")
        self.roi3 = ROI(label="ROI3")
        self.manager.add_roi(self.roi1)
        self.manager.add_roi(self.roi2)
        self.manager.add_roi(self.roi3)
        
    def test_single_selection(self):
        """Verify single selection logic (clearing others)."""
        self.manager.set_selection(self.roi1.id, clear_others=True)
        self.assertTrue(self.roi1.selected)
        self.assertFalse(self.roi2.selected)
        self.assertEqual(self.manager.get_selected_ids(), [self.roi1.id])
        
    def test_multi_selection(self):
        """Verify multi-selection logic (set_selected_ids)."""
        self.manager.set_selected_ids([self.roi1.id, self.roi2.id])
        self.assertTrue(self.roi1.selected)
        self.assertTrue(self.roi2.selected)
        self.assertFalse(self.roi3.selected)
        self.assertEqual(set(self.manager.get_selected_ids()), {self.roi1.id, self.roi2.id})
        
    def test_selection_update_workflow(self):
        """Simulate the Ctrl+Click workflow."""
        # 1. Select ROI1
        self.manager.set_selected_ids([self.roi1.id])
        self.assertTrue(self.roi1.selected)
        
        # 2. Ctrl+Click ROI2 (Add to selection)
        current = self.manager.get_selected_ids()
        current.append(self.roi2.id)
        self.manager.set_selected_ids(current)
        
        self.assertTrue(self.roi1.selected)
        self.assertTrue(self.roi2.selected)
        self.assertFalse(self.roi3.selected)
        
        # 3. Ctrl+Click ROI1 (Remove from selection)
        current = self.manager.get_selected_ids()
        current.remove(self.roi1.id)
        self.manager.set_selected_ids(current)
        
        self.assertFalse(self.roi1.selected)
        self.assertTrue(self.roi2.selected)
        
    def test_clear_selection(self):
        self.manager.set_selected_ids([self.roi1.id, self.roi2.id])
        self.manager.set_selection(None, clear_others=True)
        self.assertFalse(self.roi1.selected)
        self.assertFalse(self.roi2.selected)
        self.assertEqual(len(self.manager.get_selected_ids()), 0)

if __name__ == '__main__':
    unittest.main()
