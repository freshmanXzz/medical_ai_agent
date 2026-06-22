# Martin - Medical AI Agent

> **AI Agent 影像智能体雏形** —— 基于 MONAI 深度学习框架、RAG 检索增强生成技术和 DeepSeek 大语言模型的肺部 CT 智能诊断系统

## 项目定位

Martin 不是一个简单的病例报告生成工具，而是一个**面向医学影像的 AI Agent 雏形**。它通过多模态技术栈（计算机视觉 + 检索增强生成 + 大语言模型）实现肺部 CT 的自动化智能诊断，核心目标是：

1. **精准检测**：基于深度学习定位肺部结节
2. **循证诊断**：通过 RAG 技术确保诊断意见来自权威医学指南，避免 LLM 幻觉
3. **智能报告**：自动生成结构化的专业病例报告

## RAG 检索增强生成

本项目采用 **RAG（Retrieval-Augmented Generation）** 架构解决医疗场景下大语言模型的核心痛点：

### 问题：LLM 幻觉

大语言模型在生成病例报告时，容易产生"看似合理但医学不准确"的内容（幻觉）。在医疗场景中，这可能导致错误的诊断建议。

### 解决方案：知识库增强

```
CT影像输入 → MONAI检测结节 → RAG检索知识库 → LLM生成循证报告
                ↓                    ↓
            结节位置/大小    权威医学指南/共识
```

**工作流程**：
1. **向量化存储**：将《CT肺结节诊断专家共识》、《Lung-RADS分级标准》等权威文档通过 Embedding 模型向量化，存储在 **ChromaDB** 本地向量数据库
2. **相似度检索**：根据检测结果（结节大小、形态等）自动检索相关知识库内容
3. **上下文增强**：将检索到的医学指南作为上下文输入 LLM，约束生成内容
4. **循证生成**：确保每一份诊断意见和建议都有据可查，来自真实的医学文献和临床指南

### 知识库来源

- Lung-RADS v2022 分级标准
- CT肺结节诊断专家共识（2023）
- 肺结节诊疗指南（2024）
- 肺部影像报告和数据系统

### 技术实现

| 组件 | 技术 |
|:-----|:-----|
| 向量数据库 | ChromaDB（本地持久化） |
| Embedding 模型 | BGE-Small-ZH-v1.5（本地部署） |
| 文档格式 | Markdown / CSV / PDF / Word |
| 检索方式 | 余弦相似度 + 分类过滤 |

## 功能特性

- **肺部结节检测**：基于 MONAI RetinaNet 3D 目标检测模型
- **病例报告生成**：支持模板生成和 LLM 智能生成两种模式
- **RAG 循证诊断**：通过知识库检索确保诊断意见有医学依据
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
│   ├── rag/                   # RAG 检索增强子模块
│   │   ├── document_loader.py # 文档加载器（MD/CSV/PDF/Word）
│   │   ├── embedding_client.py# Embedding 向量生成
│   │   ├── vector_store.py    # ChromaDB 向量数据库
│   │   └── retriever.py       # 知识检索器
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

### 一键测试

运行完整流程测试脚本：

```bash
# 基础测试（无需API密钥）
python tests/test_one_click.py

# 完整测试（包含LLM，需要API密钥）
set DEEPSEEK_API_KEY=sk-xxx
python tests/test_one_click.py
```

测试内容：
1. CT图像检测推理
2. 病例报告生成（模板）
3. 病例报告生成（LLM，需要API密钥）
4. 结果管理器验证

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

## RAG 知识库使用

### 导入医学知识

将权威医学文档（PDF/Word/Markdown/CSV）放入 `knowledge_base/` 目录，执行向量化：

```bash
# 导入知识库到 ChromaDB（自动创建向量索引）
python scripts/import_knowledge.py

# 输出位置：项目根目录 ChromaDB/（本地持久化，已排除在版本控制外）
```

### 知识库查询

```python
from martin.rag import Retriever, EmbeddingClient, VectorStore

# 初始化检索器
embedding_client = EmbeddingClient()
vector_store = VectorStore()
vector_store.connect()

retriever = Retriever(embedding_client, vector_store, top_k=5)

# 根据检测结节的特征检索相关知识
results = retriever.search("肺结节直径8mm实性结节随访建议")

for result in results:
    print(f"相似度: {result['similarity']:.4f}")
    print(f"来源: {result['source']}")
    print(f"内容: {result['content'][:200]}...")
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

### rag - 检索增强模块

| 类 | 功能 |
|:---|:-----|
| `DocumentLoader` | 文档加载器（支持 MD/CSV/PDF/Word） |
| `EmbeddingClient` | BGE 模型本地 Embedding 生成 |
| `VectorStore` | ChromaDB 向量数据库客户端 |
| `Retriever` | 相似度检索器 |

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
| RAG 向量库 | ChromaDB（本地持久化） |
| Embedding | BGE-Small-ZH-v1.5（本地部署） |
| 图像处理 | Nibabel, NumPy, SciPy |
| 模型 | RetinaNet 3D + ResNet50 骨干网络 |

## 引用

- [MONAI](https://monai.io/)
- [DeepSeek](https://www.deepseek.com/)
- [LUNA16 Challenge](https://luna16.grand-challenge.org/)

## 许可证

MIT License
