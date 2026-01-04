
import sys
import os
import atexit
import unittest
import tempfile
import numpy as np
import cv2
from PySide6.QtGui import QPainterPath, QUndoStack
from PySide6.QtWidgets import QApplication

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.core.project_model import ProjectModel, SceneData, ChannelDef
from src.core.roi_model import RoiManager, ROI
from src.core.enhance import EnhanceProcessor

# Mock QApplication for QUndoStack
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
app = QApplication.instance() or QApplication(sys.argv)
atexit.register(app.quit)

class TestEnhancePipeline(unittest.TestCase):
    
    def setUp(self):
        # Create a synthetic 16-bit image (100x100)
        # Gradient background + Noise + A bright circle
        x = np.linspace(0, 1, 100)
        y = np.linspace(0, 1, 100)
        xv, yv = np.meshgrid(x, y)
        
        # Background: 1000 to 5000
        background = (xv * 4000 + 1000).astype(np.float32)
        
        # Circle at (50,50) radius 20
        circle = np.zeros((100, 100), dtype=np.float32)
        dist = np.sqrt((xv-0.5)**2 + (yv-0.5)**2)
        circle[dist < 0.2] = 20000
        
        # Noise
        np.random.seed(42)
        noise = np.random.normal(0, 500, (100, 100))
        
        self.img_16 = np.clip(background + circle + noise, 0, 65535).astype(np.uint16)
        
        # RGB Image (100x100x3)
        self.img_rgb = np.dstack([self.img_16, self.img_16, self.img_16])

    def test_realtime_pipeline_basic(self):
        """Test Stage 2 pipeline runs without error on 16-bit data."""
        params = {
            'percentile_stretch': True,
            'lower_percentile': 2,
            'upper_percentile': 98,
            'bilateral_filter': True,
            'bilateral_d': 5,
            'bilateral_sigma_color': 50,
            'bilateral_sigma_space': 50,
            'wavelet_denoise': True,
            'wavelet_base': 'db1',
            'auto_sigma': True
        }
        
        result = EnhanceProcessor.process_realtime_pipeline(self.img_16, params)
        
        self.assertIsNotNone(result)
        self.assertEqual(result.shape, self.img_16.shape)
        self.assertEqual(result.dtype, np.uint16)
        
        # Check if noise is reduced (std dev in flat area should be lower)
        # Flat area: top left 10x10 (mostly gradient)
        std_orig = np.std(self.img_16[0:10, 0:10])
        std_res = np.std(result[0:10, 0:10])
        self.assertLess(std_res, std_orig)

    def test_richardson_lucy(self):
        """Test RL deconvolution with and without TV regularization."""
        # Create Gaussian PSF
        ksize = 11
        sigma = 2.0
        x = cv2.getGaussianKernel(ksize, sigma)
        psf = x @ x.T
        
        # 1. Without TV
        res_no_tv = EnhanceProcessor.apply_richardson_lucy(self.img_16, psf, iterations=5, tv_reg=False)
        self.assertEqual(res_no_tv.dtype, np.uint16)
        
        # 2. With TV
        res_tv = EnhanceProcessor.apply_richardson_lucy(self.img_16, psf, iterations=5, tv_reg=True)
        self.assertEqual(res_tv.dtype, np.uint16)
        
    def test_nlm_denoising(self):
        """Test NLM denoising."""
        res = EnhanceProcessor.apply_nlm_denoising(self.img_16, h=10)
        self.assertEqual(res.dtype, np.uint16)
        
    def test_rgb_support(self):
        """Test all methods with RGB input."""
        # Stage 2
        params = {
            'percentile_stretch': True,
            'bilateral_filter': True,
            'wavelet_denoise': True
        }
        res_rt = EnhanceProcessor.process_realtime_pipeline(self.img_rgb, params)
        self.assertEqual(res_rt.shape, (100, 100, 3))
        
        # RL
        ksize = 11
        sigma = 2.0
        x = cv2.getGaussianKernel(ksize, sigma)
        psf = x @ x.T
        res_rl = EnhanceProcessor.apply_richardson_lucy(self.img_rgb, psf, iterations=2, tv_reg=True)
        self.assertEqual(res_rl.shape, (100, 100, 3))
        
        # NLM
        res_nlm = EnhanceProcessor.apply_nlm_denoising(self.img_rgb, h=10)
        self.assertEqual(res_nlm.shape, (100, 100, 3))

class TestProjectModel(unittest.TestCase):
    def test_pool_logic(self):
        model = ProjectModel()
        files = ["img1.tif", "img2.tif", "img3.tif"]
        model.add_to_pool(files)
        
        # Initially all unassigned
        self.assertEqual(len(model.pool_files), 3)
        self.assertEqual(len(model.unassigned_files), 3)
        self.assertEqual(len(model.get_assigned_files()), 0)
        
        # Assign img1 to a scene
        scene_id = model.add_manual_scene("Scene1", ["DAPI"])
        model.update_channel_path(scene_id, 0, "img1.tif")
        
        assigned = model.get_assigned_files()
        self.assertIn("img1.tif", assigned)
        self.assertNotIn("img2.tif", assigned)
        
        # Check unassigned
        unassigned = model.unassigned_files
        self.assertNotIn("img1.tif", unassigned)
        self.assertIn("img2.tif", unassigned)
        self.assertEqual(len(unassigned), 2)
        
        # Unassign (clear path)
        model.update_channel_path(scene_id, 0, "")
        self.assertEqual(len(model.get_assigned_files()), 0)
        self.assertEqual(len(model.unassigned_files), 3)

    def test_project_template_applies_to_new_manual_scene(self):
        model = ProjectModel()
        template = [
            {"name": "DAPI", "color": "#0000FF"},
            {"name": "GFP", "color": "#00FF00"},
            {"name": "RFP", "color": "#FF0000"},
        ]
        model.set_project_template(template)
        scene_id = model.add_manual_scene("SceneWithTemplate")
        scene = model.get_scene(scene_id)
        self.assertIsNotNone(scene)
        self.assertEqual(len(scene.channels), 3)
        self.assertEqual([ch.channel_type for ch in scene.channels], ["DAPI", "GFP", "RFP"])

    def test_project_template_persists_in_project_json_and_is_used(self):
        template = [
            {"name": "DAPI", "color": "#0000FF"},
            {"name": "GFP", "color": "#00FF00"},
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            model = ProjectModel()
            model.set_root_path(tmpdir)
            model._set_project_template_internal(template)
            model.save_project()

            model2 = ProjectModel()
            self.assertTrue(model2.load_project(tmpdir))
            scene_id = model2.add_manual_scene("SceneAfterLoad")
            scene = model2.get_scene(scene_id)
            self.assertIsNotNone(scene)
            self.assertEqual(len(scene.channels), 2)
            self.assertEqual([ch.channel_type for ch in scene.channels], ["DAPI", "GFP"])

class TestRoiManager(unittest.TestCase):
    def test_undo_redo(self):
        manager = RoiManager()
        roi = ROI(label="TestROI")
        
        # 1. Add ROI
        manager.add_roi(roi, undoable=True)
        self.assertIn(roi.id, manager._rois)
        
        # 2. Undo Add -> Remove
        manager.undo()
        self.assertNotIn(roi.id, manager._rois)
        
        # 3. Redo Add -> Add again
        manager.redo()
        self.assertIn(roi.id, manager._rois)
        
        # 4. Remove ROI
        manager.remove_roi(roi.id, undoable=True)
        self.assertNotIn(roi.id, manager._rois)
        
        # 5. Undo Remove -> Add back
        manager.undo()
        self.assertIn(roi.id, manager._rois)

if __name__ == '__main__':
    unittest.main()
