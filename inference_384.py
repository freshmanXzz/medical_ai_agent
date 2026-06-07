import os
import sys
import json
import torch
import time
from datetime import datetime

print("=" * 60)
print("肺部结节检测推理 - 用户参数版本")
print("参数配置: [384, 384, 128], overlap=0.25")
print("=" * 60)

# 记录开始时间
start_time = time.time()
start_datetime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
print(f"开始时间: {start_datetime}")

bundle_path = os.path.join(os.path.dirname(__file__), "model", "lung_nodule_ct_detection-0.6.8", "lung_nodule_ct_detection-0.6.8")
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
print(f"\n使用设备: {device}")
print(f"GPU: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU'}")
print(f"显存: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.2f} GB")

data_path = os.path.join("data", "1.3.6.1.4.1.14519.5.2.1.6279.6001.395623571499047043765181005112.nii.gz")
output_dir = "results"
os.makedirs(output_dir, exist_ok=True)

# 模型构建
model_start = time.time()
print("\n1. 构建模型...")

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
).to(device)

print("加载权重...")
checkpoint_path = os.path.join(bundle_path, "models", "model.pt")
checkpoint = torch.load(checkpoint_path, map_location=device, weights_only=False)
network.load_state_dict(checkpoint)
network.eval()

model_time = time.time() - model_start
print(f"模型构建完成，耗时: {model_time:.2f} 秒")

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
    score_thresh=0.02,
    topk_candidates_per_level=1000,
    nms_thresh=0.22,
    detections_per_img=300
)

# 用户指定的参数
roi_size = [384, 384, 128]
overlap = 0.25

print(f"\n2. 设置滑动窗口参数:")
print(f"   ROI大小: {roi_size}")
print(f"   重叠率: {overlap}")
print(f"   设备: {device}")

detector.set_sliding_window_inferer(
    roi_size=roi_size,
    overlap=overlap,
    sw_batch_size=1,
    mode='constant',
    device=device
)

detector.eval()

# 预处理
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

# 数据加载
data_start = time.time()
print("\n3. 加载数据...")
data_list = [{"image": data_path}]
dataset = Dataset(data=data_list, transform=preprocessing)
dataloader = DataLoader(
    dataset=dataset,
    batch_size=1,
    shuffle=False,
    num_workers=0,
    collate_fn=no_collation
)
data_time = time.time() - data_start
print(f"数据加载完成，耗时: {data_time:.2f} 秒")

# 推理
inference_start = time.time()
print(f"\n4. 开始推理 (ROI={roi_size}, overlap={overlap})...")
print("   这可能需要较长时间，请耐心等待...")

results = []
with torch.no_grad():
    for batch_idx, batch_data in enumerate(dataloader):
        inputs = [data["image"].to(device) for data in batch_data]
        print(f"   输入形状: {inputs[0].shape}")
        
        outputs = detector(inputs, use_inferer=True)
        
        for i, data in enumerate(batch_data):
            result = {**outputs[i], "image": data["image"]}
            result = postprocessing(result)
            results.append(result)

inference_time = time.time() - inference_start
print(f"\n推理完成!")
print(f"推理耗时: {inference_time:.2f} 秒 ({inference_time/60:.2f} 分钟)")

# 保存结果
save_start = time.time()
print("\n5. 保存结果...")
output_results = []
for result in results:
    boxes = result["box"].cpu().numpy() if isinstance(result["box"], torch.Tensor) else result["box"]
    labels = result["label"].cpu().numpy() if isinstance(result["label"], torch.Tensor) else result["label"]
    scores = result["label_scores"].cpu().numpy() if isinstance(result["label_scores"], torch.Tensor) else result["label_scores"]
    
    nodules = []
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
            }
        }
        nodules.append(nodule)
    
    output_results.append({
        "image": os.path.basename(data_path),
        "nodules": nodules,
        "total_nodules": len(nodules),
        "roi_size": roi_size,
        "overlap": overlap
    })

output_file = os.path.join(output_dir, f"detection_results_384x384x128.json")
with open(output_file, "w", encoding="utf-8") as f:
    json.dump(output_results, f, indent=4, ensure_ascii=False)

save_time = time.time() - save_start
print(f"结果已保存到: {output_file}")
print(f"保存耗时: {save_time:.2f} 秒")

# 打印结果汇总
total_time = time.time() - start_time
end_datetime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

print("\n" + "=" * 60)
print("推理完成!")
print("=" * 60)
print(f"\n📊 时间统计:")
print(f"  开始时间: {start_datetime}")
print(f"  结束时间: {end_datetime}")
print(f"  总耗时: {total_time:.2f} 秒 ({total_time/60:.2f} 分钟)")
print(f"\n⏱️ 详细耗时:")
print(f"  模型构建: {model_time:.2f} 秒")
print(f"  数据加载: {data_time:.2f} 秒")
print(f"  推理计算: {inference_time:.2f} 秒 ({inference_time/60:.2f} 分钟)")
print(f"  结果保存: {save_time:.2f} 秒")
print(f"\n⚙️ 参数配置:")
print(f"  ROI大小: {roi_size}")
print(f"  重叠率: {overlap}")
print(f"  设备: {device}")
print(f"\n🔍 检测结果:")
for result in output_results:
    print(f"  图像: {result['image']}")
    print(f"  检测到结节数量: {result['total_nodules']}")
    if result['nodules']:
        print(f"  结节详情:")
        for nodule in result['nodules']:
            print(f"    结节 {nodule['index']}: 置信度={nodule['score']:.4f}, 位置=({nodule['center']['x']:.2f}, {nodule['center']['y']:.2f}, {nodule['center']['z']:.2f}), 尺寸={nodule['dimensions']['width']:.2f}×{nodule['dimensions']['height']:.2f}×{nodule['dimensions']['depth']:.2f}")
print("\n" + "=" * 60)
