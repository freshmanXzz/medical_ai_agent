# 肺部结节检测项目 - 代码阅读指南

## 📋 目录
1. [项目概述](#项目概述)
2. [文件结构](#文件结构)
3. [推荐阅读顺序](#推荐阅读顺序)
4. [核心代码解析](#核心代码解析)
5. [关键参数说明](#关键参数说明)
6. [运行指南](#运行指南)
7. [常见问题](#常见问题)

---

## 1. 项目概述

本项目使用 MONAI 框架和 RetinaNet 模型进行肺部结节检测。主要功能：
- 读取 NIfTI 格式的 CT 图像
- 使用预训练模型进行推理
- 输出检测到的结节位置和置信度
- 支持可视化展示

---

## 2. 文件结构

```
medical-ai-agent/
├── data/                           # CT图像数据
│   └── 1.3.6.1.4.1.14519.5.2.1.6279.6001.395623571499047043765181005112.nii.gz
├── model/                          # 模型文件
│   └── lung_nodule_ct_detection-0.6.8/
│       └── lung_nodule_ct_detection-0.6.8/
│           ├── configs/            # 官方配置文件
│           │   ├── inference.json  # 推理配置
│           │   └── metadata.json   # 模型元数据
│           ├── models/             # 模型权重
│           │   └── model.pt        # 预训练权重
│           └── scripts/            # 官方脚本
│               └── detection_inferer.py  # 推理器实现
├── results/                        # 检测结果
│   └── detection_results.json      # JSON格式结果
├── visualization/                  # 可视化结果
│   ├── nodule_slices.png           # 结节切片视图
│   ├── mip_visualization.png       # 最大密度投影
│   └── nodule_enlarged.png         # 结节放大图
├── 1.txt                           # 需求文档
├── inference_final.py              # ⭐ 完整推理脚本（推荐起点）
├── inference_384.py                # 使用 [384,384,128] 参数
└── visualize_results.py            # 可视化脚本
```

---

## 3. 推荐阅读顺序

### 🔹 第一阶段：了解整体流程
1. **`inference_final.py`** - 完整推理流程，从数据加载到结果输出
2. **`model/lung_nodule_ct_detection-0.6.8/configs/inference.json`** - 官方配置

### 🔹 第二阶段：深入理解组件
3. **`model/lung_nodule_ct_detection-0.6.8/scripts/detection_inferer.py`** - 推理器实现
4. **`visualize_results.py`** - 可视化方法

### 🔹 第三阶段：实践验证
5. 运行 `inference_final.py` 观察输出
6. 运行 `visualize_results.py` 查看可视化效果

---

## 4. 核心代码解析

### 4.1 主推理流程 (`inference_final.py`)

```python
# 第1部分：导入依赖（1-20行）
import torch
from monai.transforms import Compose, LoadImaged, ...
from monai.apps.detection import RetinaNetDetector, ...

# 第2部分：设备配置（22-25行）
device = torch.device('cuda:0' if torch.cuda.is_available() else 'cpu')

# 第3部分：模型构建（30-50行）
# - AnchorGenerator: 生成锚点框
# - resnet50: 特征提取骨干网络
# - RetinaNet: 检测网络

# 第4部分：加载权重（52-56行）
checkpoint = torch.load('model.pt')
network.load_state_dict(checkpoint)

# 第5部分：检测器配置（58-80行）
detector = RetinaNetDetector(...)
detector.set_sliding_window_inferer(
    roi_size=[192, 192, 64],    # 滑动窗口大小
    overlap=0.5,                 # 重叠率
    device=device
)

# 第6部分：预处理（82-95行）
preprocessing = Compose([
    LoadImaged(keys="image"),           # 加载图像
    Orientationd(keys="image", axcodes="RAS"),  # 方向转换
    Spacingd(keys="image", pixdim=[0.703125, 0.703125, 1.25]),  # 重采样
    ScaleIntensityRanged(              # 灰度归一化
        keys="image",
        a_min=-1024.0,   # CT值下限（空气）
        a_max=300.0,     # CT值上限（软组织）
        b_min=0.0,
        b_max=1.0
    )
])

# 第7部分：执行推理（100-110行）
outputs = detector(inputs, use_inferer=True)
```

### 4.2 关键组件说明

| 组件 | 作用 | 关键参数 |
|:-----|:-----|:---------|
| **AnchorGenerator** | 生成不同尺度的锚点框 | `feature_map_scales`, `base_anchor_shapes` |
| **resnet50** | 提取图像特征 | `spatial_dims=3`, `n_input_channels=1` |
| **RetinaNet** | 目标检测网络 | `num_classes=1`, `num_anchors=3` |
| **RetinaNetDetector** | 检测器封装 | `network`, `anchor_generator` |

### 4.3 滑动窗口推理

```python
detector.set_sliding_window_inferer(
    roi_size=[192, 192, 64],  # 每次处理的窗口大小
    overlap=0.5,               # 窗口重叠比例
    sw_batch_size=1,           # 批处理大小
    mode='constant',           # 边界填充方式
    device=device              # 推理设备
)
```

**工作原理**：
1. 将大图像分成多个小窗口
2. 对每个窗口独立推理
3. 合并所有窗口的检测结果

---

## 5. 关键参数说明

### 5.1 预处理参数

| 参数 | 值 | 说明 |
|:-----|:---|:-----|
| `axcodes` | "RAS" | 图像方向（Right-Anterior-Superior） |
| `pixdim` | [0.703125, 0.703125, 1.25] | 目标像素间距（mm） |
| `a_min` | -1024.0 | CT值下限（空气） |
| `a_max` | 300.0 | CT值上限（软组织） |

### 5.2 检测参数

| 参数 | 值 | 说明 |
|:-----|:---|:-----|
| `roi_size` | [192, 192, 64] | 滑动窗口大小 |
| `overlap` | 0.5 | 窗口重叠率 |
| `score_thresh` | 0.02 | 检测置信度阈值 |
| `nms_thresh` | 0.22 | NMS阈值 |
| `detections_per_img` | 300 | 最大检测数 |

### 5.3 参数对比

| 参数配置 | ROI大小 | 检测结节数 | 推理时间 | 显存需求 |
|:--------|:-------|:---------:|:--------:|:--------:|
| 优化参数 | [192, 192, 64] | 2 | ~10秒 | <4GB |
| 用户参数 | [384, 384, 128] | 1 | ~45-60秒 | ~12GB |
| 官方参数 | [512, 512, 192] | - | - | >12GB ❌ |

---

## 6. 运行指南

### 6.1 环境要求
- Python 3.10+
- PyTorch 2.5+ (CUDA 12.1)
- MONAI 1.3+
- nibabel

### 6.2 运行命令

```bash
# 使用优化参数（推荐）
python inference_final.py

# 使用用户参数 [384, 384, 128]
python inference_384.py

# 可视化结果
python visualize_results.py
```

### 6.3 输出说明

**检测结果格式** (`results/detection_results.json`)：
```json
{
    "image": "1.3.6.1.4.1.14519.5.2.1.6279.6001.395623571499047043765181005112.nii.gz",
    "nodules": [
        {
            "index": 1,
            "score": 0.9779,
            "center": {"x": -64.00, "y": -5.29, "z": -85.50},
            "dimensions": {"width": 4.91, "height": 4.69, "depth": 5.24}
        }
    ],
    "total_nodules": 1
}
```

---

## 7. 常见问题

### Q1: 为什么官方参数 [512, 512, 192] 无法运行？
**A**: 官方参数需要超过12GB显存，RTX 3060只有12GB，会导致显存不足。

### Q2: 检测结果数量为什么不同？
**A**: 主要受 `score_thresh` 参数影响：
- `score_thresh=0.02`（默认）：检测高置信度结节
- `score_thresh=0.001`：检测更多候选结节（可能包含假阳性）

### Q3: NMS阈值的作用？
**A**: NMS（非极大值抑制）用于去除重叠检测框，阈值越低越严格。

### Q4: 如何调整参数？
**A**: 修改 `inference_final.py` 中的以下代码：
```python
detector.set_sliding_window_inferer(
    roi_size=[192, 192, 64],  # 修改窗口大小
    overlap=0.5                # 修改重叠率
)

detector.set_box_selector_parameters(
    score_thresh=0.02,  # 修改检测阈值
    nms_thresh=0.22     # 修改NMS阈值
)
```

---

## 📚 参考资料

1. **MONAI官方文档**: https://docs.monai.io/
2. **RetinaNet论文**: https://arxiv.org/abs/1708.02002
3. **LUNA16数据集**: https://luna16.grand-challenge.org/

---

**阅读建议**：从 `inference_final.py` 开始，逐段理解数据加载、模型构建、推理执行的完整流程！
