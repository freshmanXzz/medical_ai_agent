# Martin Medical AI Agent - 项目文档

## 目录

1. [项目概述](#1-项目概述)
2. [项目结构](#2-项目结构)
3. [核心模块说明](#3-核心模块说明)
4. [命令行接口](#4-命令行接口)
5. [API使用示例](#5-api使用示例)
6. [配置参数说明](#6-配置参数说明)
7. [测试说明](#7-测试说明)
8. [环境要求](#8-环境要求)

---

## 1. 项目概述

**Martin** 是一个基于 MONAI 框架的肺部结节检测医学 AI 系统，支持 CT 图像分析和 LLM 报告生成。

### 主要功能

- 医学影像处理：支持 NIfTI 和 MetaImage 格式
- 肺部结节检测：使用 RetinaNet 模型进行精准检测
- LLM 集成：接入 DeepSeek 进行报告分析和生成
- 命令行接口：提供便捷的 CLI 工具
- GPU 加速：支持 CUDA 加速推理

---

## 2. 项目结构

```
medical_ai_agent/
├── martin/                          # 核心包
│   ├── __init__.py                  # 包初始化，导出主要类
│   ├── __main__.py                  # 命令行入口
│   ├── inference.py                  # 推理模块（新版，推荐使用）
│   ├── llm/                         # LLM 模块
│   │   ├── __init__.py
│   │   └── deepseek_client.py       # DeepSeek API 客户端
│   └── monai/                       # 医学影像模块
│       ├── __init__.py
│       ├── nodule_detector.py       # 结节检测器（旧版）
│       └── image_processor.py        # 图像处理工具
├── tests/                           # 测试目录
│   ├── test_inference_direct.py     # 直接推理测试
│   ├── test_monai.py                # MONAI 模块单元测试
│   ├── test_llm.py                  # LLM 模块单元测试
│   └── test_model_only.py            # 模型加载验证
├── model/                           # 模型文件目录
│   └── lung_nodule_ct_detection-0.6.8/
│       └── lung_nodule_ct_detection-0.6.8/
│           ├── configs/             # 官方配置文件
│           ├── models/              # 模型权重
│           └── scripts/             # 官方脚本
├── data/                           # 数据文件目录
├── doc/                            # 文档目录
├── README.md                       # 项目说明
├── requirements.txt                # 依赖清单
└── pyproject.toml                  # 项目配置
```

---

## 3. 核心模块说明

### 3.1 推理模块 (inference.py)

**推荐使用**，封装了完整的推理流程。

#### 类：LungNoduleDetector

```python
from martin.inference import LungNoduleDetector, detect_nodules

# 方式一：使用类
detector = LungNoduleDetector()
result = detector.detect("path/to/image.nii.gz")

# 方式二：使用便捷函数
result = detect_nodules("path/to/image.nii.gz")
```

#### 主要方法

| 方法名 | 说明 | 参数 | 返回值 |
|:-------|:-----|:-----|:-------|
| `detect()` | 检测肺部结节 | `image_path: str` | `Dict` - 包含检测结果的字典 |
| `detect_batch()` | 批量检测 | `image_paths: List[str]` | `List[Dict]` - 检测结果列表 |
| `_prepare_dataloader()` | 准备数据加载器 | `image_path: str` | DataLoader 对象 |
| `_execute_inference()` | 执行推理 | `dataloader` | `List` - 原始结果列表 |
| `_parse_results()` | 解析检测结果 | `results: List` | `List[Dict]` - 结节列表 |
| `_log_nodule_summary()` | 记录结节摘要 | `nodules: List[Dict]` | None |

#### 返回结果格式

```json
{
    "image": "filename.nii.gz",
    "total_nodules": 2,
    "nodules": [
        {
            "index": 1,
            "score": 0.9947,
            "center": {"x": -64.0, "y": -5.09, "z": -85.45},
            "dimensions": {"width": 4.89, "height": 4.94, "depth": 4.94},
            "diameter": 4.94
        }
    ]
}
```

#### 特性

- **自动设备选择**：优先使用 GPU，无 GPU 时自动降级到 CPU
- **日志记录**：完整的推理过程日志，支持控制台和文件输出
- **模块化设计**：推理流程拆分为独立函数，便于维护和测试

---

### 3.2 旧版检测器 (monai/nodule_detector.py)

**向后兼容**的旧版检测器，功能与新版基本一致。

#### 类：NoduleDetector

```python
from martin.monai import NoduleDetector

detector = NoduleDetector(device='cuda')
nodules = detector.detect("path/to/image.nii.gz")
detector.save_results(nodules, "results.json")
```

#### 主要方法

| 方法名 | 说明 |
|:-------|:-----|
| `detect()` | 检测肺部结节，返回结节列表 |
| `save_results()` | 保存检测结果到 JSON 文件 |

---

### 3.3 图像处理模块 (monai/image_processor.py)

#### 类：ImageProcessor

静态方法集合，提供医学图像处理功能。

```python
from martin.monai import ImageProcessor

# 读取 NIfTI 文件
data, affine, header = ImageProcessor.read_nifti("image.nii.gz")

# 读取 MetaImage 文件
data, spacing, metadata = ImageProcessor.read_metaimage("image.mhd")

# 格式转换
ImageProcessor.metaimage_to_nifti("input.mhd", "output.nii.gz")

# 灰度归一化
normalized = ImageProcessor.normalize_intensity(data)

# 图像重采样
resampled = ImageProcessor.resample(data, [1.0, 1.0, 2.5], [0.7, 0.7, 1.25])

# 获取图像信息
info = ImageProcessor.get_image_info("image.nii.gz")
```

#### 支持的图像格式

| 格式 | 扩展名 | 说明 |
|:-----|:-------|:-----|
| NIfTI | `.nii`, `.nii.gz` | 标准医学图像格式 |
| MetaImage | `.mhd` / `.raw` | ITK 常用格式 |

---

### 3.4 LLM 模块 (llm/deepseek_client.py)

#### 类：DeepSeekClient

DeepSeek API 客户端，用于生成医学报告和分析。

```python
from martin.llm import DeepSeekClient

# 初始化客户端
client = DeepSeekClient(api_key="your-api-key")
# 或设置环境变量：export DEEPSEEK_API_KEY="your-api-key"

# 与模型对话
response = client.chat([{"role": "user", "content": "Hello!"}])

# 分析报告
analysis = client.analyze_report(report_data)

# 生成报告
report = client.generate_report(nodules)

# 总结发现
summary = client.summarize_findings(findings)
```

#### 主要方法

| 方法名 | 说明 | 参数 | 返回值 |
|:-------|:-----|:-----|:-------|
| `chat()` | 与模型对话 | `messages`, `temperature`, `max_tokens` | `str` - 模型回复 |
| `analyze_report()` | 分析医学报告 | `report_data: Dict` | `str` - 分析结果 |
| `generate_report()` | 生成医学报告 | `nodules: List[Dict]` | `str` - 格式化的报告 |
| `summarize_findings()` | 总结检测发现 | `findings: List[Dict]` | `str` - 总结内容 |

---

## 4. 命令行接口

### 使用方式

```bash
python -m martin <command> [options]
```

### 可用命令

#### 4.1 detect - 检测肺部结节

```bash
python -m martin detect -i <input_image> [-o <output_json>] [--device <cuda|cpu>]
```

**参数说明：**

| 参数 | 必填 | 默认值 | 说明 |
|:-----|:----:|:-------|:-----|
| `-i`, `--input` | 是 | - | 输入图像文件路径 |
| `-o`, `--output` | 否 | `results/detection_results.json` | 输出结果文件路径 |
| `--device` | 否 | 自动选择 | 运行设备 (cuda/cpu) |

**示例：**

```bash
python -m martin detect -i data/ct_scan.nii.gz -o results/detection.json
```

#### 4.2 analyze - 分析检测结果

```bash
python -m martin analyze -i <input_json> [--api-key <key>]
```

**参数说明：**

| 参数 | 必填 | 默认值 | 说明 |
|:-----|:----:|:-------|:-----|
| `-i`, `--input` | 是 | - | 检测结果 JSON 文件路径 |
| `--api-key` | 否 | 环境变量 | DeepSeek API 密钥 |

**示例：**

```bash
python -m martin analyze -i results/detection.json --api-key YOUR_API_KEY
```

#### 4.3 report - 生成医学报告

```bash
python -m martin report -i <input_json> [-o <output_txt>] [--api-key <key>]
```

**参数说明：**

| 参数 | 必填 | 默认值 | 说明 |
|:-----|:----:|:-------|:-----|
| `-i`, `--input` | 是 | - | 检测结果 JSON 文件路径 |
| `-o`, `--output` | 否 | `results/report.txt` | 输出报告文件路径 |
| `--api-key` | 否 | 环境变量 | DeepSeek API 密钥 |

**示例：**

```bash
python -m martin report -i results/detection.json -o results/report.txt
```

#### 4.4 convert - 转换图像格式

```bash
python -m martin convert -i <input_file> -o <output_file>
```

**示例：**

```bash
python -m martin convert -i data/scan.mhd -o data/scan.nii.gz
```

#### 4.5 info - 查看图像信息

```bash
python -m martin info -i <input_image>
```

**示例：**

```bash
python -m martin info -i data/ct_scan.nii.gz
```

---

## 5. API 使用示例

### 5.1 基础使用

```python
from martin.inference import detect_nodules

# 检测结节
result = detect_nodules("data/ct_scan.nii.gz")

print(f"检测到 {result['total_nodules']} 个结节")
for nodule in result['nodules']:
    print(f"  结节 {nodule['index']}: 置信度={nodule['score']:.2%}")
```

### 5.2 批量处理

```python
from martin.inference import LungNoduleDetector

detector = LungNoduleDetector()

image_paths = [
    "data/scan1.nii.gz",
    "data/scan2.nii.gz",
    "data/scan3.nii.gz"
]

results = detector.detect_batch(image_paths)

for result in results:
    if 'error' in result:
        print(f"处理 {result['image']} 失败: {result['error']}")
    else:
        print(f"{result['image']}: {result['total_nodules']} 个结节")
```

### 5.3 结合 LLM 生成报告

```python
from martin.inference import detect_nodules
from martin.llm import DeepSeekClient

# 检测结节
result = detect_nodules("data/ct_scan.nii.gz")

# 生成报告
client = DeepSeekClient()  # 需要设置 DEEPSEEK_API_KEY 环境变量
report = client.generate_report(result['nodules'])

print(report)
```

### 5.4 图像格式转换

```python
from martin.monai import ImageProcessor

# MetaImage 转 NIfTI
ImageProcessor.metaimage_to_nifti(
    "data/scan.mhd",
    "data/scan.nii.gz"
)

# 获取图像信息
info = ImageProcessor.get_image_info("data/scan.nii.gz")
print(f"尺寸: {info['dim_size']}")
print(f"像素间距: {info['spacing']} mm")
```

---

## 6. 配置参数说明

### 6.1 推理参数（官方配置）

来自 `model/lung_nodule_ct_detection-0.6.8/configs/inference.json`

#### 滑动窗口参数

| 参数 | 默认值 | 说明 |
|:-----|:-------|:-----|
| `roi_size` | [512, 512, 192] | 滑动窗口尺寸 |
| `overlap` | 0.25 | 窗口重叠率 |
| `sw_batch_size` | 1 | 批处理大小 |
| `mode` | 'constant' | 填充模式 |

#### 检测器参数

| 参数 | 默认值 | 说明 |
|:-----|:-------|:-----|
| `score_thresh` | 0.02 | 置信度阈值 |
| `topk_candidates_per_level` | 1000 | 每层最大候选框数 |
| `nms_thresh` | 0.22 | NMS 非极大值抑制阈值 |
| `detections_per_img` | 300 | 每张图像最大检测数 |

#### 预处理参数

| 参数 | 值 | 说明 |
|:-----|:---|:-----|
| `pixdim` | [0.703125, 0.703125, 1.25] | 像素间距 (mm) |
| `a_min` | -1024.0 | CT 值最小值 (HU) |
| `a_max` | 300.0 | CT 值最大值 (HU) |
| `b_min` | 0.0 | 归一化最小值 |
| `b_max` | 1.0 | 归一化最大值 |

---

## 7. 测试说明

### 7.1 测试文件说明

| 文件 | 说明 | 运行命令 |
|:-----|:-----|:---------|
| `test_inference_direct.py` | 直接推理测试，不依赖 unittest | `python tests/test_inference_direct.py` |
| `test_monai.py` | MONAI 模块单元测试 | `python -m pytest tests/test_monai.py -v` |
| `test_llm.py` | LLM 模块单元测试 | `python -m pytest tests/test_llm.py -v` |
| `test_model_only.py` | 模型加载验证（不执行推理） | `python tests/test_model_only.py` |

### 7.2 运行测试

```bash
# 运行所有测试
python -m pytest tests/ -v

# 运行特定测试
python -m pytest tests/test_monai.py -v

# 直接运行推理测试
python tests/test_inference_direct.py
```

---

## 8. 环境要求

### 8.1 系统要求

| 组件 | 最低要求 | 推荐配置 |
|:-----|:--------|:---------|
| Python | >= 3.10 | 3.10 / 3.11 |
| GPU | - | NVIDIA GPU with CUDA |
| GPU 显存 | - | >= 12GB |
| 内存 | 8GB | 16GB+ |

### 8.2 Python 依赖

```
torch>=2.0.0
torchvision>=0.15.0
torchaudio>=2.0.0
monai>=1.3.0
nibabel>=5.0.0
numpy>=1.24.0
matplotlib>=3.7.0
scipy>=1.10.0
requests>=2.31.0
```

### 8.3 模型文件

从 MONAI Model Zoo 下载预训练模型：

```
model/lung_nodule_ct_detection-0.6.8/
└── lung_nodule_ct_detection-0.6.8/
    └── models/
        └── model.pt    # 需要下载的模型权重
```

---

## 附录 A: 返回值数据结构

### 结节数据结构

```python
{
    "index": int,           # 结节索引（从1开始）
    "score": float,         # 置信度 (0-1)
    "center": {             # 结节中心位置（世界坐标系，mm）
        "x": float,
        "y": float,
        "z": float
    },
    "dimensions": {         # 结节尺寸（mm）
        "width": float,
        "height": float,
        "depth": float
    },
    "diameter": float      # 最大直径（mm）
}
```

### 检测结果数据结构

```python
{
    "image": str,           # 图像文件名
    "total_nodules": int,   # 检测到的结节总数
    "nodules": [            # 结节列表
        {...},              # 结节数据结构
        ...
    ]
}
```

---

## 附录 B: 日志说明

日志文件保存在 `log/` 目录下，按日期命名：

```
log/
└── 2026-06-08.log
```

日志格式：

```
2026-06-08 12:21:11,387 - martin.inference - INFO - 检测到 NVIDIA GPU，将使用 CUDA 加速
2026-06-08 12:21:18,510 - martin.inference - INFO - 变换管道设置完成
2026-06-08 12:21:18,511 - martin.inference - INFO - LungNoduleDetector 初始化成功，使用设备: cuda:0
```

---

## 版本信息

- **版本**: 0.1.0
- **作者**: Martin
- **框架**: MONAI >= 1.3.0
- **模型**: lung_nodule_ct_detection-0.6.8

---

*文档生成时间: 2026-06-08*
