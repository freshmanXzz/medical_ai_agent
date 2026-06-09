# Martin - Medical AI Agent 项目文档

> 基于 MONAI 深度学习框架和 DeepSeek 大语言模型的肺部 CT 结节检测与病例报告生成系统

---

## 目录

1. [项目概述](#1-项目概述)
2. [项目结构](#2-项目结构)
3. [核心模块详解](#3-核心模块详解)
   - 3.1 [martin/__init__.py - 包初始化](#31-martin__init__py)
   - 3.2 [martin/__main__.py - 命令行入口](#32-martin__main__py)
   - 3.3 [martin/inference.py - 推理模块](#33-martininferencepy)
4. [MONAI 子模块](#4-monai-子模块)
   - 4.1 [martin/monai/__init__.py](#41-martinmonai__init__py)
   - 4.2 [martin/monai/nodule_detector.py - 结节检测器](#42-martinmonainodule_detectorpy)
   - 4.3 [martin/monai/image_processor.py - 图像处理](#43-martinmonaiimage_processorpy)
5. [LLM 子模块](#5-llm-子模块)
   - 5.1 [martin/llm/__init__.py](#51-martinllm__init__py)
   - 5.2 [martin/llm/deepseek_client.py - DeepSeek 客户端](#52-martinllmdeepseek_clientpy)
   - 5.3 [martin/llm/case_generator.py - 病例生成器](#53-martinllmcase_generatorpy)
6. [工具模块](#6-工具模块)
   - 6.1 [martin/util/__init__.py](#61-martinutil__init__py)
   - 6.2 [martin/util/logger.py - 日志工具](#62-martinutilloggerpy)
7. [测试模块](#7-测试模块)
8. [命令行使用指南](#8-命令行使用指南)
9. [API 使用示例](#9-api-使用示例)
10. [环境配置](#10-环境配置)

---

## 1. 项目概述

Martin 是一个医疗 AI 智能体，主要功能：

- **肺部结节检测**：基于 MONAI 框架的 RetinaNet 3D 目标检测模型
- **病例报告生成**：支持模板生成和 LLM 智能生成两种模式
- **医学图像转换**：支持 MetaImage (.mhd) 转 NIfTI (.nii.gz)
- **LLM 分析**：调用 DeepSeek API 进行智能医学分析

### 技术栈

| 组件 | 技术 |
|:-----|:-----|
| 深度学习 | PyTorch + MONAI |
| LLM | DeepSeek API (支持兼容 OpenAI 协议的端点) |
| 图像处理 | Nibabel, NumPy, SciPy |
| 模型 | RetinaNet 3D + ResNet50 骨干网络 |
| GPU 加速 | CUDA 11.8 |

---

## 2. 项目结构

```
medical_ai_agent/
├── martin/                    # 核心源码包
│   ├── __init__.py            # 包初始化，导出核心类
│   ├── __main__.py            # CLI 命令行入口
│   ├── inference.py           # 统一推理模块
│   │
│   ├── monai/                 # MONAI 医学影像子模块
│   │   ├── __init__.py        # 子模块初始化
│   │   ├── nodule_detector.py # 结节检测器
│   │   └── image_processor.py # 图像处理工具
│   │
│   ├── llm/                   # LLM 接入子模块
│   │   ├── __init__.py        # 子模块初始化
│   │   ├── deepseek_client.py # DeepSeek API 客户端
│   │   └── case_generator.py  # 病例报告生成器
│   │
│   └── util/                  # 通用工具子模块
│       ├── __init__.py        # 子模块初始化
│       └── logger.py          # 统一日志工具类
│
├── tests/                     # 单元测试
│   ├── test_monai.py          # MONAI 模块测试
│   ├── test_model_only.py     # 模型加载测试
│   ├── test_inference_direct.py # 直接推理测试
│   ├── test_logger.py         # 日志工具测试
│   ├── test_case_generator.py # 病例生成器测试
│   ├── test_llm.py            # LLM 客户端测试
│   └── test_full_pipeline.py  # 完整流程测试
│
├── model/                     # 模型权重文件
│   └── lung_nodule_ct_detection-0.6.8/
│       └── lung_nodule_ct_detection-0.6.8/
│           ├── configs/       # 模型配置
│           ├── scripts/       # 模型脚本
│           └── models/
│               └── model.pt   # 权重文件
│
├── data/                      # 测试数据
│   └── raw_data/              # 原始数据
│
├── doc/                       # 项目文档
│   └── API_DOCUMENTATION.md
│
├── .gitignore                 # Git 忽略规则
├── LICENSE                    # 开源协议
├── README.md                  # 项目说明
├── pyproject.toml             # 项目配置
└── requirements.txt           # Python 依赖
```

### 目录说明

| 目录 | 用途 |
|:-----|:-----|
| `martin/` | 核心源码，所有业务逻辑 |
| `martin/monai/` | MONAI 相关：模型加载、推理、图像处理 |
| `martin/llm/` | LLM 相关：API 调用、报告生成 |
| `martin/util/` | 通用工具：日志等可复用组件 |
| `tests/` | 单元测试和集成测试 |
| `model/` | 预训练模型权重 |
| `data/` | 测试数据 |
| `doc/` | 项目文档 |
| `results/` | 运行输出结果（自动生成） |
| `log/` | 日志文件（自动生成） |

---

## 3. 核心模块详解

### 3.1 [martin/__init__.py](file:///E:/moani/medical_ai_agent/martin/__init__.py)

**作用**：核心包初始化文件

**功能**：
- 定义版本号和作者信息
- 统一导出核心类和函数，方便外部调用

**导出的内容**：
```python
from martin import LungNoduleDetector  # 检测器类
from martin import detect_nodules      # 便捷检测函数
from martin import NoduleDetector      # MONAI 检测器
from martin import ImageProcessor      # 图像处理
from martin import DeepSeekClient      # LLM 客户端
from martin import CaseGenerator       # 病例生成器
```

---

### 3.2 [martin/__main__.py](file:///E:/moani/medical_ai_agent/martin/__main__.py)

**作用**：命令行入口，提供 CLI 交互界面

**支持的命令**：

| 命令 | 说明 | 示例 |
|:-----|:-----|:-----|
| `detect` | 检测肺部结节 | `python -m martin detect -i image.nii.gz` |
| `case` | 生成病例报告 | `python -m martin case -i results.json --llm` |
| `analyze` | 分析检测结果 | `python -m martin analyze -i results.json` |
| `report` | 生成医学报告 | `python -m martin report -i results.json -o report.txt` |
| `convert` | 转换图像格式 | `python -m martin convert -i image.mhd -o image.nii.gz` |
| `info` | 查看图像信息 | `python -m martin info -i image.nii.gz` |

**核心函数**：

| 函数 | 说明 |
|:-----|:-----|
| `main()` | 解析命令行参数，分发到各子命令 |
| `run_detect()` | 执行结节检测 |
| `run_case()` | 生成病例报告（支持模板和LLM） |
| `run_analyze()` | 调用 LLM 分析检测结果 |
| `run_report()` | 调用 LLM 生成医学报告 |
| `run_convert()` | 转换图像格式 |
| `run_info()` | 显示图像信息 |

**代码架构**：
```
CLI 入口 (argparse)
    ├── detect 命令 → NoduleDetector.detect()
    ├── case 命令 → CaseGenerator.generate_case() 或 generate_with_llm()
    ├── analyze 命令 → DeepSeekClient.analyze_report()
    ├── report 命令 → DeepSeekClient.generate_report()
    ├── convert 命令 → ImageProcessor.metaimage_to_nifti()
    └── info 命令 → ImageProcessor.get_image_info()
```

---

### 3.3 [martin/inference.py](file:///E:/moani/medical_ai_agent/martin/inference.py)

**作用**：统一推理模块，封装完整的 CT 图像检测流程

#### 类：LungNoduleDetector

| 方法 | 说明 |
|:-----|:-----|
| `__init__()` | 初始化检测器，自动检测设备、加载模型 |
| `_get_device()` | 自动获取运行设备（GPU/CPU） |
| `_get_model_path()` | 自动查找模型权重文件路径 |
| `_load_model()` | 构建 RetinaNet 模型并加载权重 |
| `_setup_transforms()` | 设置预处理和后处理管道 |
| `_prepare_dataloader()` | 准备数据加载器 |
| `_execute_inference()` | 执行模型推理 |
| `_parse_results()` | 解析检测结果为结节列表 |
| `detect()` | 检测单张图像（对外接口） |
| `detect_batch()` | 批量检测多张图像 |
| `_log_nodule_summary()` | 记录结节摘要信息 |

#### 函数：detect_nodules()

便捷函数，一行代码完成检测：
```python
result = detect_nodules("path/to/image.nii.gz")
```

#### 推理流程

```
detect(image_path)
    ├── 步骤 1/4: _prepare_dataloader() - 加载并预处理图像
    ├── 步骤 2/4: _execute_inference() - 模型推理
    ├── 步骤 3/4: _parse_results() - 解析检测结果
    └── 步骤 4/4: 构建输出字典
```

#### 预处理管道

```python
LoadImaged → EnsureChannelFirstd → Orientationd(RAS) → 
Spacingd(0.703125, 0.703125, 1.25) → 
ScaleIntensityRanged(-1024~300 → 0~1) → EnsureTyped
```

#### 后处理管道

```python
ClipBoxToImaged → AffineBoxToWorldCoordinated → ConvertBoxModed(cccwhd)
```

#### 检测器参数（官方配置）

```python
score_thresh = 0.02           # 置信度阈值
topk_candidates_per_level = 1000  # 每层候选数
nms_thresh = 0.22             # NMS 阈值
detections_per_img = 300      # 每张图最大检测数
roi_size = [512, 512, 192]    # 滑动窗口大小
overlap = 0.25                # 窗口重叠率
```

#### 返回值结构

```python
{
    "image": "图像文件名",
    "nodules": [
        {
            "index": 1,           # 结节索引
            "score": 0.9947,      # 置信度 (0~1)
            "center": {           # 中心位置 (mm)
                "x": -64.00,
                "y": -5.09,
                "z": -85.45
            },
            "dimensions": {       # 三维尺寸 (mm)
                "width": 4.91,
                "height": 4.96,
                "depth": 5.01
            },
            "diameter": 5.01      # 最大直径 (mm)
        }
    ],
    "total_nodules": 1          # 结节总数
}
```

---

## 4. MONAI 子模块

### 4.1 [martin/monai/__init__.py](file:///E:/moani/medical_ai_agent/martin/monai/__init__.py)

**作用**：MONAI 子模块初始化

**导出的类**：
- `NoduleDetector` - 结节检测器
- `ImageProcessor` - 图像处理工具

---

### 4.2 [martin/monai/nodule_detector.py](file:///E:/moani/medical_ai_agent/martin/monai/nodule_detector.py)

**作用**：基于 MONAI 的肺部结节检测器

#### 类：NoduleDetector

| 方法 | 说明 |
|:-----|:-----|
| `__init__()` | 初始化，可指定设备和模型路径 |
| `_load_model()` | 加载 RetinaNet 模型 |
| `detect()` | 检测图像中的结节 |
| `save_results()` | 保存检测结果到 JSON |

#### 与 inference.py 的区别

| 特性 | inference.py | nodule_detector.py |
|:-----|:-------------|:-------------------|
| 接口 | 类 + 便捷函数 | 仅类 |
| 日志 | 统一日志 | 统一日志 |
| 输出 | 结构化字典 | 结节列表 |
| 用途 | 统一推理入口 | CLI 命令调用 |

---

### 4.3 [martin/monai/image_processor.py](file:///E:/moani/medical_ai_agent/martin/monai/image_processor.py)

**作用**：医学图像处理工具类

#### 类：ImageProcessor（全部为静态方法）

| 方法 | 说明 | 参数 | 返回值 |
|:-----|:-----|:-----|:-----|
| `read_nifti()` | 读取 NIfTI 图像 | file_path | (data, affine, header) |
| `read_metaimage()` | 读取 MetaImage (.mhd/.raw) | mhd_path | (data, spacing, metadata) |
| `metaimage_to_nifti()` | MHD 转 NIfTI | mhd_path, output_path | None |
| `normalize_intensity()` | 灰度归一化 | data, a_min, a_max, b_min, b_max | 归一化数据 |
| `resample()` | 图像重采样 | data, original_spacing, target_spacing | 重采样数据 |
| `get_image_info()` | 获取图像信息 | file_path | {dim_size, spacing, voxel_count, data_range} |

#### 支持的图像格式

| 格式 | 扩展名 | 说明 |
|:-----|:-------|:-----|
| NIfTI | .nii, .nii.gz | 标准医学图像格式，支持压缩 |
| MetaImage | .mhd + .raw | ITK 格式，头文件 + 二进制数据 |

#### 典型用途

```python
# 获取图像信息
info = ImageProcessor.get_image_info("image.nii.gz")
print(f"尺寸: {info['dim_size']}")

# 格式转换
ImageProcessor.metaimage_to_nifti("input.mhd", "output.nii.gz")

# 灰度归一化（CT值转0~1）
normalized = ImageProcessor.normalize_intensity(data, -1024, 300, 0, 1)
```

---

## 5. LLM 子模块

### 5.1 [martin/llm/__init__.py](file:///E:/moani/medical_ai_agent/martin/llm/__init__.py)

**作用**：LLM 子模块初始化

**导出的类**：
- `DeepSeekClient` - DeepSeek API 客户端
- `CaseGenerator` - 病例报告生成器

---

### 5.2 [martin/llm/deepseek_client.py](file:///E:/moani/medical_ai_agent/martin/llm/deepseek_client.py)

**作用**：DeepSeek LLM API 客户端，兼容 OpenAI 协议

#### 类：DeepSeekClient

**初始化参数**：

| 参数 | 说明 | 默认值 |
|:-----|:-----|:-------|
| `api_key` | API 密钥 | 环境变量 `DEEPSEEK_API_KEY` |
| `base_url` | API 端点 URL | `https://api.deepseek.com/v1` |
| `model` | 模型名称 | 环境变量 `DEEPSEEK_MODEL` |

**方法**：

| 方法 | 说明 | 参数 | 返回值 |
|:-----|:-----|:-----|:-------|
| `chat()` | 通用对话接口 | messages, temperature, max_tokens | 模型回复 |
| `analyze_report()` | 分析医学报告 | report_data | 分析结果 |
| `generate_report()` | 生成医学报告 | nodules | 报告文本 |
| `summarize_findings()` | 总结检测发现 | findings | 总结文本 |

**环境变量配置**：

```bash
DEEPSEEK_API_KEY=sk-xxx
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-chat
```

**支持的自定义端点**（兼容 OpenAI 协议的服务）：
```bash
# 阿里云 DashScope
DEEPSEEK_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
DEEPSEEK_MODEL=deepseek-v4-flash
```

---

### 5.3 [martin/llm/case_generator.py](file:///E:/moani/medical_ai_agent/martin/llm/case_generator.py)

**作用**：基于检测结果生成医学病例报告

#### 类：CaseGenerator

**初始化参数**：

| 参数 | 说明 | 默认值 |
|:-----|:-----|:-------|
| `api_key` | DeepSeek API 密钥 | 从环境变量读取 |
| `base_url` | API 基础 URL | 从环境变量读取 |
| `model` | 模型名称 | 从环境变量读取 |

**方法**：

| 方法 | 说明 | 参数 | 返回值 |
|:-----|:-----|:-----|:-------|
| `generate_case()` | 模板生成报告 | detection_result, report_type, language | 报告文本 |
| `generate_with_llm()` | LLM 智能生成 | detection_result, report_type | 报告文本 |

#### 支持的报告类型

| 类型 | 说明 | 适用场景 |
|:-----|:-----|:---------|
| `brief` | 简洁版 | 快速浏览，核心信息 |
| `detailed` | 详细版 | 医生诊断参考 |
| `research` | 科研版 | 学术研究，含统计分析 |

#### 支持的语言

| 代码 | 语言 |
|:-----|:-----|
| `zh` | 中文（默认） |
| `en` | 英文 |

#### 两种生成模式

| 模式 | 方法 | 速度 | 专业性 | 需要 API |
|:-----|:-----|:-----|:-------|:--------|
| 模板生成 | `generate_case()` | 即时 | 基础 | 不需要 |
| LLM 生成 | `generate_with_llm()` | 网络请求 | 高 | 需要 |

#### 使用示例

```python
from martin.llm import CaseGenerator

generator = CaseGenerator()

# 模板生成（快速）
report = generator.generate_case(result, "detailed", "zh")

# LLM 生成（智能）
llm_gen = CaseGenerator(api_key="sk-xxx")
report = llm_gen.generate_with_llm(result, "detailed")
```

---

## 6. 工具模块

### 6.1 [martin/util/__init__.py](file:///E:/moani/medical_ai_agent/martin/util/__init__.py)

**作用**：通用工具模块初始化

**导出的类**：
- `AppLogger` - 统一日志工具类

### 6.2 [martin/util/logger.py](file:///E:/moani/medical_ai_agent/martin/util/logger.py)

**作用**：统一日志工具类，单例模式

#### 类：AppLogger

**特性**：
- **单例模式**：同一名称的日志实例全局唯一
- **双输出**：同时输出到控制台和文件
- **按日分割**：日志文件按日期命名（如 `2026-06-09.log`）
- **自动创建**：自动创建 `log/` 目录

**方法**：

| 方法 | 说明 | 参数 | 返回值 |
|:-----|:-----|:-----|:-------|
| `__init__()` | 初始化日志实例 | name, log_dir | None |
| `get_logger()` | 获取 Logger 实例 | - | logging.Logger |
| `setup_logging()` | 便捷方法，获取配置好的日志 | name, log_dir | logging.Logger |

**全局便捷函数**：

```python
from martin.util.logger import get_logger
logger = get_logger(__name__)
```

**使用方式**（推荐）：

```python
from martin.util import AppLogger

# 推荐：使用便捷方法
logger = AppLogger.setup_logging(__name__)

# 或使用全局函数
logger = get_logger(__name__)

# 使用
logger.info("信息")
logger.warning("警告")
logger.error("错误")
```

**日志格式**：

```
2026-06-09 12:35:30,448 - martin.inference - INFO - 检测完成，共检测到 1 个结节
```

**日志文件位置**：
- 默认路径：项目根目录 `/log/YYYY-MM-DD.log`
- 自动创建，无需手动配置

---

## 7. 测试模块

所有测试文件位于 `tests/` 目录：

| 文件 | 测试内容 | 说明 |
|:-----|:---------|:-----|
| `test_monai.py` | MONAI 模块 | 模型加载、图像读取、预处理 |
| `test_model_only.py` | 仅模型 | 单独测试模型加载和权重 |
| `test_inference_direct.py` | 直接推理 | 不使用 unittest 框架的推理测试 |
| `test_logger.py` | 日志工具 | 日志初始化、输出、单例模式 |
| `test_case_generator.py` | 病例生成 | 模板生成、LLM 生成 |
| `test_llm.py` | LLM 客户端 | API 调用、各种接口 |
| `test_full_pipeline.py` | 完整流程 | 从推理到报告生成 |

### 运行测试

```bash
# 运行所有测试
python -m pytest tests/ -v

# 运行单个测试
python tests/test_inference_direct.py

# 运行特定测试文件
python -m pytest tests/test_monai.py -v
```

---

## 8. 命令行使用指南

### 基本用法

```bash
# 查看帮助
python -m martin --help

# 查看子命令帮助
python -m martin detect --help
```

### detect 命令

```bash
# 基本检测
python -m martin detect -i data/image.nii.gz

# 指定输出路径
python -m martin detect -i data/image.nii.gz -o results/my_result.json

# 指定运行设备
python -m martin detect -i data/image.nii.gz --device cuda
```

### case 命令

```bash
# 模板生成详细版报告（中文）
python -m martin case -i results/detection_results.json -o report.md

# 模板生成简洁版报告（英文）
python -m martin case -i results/detection_results.json -o report_en.md \
    --type brief --lang en

# LLM 智能生成报告
python -m martin case -i results/detection_results.json --llm --api-key sk-xxx
```

### analyze 命令

```bash
python -m martin analyze -i results/detection_results.json --api-key sk-xxx
```

### convert 命令

```bash
python -m martin convert -i data/image.mhd -o data/image.nii.gz
```

### info 命令

```bash
python -m martin info -i data/image.nii.gz
```

---

## 9. API 使用示例

### 基础检测

```python
from martin import LungNoduleDetector, detect_nodules

# 方式 1：使用类
detector = LungNoduleDetector()
result = detector.detect("data/image.nii.gz")

# 方式 2：使用便捷函数
result = detect_nodules("data/image.nii.gz")
```

### 批量检测

```python
detector = LungNoduleDetector()

image_paths = ["image1.nii.gz", "image2.nii.gz", "image3.nii.gz"]
results = detector.detect_batch(image_paths)

for result in results:
    print(f"{result['image']}: {result['total_nodules']} 个结节")
```

### 生成病例报告

```python
from martin.llm import CaseGenerator

generator = CaseGenerator()

# 模板生成
report = generator.generate_case(result, "detailed", "zh")

# LLM 生成
llm_gen = CaseGenerator(api_key="sk-xxx")
report = llm_gen.generate_with_llm(result, "detailed")
```

### 图像处理

```python
from martin.monai import ImageProcessor

# 获取图像信息
info = ImageProcessor.get_image_info("image.nii.gz")

# 格式转换
ImageProcessor.metaimage_to_nifti("input.mhd", "output.nii.gz")

# 灰度归一化
normalized = ImageProcessor.normalize_intensity(data, -1024, 300)
```

### LLM 分析

```python
from martin.llm import DeepSeekClient

client = DeepSeekClient(api_key="sk-xxx")

# 分析检测结果
analysis = client.analyze_report(result)

# 生成医学报告
report = client.generate_report(result["nodules"])
```

---

## 10. 环境配置

### 系统要求

| 组件 | 要求 |
|:-----|:-----|
| Python | 3.10+ |
| GPU | NVIDIA CUDA 11.8+ (推荐) |
| 内存 | 16GB+ |
| 显存 | 8GB+ |

### 安装依赖

```bash
pip install -r requirements.txt
```

### 环境变量（可选）

```bash
# LLM 配置
export DEEPSEEK_API_KEY="sk-xxx"
export DEEPSEEK_BASE_URL="https://api.deepseek.com/v1"
export DEEPSEEK_MODEL="deepseek-chat"
```

### 模型文件

模型权重文件需放置在以下路径：

```
model/lung_nodule_ct_detection-0.6.8/
└── lung_nodule_ct_detection-0.6.8/
    └── models/
        └── model.pt
```

模型可通过 MONAI Model Zoo 下载，或使用自定义路径：

```python
detector = LungNoduleDetector(model_path="/path/to/model.pt")
```

---

## 附录：日志输出示例

```
============================================================
肺部结节检测推理模块已加载
============================================================
检测到 NVIDIA GPU，将使用 CUDA 加速
GPU 型号: NVIDIA GeForce RTX 4070 SUPER
GPU 显存: 11.99 GB
正在构建模型...
正在加载权重: model/.../model.pt
权重加载成功
模型加载完成
变换管道设置完成
开始检测图像: data/image.nii.gz
步骤 1/4: 准备数据...
  数据准备完成: 0.00秒
步骤 2/4: 执行推理...
  推理完成: 11.99秒
步骤 3/4: 解析检测结果...
  结果解析完成: 0.00秒
步骤 4/4: 构建输出结果...
检测完成，共检测到 1 个结节
```
