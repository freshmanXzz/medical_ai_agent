"""
肺部结节检测推理模块
提供可重用的推理功能，支持被其他模块调用
"""
import os
import sys
import logging
import torch
from datetime import datetime
from typing import List, Dict, Optional, Union

# 设置日志
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# 清除已有的处理器
logger.handlers.clear()

# 设置日志格式
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# 添加控制台输出
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# 创建日志目录
log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "log")
os.makedirs(log_dir, exist_ok=True)

# 按日期生成日志文件名
log_filename = datetime.now().strftime("%Y-%m-%d") + ".log"
log_filepath = os.path.join(log_dir, log_filename)

# 添加文件处理器
file_handler = logging.FileHandler(log_filepath, encoding='utf-8', mode='a')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# 记录模块启动信息
logger.info("=" * 60)
logger.info("肺部结节检测推理模块已加载")
logger.info(f"日志文件: {log_filepath}")
logger.info("=" * 60)


class LungNoduleDetector:
    """
    肺部结节检测类
    封装了完整的推理流程，包括模型加载、预处理、推理和后处理
    """
    
    def __init__(self, model_path: Optional[str] = None):
        """
        初始化检测器
        
        Args:
            model_path: 模型权重文件路径，如果为None则自动查找默认路径
        """
        self.device = self._get_device()
        self.model_path = self._get_model_path(model_path)
        self.detector = None
        self.preprocessing = None
        self.postprocessing = None
        self._load_model()
        self._setup_transforms()
        logger.info(f"LungNoduleDetector 初始化成功，使用设备: {self.device}")
    
    @staticmethod
    def _get_device() -> torch.device:
        """自动获取运行设备"""
        if torch.cuda.is_available():
            device = torch.device('cuda:0')
            logger.info(f"检测到 NVIDIA GPU，将使用 CUDA 加速")
            logger.info(f"GPU 型号: {torch.cuda.get_device_name(0)}")
            logger.info(f"GPU 显存: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.2f} GB")
        else:
            device = torch.device('cpu')
            logger.info("未检测到 GPU，将使用 CPU 运行")
        return device
    
    @staticmethod
    def _get_model_path(custom_path: Optional[str] = None) -> str:
        """自动获取模型权重文件路径"""
        if custom_path and os.path.exists(custom_path):
            logger.info(f"使用自定义模型路径: {custom_path}")
            return custom_path
        
        # 自动搜索可能的模型路径
        possible_paths = [
            # 相对于当前文件的路径
            os.path.join(os.path.dirname(os.path.dirname(__file__)), 
                        "model", "lung_nodule_ct_detection-0.6.8", 
                        "lung_nodule_ct_detection-0.6.8", "models", "model.pt"),
            # 相对于项目根目录的路径
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "model", "lung_nodule_ct_detection-0.6.8",
                        "lung_nodule_ct_detection-0.6.8", "models", "model.pt"),
        ]
        
        # 尝试每个路径
        for model_path in possible_paths:
            if os.path.exists(model_path):
                logger.info(f"自动找到模型文件: {model_path}")
                return model_path
        
        # 如果都没找到，返回第一个路径作为默认值
        logger.warning(f"未找到模型文件，将使用默认路径: {possible_paths[0]}")
        return possible_paths[0]
    
    def _load_model(self):
        """加载模型"""
        try:
            # 动态导入MONAI模块
            from monai.apps.detection.networks.retinanet_detector import RetinaNetDetector
            from monai.apps.detection.utils.anchor_utils import AnchorGeneratorWithAnchorShape
            from monai.networks.nets import resnet50
            from monai.apps.detection.networks.retinanet_network import resnet_fpn_feature_extractor, RetinaNet
            
            logger.info("正在构建模型...")
            
            # 模型参数
            spatial_dims = 3
            num_classes = 1
            size_divisible = [16, 16, 8]
            
            # 创建锚点生成器
            anchor_generator = AnchorGeneratorWithAnchorShape(
                feature_map_scales=[1, 2, 4],
                base_anchor_shapes=[[6, 8, 4], [8, 6, 5], [10, 10, 6]]
            )
            
            # 创建骨干网络
            backbone = resnet50(
                spatial_dims=3,
                n_input_channels=1,
                conv1_t_stride=[2, 2, 1],
                conv1_t_size=[7, 7, 7]
            )
            
            # 创建特征提取器
            feature_extractor = resnet_fpn_feature_extractor(backbone, 3, False, [1, 2], None)
            
            # 创建RetinaNet网络
            network = RetinaNet(
                spatial_dims=spatial_dims,
                num_classes=num_classes,
                num_anchors=3,
                feature_extractor=feature_extractor,
                size_divisible=size_divisible,
                use_list_output=False
            ).to(self.device)
            
            # 加载权重
            if os.path.exists(self.model_path):
                logger.info(f"正在加载权重: {self.model_path}")
                checkpoint = torch.load(self.model_path, map_location=self.device, weights_only=False)
                network.load_state_dict(checkpoint)
                logger.info("权重加载成功")
            else:
                logger.warning(f"模型文件不存在: {self.model_path}")
            
            network.eval()
            
            # 创建检测器
            self.detector = RetinaNetDetector(
                network=network,
                anchor_generator=anchor_generator,
                debug=False,
                spatial_dims=spatial_dims,
                num_classes=num_classes,
                size_divisible=size_divisible
            )
            
            # 设置检测器参数
            self.detector.set_target_keys(box_key='box', label_key='label')
            self.detector.set_box_selector_parameters(
                score_thresh=0.05,
                topk_candidates_per_level=500,
                nms_thresh=0.22,
                detections_per_img=100
            )
            self.detector.set_sliding_window_inferer(
                roi_size=[384, 384,128],
                overlap=0.5,
                sw_batch_size=1,
                mode='constant',
                device=self.device
            )
            self.detector.eval()
            
            logger.info("模型加载完成")
            
        except ImportError as e:
            logger.error(f"导入MONAI模块失败: {e}")
            raise
        except Exception as e:
            logger.error(f"模型加载失败: {e}")
            raise
    
    def _setup_transforms(self):
        """设置预处理和后处理变换"""
        try:
            from monai.transforms import Compose, LoadImaged, EnsureChannelFirstd, Orientationd, Spacingd, ScaleIntensityRanged, EnsureTyped
            from monai.apps.detection.transforms.dictionary import ClipBoxToImaged, AffineBoxToWorldCoordinated, ConvertBoxModed
            
            # 预处理管道
            self.preprocessing = Compose([
                LoadImaged(keys="image"),
                EnsureChannelFirstd(keys="image"),
                Orientationd(keys="image", axcodes="RAS"),
                Spacingd(keys="image", pixdim=[0.703125, 0.703125, 1.25]),
                ScaleIntensityRanged(
                    keys="image",
                    a_min=-1024.0,
                    a_max=300.0,
                    b_min=0.0,
                    b_max=1.0,
                    clip=True
                ),
                EnsureTyped(keys="image")
            ])
            
            # 后处理管道
            self.postprocessing = Compose([
                ClipBoxToImaged(
                    box_keys="box",
                    label_keys="label",
                    box_ref_image_keys="image",
                    remove_empty=True
                ),
                AffineBoxToWorldCoordinated(
                    box_keys="box",
                    box_ref_image_keys="image",
                    affine_lps_to_ras=True
                ),
                ConvertBoxModed(box_keys="box", src_mode="xyzxyz", dst_mode="cccwhd"),
            ])
            
            logger.info("变换管道设置完成")
            
        except ImportError as e:
            logger.error(f"导入MONAI变换模块失败: {e}")
            raise
    
    def detect(self, image_path: str) -> Dict:
        """
        检测单张图像中的肺部结节
        
        Args:
            image_path: 图像文件路径（支持NIfTI格式）
            
        Returns:
            包含检测结果的字典，格式如下:
            {
                "image": 图像文件名,
                "nodules": [
                    {
                        "index": 结节索引,
                        "score": 置信度,
                        "center": {"x": x坐标, "y": y坐标, "z": z坐标},
                        "dimensions": {"width": 宽度, "height": 高度, "depth": 深度},
                        "diameter": 直径
                    }
                ],
                "total_nodules": 结节总数
            }
        """
        import time
        
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"图像文件不存在: {image_path}")
        
        logger.info(f"开始检测图像: {image_path}")
        
        try:
            from monai.data import Dataset, DataLoader
            from monai.data.utils import no_collation
            
            # 准备数据
            logger.info("步骤 1/4: 准备数据...")
            data_list = [{"image": image_path}]
            
            t0 = time.time()
            dataset = Dataset(data=data_list, transform=self.preprocessing)
            logger.info(f"  数据集创建完成: {time.time() - t0:.2f}秒")
            
            t0 = time.time()
            dataloader = DataLoader(
                dataset=dataset,
                batch_size=1,
                shuffle=False,
                num_workers=0,
                collate_fn=no_collation
            )
            logger.info(f"  数据加载器创建完成: {time.time() - t0:.2f}秒")
            
            results = []
            
            # 执行推理
            logger.info("步骤 2/4: 执行推理...")
            t0 = time.time()
            
            with torch.no_grad():
                for batch_idx, batch_data in enumerate(dataloader):
                    logger.info(f"  处理批次 {batch_idx + 1}...")
                    
                    t1 = time.time()
                    inputs = [data["image"].to(self.device) for data in batch_data]
                    logger.info(f"    数据移动到设备: {time.time() - t1:.2f}秒")
                    logger.info(f"    输入形状: {inputs[0].shape}")
                    
                    t1 = time.time()
                    logger.info("    执行模型推理 (这可能需要一些时间)...")
                    outputs = self.detector(inputs, use_inferer=True)
                    logger.info(f"    推理完成: {time.time() - t1:.2f}秒")
                    
                    # 后处理
                    logger.info("步骤 3/4: 后处理...")
                    t1 = time.time()
                    for i, data in enumerate(batch_data):
                        result = {**outputs[i], "image": data["image"]}
                        result = self.postprocessing(result)
                        results.append(result)
                    logger.info(f"  后处理完成: {time.time() - t1:.2f}秒")
            
            logger.info(f"推理执行完成: {time.time() - t0:.2f}秒")
            
            # 解析结果
            logger.info("步骤 4/4: 解析检测结果...")
            t0 = time.time()
            
            nodules = []
            for result in results:
                boxes = result["box"].cpu().numpy() if isinstance(result["box"], torch.Tensor) else result["box"]
                scores = result["label_scores"].cpu().numpy() if isinstance(result["label_scores"], torch.Tensor) else result["label_scores"]
                
                logger.info(f"  检测到 {len(boxes)} 个候选框")
                
                for j in range(len(boxes)):
                    nodule = {
                        "index": j + 1,
                        "score": float(scores[j]),
                        "center": {
                            "x": float(boxes[j][0]),
                            "y": float(boxes[j][1]),
                            "z": float(boxes[j][2])
                        },
                        "dimensions": {
                            "width": float(boxes[j][3]),
                            "height": float(boxes[j][4]),
                            "depth": float(boxes[j][5])
                        },
                        "diameter": float(max(boxes[j][3], boxes[j][4], boxes[j][5]))
                    }
                    nodules.append(nodule)
            
            logger.info(f"结果解析完成: {time.time() - t0:.2f}秒")
            
            output_result = {
                "image": os.path.basename(image_path),
                "nodules": nodules,
                "total_nodules": len(nodules)
            }
            
            logger.info(f"检测完成，共检测到 {len(nodules)} 个结节")
            
            # 输出摘要信息
            if nodules:
                logger.info("\n检测到的结节:")
                for nodule in nodules:
                    logger.info(
                        f"  结节 {nodule['index']}: "
                        f"置信度={nodule['score']:.4f}, "
                        f"直径={nodule['diameter']:.2f}mm, "
                        f"位置=({nodule['center']['x']:.2f}, {nodule['center']['y']:.2f}, {nodule['center']['z']:.2f})"
                    )
            
            return output_result
            
        except Exception as e:
            logger.error(f"检测过程中发生错误: {e}")
            import traceback
            logger.error(traceback.format_exc())
            raise
    
    def detect_batch(self, image_paths: List[str]) -> List[Dict]:
        """
        批量检测图像
        
        Args:
            image_paths: 图像文件路径列表
            
        Returns:
            检测结果列表，每个元素对应一张图像的检测结果
        """
        results = []
        for image_path in image_paths:
            try:
                result = self.detect(image_path)
                results.append(result)
            except Exception as e:
                logger.error(f"处理图像 {image_path} 失败: {e}")
                results.append({
                    "image": os.path.basename(image_path),
                    "error": str(e),
                    "nodules": [],
                    "total_nodules": 0
                })
        return results


# 提供简单的函数接口
def detect_nodules(image_path: str) -> Dict:
    """
    便捷函数：检测单张图像中的肺部结节
    
    自动查找模型文件并选择最佳运行设备
    
    Args:
        image_path: 图像文件路径
        
    Returns:
        检测结果字典
    """
    detector = LungNoduleDetector()
    return detector.detect(image_path)


def main():
    """
    命令行入口，用于直接测试推理功能
    """
    import argparse
    
    parser = argparse.ArgumentParser(description="肺部结节检测")
    parser.add_argument("--image", "-i", required=True, help="输入图像路径")
    
    args = parser.parse_args()
    
    result = detect_nodules(args.image)
    
    print("\n" + "=" * 60)
    print("检测结果:")
    print("=" * 60)
    print(f"图像: {result['image']}")
    print(f"检测到结节数: {result['total_nodules']}")
    
    if result['nodules']:
        print("\n结节详情:")
        for nodule in result['nodules']:
            print(f"  结节 {nodule['index']}:")
            print(f"    置信度: {nodule['score']:.4f}")
            print(f"    直径: {nodule['diameter']:.2f}mm")
            print(f"    中心位置: ({nodule['center']['x']:.2f}, {nodule['center']['y']:.2f}, {nodule['center']['z']:.2f})")
            print(f"    尺寸: {nodule['dimensions']['width']:.2f} x {nodule['dimensions']['height']:.2f} x {nodule['dimensions']['depth']:.2f}")


if __name__ == "__main__":
    main()