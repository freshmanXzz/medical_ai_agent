# 导入必要的依赖库
import os
import sys
import json
import torch

# 打印程序标题
print("=" * 60)
print("肺部结节检测推理 - 最终版本")
print("=" * 60)

# 设置模型路径：拼接当前目录下的模型文件夹路径
bundle_path = os.path.join(os.path.dirname(__file__), "model", "lung_nodule_ct_detection-0.6.8", "lung_nodule_ct_detection-0.6.8")
# 将模型脚本目录添加到系统路径，以便导入自定义模块
sys.path.insert(0, os.path.join(bundle_path, "scripts"))

# 导入MONAI的核心组件
from monai.transforms import Compose, LoadImaged, EnsureChannelFirstd, Orientationd, Spacingd, ScaleIntensityRanged, EnsureTyped
from monai.apps.detection.transforms.dictionary import ClipBoxToImaged, AffineBoxToWorldCoordinated, ConvertBoxModed
from monai.data import Dataset, DataLoader
from monai.data.utils import no_collation
from monai.apps.detection.networks.retinanet_detector import RetinaNetDetector
from monai.apps.detection.utils.anchor_utils import AnchorGeneratorWithAnchorShape
from monai.networks.nets import resnet50
from monai.apps.detection.networks.retinanet_network import resnet_fpn_feature_extractor, RetinaNet

# 设置计算设备：优先使用GPU（cuda:0），否则使用CPU
device = torch.device('cuda:0' if torch.cuda.is_available() else 'cpu')
print(f"使用设备: {device}")

# 设置数据路径和输出目录
data_path = os.path.join("data", "1.3.6.1.4.1.14519.5.2.1.6279.6001.395623571499047043765181005112.nii.gz")
output_dir = "results"
# 创建输出目录（如果不存在）
os.makedirs(output_dir, exist_ok=True)

# ==================== 模型构建阶段 ====================
print("\n构建模型...")

# 定义模型参数
spatial_dims = 3                  # 3D检测任务
num_classes = 1                   # 只有一个类别：肺部结节
size_divisible = [16, 16, 8]      # 特征图尺寸对齐要求

# 1. 创建锚点生成器（Anchor Generator）
# 作用：在特征图上生成不同尺度的锚点框
# 参数说明：
#   feature_map_scales: 特征图相对于原图的缩放比例
#   base_anchor_shapes: 锚点框的基础尺寸（宽, 高, 深）
anchor_generator = AnchorGeneratorWithAnchorShape(
    feature_map_scales=[1, 2, 4],
    base_anchor_shapes=[[6, 8, 4], [8, 6, 5], [10, 10, 6]]
)

# 2. 创建骨干网络（Backbone）：ResNet50
# 作用：提取图像特征
# 参数说明：
#   spatial_dims: 3D网络
#   n_input_channels: 输入通道数（CT图像为单通道）
#   conv1_t_stride: 第一层卷积的步长
#   conv1_t_size: 第一层卷积核大小
backbone = resnet50(
    spatial_dims=3,
    n_input_channels=1,
    conv1_t_stride=[2, 2, 1],
    conv1_t_size=[7, 7, 7]
)

# 3. 创建特征提取器（FPN）
# 作用：构建特征金字塔网络，融合多尺度特征
feature_extractor = resnet_fpn_feature_extractor(backbone, 3, False, [1, 2], None)

# 4. 创建RetinaNet检测网络
# 作用：端到端的目标检测网络
# 参数说明：
#   spatial_dims: 3D检测
#   num_classes: 类别数
#   num_anchors: 每个位置的锚点数量
#   feature_extractor: 特征提取器
#   size_divisible: 特征图对齐
#   use_list_output: 是否使用列表输出
network = RetinaNet(
    spatial_dims=spatial_dims,
    num_classes=num_classes,
    num_anchors=3,
    feature_extractor=feature_extractor,
    size_divisible=size_divisible,
    use_list_output=False
).to(device)  # 将网络移动到指定设备

# 加载预训练权重
print("加载权重...")
checkpoint_path = os.path.join(bundle_path, "models", "model.pt")
checkpoint = torch.load(checkpoint_path, map_location=device, weights_only=False)
network.load_state_dict(checkpoint)
network.eval()  # 设置为评估模式

# ==================== 检测器配置阶段 ====================
print("创建检测器...")

# 创建RetinaNet检测器实例
detector = RetinaNetDetector(
    network=network,
    anchor_generator=anchor_generator,
    debug=False,
    spatial_dims=spatial_dims,
    num_classes=num_classes,
    size_divisible=size_divisible
)

# 设置目标键名称（用于数据字典）
detector.set_target_keys(box_key='box', label_key='label')

# 设置检测框选择器参数
# 参数说明：
#   score_thresh: 检测置信度阈值（低于此值的框被过滤）
#   topk_candidates_per_level: 每层特征图保留的候选框数量
#   nms_thresh: NMS（非极大值抑制）的IoU阈值
#   detections_per_img: 每张图最大检测框数量
detector.set_box_selector_parameters(
    score_thresh=0.05,
    topk_candidates_per_level=500,
    nms_thresh=0.22,
    detections_per_img=100
)

# 设置滑动窗口推理器（用于处理大尺寸图像）
# 参数说明：
#   roi_size: 滑动窗口大小（每次处理的图像块尺寸）
#   overlap: 窗口重叠比例（避免边界效应）
#   sw_batch_size: 批处理大小
#   mode: 边界填充模式
#   device: 推理设备
detector.set_sliding_window_inferer(
    roi_size=[192, 192, 64],
    overlap=0.5,
    sw_batch_size=1,
    mode='constant',
    device=device
)

detector.eval()  # 设置检测器为评估模式

# ==================== 预处理管道 ====================
print("创建预处理...")

# 预处理管道：按顺序执行以下操作
preprocessing = Compose([
    LoadImaged(keys="image"),                              # 加载NIfTI图像
    EnsureChannelFirstd(keys="image"),                      # 确保通道维度在前
    Orientationd(keys="image", axcodes="RAS"),             # 将图像方向转换为RAS坐标系
    Spacingd(keys="image", pixdim=[0.703125, 0.703125, 1.25]),  # 重采样到目标像素间距
    ScaleIntensityRanged(                                  # 灰度值归一化
        keys="image",
        a_min=-1024.0,   # CT值下限（空气的HU值）
        a_max=300.0,     # CT值上限（软组织的典型范围）
        b_min=0.0,       # 归一化后最小值
        b_max=1.0,       # 归一化后最大值
        clip=True        # 是否裁剪超出范围的值
    ),
    EnsureTyped(keys="image")                              # 转换为Tensor类型
])

# 后处理管道：处理检测结果
postprocessing = Compose([
    ClipBoxToImaged(                                       # 将检测框裁剪到图像边界内
        box_keys="box",
        label_keys="label",
        box_ref_image_keys="image",
        remove_empty=True
    ),
    AffineBoxToWorldCoordinated(                           # 将检测框坐标转换到世界坐标系
        box_keys="box",
        box_ref_image_keys="image",
        affine_lps_to_ras=True
    ),
    ConvertBoxModed(box_keys="box", src_mode="xyzxyz", dst_mode="cccwhd"),  # 转换边界框格式
])

# ==================== 数据加载阶段 ====================
print("加载数据...")

# 创建数据列表（支持批量处理多张图像）
data_list = [{"image": data_path}]

# 创建数据集和数据加载器
dataset = Dataset(data=data_list, transform=preprocessing)
dataloader = DataLoader(
    dataset=dataset,
    batch_size=1,           # 批大小
    shuffle=False,          # 不打乱顺序
    num_workers=0,          # 不使用多线程加载
    collate_fn=no_collation  # 保持原始数据格式
)

# ==================== 推理执行阶段 ====================
print("\n执行推理（这可能需要几分钟，请耐心等待）...")
results = []

# 使用torch.no_grad()禁用梯度计算，节省内存并加速推理
with torch.no_grad():
    # 遍历数据加载器
    for batch_idx, batch_data in enumerate(dataloader):
        print(f"处理图像 {batch_idx + 1}...")
        
        # 将数据移动到指定设备
        inputs = [data["image"].to(device) for data in batch_data]
        print(f"输入形状: {inputs[0].shape}")
        
        # 运行检测器进行推理
        print("运行检测器...")
        outputs = detector(inputs, use_inferer=True)
        print(f"检测完成")
        
        # 对每个结果进行后处理
        for i, data in enumerate(batch_data):
            result = {**outputs[i], "image": data["image"]}
            result = postprocessing(result)
            results.append(result)
            print("后处理完成")

# ==================== 结果保存阶段 ====================
print("\n保存结果...")
output_results = []

# 处理检测结果
for result in results:
    # 将Tensor转换为NumPy数组
    boxes = result["box"].cpu().numpy() if isinstance(result["box"], torch.Tensor) else result["box"]
    labels = result["label"].cpu().numpy() if isinstance(result["label"], torch.Tensor) else result["label"]
    scores = result["label_scores"].cpu().numpy() if isinstance(result["label_scores"], torch.Tensor) else result["label_scores"]
    
    # 整理结节信息
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
    
    # 添加到输出结果
    output_results.append({
        "image": os.path.basename(data_path),
        "nodules": nodules,
        "total_nodules": len(nodules)
    })

# 将结果保存为JSON文件
output_file = os.path.join(output_dir, "detection_results.json")
with open(output_file, "w", encoding="utf-8") as f:
    json.dump(output_results, f, indent=4, ensure_ascii=False)

print(f"结果已保存到: {output_file}")

# ==================== 结果输出阶段 ====================
print("\n检测结果汇总:")
print("-" * 60)
for result in output_results:
    print(f"图像: {result['image']}")
    print(f"检测到结节数量: {result['total_nodules']}")
    if result['nodules']:
        print("\n结节详情:")
        for nodule in result['nodules']:
            print(f"  结节 {nodule['index']}:")
            print(f"    置信度: {nodule['score']:.4f}")
            print(f"    中心位置: ({nodule['center']['x']:.2f}, {nodule['center']['y']:.2f}, {nodule['center']['z']:.2f})")
            print(f"    尺寸: {nodule['dimensions']['width']:.2f} x {nodule['dimensions']['height']:.2f} x {nodule['dimensions']['depth']:.2f}")
    print("-" * 60)

print("\n推理完成!")
