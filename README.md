# Martin - Medical AI Agent

> 基于 MONAI 深度学习框架和 DeepSeek 大语言模型的肺部 CT 结节检测与病例报告生成系统

## 功能特性

- **肺部结节检测**：基于 MONAI RetinaNet 3D 目标检测模型
- **病例报告生成**：支持模板生成和 LLM 智能生成两种模式
- **医学图像处理**：支持 NIfTI 和 MetaImage 格式转换
- **LLM 智能分析**：调用 DeepSeek API 进行专业医学分析
- **命令行工具**：提供完整的 CLI 交互界面
- **GPU 加速**：支持 CUDA 加速推理

## 项目结构

```
medical_ai_agent/
├── martin/                    # 核心源码包
│   ├── __init__.py            # 包初始化，导出核心类
│   ├── __main__.py            # CLI 命令行入口
│   ├── inference.py           # 统一推理模块
│   │
│   ├── monai/                 # MONAI 医学影像子模块
│   │   ├── nodule_detector.py # 结节检测器
│   │   └── image_processor.py # 图像处理工具
│   │
│   ├── llm/                   # LLM 接入子模块
│   │   ├── deepseek_client.py # DeepSeek API 客户端
│   │   └── case_generator.py  # 病例报告生成器
│   │
│   └── util/                  # 通用工具子模块
│       ├── logger.py          # 统一日志工具类
│       └── result_manager.py  # 结果文件管理器
│
├── tests/                     # 单元测试
├── model/                     # 预训练模型权重
├── data/                      # 测试数据
├── doc/                       # 项目文档
├── results/                   # 输出结果（按日期分类，自动生成）
│   └── YYYY-MM-DD/           # 按日期存储
├── log/                       # 日志文件（自动生成）
└── README.md
```

## 快速开始

### 安装依赖

```bash
# 创建虚拟环境
conda create -n monai_learning python=3.10
conda activate monai_learning

# 安装依赖
pip install -r requirements.txt
```

### 下载模型

从 MONAI Model Zoo 下载预训练模型，放置到以下路径：

```
model/lung_nodule_ct_detection-0.6.8/
└── lung_nodule_ct_detection-0.6.8/
    └── models/
        └── model.pt
```

## 命令行使用

```bash
# 检测肺部结节
python -m martin detect -i data/image.nii.gz -o results/detection.json

# 生成病例报告（模板生成，无需API）
python -m martin case -i results/detection.json -o report.md

# 生成病例报告（LLM智能生成，需要API密钥）
python -m martin case -i results/detection.json -o report.md --llm --api-key YOUR_KEY

# 分析检测结果（需要DeepSeek API密钥）
python -m martin analyze -i results/detection.json --api-key YOUR_API_KEY

# 生成医学报告
python -m martin report -i results/detection.json -o results/report.txt --api-key YOUR_API_KEY

# 转换图像格式（MetaImage -> NIfTI）
python -m martin convert -i data/scan.mhd -o data/scan.nii.gz

# 查看图像信息
python -m martin info -i data/ct_scan.nii.gz
```

### 报告类型

| 类型 | 说明 | 适用场景 |
|:-----|:-----|:---------|
| `brief` | 简洁版 | 快速浏览 |
| `detailed` | 详细版 | 医生诊断参考 |
| `research` | 科研版 | 学术研究 |

## API 使用示例

### 检测结节

```python
from martin import LungNoduleDetector, detect_nodules

# 方式1：使用类
detector = LungNoduleDetector()
result = detector.detect("data/image.nii.gz")

# 方式2：使用便捷函数
result = detect_nodules("data/image.nii.gz")

print(f"检测到 {result['total_nodules']} 个结节")
```

### 批量检测

```python
detector = LungNoduleDetector()
image_paths = ["image1.nii.gz", "image2.nii.gz"]
results = detector.detect_batch(image_paths)
```

### 生成病例报告

```python
from martin.llm import CaseGenerator

generator = CaseGenerator()

# 模板生成（快速，无需API）
report = generator.generate_case(result, "detailed", "zh")

# LLM生成（智能，需要API密钥）
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
```

## 核心模块

### monai - 医学影像模块

| 类 | 功能 |
|:---|:-----|
| `NoduleDetector` | 肺部结节检测器 |
| `ImageProcessor` | 图像处理和格式转换 |

### llm - 语言模型模块

| 类 | 功能 |
|:---|:-----|
| `DeepSeekClient` | DeepSeek API 客户端 |
| `CaseGenerator` | 病例报告生成器 |

### util - 通用工具

| 类 | 功能 |
|:---|:-----|
| `AppLogger` | 统一日志工具（单例模式） |
| `ResultManager` | 结果文件管理器（按日期分类） |

## 配置

### 环境变量

```bash
# DeepSeek API配置
export DEEPSEEK_API_KEY="your-api-key"
export DEEPSEEK_BASE_URL="https://api.deepseek.com/v1"
export DEEPSEEK_MODEL="deepseek-chat"

# 支持阿里云DashScope（兼容OpenAI协议）
export DEEPSEEK_BASE_URL="https://dashscope.aliyuncs.com/compatible-mode/v1"
export DEEPSEEK_MODEL="deepseek-v4-flash"
```

### 推理参数（官方配置）

| 参数 | 默认值 | 说明 |
|:-----|:-------|:-----|
| roi_size | [512, 512, 192] | 滑动窗口尺寸 |
| overlap | 0.25 | 窗口重叠率 |
| score_thresh | 0.02 | 置信度阈值 |
| topk_candidates_per_level | 1000 | 每层候选数 |
| nms_thresh | 0.22 | NMS阈值 |
| detections_per_img | 300 | 每张图最大检测数 |

## 运行测试

```bash
# 运行所有测试
python -m pytest tests/ -v

# 运行特定测试
python -m pytest tests/test_monai.py -v

# 直接运行推理测试
python tests/test_inference_direct.py
```

## 输出格式

### 检测结果

```json
{
    "image": "image.nii.gz",
    "nodules": [
        {
            "index": 1,
            "score": 0.9947,
            "center": {"x": -64.00, "y": -5.09, "z": -85.45},
            "dimensions": {"width": 4.91, "height": 4.96, "depth": 5.01},
            "diameter": 5.01
        }
    ],
    "total_nodules": 1
}
```

## 系统要求

| 组件 | 要求 |
|:-----|:-----|
| Python | >= 3.10 |
| PyTorch | >= 2.0.0 |
| MONAI | >= 1.3.0 |
| CUDA | >= 11.8 (推荐) |
| GPU显存 | >= 8GB |

## 项目文档

详细 API 文档请查看：

- [项目完整文档](doc/PROJECT_DOCUMENTATION.md)
- [API 参考文档](doc/API_DOCUMENTATION.md)

## 技术栈

| 组件 | 技术 |
|:-----|:-----|
| 深度学习 | PyTorch + MONAI |
| LLM | DeepSeek API (支持兼容 OpenAI 协议的端点) |
| 图像处理 | Nibabel, NumPy, SciPy |
| 模型 | RetinaNet 3D + ResNet50 骨干网络 |

## 引用

- [MONAI](https://monai.io/)
- [DeepSeek](https://www.deepseek.com/)
- [LUNA16 Challenge](https://luna16.grand-challenge.org/)

## 许可证

MIT License
