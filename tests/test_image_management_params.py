import unittest
import os
import json
from src.core.image_management_params import (
    ImageResourceMetadata, ImageLoadParams, ImageProcessingParams,
    ImageFormat, CacheStrategy, ScaleMode, EnhancementParams, DisplayAdjustmentParams
)
from src.core.graphics_params import GraphicsParams

class TestImageManagementParams(unittest.TestCase):

    def test_metadata_creation(self):
        path = "C:/Images/test.tif"
        meta = ImageResourceMetadata(resource_path=path)
        self.assertEqual(meta.format_type, ImageFormat.TIFF)
        self.assertTrue(len(meta.resource_id) > 0)
        # Check normalization (os specific, but should not crash)
        self.assertTrue(isinstance(meta.resource_path, str))

    def test_load_params(self):
        params = ImageLoadParams(cache_strategy=CacheStrategy.DISK, target_size=(100, 100))
        self.assertEqual(params.cache_strategy, CacheStrategy.DISK)
        self.assertEqual(params.target_size, (100, 100))
        
        d = params.to_dict()
        self.assertEqual(d['cache_strategy'], 'disk')

    def test_processing_params_conversion(self):
        # Test to_graphics_params
        proc_params = ImageProcessingParams(crop_region=(10, 10, 200, 300))
        proc_params.display.opacity = 0.5
        gp = proc_params.to_graphics_params()
        self.assertEqual(gp.width, 200)
        self.assertEqual(gp.height, 300)
        self.assertEqual(gp.alpha, 0.5)

        # Test from_graphics_params
        gp_in = GraphicsParams(width=500, height=500)
        proc_params_out = ImageProcessingParams.from_graphics_params(gp_in)
        self.assertIsInstance(proc_params_out, ImageProcessingParams)

    def test_processing_serialization(self):
        params = ImageProcessingParams(rotation_angle=45.0, filter_effect="blur")
        # Ensure nested objects are initialized
        self.assertIsNotNone(params.enhancement)
        self.assertIsNotNone(params.display)
        
        json_str = params.to_json()
        
        # Simple verify it's valid JSON
        data = json.loads(json_str)
        self.assertEqual(data['rotation_angle'], 45.0)
        self.assertEqual(data['filter_effect'], "blur")
        self.assertTrue('enhancement' in data)
        self.assertTrue('display' in data)

    def test_display_params(self):
        d = DisplayAdjustmentParams(color="#FF0000", min_val=100, max_val=2000)
        self.assertEqual(d.color, "#FF0000")
        self.assertEqual(d.min_val, 100)
        
    def test_enhancement_params(self):
        e = EnhancementParams(bg_enabled=True, bg_strength=2.0)
        d = e.to_pipeline_dict()
        self.assertTrue(d['bg_enabled'])
        self.assertEqual(d['bg_strength'], 2.0)

if __name__ == '__main__':
    unittest.main()
