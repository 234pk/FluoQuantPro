import unittest
import json
from src.core.graphics_params import GraphicsParams, ColorMode, CoordinateSystem

class TestGraphicsParams(unittest.TestCase):

    def test_default_init(self):
        params = GraphicsParams()
        self.assertEqual(params.width, 1920)
        self.assertEqual(params.height, 1080)
        self.assertEqual(params.color_mode, ColorMode.RGB)
        self.assertEqual(params.dpi, 300)
        self.assertEqual(params.alpha, 1.0)
        self.assertEqual(params.coordinate_system, CoordinateSystem.CARTESIAN)

    def test_validation_valid(self):
        # Should not raise
        GraphicsParams(width=100, height=100, dpi=72, alpha=0.5)

    def test_validation_invalid_dimensions(self):
        with self.assertRaises(ValueError):
            GraphicsParams(width=0)
        with self.assertRaises(ValueError):
            GraphicsParams(height=-10)

    def test_validation_invalid_dpi(self):
        with self.assertRaises(ValueError):
            GraphicsParams(dpi=10)
        with self.assertRaises(ValueError):
            GraphicsParams(dpi=3000)

    def test_validation_invalid_alpha(self):
        with self.assertRaises(ValueError):
            GraphicsParams(alpha=-0.1)
        with self.assertRaises(ValueError):
            GraphicsParams(alpha=1.1)

    def test_validation_string_enum(self):
        params = GraphicsParams(color_mode="CMYK")
        self.assertEqual(params.color_mode, ColorMode.CMYK)
        
        with self.assertRaises(ValueError):
            GraphicsParams(color_mode="INVALID")

    def test_merge(self):
        p1 = GraphicsParams(width=800, height=600)
        p2 = GraphicsParams(width=1024, height=768, dpi=150)
        
        merged = p1.merge(p2)
        
        # Merge logic: takes p2's values
        self.assertEqual(merged.width, 1024)
        self.assertEqual(merged.height, 768)
        self.assertEqual(merged.dpi, 150)
        # p2 has default alpha=1.0, so it overrides p1's alpha (also 1.0)
        self.assertEqual(merged.alpha, 1.0)

    def test_serialization(self):
        params = GraphicsParams(width=100, height=200, color_mode=ColorMode.CMYK)
        json_str = params.to_json()
        
        loaded = GraphicsParams.from_json(json_str)
        self.assertEqual(loaded.width, params.width)
        self.assertEqual(loaded.height, params.height)
        self.assertEqual(loaded.color_mode, params.color_mode)

    def test_default_config(self):
        default = GraphicsParams.default_config()
        self.assertEqual(default.width, 1920)

if __name__ == '__main__':
    unittest.main()
