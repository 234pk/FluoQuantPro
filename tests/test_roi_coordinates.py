import sys
import unittest
from unittest.mock import MagicMock, patch
from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QPainterPath

# Mocking imports to avoid full GUI dependency if possible, 
# but we need QGraphicsItem logic, so we need QApplication
from PySide6.QtWidgets import QApplication

# Adjust path to include project root
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.core.roi_model import ROI
# We need to import RoiGraphicsItem, but it depends on QtRenderEngine
# We might need to mock StyleConfigCenter if it needs resources
from src.gui.canvas_view import RoiGraphicsItem

class TestRoiCoordinates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Create QApplication instance if it doesn't exist
        if not QApplication.instance():
            cls.app = QApplication(sys.argv)

    def test_coordinate_mapping_logic(self):
        """
        Verify the logic flow:
        Tool (Scene) -> Map to Image -> ROI (Store Image) -> RoiGraphicsItem (Scale to Scene)
        """
        
        # 1. Setup Mock View with specific scaling
        # Scenario: 2000x2000 Image, displayed at 0.5 scale (1000x1000 Scene)
        display_scale = 0.5
        
        view_mock = MagicMock()
        view_mock.display_scale = display_scale
        
        # Mock get_image_coordinates: Scene -> Image (Divide by scale)
        def get_image_coordinates(scene_pos):
            return QPointF(scene_pos.x() / display_scale, scene_pos.y() / display_scale)
        
        view_mock.get_image_coordinates = get_image_coordinates
        
        # 2. Simulate Tool Interaction
        # User draws a 100x100 rect at (100, 100) in SCENE coordinates
        start_scene = QPointF(100, 100)
        end_scene = QPointF(200, 200)
        
        # Tool performs mapping
        start_image = view_mock.get_image_coordinates(start_scene)
        end_image = view_mock.get_image_coordinates(end_scene)
        
        # Verify Mapping
        self.assertEqual(start_image.x(), 200.0) # 100 / 0.5
        self.assertEqual(end_image.x(), 400.0)   # 200 / 0.5
        
        # 3. Create ROI
        roi = ROI(label="TestRect", color="#FF0000", channel_index=0)
        roi.reconstruct_from_points([start_image, end_image], roi_type="rectangle")
        
        # Verify ROI storage (Should be Image Coordinates)
        roi_rect = roi.path.boundingRect()
        self.assertEqual(roi_rect.x(), 200.0)
        self.assertEqual(roi_rect.width(), 200.0) # 400 - 200
        
        # 4. Create RoiGraphicsItem
        # It receives the ROI (Image Coords) and the display_scale
        # It should scale the path BACK to Scene Coords for drawing
        
        # NOTE: RoiGraphicsItem calls self._scale_path(roi.path, display_scale)
        # We need to verify _scale_path logic.
        # Since we can't easily instantiate RoiGraphicsItem without a full scene/view context sometimes,
        # let's try to instantiate it with a dummy parent or None.
        
        item = RoiGraphicsItem(roi, display_scale=display_scale)
        
        # Verify Item Path (Should be Scene Coordinates)
        item_rect = item.path().boundingRect()
        
        print(f"ROI Rect (Image): {roi_rect}")
        print(f"Item Rect (Scene): {item_rect}")
        
        # Expected: 100x100 at 100,100
        self.assertAlmostEqual(item_rect.x(), 100.0)
        self.assertAlmostEqual(item_rect.width(), 100.0)
        
        print("Coordinate Mapping Test Passed!")

    def test_legacy_compatibility(self):
        """
        Verify what happens if mapping fails (Legacy behavior).
        """
        display_scale = 0.5
        
        # User draws 100x100 at (100, 100) SCENE
        start_scene = QPointF(100, 100)
        end_scene = QPointF(200, 200)
        
        # Mapping FAILS -> Use Scene Coords directly
        start_image = start_scene
        end_image = end_scene
        
        # ROI Created with SCENE coords (BAD!)
        roi = ROI(label="TestRect_Bad", color="#FF0000", channel_index=0)
        roi.reconstruct_from_points([start_image, end_image], roi_type="rectangle")
        
        roi_rect = roi.path.boundingRect()
        self.assertEqual(roi_rect.x(), 100.0) # Stored as 100 (should be 200)
        
        # Item Created
        item = RoiGraphicsItem(roi, display_scale=display_scale)
        item_rect = item.path().boundingRect()
        
        print(f"Bad ROI Rect: {roi_rect}")
        print(f"Bad Item Rect: {item_rect}")
        
        # Item scales it down AGAIN: 100 * 0.5 = 50
        self.assertAlmostEqual(item_rect.x(), 50.0)
        self.assertAlmostEqual(item_rect.width(), 50.0)
        
        print("Legacy Compatibility Check: Confirmed double-scaling issue if mapping fails.")

if __name__ == '__main__':
    unittest.main()
