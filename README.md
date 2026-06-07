# Martin - Medical AI Agent

基于MONAI框架的肺部结节检测系统，支持CT图像分析和LLM报告生成。

## 🌟 功能特性

- ✅ **医学影像处理**：支持NIfTI和MetaImage格式
- ✅ **肺部结节检测**：使用RetinaNet模型进行精准检测
- ✅ **LLM集成**：接入DeepSeek进行报告分析和生成
- ✅ **命令行接口**：提供便捷的CLI工具
- ✅ **GPU加速**：支持CUDA加速推理

## 📁 项目结构

```
MedicalAIAgent/
├── martin/                    # 核心包
│   ├── __init__.py           # 包初始化
│   ├── __main__.py           # 命令行入口
│   ├── minai/                # 医学影像模块
│   │   ├── __init__.py
│   │   ├── nodule_detector.py    # 结节检测
│   │   └── image_processor.py    # 图像处理
│   └── llm/                  # LLM模块
│       ├── __init__.py
│       └── deepseek_client.py    # DeepSeek客户端
├── tests/                    # 测试目录
│   ├── test_monai.py         # MONAI模块测试
│   └── test_llm.py           # LLM模块测试
├── docs/                     # 项目文档
├── examples/                 # 使用示例
├── data/                     # 数据文件
├── configs/                  # 配置文件
├── scripts/                  # 脚本文件
├── logs/                     # 日志目录
├── .gitignore                # Git忽略配置
├── README.md                 # 项目说明
├── requirements.txt          # 依赖清单
├── pyproject.toml            # 项目配置
└── LICENSE                   # 许可证
```

## 🚀 快速开始

### 安装依赖

```bash
# 创建虚拟环境
conda create -n martin python=3.10
conda activate martin

# 安装依赖
pip install -r requirements.txt
```

### 下载模型

从MONAI Model Zoo下载预训练模型：
```bash
# 下载并解压到 model/ 目录
lung_nodule_ct_detection-0.6.8/
└── models/
    └── model.pt
```

### 命令行使用

```bash
# 检测肺部结节
python -m martin detect -i data/ct_scan.nii.gz -o results/detection.json

# 分析检测结果（需要DeepSeek API密钥）
python -m martin analyze -i results/detection.json --api-key YOUR_API_KEY

# 生成医学报告
python -m martin report -i results/detection.json -o results/report.txt

# 转换图像格式（MetaImage -> NIfTI）
python -m martin convert -i data/scan.mhd -o data/scan.nii.gz

# 查看图像信息
python -m martin info -i data/ct_scan.nii.gz
```

### API使用

```python
from martin.minai import NoduleDetector
from martin.llm import DeepSeekClient

# 检测结节
detector = NoduleDetector()
nodules = detector.detect("data/ct_scan.nii.gz")

# 分析结果
client = DeepSeekClient(api_key="YOUR_API_KEY")
analysis = client.analyze_report({"total_nodules": len(nodules), "nodules": nodules})

# 生成报告
report = client.generate_report(nodules)
```

## 📦 核心模块

### minai - 医学影像模块

| 模块 | 功能 |
|:-----|:-----|
| `NoduleDetector` | 肺部结节检测 |
| `ImageProcessor` | 图像处理和格式转换 |

### llm - 语言模型模块

| 模块 | 功能 |
|:-----|:-----|
| `DeepSeekClient` | DeepSeek API客户端 |

## ⚙️ 配置

### 环境变量

```bash
# DeepSeek API密钥
export DEEPSEEK_API_KEY="your-api-key"
```

### 检测参数

| 参数 | 默认值 | 说明 |
|:-----|:-----|:-----|
| roi_size | [192, 192, 64] | 滑动窗口尺寸 |
| overlap | 0.5 | 窗口重叠率 |
| score_thresh | 0.05 | 置信度阈值 |
| nms_thresh | 0.22 | NMS阈值 |

## 🧪 运行测试

```bash
# 运行所有测试
python -m pytest tests/ -v

# 运行特定测试
python -m pytest tests/test_monai.py -v
```

## 📝 输出格式

```json
{
    "total_nodules": 2,
    "nodules": [
        {
            "index": 1,
            "score": 0.9779,
            "center": {"x": -64.00, "y": -5.29, "z": -85.50},
            "dimensions": {"width": 4.91, "height": 4.69, "depth": 5.24},
            "diameter": 5.24
        }
    ]
}
```

## 📋 系统要求

| 组件 | 要求 |
|:-----|:-----|
| Python | >= 3.10 |
| PyTorch | >= 2.0.0 |
| MONAI | >= 1.3.0 |
| CUDA | >= 11.8 (推荐) |
| GPU显存 | >= 12GB |

## 📄 许可证

MIT License

## 🔗 引用

- MONAI: https://monai.io/
- DeepSeek: https://www.deepseek.com/
- LUNA16 Dataset: https://luna16.grand-challenge.org/
