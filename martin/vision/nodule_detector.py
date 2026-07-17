"""
NoduleDetector - 肺部结节检测模块
基于MONAI框架实现的RetinaNet检测模型
"""
import os
import sys
import json
import torch
import numpy as np
from typing import List, Dict, Optional

from martin.utils import AppLogger

logger = AppLogger.setup_logging(__name__)


class NoduleDetector:
    """
    肺部结节检测器

    Args:
        model_path: 模型权重文件路径，如果为None则自动查找默认路径
        device: 运行设备 ('cuda' 或 'cpu')
    """

    def __init__(self, model_path: str = None, device: str = None):
        self.device = self._get_device(device)
        self.model_path = self._get_model_path(model_path)
        self.detector = None
        self._load_model()
        logger.info(f"NoduleDetector 初始化成功，使用设备: {self.device}")

    @staticmethod
    def _get_device(device: Optional[str] = None) -> torch.device:
        """自动获取运行设备"""
        if device:
            return torch.device(device)
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

        possible_paths = [
            os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                "models", "vision", "lung_nodule_ct_detection-0.6.8",
                "lung_nodule_ct_detection-0.6.8", "models", "model.pt"
            ),
            os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "models", "vision", "lung_nodule_ct_detection-0.6.8",
                "lung_nodule_ct_detection-0.6.8", "models", "model.pt"
            ),
        ]

        for model_path in possible_paths:
            if os.path.exists(model_path):
                logger.info(f"自动找到模型文件: {model_path}")
                return model_path

        logger.warning(f"未找到模型文件，将使用默认路径: {possible_paths[0]}")
        return possible_paths[0]

    def _load_model(self):
        """加载检测模型"""
        try:
            from monai.apps.detection.networks.retinanet_detector import RetinaNetDetector
            from monai.apps.detection.utils.anchor_utils import AnchorGeneratorWithAnchorShape
            from monai.networks.nets import resnet50
            from monai.apps.detection.networks.retinanet_network import resnet_fpn_feature_extractor, RetinaNet

            logger.info("正在构建模型...")

            spatial_dims = 3
            num_classes = 1
            size_divisible = [16, 16, 8]

            anchor_generator = AnchorGeneratorWithAnchorShape(
                feature_map_scales=[1, 2, 4],
                base_anchor_shapes=[[6, 8, 4], [8, 6, 5], [10, 10, 6]]
            )

            backbone = resnet50(
                spatial_dims=3,
                n_input_channels=1,
                conv1_t_stride=[2, 2, 1],
                conv1_t_size=[7, 7, 7]
            )
            feature_extractor = resnet_fpn_feature_extractor(backbone, 3, False, [1, 2], None)

            network = RetinaNet(
                spatial_dims=spatial_dims,
                num_classes=num_classes,
                num_anchors=3,
                feature_extractor=feature_extractor,
                size_divisible=size_divisible,
                use_list_output=False
            ).to(self.device)

            if os.path.exists(self.model_path):
                logger.info(f"正在加载权重: {self.model_path}")
                checkpoint = torch.load(self.model_path, map_location=self.device, weights_only=False)
                network.load_state_dict(checkpoint)
                logger.info("权重加载成功")
            else:
                logger.warning(f"模型文件不存在: {self.model_path}")

            network.eval()

            self.detector = RetinaNetDetector(
                network=network,
                anchor_generator=anchor_generator,
                debug=False,
                spatial_dims=spatial_dims,
                num_classes=num_classes,
                size_divisible=size_divisible
            )

            self.detector.set_target_keys(box_key='box', label_key='label')
            self.detector.set_box_selector_parameters(
                score_thresh=0.02,
                topk_candidates_per_level=1000,
                nms_thresh=0.22,
                detections_per_img=300
            )

            self.detector.set_sliding_window_inferer(
                roi_size=[512, 512, 192],
                overlap=0.25,
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
        from monai.transforms import (
            Compose, LoadImaged, EnsureChannelFirstd,
            Orientationd, Spacingd, ScaleIntensityRanged, EnsureTyped
        )
        from monai.apps.detection.transforms.dictionary import (
            ClipBoxToImaged, AffineBoxToWorldCoordinated, ConvertBoxModed
        )

        preprocessing = Compose([
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

        postprocessing = Compose([
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

        return preprocessing, postprocessing

    def _prepare_dataloader(self, image_path: str, preprocessing):
        """准备数据加载器"""
        from monai.data import Dataset, DataLoader
        from monai.data.utils import no_collation

        data_list = [{"image": image_path}]
        dataset = Dataset(data=data_list, transform=preprocessing)
        dataloader = DataLoader(
            dataset=dataset,
            batch_size=1,
            shuffle=False,
            num_workers=0,
            collate_fn=no_collation
        )
        return dataloader

    def detect(self, image_path: str, max_slices: Optional[int] = None) -> Dict:
        """
        检测单张图像中的肺部结节

        Args:
            image_path: 图像文件路径（支持NIfTI格式）
            max_slices: 限制Z轴最大切片数，用于快速测试。
                        None表示处理完整体积，建议测试时设为96。

        Returns:
            包含检测结果的字典
        """
        import time

        if not os.path.exists(image_path):
            raise FileNotFoundError(f"图像文件不存在: {image_path}")

        logger.info(f"开始检测图像: {image_path}")

        try:
            preprocessing, postprocessing = self._setup_transforms()

            logger.info("步骤 1/3: 准备数据...")
            t0 = time.time()
            dataloader = self._prepare_dataloader(image_path, preprocessing)
            logger.info(f"  数据准备完成: {time.time() - t0:.2f}秒")

            logger.info("步骤 2/3: 执行推理...")
            if max_slices:
                logger.info(f"  快速模式: 仅处理前 {max_slices} 层切片")
                self.detector.set_sliding_window_inferer(
                    roi_size=[256, 256, 64],
                    overlap=0.25,
                    sw_batch_size=4,
                    mode='constant',
                    device=self.device,
                )
            t0 = time.time()
            results = []
            with torch.no_grad():
                for batch_data in dataloader:
                    inputs = [data["image"].to(self.device) for data in batch_data]
                    if max_slices is not None:
                        inputs = [inp[..., :max_slices] for inp in inputs]
                    outputs = self.detector(inputs, use_inferer=True)
                    for i, data in enumerate(batch_data):
                        result = {**outputs[i], "image": data["image"]}
                        result = postprocessing(result)
                        results.append(result)
            logger.info(f"  推理完成: {time.time() - t0:.2f}秒")

            logger.info("步骤 3/3: 解析检测结果...")
            t0 = time.time()
            nodules = []
            for result in results:
                boxes = result["box"].cpu().numpy()
                scores = result["label_scores"].cpu().numpy()

                sorted_indices = np.argsort(scores)[::-1]
                boxes = boxes[sorted_indices]
                scores = scores[sorted_indices]

                for j, (box, score) in enumerate(zip(boxes, scores)):
                    nodules.append({
                        "index": j + 1,
                        "score": float(score),
                        "center": {
                            "x": float(box[0]),
                            "y": float(box[1]),
                            "z": float(box[2])
                        },
                        "dimensions": {
                            "width": float(box[3]),
                            "height": float(box[4]),
                            "depth": float(box[5])
                        },
                        "diameter": float(max(box[3], box[4], box[5]))
                    })
            logger.info(f"  结果解析完成: {time.time() - t0:.2f}秒")

            output_result = {
                "image": os.path.basename(image_path),
                "nodules": nodules,
                "total_nodules": len(nodules)
            }

            logger.info(f"检测完成，共检测到 {len(nodules)} 个结节")
            self._log_nodule_summary(nodules)

            return output_result

        except Exception as e:
            logger.error(f"检测过程中发生错误: {e}")
            import traceback
            logger.error(traceback.format_exc())
            raise

    def _log_nodule_summary(self, nodules: List[Dict]):
        """记录结节摘要信息"""
        if nodules:
            logger.info("\n检测到的结节:")
            for nodule in nodules:
                logger.info(
                    f"  结节 {nodule['index']}: 置信度={nodule['score']:.4f}, "
                    f"直径={nodule['diameter']:.2f}mm, "
                    f"位置=({nodule['center']['x']:.2f}, "
                    f"{nodule['center']['y']:.2f}, {nodule['center']['z']:.2f})"
                )

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

    def save_result(
        self,
        result: Dict,
        filepath: str = None,
        use_date_dir: bool = True
    ) -> str:
        """
        保存检测结果到文件

        Args:
            result: 检测结果字典
            filepath: 输出文件路径，如果为None则自动生成
            use_date_dir: 是否使用按日期分类的目录

        Returns:
            保存的文件路径
        """
        from martin.utils import get_result_manager

        manager = get_result_manager()

        if filepath:
            if use_date_dir:
                date_dir = manager.get_today_dir()
                filename = os.path.basename(filepath)
                filepath = os.path.join(date_dir, filename)
                os.makedirs(os.path.dirname(filepath), exist_ok=True)
        else:
            filepath = manager.save_detection_result(result)

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=4, ensure_ascii=False)

        logger.info(f"检测结果已保存到: {filepath}")
        return filepath


def detect_nodules(image_path: str) -> Dict:
    """
    便捷函数：检测单张图像中的肺部结节

    自动查找模型文件并选择最佳运行设备

    Args:
        image_path: 图像文件路径

    Returns:
        检测结果字典
    """
    detector = NoduleDetector()
    return detector.detect(image_path)


if __name__ == "__main__":
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