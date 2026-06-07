"""
直接从 .mhd/.raw 文件进行肺部结节检测（最终版本）
正确处理方向转换和重采样
"""
import os
import sys
import json
import torch
import numpy as np

print("=" * 70)
print("MetaImage 肺部结节检测（最终版本）")
print("=" * 70)

# ==================== 1. 解析 .mhd 文件 ====================
def parse_mhd(mhd_path):
    metadata = {}
    with open(mhd_path, 'r') as f:
        for line in f:
            line = line.strip()
            if '=' in line:
                key, value = line.split('=', 1)
                metadata[key.strip()] = value.strip()
    return metadata

def read_raw_data(mhd_path, metadata):
    raw_filename = metadata['ElementDataFile']
    raw_path = os.path.join(os.path.dirname(mhd_path), raw_filename)
    dim_size = [int(x) for x in metadata['DimSize'].split()]
    spacing = [float(x) for x in metadata['ElementSpacing'].split()]
    
    data = np.fromfile(raw_path, dtype=np.int16)
    data = data.reshape(dim_size[2], dim_size[1], dim_size[0])  # (z, y, x)
    
    return data.copy(), dim_size, spacing  # 使用copy避免负步长问题

# 设置文件路径
mhd_file = "1.3.6.1.4.1.14519.5.2.1.6279.6001.395623571499047043765181005112.mhd"

print(f"\n【步骤1】解析 {os.path.basename(mhd_file)}...")
metadata = parse_mhd(mhd_file)

dim_size = [int(x) for x in metadata['DimSize'].split()]
spacing = [float(x) for x in metadata['ElementSpacing'].split()]
orientation = metadata['AnatomicalOrientation']

print(f"  图像尺寸: {dim_size}")
print(f"  像素间距: {spacing} mm")
print(f"  方向: {orientation}")
print(f"  数据文件: {metadata['ElementDataFile']}")

print("\n【步骤2】读取 .raw 数据...")
ct_data, dim_size, spacing = read_raw_data(mhd_file, metadata)
print(f"  数据形状: {ct_data.shape}")
print(f"  CT值范围: [{ct_data.min()}, {ct_data.max()}]")

# ==================== 2. 转换为 NIfTI 格式 ====================
print("\n【步骤3】转换为 NIfTI 格式...")

import nibabel as nib

# 创建仿射矩阵
affine = np.diag([spacing[0], spacing[1], spacing[2], 1.0])

# 处理方向
if orientation == "RAI":
    # RAI -> RAS: 翻转z轴
    ct_data = ct_data[::-1, :, :].copy()  # 使用copy避免负步长

# 创建NIfTI图像
img = nib.Nifti1Image(ct_data, affine)

# 保存为临时NIfTI文件
temp_nifti = "temp_ct.nii.gz"
nib.save(img, temp_nifti)
print(f"  已保存临时文件: {temp_nifti}")

# ==================== 3. 使用 MONAI 进行检测 ====================
print("\n【步骤4】使用 MONAI 进行检测...")

bundle_path = os.path.join(os.path.dirname(__file__), "model",
                          "lung_nodule_ct_detection-0.6.8",
                          "lung_nodule_ct_detection-0.6.8")
sys.path.insert(0, os.path.join(bundle_path, "scripts"))

from monai.transforms import Compose, LoadImaged, EnsureChannelFirstd, Orientationd, Spacingd, ScaleIntensityRanged, EnsureTyped
from monai.apps.detection.transforms.dictionary import ClipBoxToImaged, AffineBoxToWorldCoordinated, ConvertBoxModed
from monai.data import Dataset, DataLoader
from monai.data.utils import no_collation
from monai.apps.detection.networks.retinanet_detector import RetinaNetDetector
from monai.apps.detection.utils.anchor_utils import AnchorGeneratorWithAnchorShape
from monai.networks.nets import resnet50
from monai.apps.detection.networks.retinanet_network import resnet_fpn_feature_extractor, RetinaNet

device = torch.device('cuda:0' if torch.cuda.is_available() else 'cpu')
print(f"  使用设备: {device}")

# 预处理管道
preprocessing = Compose([
    LoadImaged(keys="image"),
    EnsureChannelFirstd(keys="image"),
    Orientationd(keys="image", axcodes="RAS"),
    Spacingd(keys="image", pixdim=[0.703125, 0.703125, 1.25]),
    ScaleIntensityRanged(keys="image", a_min=-1024.0, a_max=300.0,
                        b_min=0.0, b_max=1.0, clip=True),
    EnsureTyped(keys="image")
])

postprocessing = Compose([
    ClipBoxToImaged(box_keys="box", label_keys="label",
                   box_ref_image_keys="image", remove_empty=True),
    AffineBoxToWorldCoordinated(box_keys="box", box_ref_image_keys="image",
                               affine_lps_to_ras=True),
    ConvertBoxModed(box_keys="box", src_mode="xyzxyz", dst_mode="cccwhd"),
])

# 加载数据
data_list = [{"image": temp_nifti}]
dataset = Dataset(data=data_list, transform=preprocessing)
dataloader = DataLoader(dataset=dataset, batch_size=1, shuffle=False,
                       num_workers=0, collate_fn=no_collation)

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

checkpoint_path = os.path.join(bundle_path, "models", "model.pt")
checkpoint = torch.load(checkpoint_path, map_location=device, weights_only=False)
network.load_state_dict(checkpoint)
network.eval()

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

# 执行推理
print("  执行推理...")
results = []
with torch.no_grad():
    for batch_data in dataloader:
        inputs = [data["image"].to(device) for data in batch_data]
        outputs = detector(inputs, use_inferer=True)

        for i, data in enumerate(batch_data):
            result = {**outputs[i], "image": data["image"]}
            result = postprocessing(result)
            results.append(result)

# ==================== 4. 输出结果 ====================
print("\n" + "=" * 70)
print("【检测结果】")
print("=" * 70)

for result in results:
    boxes = result["box"].cpu().numpy() if isinstance(result["box"], torch.Tensor) else result["box"]
    scores = result["label_scores"].cpu().numpy() if isinstance(result["label_scores"], torch.Tensor) else result["label_scores"]

    sorted_indices = np.argsort(scores)[::-1]
    boxes = boxes[sorted_indices]
    scores = scores[sorted_indices]

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
output_file = "results/metaimage_raw_detection_final.json"
os.makedirs("results", exist_ok=True)

output_data = {
    "source_files": {
        "mhd": os.path.basename(mhd_file),
        "raw": metadata['ElementDataFile']
    },
    "image_info": {
        "dim_size": dim_size,
        "element_spacing": spacing,
        "orientation": orientation
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
    json.dump(output_data, f, indent=4, ensure_ascii=False)

# 清理临时文件
os.remove(temp_nifti)

print(f"\n结果已保存到: {output_file}")
print("\n" + "=" * 70)
print("检测完成！")
print("=" * 70)
