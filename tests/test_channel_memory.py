from unittest.mock import MagicMock, patch
import sys
import unittest
import gc

# Add project root to sys.path
sys.path.append('f:\\ubuntu\\IF_analyzer\\FluoQuantPro')

from src.core.data_model import ImageChannel

class TestImageChannelMemory(unittest.TestCase):
    def test_unload_raw_data(self):
        import numpy as np
        
        # Create a channel with data
        ch = ImageChannel(file_path="test.tif", name="DAPI", color="#0000FF", data=np.zeros((1024, 1024), dtype=np.uint8))
        data = ch._raw_data

        
        self.assertIsNotNone(ch._raw_data)
        print(f"Ref count before unload: {sys.getrefcount(data)}")
        
        # Unload
        ch.unload_raw_data()
        
        self.assertIsNone(ch._raw_data)
        print(f"Ref count after unload: {sys.getrefcount(data)}")
        
        # Check if data is still referenced (by local var 'data')
        # If we delete local var, ref count should drop
        del data
        gc.collect()
        
if __name__ == '__main__':
    unittest.main()
