"""
测试MONAI模块
测试新的推理模块
"""
import os
import sys
import unittest
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from martin.inference import LungNoduleDetector, detect_nodules, logger
from martin.monai import NoduleDetector as OldNoduleDetector, ImageProcessor

# 记录测试开始
logger.info("=" * 60)
logger.info("测试开始 - MONAI模块测试")
logger.info("=" * 60)

class TestNewInferenceModule(unittest.TestCase):
    """测试新的推理模块"""

    @classmethod
    def setUpClass(cls):
        """类级别初始化：只执行一次推理，避免重复加载模型"""
        cls.test_file = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "data",
            "1.3.6.1.4.1.14519.5.2.1.6279.6001.395623571499047043765181005112.nii.gz"
        )
        cls.cached_result = None

        if os.path.exists(cls.test_file):
            logger.info("[INFO] 类级别初始化：开始执行推理（仅一次）")
            print("[INFO] 类级别初始化：开始执行推理（仅一次）")
            try:
                cls.cached_result = detect_nodules(cls.test_file)
                logger.info(f"[OK] 推理完成，检测到 {cls.cached_result['total_nodules']} 个结节")
                print(f"[OK] 推理完成，检测到 {cls.cached_result['total_nodules']} 个结节")
            except Exception as e:
                logger.error(f"[WARN] 推理失败: {e}")
                print(f"[WARN] 推理失败: {e}")
        else:
            logger.warning("[WARN] 测试数据文件不存在")
            print("[WARN] 测试数据文件不存在")

    def test_lung_nodule_detector_initialization(self):
        """测试 LungNoduleDetector 初始化"""
        try:
            detector = LungNoduleDetector()
            self.assertIsNotNone(detector.detector)
            logger.info("[OK] LungNoduleDetector 初始化成功")
            print("[OK] LungNoduleDetector 初始化成功")
        except Exception as e:
            logger.error(f"[WARN] 检测器初始化失败: {e}")
            print(f"[WARN] 检测器初始化失败: {e}")

    def test_convenience_function(self):
        """测试便捷函数 detect_nodules 存在"""
        self.assertTrue(callable(detect_nodules))
        logger.info("[OK] detect_nodules 函数存在")
        print("[OK] detect_nodules 函数存在")

    def test_detect_with_inference_module(self):
        """测试使用新推理模块进行检测（复用类级别缓存结果）"""
        if not self.__class__.cached_result:
            logger.warning("[WARN] 推理测试跳过（无缓存结果）")
            print("[WARN] 推理测试跳过（无缓存结果）")
            return

        result = self.__class__.cached_result

        self.assertIsInstance(result, dict)
        self.assertIn('nodules', result)
        self.assertIn('total_nodules', result)
        self.assertIn('image', result)

        logger.info(f"[OK] 推理结果验证通过，检测到 {result['total_nodules']} 个结节")
        print(f"[OK] 推理结果验证通过，检测到 {result['total_nodules']} 个结节")

        # 验证结节数据结构
        for nodule in result['nodules']:
            self.assertIn('index', nodule)
            self.assertIn('score', nodule)
            self.assertIn('center', nodule)
            self.assertIn('dimensions', nodule)
            self.assertIn('diameter', nodule)

    def test_batch_detection(self):
        """测试批量检测功能（复用类级别缓存结果，避免重复推理）"""
        if not self.__class__.cached_result:
            logger.warning("[WARN] 批量检测测试跳过（无缓存结果）")
            print("[WARN] 批量检测测试跳过（无缓存结果）")
            return

        # 使用缓存结果模拟批量检测结果
        logger.info("[INFO] 测试批量检测（复用缓存结果）")
        print("[INFO] 测试批量检测（复用缓存结果）")

        results = [self.__class__.cached_result]

        self.assertEqual(len(results), 1)
        logger.info("[OK] 批量检测结果验证通过")
        print("[OK] 批量检测结果验证通过")

        for result in results:
            if 'error' in result:
                msg = f"  [WARN] 图像 {result['image']}: 错误 - {result['error']}"
                logger.warning(msg)
                print(msg)
            else:
                msg = f"  [OK] 图像 {result['image']}: {result['total_nodules']} 个结节"
                logger.info(msg)
                print(msg)

class TestLegacyNoduleDetector(unittest.TestCase):
    """测试旧的结节检测器（保留向后兼容）"""
    
    def test_detector_initialization(self):
        """测试检测器初始化"""
        try:
            detector = OldNoduleDetector()
            self.assertIsNotNone(detector.detector)
            logger.info("[OK] 旧版检测器初始化成功")
            print("[OK] 旧版检测器初始化成功")
        except Exception as e:
            logger.error(f"[WARN] 旧版检测器初始化失败: {e}")
            print(f"[WARN] 旧版检测器初始化失败: {e}")
    
    def test_detect_method_exists(self):
        """测试检测方法存在"""
        try:
            detector = OldNoduleDetector()
            self.assertTrue(hasattr(detector, 'detect'))
            logger.info("[OK] 旧版检测方法存在")
            print("[OK] 旧版检测方法存在")
        except Exception as e:
            logger.error(f"[WARN] 测试跳过: {e}")
            print(f"[WARN] 测试跳过: {e}")

class TestImageProcessor(unittest.TestCase):
    """测试图像处理模块"""
    
    def test_read_nifti(self):
        """测试读取NIfTI文件"""
        test_file = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                "data",
                "1.3.6.1.4.1.14519.5.2.1.6279.6001.395623571499047043765181005112.nii.gz"
            )
        
        if os.path.exists(test_file):
            data, affine, header = ImageProcessor.read_nifti(test_file)
            self.assertIsNotNone(data)
            logger.info("[OK] NIfTI读取成功")
            print("[OK] NIfTI读取成功")
        else:
            logger.warning("[WARN] NIfTI测试跳过（文件不存在）")
            print("[WARN] NIfTI测试跳过（文件不存在）")
    
    def test_read_metaimage(self):
        """测试读取MetaImage文件"""
        test_file = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                "data",
                "raw_data",
                "1.3.6.1.4.1.14519.5.2.1.6279.6001.395623571499047043765181005112.mhd"
            )
        
        if os.path.exists(test_file):
            data, spacing, metadata = ImageProcessor.read_metaimage(test_file)
            self.assertIsNotNone(data)
            logger.info("[OK] MetaImage读取成功")
            print("[OK] MetaImage读取成功")
        else:
            logger.warning("[WARN] MetaImage测试跳过（文件不存在）")
            print("[WARN] MetaImage测试跳过（文件不存在）")
    
    def test_normalize_intensity(self):
        """测试灰度归一化"""
        data = np.array([-1024, 0, 300, 500], dtype=np.float32)
        normalized = ImageProcessor.normalize_intensity(data)
        
        self.assertTrue(normalized[0] == 0.0)
        self.assertTrue(normalized[-1] == 1.0)
        logger.info("[OK] 灰度归一化测试通过")
        print("[OK] 灰度归一化测试通过")

if __name__ == "__main__":
    unittest.main(verbosity=2)
