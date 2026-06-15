"""
CaseGenerator - 病例报告生成器

基于检测结果生成结构化的医学病例报告，支持多种报告格式：
- brief: 简洁版报告（适合快速浏览）
- detailed: 详细版报告（适合医生诊断参考）
- research: 科研版报告（适合学术研究）
- rag: RAG增强版报告（基于知识库生成）
"""

import json
from typing import Dict, Optional, List

from martin.util import AppLogger

# 获取日志实例
logger = AppLogger.setup_logging(__name__)


class CaseGenerator:
    """
    病例报告生成器

    Args:
        api_key: DeepSeek API密钥，优先从环境变量获取
        base_url: API基础URL，支持自定义端点
        model: 模型名称
        use_rag: 是否启用RAG增强
    """

    def __init__(
        self,
        api_key: str = None,
        base_url: str = None,
        model: str = None,
        use_rag: bool = False,
    ):
        self._api_key = api_key
        self._base_url = base_url
        self._model = model
        self._client = None
        self._use_rag = use_rag
        self._retriever = None

    def _get_client(self):
        """延迟初始化DeepSeek客户端"""
        if self._client is None:
            from .deepseek_client import DeepSeekClient

            kwargs = {"api_key": self._api_key}
            if self._base_url:
                kwargs["base_url"] = self._base_url
            if self._model:
                kwargs["model"] = self._model
            self._client = DeepSeekClient(**kwargs)
        return self._client

    def _get_retriever(self):
        """延迟初始化RAG检索器"""
        if self._retriever is None and self._use_rag:
            try:
                from martin.rag import Retriever, EmbeddingClient, VectorStore

                embedding_client = EmbeddingClient()
                vector_store = VectorStore()
                vector_store.connect()
                self._retriever = Retriever(embedding_client, vector_store, top_k=5)
                logger.info("RAG检索器初始化成功")
            except Exception as e:
                logger.error(f"RAG检索器初始化失败: {e}")
                self._use_rag = False
        return self._retriever

    def _query_knowledge_base(self, detection_result: Dict) -> str:
        """
        查询知识库获取相关医学知识

        Args:
            detection_result: 检测结果字典

        Returns:
            格式化的知识库上下文文本
        """
        if not self._use_rag:
            return ""

        retriever = self._get_retriever()
        if not retriever:
            return ""

        try:
            results = retriever.search_by_detection(detection_result)
            if results:
                context = retriever._format_results(results)
                logger.info(f"从知识库检索到 {len(results)} 条相关知识")
                return context
            else:
                logger.info("未检索到相关知识库内容")
                return ""
        except Exception as e:
            logger.error(f"知识库查询失败: {e}")
            return ""

    def generate_case(
        self,
        detection_result: Dict,
        report_type: str = "detailed",
        language: str = "zh",
    ) -> str:
        """
        生成病例报告

        Args:
            detection_result: 检测结果字典，包含 image、nodules、total_nodules 字段
            report_type: 报告类型，可选值: brief/detailed/research
            language: 语言，可选值: zh/en

        Returns:
            格式化的病例报告字符串
        """
        logger.info(f"开始生成病例报告，类型: {report_type}，语言: {language}")

        report_type = report_type.lower()
        language = language.lower()

        if report_type == "brief":
            report = self._generate_brief_report(detection_result, language)
        elif report_type == "research":
            report = self._generate_research_report(detection_result, language)
        else:
            report = self._generate_detailed_report(detection_result, language)

        logger.info("病例报告生成完成")
        return report

    def _generate_brief_report(self, data: Dict, language: str) -> str:
        """
        生成简洁版报告

        适合快速浏览，包含核心信息：
        - 基本信息
        - 结节数量
        - 关键发现总结
        """
        nodules = data.get("nodules", [])
        total_nodules = data.get("total_nodules", 0)
        image_name = data.get("image", "unknown")

        if language == "en":
            report = f"""
Medical Report Summary
======================

Patient ID: {image_name}
Date: Auto-generated

Findings:
- Total nodules detected: {total_nodules}

{"No nodules detected." if total_nodules == 0 else self._format_nodules_en(nodules)}

Recommendation: Please consult radiologist for further evaluation.
"""
        else:
            report = f"""
医学报告摘要
============

患者ID: {image_name}
日期: 自动生成

检测结果:
- 检测到结节总数: {total_nodules} 个

{"未检测到结节。" if total_nodules == 0 else self._format_nodules_zh(nodules)}

建议: 请咨询放射科医生进行进一步评估。
"""

        return report.strip()

    def _generate_detailed_report(self, data: Dict, language: str) -> str:
        """
        生成详细版报告

        适合医生诊断参考，包含完整信息：
        - 患者信息
        - 检查方法
        - 详细检测结果
        - 诊断结论
        - 建议
        """
        nodules = data.get("nodules", [])
        total_nodules = data.get("total_nodules", 0)
        image_name = data.get("image", "unknown")

        if language == "en":
            report = f"""
MEDICAL REPORT
==============

[Patient Information]
- Patient ID: {image_name}
- Report Type: Detailed
- Date: Auto-generated

[Examination Method]
- Modality: Chest CT
- Reconstruction: Standard

[Findings]
Total nodules detected: {total_nodules}

{"No pulmonary nodules detected." if total_nodules == 0 else self._format_nodules_detailed_en(nodules)}

[Impression]
{self._generate_impression_en(nodules)}

[Recommendation]
{self._generate_recommendation_en(nodules)}

[Disclaimer]
This report is generated by AI and should be reviewed by a qualified radiologist.
"""
        else:
            report = f"""
医学报告
========

【患者信息】
- 患者ID: {image_name}
- 报告类型: 详细版
- 生成日期: 自动生成

【检查方法】
- 检查方式: 胸部CT
- 重建方式: 标准重建

【检测结果】
共检测到 {total_nodules} 个肺部结节

{"未检测到肺部结节。" if total_nodules == 0 else self._format_nodules_detailed_zh(nodules)}

【诊断结论】
{self._generate_impression_zh(nodules)}

【建议】
{self._generate_recommendation_zh(nodules)}

【免责声明】
本报告由AI自动生成，需经专业放射科医生审核确认。
"""

        return report.strip()

    def _generate_research_report(self, data: Dict, language: str) -> str:
        """
        生成科研版报告

        适合学术研究，包含：
        - 完整的结节数据表格
        - 统计分析
        - 数据质量评估
        """
        nodules = data.get("nodules", [])
        total_nodules = data.get("total_nodules", 0)
        image_name = data.get("image", "unknown")

        # 统计分析
        avg_diameter = sum(n["diameter"] for n in nodules) / max(total_nodules, 1)
        avg_score = sum(n["score"] for n in nodules) / max(total_nodules, 1)
        max_diameter = max(n["diameter"] for n in nodules) if nodules else 0
        min_diameter = min(n["diameter"] for n in nodules) if nodules else 0

        if language == "en":
            report = f"""
RESEARCH REPORT
===============

[Study Information]
- Sample ID: {image_name}
- Report Type: Research
- Date: Auto-generated

[Scan Parameters]
- Modality: Chest CT
- Analysis Method: AI-based nodule detection

[Detection Statistics]
- Total nodules: {total_nodules}
- Average diameter: {avg_diameter:.2f} mm
- Average confidence: {avg_score:.4f}
- Maximum diameter: {max_diameter:.2f} mm
- Minimum diameter: {min_diameter:.2f} mm

[Detailed Nodule Data]
{"No nodules detected." if total_nodules == 0 else self._format_nodules_table_en(nodules)}

[Data Quality Assessment]
- Image quality: Good
- Detection confidence: {"High" if avg_score > 0.9 else "Medium" if avg_score > 0.7 else "Low"}
- Recommendation: {"Further evaluation recommended" if total_nodules > 0 else "No abnormalities detected"}

[JSON Data for Processing]
{json.dumps(nodules, indent=2, ensure_ascii=False)}
"""
        else:
            report = f"""
科研报告
========

【研究信息】
- 样本ID: {image_name}
- 报告类型: 科研版
- 生成日期: 自动生成

【扫描参数】
- 检查方式: 胸部CT
- 分析方法: AI结节检测

【检测统计】
- 结节总数: {total_nodules}
- 平均直径: {avg_diameter:.2f} mm
- 平均置信度: {avg_score:.4f}
- 最大直径: {max_diameter:.2f} mm
- 最小直径: {min_diameter:.2f} mm

【结节详细数据】
{"未检测到结节。" if total_nodules == 0 else self._format_nodules_table_zh(nodules)}

【数据质量评估】
- 图像质量: 良好
- 检测置信度: {"高" if avg_score > 0.9 else "中" if avg_score > 0.7 else "低"}
- 建议: {"建议进一步研究" if total_nodules > 0 else "未检测到异常"}

【JSON格式数据（便于处理）】
{json.dumps(nodules, indent=2, ensure_ascii=False)}
"""

        return report.strip()

    def _format_nodules_zh(self, nodules) -> str:
        """格式化结节列表（中文简洁版）"""
        lines = []
        for nodule in nodules[:5]:  # 最多显示5个
            lines.append(
                f"- 结节 {nodule['index']}: 直径 {nodule['diameter']:.2f}mm, 置信度 {nodule['score']:.2%}"
            )
        if len(nodules) > 5:
            lines.append(f"- ... 还有 {len(nodules) - 5} 个结节")
        return "\n".join(lines)

    def _format_nodules_en(self, nodules) -> str:
        """格式化结节列表（英文简洁版）"""
        lines = []
        for nodule in nodules[:5]:
            lines.append(
                f"- Nodule {nodule['index']}: {nodule['diameter']:.2f}mm, confidence {nodule['score']:.2%}"
            )
        if len(nodules) > 5:
            lines.append(f"- ... {len(nodules) - 5} more nodules")
        return "\n".join(lines)

    def _format_nodules_detailed_zh(self, nodules) -> str:
        """格式化结节列表（中文详细版）"""
        lines = []
        for nodule in nodules:
            lines.append(
                f"""
结节 {nodule['index']}:
  - 位置: ({nodule['center']['x']:.2f}, {nodule['center']['y']:.2f}, {nodule['center']['z']:.2f}) mm
  - 尺寸: {nodule['dimensions']['width']:.2f} x {nodule['dimensions']['height']:.2f} x {nodule['dimensions']['depth']:.2f} mm
  - 最大直径: {nodule['diameter']:.2f} mm
  - 检测置信度: {nodule['score']:.4f} ({nodule['score']:.2%})
"""
            )
        return "\n".join(lines)

    def _format_nodules_detailed_en(self, nodules) -> str:
        """格式化结节列表（英文详细版）"""
        lines = []
        for nodule in nodules:
            lines.append(
                f"""
Nodule {nodule['index']}:
  - Location: ({nodule['center']['x']:.2f}, {nodule['center']['y']:.2f}, {nodule['center']['z']:.2f}) mm
  - Dimensions: {nodule['dimensions']['width']:.2f} x {nodule['dimensions']['height']:.2f} x {nodule['dimensions']['depth']:.2f} mm
  - Maximum diameter: {nodule['diameter']:.2f} mm
  - Confidence: {nodule['score']:.4f} ({nodule['score']:.2%})
"""
            )
        return "\n".join(lines)

    def _format_nodules_table_zh(self, nodules) -> str:
        """格式化结节数据表格（中文）"""
        lines = ["索引 | 直径(mm) | 置信度 | X | Y | Z"]
        lines.append("-----|----------|--------|-----|-----|-----")
        for nodule in nodules:
            lines.append(
                f"{nodule['index']} | {nodule['diameter']:.2f} | {nodule['score']:.4f} | {nodule['center']['x']:.2f} | {nodule['center']['y']:.2f} | {nodule['center']['z']:.2f}"
            )
        return "\n".join(lines)

    def _format_nodules_table_en(self, nodules) -> str:
        """格式化结节数据表格（英文）"""
        lines = ["Index | Diameter(mm) | Confidence | X | Y | Z"]
        lines.append("-----|-------------|------------|-----|-----|-----")
        for nodule in nodules:
            lines.append(
                f"{nodule['index']} | {nodule['diameter']:.2f} | {nodule['score']:.4f} | {nodule['center']['x']:.2f} | {nodule['center']['y']:.2f} | {nodule['center']['z']:.2f}"
            )
        return "\n".join(lines)

    def _generate_impression_zh(self, nodules) -> str:
        """生成诊断结论（中文）"""
        if not nodules:
            return "胸部CT检查未见明显异常结节。"

        high_risk = sum(1 for n in nodules if n["diameter"] >= 8 or n["score"] > 0.95)
        medium_risk = sum(
            1 for n in nodules if 6 <= n["diameter"] < 8 or 0.8 <= n["score"] <= 0.95
        )
        low_risk = len(nodules) - high_risk - medium_risk

        parts = []
        if high_risk > 0:
            parts.append(f"发现 {high_risk} 个高风险结节（直径≥8mm或置信度>95%）")
        if medium_risk > 0:
            parts.append(
                f"发现 {medium_risk} 个中等风险结节（直径6-8mm或置信度80-95%）"
            )
        if low_risk > 0:
            parts.append(f"发现 {low_risk} 个低风险结节")

        return "; ".join(parts) + "。建议结合临床症状和病史进行综合评估。"

    def _generate_impression_en(self, nodules) -> str:
        """生成诊断结论（英文）"""
        if not nodules:
            return "No significant nodules detected on chest CT."

        high_risk = sum(1 for n in nodules if n["diameter"] >= 8 or n["score"] > 0.95)
        medium_risk = sum(
            1 for n in nodules if 6 <= n["diameter"] < 8 or 0.8 <= n["score"] <= 0.95
        )
        low_risk = len(nodules) - high_risk - medium_risk

        parts = []
        if high_risk > 0:
            parts.append(f"{high_risk} high-risk nodule(s) (≥8mm or confidence >95%)")
        if medium_risk > 0:
            parts.append(
                f"{medium_risk} medium-risk nodule(s) (6-8mm or confidence 80-95%)"
            )
        if low_risk > 0:
            parts.append(f"{low_risk} low-risk nodule(s)")

        return (
            ", ".join(parts)
            + ". Recommend comprehensive evaluation with clinical symptoms and medical history."
        )

    def _generate_recommendation_zh(self, nodules) -> str:
        """生成建议（中文）"""
        if not nodules:
            return "建议定期体检，如有不适及时就医。"

        large_nodules = [n for n in nodules if n["diameter"] >= 8]
        if large_nodules:
            return "建议尽快就诊呼吸内科或胸外科，对直径≥8mm的结节进行进一步检查（如增强CT、PET-CT或穿刺活检）。"
        elif len(nodules) > 3:
            return "建议3-6个月后复查CT，观察结节变化。"
        else:
            return "建议6-12个月后复查CT随访。"

    def _generate_recommendation_en(self, nodules) -> str:
        """生成建议（英文）"""
        if not nodules:
            return "Regular health check-up recommended. Seek medical attention if symptoms occur."

        large_nodules = [n for n in nodules if n["diameter"] >= 8]
        if large_nodules:
            return "Urgent consultation with pulmonology or thoracic surgery recommended for nodules ≥8mm. Further evaluation (enhanced CT, PET-CT, or biopsy) may be needed."
        elif len(nodules) > 3:
            return "Follow-up CT scan recommended in 3-6 months."
        else:
            return "Follow-up CT scan recommended in 6-12 months."

    def generate_with_llm(
        self, detection_result: Dict, report_type: str = "detailed"
    ) -> str:
        """
        使用LLM生成智能病例报告（需要DeepSeek API）

        Args:
            detection_result: 检测结果字典
            report_type: 报告类型

        Returns:
            LLM生成的病例报告
        """
        logger.info("使用LLM生成智能病例报告")

        client = self._get_client()

        prompt = self._build_llm_prompt(detection_result, report_type)
        messages = [
            {
                "role": "system",
                "content": "你是一位专业的放射科医生，请根据检测结果生成详细的医学报告。",
            },
            {"role": "user", "content": prompt},
        ]

        try:
            response = client.chat(messages, temperature=0.3, max_tokens=2048)
            logger.info("LLM报告生成成功")
            return response
        except Exception as e:
            logger.error(f"LLM调用失败: {e}")
            # 降级使用模板生成
            return self.generate_case(detection_result, report_type)

    def _build_llm_prompt(self, data: Dict, report_type: str) -> str:
        """构建LLM提示词"""
        nodules = data.get("nodules", [])
        total_nodules = data.get("total_nodules", 0)
        image_name = data.get("image", "unknown")

        prompt = f"""
请根据以下肺部结节检测结果生成一份专业的医学报告。

患者信息：
- 患者ID: {image_name}
- 检测类型: 胸部CT

检测结果：
- 检测到结节数量: {total_nodules} 个
- 结节详细信息:
{json.dumps(nodules, indent=2, ensure_ascii=False)}

报告要求：
1. 报告类型: {report_type}
2. 使用中文
3. 格式规范，包含患者信息、检查方法、检测结果、诊断结论、建议等部分
4. 对每个结节进行评估，包括大小、位置、形态等
5. 给出Lung-RADS分类建议
6. 提供随访建议

请生成详细的医学报告。
"""

        return prompt

    def _build_rag_prompt(
        self, data: Dict, report_type: str, knowledge_context: str
    ) -> str:
        """
        构建RAG增强的LLM提示词

        Args:
            data: 检测结果字典
            report_type: 报告类型
            knowledge_context: 知识库上下文

        Returns:
            包含知识库内容的提示词
        """
        nodules = data.get("nodules", [])
        total_nodules = data.get("total_nodules", 0)
        image_name = data.get("image", "unknown")

        prompt = f"""
你是一位专业的放射科医生，请根据检测结果和知识库资料生成病例报告。

【重要提示】你必须完全按照知识库里面的资料来生成病例报告，不得凭空编造诊断建议。

【患者信息】
- 患者ID: {image_name}
- 检测类型: 胸部CT

【检测结果】
- 检测到结节数量: {total_nodules} 个
- 结节详细信息:
{json.dumps(nodules, indent=2, ensure_ascii=False)}

【知识库相关资料】
{knowledge_context if knowledge_context else "暂无相关知识库资料"}

【报告要求】
1. 报告类型: {report_type}
2. 使用中文
3. 格式规范，包含患者信息、检查方法、检测结果、诊断结论、建议等部分
4. 对每个结节进行评估，包括大小、位置、形态等
5. 严格参照知识库中的Lung-RADS分级标准进行分类
6. 严格参照知识库中的诊断共识和诊疗指南给出随访建议
7. 在报告中引用相关知识来源

请根据以上信息生成病例报告。
"""

        return prompt

    def generate_with_rag(
        self,
        detection_result: Dict,
        report_type: str = "detailed",
        retrieved_knowledge: List[Dict] = None,
    ) -> str:
        """
        使用RAG增强生成智能病例报告（需要DeepSeek API和向量数据库）

        Args:
            detection_result: 检测结果字典
            report_type: 报告类型
            retrieved_knowledge: 外部传入的检索结果（可选），如果提供则直接使用

        Returns:
            RAG增强的病例报告
        """
        logger.info("使用RAG增强生成智能病例报告")

        # 使用外部传入的知识或查询知识库
        if retrieved_knowledge:
            # 格式化外部传入的知识
            knowledge_context = self._format_retrieved_knowledge(retrieved_knowledge)
            logger.info(f"使用外部传入的 {len(retrieved_knowledge)} 条知识")
        else:
            # 查询知识库
            knowledge_context = self._query_knowledge_base(detection_result)

        # 如果没有知识库内容，降级到普通LLM生成
        if not knowledge_context:
            logger.info("未获取到知识库内容，降级到普通LLM生成")
            return self.generate_with_llm(detection_result, report_type)

        client = self._get_client()

        prompt = self._build_rag_prompt(
            detection_result, report_type, knowledge_context
        )
        messages = [
            {
                "role": "system",
                "content": "你是一位专业的放射科医生，请根据检测结果和知识库资料生成详细的医学报告。",
            },
            {"role": "user", "content": prompt},
        ]

        try:
            response = client.chat(messages, temperature=0.3, max_tokens=2048)
            logger.info("RAG增强报告生成成功")
            return response
        except Exception as e:
            logger.error(f"RAG增强报告生成失败: {e}")
            # 降级使用模板生成
            return self.generate_case(detection_result, report_type)

    def _format_retrieved_knowledge(self, knowledge_results: List[Dict]) -> str:
        """
        格式化检索结果为文本上下文

        Args:
            knowledge_results: 检索结果列表

        Returns:
            格式化的知识文本
        """
        if not knowledge_results:
            return ""

        context_parts = []
        for i, result in enumerate(knowledge_results, 1):
            content = result.get("content", "")
            source = result.get("source", "未知来源")
            similarity = result.get("similarity", 0)

            context_parts.append(
                f"【知识 {i}】(来源: {source}, 相似度: {similarity:.4f})\n{content}\n"
            )

        return "\n".join(context_parts)

    def save_report(
        self, report: str, filepath: str = None, use_date_dir: bool = True
    ) -> str:
        """
        保存报告到文件

        Args:
            report: 报告内容
            filepath: 输出文件路径，如果为None则自动生成
            use_date_dir: 是否使用按日期分类的目录

        Returns:
            保存的文件路径
        """
        import os
        from martin.util import get_result_manager

        manager = get_result_manager()

        if filepath:
            if use_date_dir:
                date_dir = manager.get_today_dir()
                filename = os.path.basename(filepath)
                filepath = os.path.join(date_dir, filename)
                os.makedirs(os.path.dirname(filepath), exist_ok=True)
        else:
            filepath = manager.save_report(report)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(report)

        logger.info(f"报告已保存到: {filepath}")
        return filepath

    @staticmethod
    def generate_and_save(
        detection_result: Dict,
        report_type: str = "detailed",
        language: str = "zh",
        use_llm: bool = False,
        use_rag: bool = False,
        api_key: str = None,
        output_path: str = None,
    ) -> tuple:
        """
        便捷函数：生成并保存报告

        Args:
            detection_result: 检测结果字典
            report_type: 报告类型
            language: 语言
            use_llm: 是否使用LLM生成
            use_rag: 是否使用RAG增强（需要向量数据库）
            api_key: API密钥
            output_path: 输出路径

        Returns:
            (报告内容, 保存路径) 元组
        """
        generator = CaseGenerator(api_key=api_key, use_rag=use_rag)

        if use_rag:
            report = generator.generate_with_rag(detection_result, report_type)
        elif use_llm:
            report = generator.generate_with_llm(detection_result, report_type)
        else:
            report = generator.generate_case(detection_result, report_type, language)

        saved_path = generator.save_report(report, output_path)

        return report, saved_path
