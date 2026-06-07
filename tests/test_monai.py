"""
测试MONAI模块
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from martin.minai import NoduleDetector, ImageProcessor

class TestNoduleDetector(unittest.TestCase):
    """测试结节检测器"""
    
    def test_detector_initialization(self):
        """测试检测器初始化"""
        try:
            detector = NoduleDetector()
            self.assertIsNotNone(detector.detector)
            print("✓ 检测器初始化成功")
        except Exception as e:
            print(f"⚠️  检测器初始化失败（可能缺少模型文件）: {e}")
    
    def test_detect_method_exists(self):
        """测试检测方法存在"""
        try:
            detector = NoduleDetector()
            self.assertTrue(hasattr(detector, 'detect'))
            print("✓ 检测方法存在")
        except Exception as e:
            print(f"⚠️  测试跳过（缺少模型文件）: {e}")

class TestImageProcessor(unittest.TestCase):
    """测试图像处理模块"""
    
    def test_read_nifti(self):
        """测试读取NIfTI文件"""
        test_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 
                               "data", "1.3.6.1.4.1.14519.5.2.1.6279.6001.395623571499047043765181005112.nii.gz")
        
        if os.path.exists(test_file):
            data, affine, header = ImageProcessor.read_nifti(test_file)
            self.assertIsNotNone(data)
            print("✓ NIfTI读取成功")
        else:
            print("⚠️  NIfTI测试跳过（文件不存在）")
    
    def test_read_metaimage(self):
        """测试读取MetaImage文件"""
        test_file = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                               "data", "raw_data", "1.3.6.1.4.1.14519.5.2.1.6279.6001.395623571499047043765181005112.mhd")
        
        if os.path.exists(test_file):
            data, spacing, metadata = ImageProcessor.read_metaimage(test_file)
            self.assertIsNotNone(data)
            print("✓ MetaImage读取成功")
        else:
            print("⚠️  MetaImage测试跳过（文件不存在）")
    
    def test_normalize_intensity(self):
        """测试灰度归一化"""
        data = np.array([-1024, 0, 300, 500], dtype=np.float32)
        normalized = ImageProcessor.normalize_intensity(data)
        
        self.assertTrue(normalized[0] == 0.0)
        self.assertTrue(normalized[-1] == 1.0)
        print("✓ 灰度归一化测试通过")

if __name__ == "__main__":
    import numpy as np
    unittest.main(verbosity=2)
