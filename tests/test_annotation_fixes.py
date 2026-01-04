
import sys
import unittest
from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtCore import QPointF, QSettings
from unittest.mock import MagicMock

# Add project root to path
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.gui.annotation_panel import AnnotationPanel
from src.core.data_model import Session, GraphicAnnotation
from src.core.roi_model import ROI

class TestAnnotationFixes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not QApplication.instance():
            cls.app = QApplication([])
        else:
            cls.app = QApplication.instance()
        settings = QSettings("FluoQuantPro", "AppSettings")
        settings.setValue("interface/sync_rois_as_annotations", True)

    def setUp(self):
        self.session = Session()
        self.panel = AnnotationPanel(self.session)

    def test_panel_initialization(self):
        """Test if AnnotationPanel initializes without error and has required attributes."""
        self.assertTrue(hasattr(self.panel, 'tool_group'), "tool_group missing")
        self.assertTrue(hasattr(self.panel, 'list_ann'), "list_ann missing")
        self.assertTrue(hasattr(self.panel, 'combo_font'), "combo_font missing")
        self.assertTrue(hasattr(self.panel, 'combo_arrow_head'), "combo_arrow_head missing")
        self.assertIsNotNone(self.panel.tool_group)
        self.assertIsNotNone(self.panel.list_ann)

    def test_tool_selection(self):
        """Test tool button selection logic."""
        # Click Arrow button
        self.panel.btn_add_arrow.click()
        self.assertTrue(self.panel.btn_add_arrow.isChecked())
        self.assertEqual(self.panel.tool_group.checkedButton(), self.panel.btn_add_arrow)
        
        # Click Line button
        self.panel.btn_add_line.click()
        self.assertFalse(self.panel.btn_add_arrow.isChecked())
        self.assertTrue(self.panel.btn_add_line.isChecked())

    def test_annotation_property_update(self):
        """Test if updating properties works without crashing."""
        # Add a dummy annotation
        ann = GraphicAnnotation(id="test1", type="rect", points=[(0,0), (10,10)])
        self.session.annotations.append(ann)
        self.panel.update_annotation_list()
        
        # Select it
        self.panel.list_ann.setCurrentRow(0)
        
        # Change thickness
        self.panel.spin_ann_thickness.setValue(5)
        
        # Verify
        self.assertEqual(self.session.annotations[0].thickness, 5)

    def test_roi_sync_option(self):
        """Verify Sync ROI option exists and is checked by default."""
        self.assertTrue(hasattr(self.panel, 'chk_sync_rois'))
        self.assertTrue(self.panel.chk_sync_rois.isChecked())

if __name__ == '__main__':
    unittest.main()
