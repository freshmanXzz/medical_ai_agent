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

# 导入统一日志工具
from martin.util import AppLogger

# 获取日志实例
logger = AppLogger.setup_logging(__name__)

class NoduleDetector:
    """
    肺部结节检测器
    
    Args:
        model_path: 模型权重文件路径
        device: 运行设备 ('cuda' 或 'cpu')
    """
    
    def __init__(self, model_path: str = None, device: str = None):
        self.device = device or ('cuda' if torch.cuda.is_available() else 'cpu')
        self.model_path = model_path
        self.detector = None
        self._load_model()
    
    def _load_model(self):
        """加载检测模型"""
        if self.model_path is None:
            # 默认模型路径
            bundle_path = os.path.join(
                os.path.dirname(__file__), "..", "..", 
                "model", "lung_nodule_ct_detection-0.6.8",
                "lung_nodule_ct_detection-0.6.8"
            )
            sys.path.insert(0, os.path.join(bundle_path, "scripts"))
            self.model_path = os.path.join(bundle_path, "models", "model.pt")
        
        from monai.apps.detection.networks.retinanet_detector import RetinaNetDetector
        from monai.apps.detection.utils.anchor_utils import AnchorGeneratorWithAnchorShape
        from monai.networks.nets import resnet50
        from monai.apps.detection.networks.retinanet_network import resnet_fpn_feature_extractor, RetinaNet
        
        # 构建模型
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
        
        # 加载权重
        checkpoint = torch.load(self.model_path, map_location=self.device, weights_only=False)
        network.load_state_dict(checkpoint)
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
            device='cpu'
        )
        self.detector.eval()
    
    def detect(self, image_path: str) -> List[Dict]:
        """
        检测CT图像中的肺部结节
        
        Args:
            image_path: NIfTI格式CT图像路径 (.nii.gz)
        
        Returns:
            结节检测结果列表，包含置信度、位置和尺寸信息
        """
        from monai.transforms import (
            Compose, LoadImaged, EnsureChannelFirstd,
            Orientationd, Spacingd, ScaleIntensityRanged, EnsureTyped
        )
        from monai.apps.detection.transforms.dictionary import (
            ClipBoxToImaged, AffineBoxToWorldCoordinated, ConvertBoxModed
        )
        from monai.data import Dataset, DataLoader
        from monai.data.utils import no_collation
        
        # 预处理管道
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
        
        # 加载数据
        data_list = [{"image": image_path}]
        dataset = Dataset(data=data_list, transform=preprocessing)
        dataloader = DataLoader(
            dataset=dataset,
            batch_size=1,
            shuffle=False,
            num_workers=0,
            collate_fn=no_collation
        )
        
        # 执行推理
        results = []
        with torch.no_grad():
            for batch_data in dataloader:
                inputs = [data["image"].to(self.device) for data in batch_data]
                outputs = self.detector(inputs, use_inferer=True)
                
                for i, data in enumerate(batch_data):
                    result = {**outputs[i], "image": data["image"]}
                    result = postprocessing(result)
                    results.append(result)
        
        # 处理结果
        nodules = []
        for result in results:
            boxes = result["box"].cpu().numpy()
            scores = result["label_scores"].cpu().numpy()
            
            # 按置信度排序
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
        
        return nodules
    
    def save_results(self, nodules: List[Dict], output_path: str):
        """
        保存检测结果到JSON文件
        
        Args:
            nodules: 结节检测结果列表
            output_path: 输出文件路径
        """
        result_data = {
            "total_nodules": len(nodules),
            "nodules": nodules
        }
        
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result_data, f, indent=4, ensure_ascii=False)
