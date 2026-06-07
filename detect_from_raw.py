"""
直接从 .mhd/.raw 文件进行肺部结节检测
无需 NIfTI 文件，直接读取原始数据
"""
import os
import sys
import json
import torch
import numpy as np

print("=" * 70)
print("直接读取 MetaImage 文件进行结节检测")
print("=" * 70)

# ==================== 1. 解析 .mhd 文件 ====================
def parse_mhd(mhd_path):
    """解析 MetaImage 头文件"""
    metadata = {}
    with open(mhd_path, 'r') as f:
        for line in f:
            line = line.strip()
            if '=' in line:
                key, value = line.split('=', 1)
                metadata[key.strip()] = value.strip()
    return metadata

def read_raw_data(mhd_path, metadata):
    """读取 .raw 二进制数据"""
    # 获取数据文件路径
    raw_filename = metadata['ElementDataFile']
    raw_path = os.path.join(os.path.dirname(mhd_path), raw_filename)
    
    # 解析尺寸
    dim_size = [int(x) for x in metadata['DimSize'].split()]
    
    # 读取二进制数据
    data = np.fromfile(raw_path, dtype=np.int16)
    
    # 重塑为3D数组 (z, y, x) -> (x, y, z)
    data = data.reshape(dim_size[2], dim_size[1], dim_size[0])
    data = data.transpose(2, 1, 0)
    
    return data, dim_size

# 设置文件路径
mhd_file = "1.3.6.1.4.1.14519.5.2.1.6279.6001.395623571499047043765181005112.mhd"

print(f"\n【步骤1】解析 {os.path.basename(mhd_file)}...")
metadata = parse_mhd(mhd_file)

print(f"  图像尺寸: {metadata['DimSize']}")
print(f"  像素间距: {metadata['ElementSpacing']} mm")
print(f"  数据文件: {metadata['ElementDataFile']}")

print("\n【步骤2】读取 .raw 数据...")
ct_data, dim_size = read_raw_data(mhd_file, metadata)
print(f"  数据形状: {ct_data.shape}")
print(f"  CT值范围: [{ct_data.min()}, {ct_data.max()}]")

# ==================== 2. 数据预处理 ====================
print("\n【步骤3】数据预处理...")

# 转换为张量 (C, D, H, W)
ct_tensor = torch.from_numpy(ct_data).float()  # (x, y, z)
ct_tensor = ct_tensor.permute(2, 1, 0)  # (z, y, x) -> (D, H, W)
ct_tensor = ct_tensor.unsqueeze(0)  # (1, D, H, W)
ct_tensor = ct_tensor.unsqueeze(0)  # (1, 1, D, H, W)

print(f"  输入张量形状: {ct_tensor.shape}")

# 灰度归一化
print("  灰度归一化...")
a_min, a_max = -1024.0, 300.0
b_min, b_max = 0.0, 1.0

input_data = ct_tensor.clone()
input_data[input_data < a_min] = a_min
input_data[input_data > a_max] = a_max
input_data = (input_data - a_min) / (a_max - a_min) * (b_max - b_min) + b_min

# ==================== 3. 加载模型 ====================
print("\n【步骤4】加载检测模型...")

bundle_path = os.path.join(os.path.dirname(__file__), "model",
                          "lung_nodule_ct_detection-0.6.8",
                          "lung_nodule_ct_detection-0.6.8")
sys.path.insert(0, os.path.join(bundle_path, "scripts"))

from monai.apps.detection.networks.retinanet_detector import RetinaNetDetector
from monai.apps.detection.utils.anchor_utils import AnchorGeneratorWithAnchorShape
from monai.networks.nets import resnet50
from monai.apps.detection.networks.retinanet_network import resnet_fpn_feature_extractor, RetinaNet

# 设置设备
device = torch.device('cuda:0' if torch.cuda.is_available() else 'cpu')
print(f"  使用设备: {device}")

# 构建模型
spatial_dims = 3
num_classes = 1
size_divisible = [16, 16, 8]

anchor_generator = AnchorGeneratorWithAnchorShape(
    feature_map_scales=[1, 2, 4],
    base_anchor_shapes=[[6, 8, 4], [8, 6, 5], [10, 10, 6]]
)

backbone = resnet50(spatial_dims=3, n_input_channels=1,
                   conv1_t_stride=[2, 2, 1], conv1_t_size=[7, 7, 7])
feature_extractor = resnet_fpn_feature_extractor(backbone, 3, False, [1, 2], None)

network = RetinaNet(
    spatial_dims=spatial_dims,
    num_classes=num_classes,
    num_anchors=3,
    feature_extractor=feature_extractor,
    size_divisible=size_divisible,
    use_list_output=False
).to(device)

# 加载权重
checkpoint_path = os.path.join(bundle_path, "models", "model.pt")
checkpoint = torch.load(checkpoint_path, map_location=device, weights_only=False)
network.load_state_dict(checkpoint)
network.eval()

# 创建检测器
detector = RetinaNetDetector(
    network=network,
    anchor_generator=anchor_generator,
    debug=False,
    spatial_dims=spatial_dims,
    num_classes=num_classes,
    size_divisible=size_divisible
)

detector.set_target_keys(box_key='box', label_key='label')
detector.set_box_selector_parameters(
    score_thresh=0.05,
    topk_candidates_per_level=500,
    nms_thresh=0.22,
    detections_per_img=100
)

detector.set_sliding_window_inferer(
    roi_size=[192, 192, 64],
    overlap=0.5,
    sw_batch_size=1,
    mode='constant',
    device=device
)
detector.eval()

# ==================== 4. 执行推理 ====================
print("\n【步骤5】执行推理...")

with torch.no_grad():
    outputs = detector(input_data.to(device), use_inferer=True)

# ==================== 5. 输出结果 ====================
print("\n" + "=" * 70)
print("【检测结果】")
print("=" * 70)

# 提取检测结果
boxes = outputs[0]["box"].cpu().numpy() if isinstance(outputs[0]["box"], torch.Tensor) else outputs[0]["box"]
scores = outputs[0]["label_scores"].cpu().numpy() if isinstance(outputs[0]["label_scores"], torch.Tensor) else outputs[0]["label_scores"]

# 按置信度排序
sorted_indices = np.argsort(scores)[::-1]
boxes = boxes[sorted_indices]
scores = scores[sorted_indices]

# 输出表格
print(f"\n检测到结节数量: {len(boxes)}")
print("-" * 70)
print(f"| {'结节':^4} | {'坐标 (x, y, z)':^35} | {'直径':^8} | {'置信度':^8} |")
print("-" * 70)

for i, (box, score) in enumerate(zip(boxes, scores)):
    center = f"({box[0]:.2f}, {box[1]:.2f}, {box[2]:.2f})"
    diameter = f"{max(box[3], box[4], box[5]):.2f}mm"
    confidence = f"{score*100:.2f}%"
    print(f"| {i+1:^4} | {center:^35} | {diameter:^8} | {confidence:^8} |")

print("-" * 70)

# 保存结果
output_file = "results/metaimage_raw_detection.json"
os.makedirs("results", exist_ok=True)

result_data = {
    "source_files": {
        "mhd": os.path.basename(mhd_file),
        "raw": metadata['ElementDataFile']
    },
    "image_info": {
        "dim_size": dim_size,
        "element_spacing": [float(x) for x in metadata['ElementSpacing'].split()]
    },
    "total_nodules": len(boxes),
    "nodules": [
        {
            "index": i + 1,
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
            "diameter": float(max(box[3], box[4], box[5])),
            "confidence": float(score)
        }
        for i, (box, score) in enumerate(zip(boxes, scores))
    ]
}

with open(output_file, 'w', encoding='utf-8') as f:
    json.dump(result_data, f, indent=4, ensure_ascii=False)

print(f"\n结果已保存到: {output_file}")
print("\n" + "=" * 70)
print("检测完成！")
print("=" * 70)
