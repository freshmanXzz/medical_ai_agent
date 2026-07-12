# Martin - Medical AI Agent

> **Martin = 医学影像检测能力 + RAG知识增强能力 + LLM推理能力 + LangChain Agent智能编排**

Martin 是一个**面向医学影像的 AI Agent 智能体**，基于 MONAI 深度学习框架、RAG 检索增强生成技术和 DeepSeek 大语言模型，通过 LangChain Agent 智能编排实现肺部 CT 的自动化智能诊断。

## 项目背景

随着人工智能技术快速发展，AI 在医学领域的应用正在从传统的单任务模型逐渐向具备感知、理解、推理和任务协同能力的智能系统演进。医学影像作为临床诊断的重要数据来源，具有数据规模大、信息复杂和专业知识依赖强等特点，如何结合深度学习、大语言模型以及知识增强技术，构建面向真实医学场景的智能辅助系统，成为当前医学人工智能领域的重要研究方向。

本项目旨在系统学习并掌握 **AI 医疗（AI for Healthcare）与医学智能体（Medical AI Agent）相关技术体系**，探索如何将医学影像分析、知识检索增强、大语言模型推理以及智能体编排技术融合为一个完整的 AI 医疗应用系统。

基于这一目标，本人设计并开发了 **Martin 医学影像智能体系统**，以肺部 CT 肺结节检测作为核心应用场景，实现从医学影像感知、医学知识获取到智能分析与报告生成的完整流程。系统核心功能包括：

- 基于 MONAI 深度学习框架实现肺部 CT 影像中的结节自动检测；
- 基于 RAG（Retrieval-Augmented Generation）技术构建医学知识增强模块，引入 Lung-RADS、肺结节诊疗指南等权威医学知识，降低大语言模型生成过程中的知识偏差；
- 基于 DeepSeek 大语言模型实现医学语义理解、检测结果分析和结构化报告生成；
- 基于 LangChain Agent 实现多工具协同调用，使系统具备任务规划、工具选择和多轮交互能力。

在系统开发过程中，本项目采用 **AI Vibe Coding** 的新型开发模式，借助 TRAE、Claude Code 等智能编程工具辅助完成项目架构设计、代码生成、模块优化和工程调试。通过人机协同的开发方式，探索人工智能工具在复杂 AI 系统研发过程中的实际应用，同时加深对 Agent 架构设计、RAG 系统构建、大模型应用开发以及医学 AI 工程化落地流程的理解。

通过 Martin 项目的实践，希望建立从算法模型、知识增强到智能体系统设计的完整技术认知，探索未来医学人工智能从"单一模型辅助分析"向"具备医学知识、推理能力和任务协同能力的智能医疗助手"发展的可能方向。

## 项目定位

Martin 不是一个简单的病例报告生成工具，而是一个**面向医学影像的 AI Agent**。它通过多模态技术栈（计算机视觉 + 检索增强生成 + 大语言模型 + Agent 智能编排）实现肺部 CT 的自动化智能诊断，核心目标是：

1. **精准检测**：基于深度学习定位肺部结节
2. **循证诊断**：通过 RAG 技术确保诊断意见来自权威医学指南，避免 LLM 幻觉
3. **智能报告**：自动生成结构化的专业病例报告
4. **Agent 编排**：通过 LangChain Agent 实现检测、检索、推理的智能编排与协同

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
- **Agent 对话**：支持多轮对话、上下文记忆、工具调用
- **审计日志**：完整记录工具调用和推理过程，支持医疗审计溯源
- **GPU 加速**：支持 CUDA 加速推理

## 项目结构

```
medical_ai_agent/
├── main.py                             # 终端启动入口（Agent 对话）
├── audit/                              # 审计日志目录
├── configs/                            # 配置文件
│   ├── __init__.py
│   ├── knowledge_base.yaml
│   └── vector_db.yaml
├── data/                               # 数据目录
│   ├── chroma_db/                      # 向量数据库
│   ├── raw_data/                       # 原始图像数据
│   └── test_chroma_db/                 # 测试向量数据库
├── knowledge_base/                     # 医学知识库文档
├── martin/                             # 核心包
│   ├── __init__.py                     # 包入口
│   ├── __main__.py                     # CLI 入口（子命令）
│   ├── config.py                       # 统一配置
│   ├── inference.py                    # 检测推理入口
│   ├── agent/                          # Agent 编排层
│   │   ├── __init__.py
│   │   ├── agent.py                    # LangChain Agent 创建与执行器
│   │   ├── agent_builder.py            # Agent 构建工厂（组装 LLM/Tools/Prompt/Memory/Logger）
│   │   ├── audit.py                    # 审计日志记录器
│   │   ├── prompt.py                   # 系统 Prompt 定义
│   │   └── tools.py                    # Agent 工具集（analyze_image, retrieve_knowledge, generate_report）
│   ├── rag/                            # RAG 检索增强模块
│   │   ├── __init__.py
│   │   ├── document_loader.py          # 文档加载器
│   │   ├── text_splitter.py            # 文本切分器
│   │   ├── embeddings.py               # 向量嵌入
│   │   ├── vector_store.py             # 向量数据库
│   │   └── retriever.py                # 检索器
│   ├── llm/                            # LLM 推理模块
│   │   ├── __init__.py
│   │   ├── chat_model.py               # LangChain ChatModel 封装
│   │   ├── chain.py                    # LCEL 报告生成链
│   │   ├── case_generator.py           # 病例报告生成器
│   │   └── deepseek_client.py          # DeepSeek API 客户端
│   ├── vision/                         # 医学视觉模块
│   │   ├── __init__.py
│   │   ├── image_processor.py          # 图像处理和格式转换
│   │   └── nodule_detector.py          # 结节检测器
│   └── utils/                          # 通用工具
│       ├── __init__.py
│       ├── logger.py                   # 日志工具
│       └── result_manager.py           # 结果管理
├── models/                             # 模型目录
│   ├── vision/                         # 视觉检测模型
│   └── embedding/                      # 嵌入模型
├── scripts/                            # 脚本工具
├── tests/                              # 测试
├── README.md
├── requirements.txt
├── pyproject.toml
└── docker-compose.yml
```

### 模块职责说明

| 模块 | 职责 | 底层技术 |
|------|------|----------|
| martin/agent | Agent 智能编排与对话管理 | LangChain Agent |
| martin/agent/agent_builder | Agent 组件组装工厂 | LangChain |
| martin/agent/prompt | 系统 Prompt 定义 | - |
| martin/agent/tools | Agent 工具集（检测、检索、报告） | @tool 装饰器 |
| martin/agent/audit | 审计日志记录 | JSONL |
| martin/rag | 知识检索增强 | LangChain RAG |
| martin/llm | 大语言模型推理 | LangChain ChatModel |
| martin/vision | 医学影像检测 | MONAI |
| martin/utils | 通用工具 | Python 标准库 |

## 快速开始

### 安装依赖

```bash
# 创建虚拟环境
python -m venv .venv
# Windows PowerShell
.venv\Scripts\Activate.ps1
# Linux/Mac
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 下载模型

从 MONAI Model Zoo 下载预训练模型，放置到以下路径：

```
models/vision/lung_nodule_ct_detection-0.6.8/
└── models/
    └── model.pt
```

下载 Embedding 模型到：

```
models/embedding/bge-small-zh-v1.5/
```

### 导入知识库

```bash
# 导入医学知识到向量数据库
python scripts/import_knowledge.py
```

## Agent 对话模式（推荐）

### 启动方式

```bash
# 方式 1：独立入口（推荐）
python main.py

# 方式 2：模块子命令
python -m martin agent

# 方式 3：带初始图像参数
python -m martin agent --image "data/image.nii.gz" --report-type detailed
```

### 运行效果

```
================================
      Martin Medical Agent
      医学智能体已启动

  输入 exit 退出对话
================================

Martin: 您好！我是 Martin 医学智能体，可以为您提供医学影像分析和知识查询服务。

User: 肺结节有哪些常见影像表现？

[Agent] 调用工具: retrieve_knowledge
[Agent] 工具参数: {'detection_context': '{"image": "unknown", "total_nodules": 0, "nodules": []}'}
[Agent] 推理过程: 用户询问肺结节影像表现，需要检索医学知识库获取相关信息...
[Agent] 观察结果: 根据 Lung-RADS 标准，肺结节按密度分为实性结节、部分实性结节和磨玻璃结节...

Martin: 根据医学知识库检索结果，肺结节常见影像表现包括：实性结节、部分实性结节和磨玻璃结节...

User: 退出
Martin: 再见！
```

### Agent 工具说明

| 工具 | 功能 | 参数 |
|------|------|------|
| `analyze_image` | 肺部CT图像结节检测 | `image_path` |
| `retrieve_knowledge` | 检索医学知识库 | `detection_context` |
| `generate_report` | 生成结构化病例报告 | `detection_result`, `report_type`, `language` |

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
from martin.vision import ImageProcessor

# 获取图像信息
info = ImageProcessor.get_image_info("image.nii.gz")

# 格式转换
ImageProcessor.metaimage_to_nifti("input.mhd", "output.nii.gz")
```

### 创建 Agent

```python
from martin.agent import build_agent

# 构建 Agent（自动完成 LLM/Tools/Prompt/Memory/Logger 的组装）
agent = build_agent(verbose=True, thread_id="session-001")

# 执行推理（MemorySaver 自动管理多轮对话记忆）
response = agent.invoke({"input": "肺结节有哪些常见影像表现？"})
print(response["output"])
```

## RAG 知识库使用

### 导入医学知识

将权威医学文档（PDF/Word/Markdown/CSV）放入 `knowledge_base/` 目录，执行向量化：

```bash
# 导入知识库到 ChromaDB（自动创建向量索引）
python scripts/import_knowledge.py

# 输出位置：data/chroma_db/（本地持久化，已排除在版本控制外）
```

### 知识库查询

```python
from martin.rag import search_by_detection
from martin.rag.embeddings import get_embeddings
from martin.rag.vector_store import get_vector_store

# 初始化向量存储
embeddings = get_embeddings()
vector_store = get_vector_store(embeddings)

# 创建检索器
retriever = vector_store.as_retriever(search_kwargs={"k": 5})

# 直接查询
results = retriever.invoke("肺结节直径8mm实性结节随访建议")

for result in results:
    print(f"来源: {result.metadata.get('source', '')}")
    print(f"内容: {result.page_content[:200]}...")

# 根据检测结果检索
detection_result = {
    "image": "test.nii.gz",
    "total_nodules": 1,
    "nodules": [{"index": 1, "diameter": 8.0, "score": 0.95}]
}
results = search_by_detection(detection_result, top_k=5)

for result in results:
    print(f"来源: {result.metadata.get('source', '')}")
    print(f"内容: {result.page_content[:200]}...")
```

## 核心模块

### vision - 医学视觉模块

| 类 | 功能 |
|:---|:-----|
| `NoduleDetector` | 肺部结节检测器 |
| `ImageProcessor` | 图像处理和格式转换 |

### llm - 语言模型模块

| 类 | 功能 |
|:---|:-----|
| `ChatModel` | LangChain ChatModel 封装 |
| `DeepSeekClient` | DeepSeek API 客户端 |
| `CaseGenerator` | 病例报告生成器 |

### rag - 检索增强模块

| 类 | 功能 |
|:---|:-----|
| `DocumentLoader` | 文档加载器（支持 MD/CSV/PDF/Word） |
| `TextSplitter` | 文本切分器 |
| `Embeddings` | BGE 模型本地 Embedding 生成 |
| `VectorStore` | ChromaDB 向量数据库客户端 |
| `Retriever` | 相似度检索器 |

### agent - Agent 编排模块

| 类/函数 | 功能 |
|:---|:-----|
| `AgentExecutor` | LangChain Agent 执行器（支持多轮对话记忆） |
| `build_agent()` | Agent 构建工厂（一键组装所有组件） |
| `SYSTEM_PROMPT` | 系统提示词定义 |
| `AuditLogger` | 审计日志记录（医疗审计溯源） |
| `analyze_image` | Agent 工具：图像检测 |
| `retrieve_knowledge` | Agent 工具：知识库检索 |
| `generate_report` | Agent 工具：报告生成 |

### utils - 通用工具

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

## 技术栈

| 组件 | 技术 |
|:-----|:-----|
| 深度学习 | PyTorch + MONAI |
| LLM | DeepSeek API (支持兼容 OpenAI 协议的端点) |
| RAG 向量库 | ChromaDB（本地持久化） |
| Embedding | BGE-Small-ZH-v1.5（本地部署） |
| Agent 编排 | LangChain + LangGraph |
| 图像处理 | Nibabel, NumPy, SciPy |
| 模型 | RetinaNet 3D + ResNet50 骨干网络 |

## 引用

- [MONAI](https://monai.io/)
- [DeepSeek](https://www.deepseek.com/)
- [LangChain](https://www.langchain.com/)
- [LUNA16 Challenge](https://luna16.grand-challenge.org/)

## 许可证

MIT License
