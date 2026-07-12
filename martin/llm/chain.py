"""LCEL 流程编排主链模块

使用 LangChain Expression Language (LCEL) 声明式编排：
检测结果 → RAG 检索 → 提示词构建 → LLM → 输出

提供三种报告类型的生成能力：
- brief: 简洁版报告
- detailed: 详细版报告
- research: 科研版报告

使用方式:
    from martin.llm.chain import generate_report

    report = generate_report(detection_result, report_type="detailed")
"""

import json
import logging
from typing import Dict, Optional

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough

from martin.llm.chat_model import get_chat_model
from martin.config import config
from martin.rag.retriever import format_results, search_by_detection

logger = logging.getLogger(__name__)

# ─── 系统提示词模板 ───────────────────────────────────────────

SYS_PROMPT_BRIEF = (
    "你是一位专业的放射科 AI 诊断专家。"
    "请根据肺部CT检测结果和知识库资料，生成一份简洁的医学报告摘要。\n"
    "【约束】\n"
    "1. 诊断结论和建议必须基于提供的【知识库资料】，不得凭空编造\n"
    "2. 引用知识库时标注来源，如 [知识1]、[知识2]\n"
    "3. 如果没有知识库资料，仅根据检测结果生成基础报告\n"
    "4. 使用markdown格式"
)

SYS_PROMPT_DETAILED = (
    "你是一位专业的放射科 AI 诊断专家。"
    "请根据肺部CT检测结果和知识库资料，生成一份详细的医学报告。\n"
    "【约束】\n"
    "1. 诊断结论和建议必须基于提供的【知识库资料】，不得凭空编造\n"
    "2. 引用知识库时标注来源，如 [知识1]、[知识2]\n"
    "3. 如果没有知识库资料，仅根据检测结果生成基础报告\n"
    "4. 对每个结节进行详细评估，包括大小、位置、形态特征\n"
    "5. 严格参照Lung-RADS分级标准对结节进行分类\n"
    "6. 给出具体的随访建议和时间间隔\n"
    "7. 使用markdown格式"
)

SYS_PROMPT_RESEARCH = (
    "你是一位专业的放射科 AI 诊断专家。"
    "请根据肺部CT检测结果和知识库资料，生成一份科研级医学报告。\n"
    "【约束】\n"
    "1. 诊断结论和建议必须基于提供的【知识库资料】，不得凭空编造\n"
    "2. 引用知识库时标注来源，如 [知识1]、[知识2]\n"
    "3. 如果没有知识库资料，仅根据检测结果生成基础报告\n"
    "4. 包含完整的统计分析（均值、中位数、标准差、分布等）\n"
    "5. 数据质量评估（检测置信度分析、图像质量评价）\n"
    "6. 提供JSON格式的结节数据便于后续处理\n"
    "7. 使用markdown格式"
)

# ─── 报告类型 -> 系统提示词映射 ──────────────────────────────

_REPORT_TYPE_MAP = {
    "brief": SYS_PROMPT_BRIEF,
    "detailed": SYS_PROMPT_DETAILED,
    "research": SYS_PROMPT_RESEARCH,
}

# ─── 用户提示词模板 ──────────────────────────────────────────

diagnosis_prompt = ChatPromptTemplate.from_messages([
    ("system", "{system_prompt}"),
    (
        "human",
        """【患者信息】
- 患者ID: {image_name}
- 检测类型: 胸部CT

【检测结果】
- 结节数量: {total_nodules} 个
- 详见: {nodules_detail}

【知识库资料】
{knowledge_context}

【报告要求】
- 报告类型: {report_type}
- 语言: 中文
- 请基于以上信息生成病例报告。""",
    ),
])


def _build_nodules_detail(detection_result: Dict, report_type: str) -> str:
    """根据报告类型格式化结节详细信息。

    迁移自 case_generator.py 的格式化逻辑：
    - brief: 简洁列表（最多显示5个结节）
    - detailed: 包含位置、尺寸、置信度的详细信息
    - research: 表格格式 + 统计分析

    Args:
        detection_result: 检测结果字典，包含 nodules 和 total_nodules 字段。
        report_type: 报告类型，可选 brief / detailed / research。

    Returns:
        格式化后的结节详情字符串。若无结节则返回"无"。
    """
    nodules = detection_result.get("nodules", [])
    total_nodules = detection_result.get("total_nodules", 0)

    if total_nodules == 0 or not nodules:
        return "无"

    report_type = report_type.lower()

    if report_type == "brief":
        return _format_nodules_brief(nodules)
    elif report_type == "research":
        return _format_nodules_research(nodules)
    else:
        return _format_nodules_detailed(nodules)


def _format_nodules_brief(nodules: list) -> str:
    """格式化结节列表（简洁版）。

    显示每个结节的基本信息，最多显示5个。

    Args:
        nodules: 结节列表。

    Returns:
        格式化的简洁结节文本。
    """
    lines = []
    for nodule in nodules[:5]:
        lines.append(
            f"- 结节 {nodule['index']}: "
            f"直径 {nodule['diameter']:.2f}mm, "
            f"置信度 {nodule['score']:.2%}"
        )
    if len(nodules) > 5:
        lines.append(f"- ... 还有 {len(nodules) - 5} 个结节")
    return "\n".join(lines)


def _format_nodules_detailed(nodules: list) -> str:
    """格式化结节列表（详细版）。

    显示每个结节的位置坐标、三维尺寸、最大直径和检测置信度。

    Args:
        nodules: 结节列表。

    Returns:
        格式化的详细结节文本。
    """
    lines = []
    for nodule in nodules:
        center = nodule.get("center", {})
        dims = nodule.get("dimensions", {})
        lines.append(
            f"\n结节 {nodule['index']}:"
            f"\n  - 位置: ({center.get('x', 0):.2f}, "
            f"{center.get('y', 0):.2f}, {center.get('z', 0):.2f}) mm"
            f"\n  - 尺寸: {dims.get('width', 0):.2f} x "
            f"{dims.get('height', 0):.2f} x {dims.get('depth', 0):.2f} mm"
            f"\n  - 最大直径: {nodule['diameter']:.2f} mm"
            f"\n  - 检测置信度: {nodule['score']:.4f} ({nodule['score']:.2%})"
        )
    return "\n".join(lines)


def _format_nodules_research(nodules: list) -> str:
    """格式化结节数据（科研版）。

    生成表格格式的结节数据，包含索引、直径、置信度和坐标信息。

    Args:
        nodules: 结节列表。

    Returns:
        格式化的科研级结节数据文本，含表头和分隔线。
    """
    lines = ["索引 | 直径(mm) | 置信度 | X | Y | Z"]
    lines.append("-----|----------|--------|-----|-----|-----")
    for nodule in nodules:
        center = nodule.get("center", {})
        lines.append(
            f"{nodule['index']} | {nodule['diameter']:.2f} | "
            f"{nodule['score']:.4f} | {center.get('x', 0):.2f} | "
            f"{center.get('y', 0):.2f} | {center.get('z', 0):.2f}"
        )
    return "\n".join(lines)


def _build_knowledge_context(detection_result: Dict, top_k: int) -> str:
    """从知识库检索并格式化相关知识。

    调用 retriever 模块的 search_by_detection 执行检索，
    再通过 format_results 将结果格式化为 LLM 可读的上下文文本。

    Args:
        detection_result: 检测结果字典。
        top_k: 检索返回的最相关文档数量。

    Returns:
        格式化的知识库上下文文本。
        若检索失败或无结果，返回"暂无相关知识库资料。"。
    """
    try:
        results = search_by_detection(
            detection_result, top_k=top_k, threshold=config.similarity_threshold
        )
        if results:
            context = format_results(results)
            logger.info("知识库检索成功，获取到 %d 条相关资料", len(results))
            return context
        else:
            logger.info("知识库检索无相关结果")
            return "暂无相关知识库资料。"
    except Exception as e:
        logger.warning("知识库检索失败: %s", e)
        return "暂无相关知识库资料。"


def _generate_template_report(detection_result: Dict, report_type: str) -> str:
    """使用模板生成降级报告（LLM 调用失败时的备用方案）。

    当 LLM 链执行失败时调用此函数，根据报告类型生成纯模板报告。
    迁移自 case_generator.py 的模板生成逻辑。

    Args:
        detection_result: 检测结果字典。
        report_type: 报告类型，可选 brief / detailed / research。

    Returns:
        模板生成的报告文本。
    """
    nodules = detection_result.get("nodules", [])
    total_nodules = detection_result.get("total_nodules", 0)
    image_name = detection_result.get("image", "unknown")

    report_type = report_type.lower()

    if report_type == "brief":
        return _build_template_brief(image_name, total_nodules, nodules)
    elif report_type == "research":
        return _build_template_research(image_name, total_nodules, nodules)
    else:
        return _build_template_detailed(image_name, total_nodules, nodules)


def _build_template_brief(image_name: str, total_nodules: int, nodules: list) -> str:
    """生成简洁版模板报告。"""
    if total_nodules == 0:
        nodule_text = "未检测到结节。"
    else:
        lines = []
        for nodule in nodules[:5]:
            lines.append(
                f"- 结节 {nodule['index']}: "
                f"直径 {nodule['diameter']:.2f}mm, "
                f"置信度 {nodule['score']:.2%}"
            )
        if len(nodules) > 5:
            lines.append(f"- ... 还有 {len(nodules) - 5} 个结节")
        nodule_text = "\n".join(lines)

    return (
        f"医学报告摘要\n"
        f"============\n\n"
        f"患者ID: {image_name}\n"
        f"日期: 自动生成\n\n"
        f"检测结果:\n"
        f"- 检测到结节总数: {total_nodules} 个\n\n"
        f"{nodule_text}\n\n"
        f"建议: 请咨询放射科医生进行进一步评估。"
    )


def _build_template_detailed(image_name: str, total_nodules: int, nodules: list) -> str:
    """生成详细版模板报告。"""
    if total_nodules == 0:
        nodule_text = "未检测到肺部结节。"
        impression = "胸部CT检查未见明显异常结节。"
        recommendation = "建议定期体检，如有不适及时就医。"
    else:
        nodule_lines = []
        for nodule in nodules:
            center = nodule.get("center", {})
            dims = nodule.get("dimensions", {})
            nodule_lines.append(
                f"\n结节 {nodule['index']}:"
                f"\n  - 位置: ({center.get('x', 0):.2f}, "
                f"{center.get('y', 0):.2f}, {center.get('z', 0):.2f}) mm"
                f"\n  - 尺寸: {dims.get('width', 0):.2f} x "
                f"{dims.get('height', 0):.2f} x {dims.get('depth', 0):.2f} mm"
                f"\n  - 最大直径: {nodule['diameter']:.2f} mm"
                f"\n  - 检测置信度: {nodule['score']:.4f} ({nodule['score']:.2%})"
            )
        nodule_text = "\n".join(nodule_lines)

        # 生成诊断结论
        high_risk = sum(
            1 for n in nodules if n["diameter"] >= 8 or n["score"] > 0.95
        )
        medium_risk = sum(
            1
            for n in nodules
            if 6 <= n["diameter"] < 8 or 0.8 <= n["score"] <= 0.95
        )
        low_risk = len(nodules) - high_risk - medium_risk

        impression_parts = []
        if high_risk > 0:
            impression_parts.append(
                f"发现 {high_risk} 个高风险结节（直径≥8mm或置信度>95%）"
            )
        if medium_risk > 0:
            impression_parts.append(
                f"发现 {medium_risk} 个中等风险结节（直径6-8mm或置信度80-95%）"
            )
        if low_risk > 0:
            impression_parts.append(f"发现 {low_risk} 个低风险结节")
        impression = (
            "; ".join(impression_parts)
            + "。建议结合临床症状和病史进行综合评估。"
        )

        # 生成随访建议
        large_nodules = [n for n in nodules if n["diameter"] >= 8]
        if large_nodules:
            recommendation = (
                "建议尽快就诊呼吸内科或胸外科，"
                "对直径≥8mm的结节进行进一步检查"
                "（如增强CT、PET-CT或穿刺活检）。"
            )
        elif len(nodules) > 3:
            recommendation = "建议3-6个月后复查CT，观察结节变化。"
        else:
            recommendation = "建议6-12个月后复查CT随访。"

    return (
        f"医学报告\n"
        f"========\n\n"
        f"【患者信息】\n"
        f"- 患者ID: {image_name}\n"
        f"- 报告类型: 详细版\n"
        f"- 生成日期: 自动生成\n\n"
        f"【检查方法】\n"
        f"- 检查方式: 胸部CT\n"
        f"- 重建方式: 标准重建\n\n"
        f"【检测结果】\n"
        f"共检测到 {total_nodules} 个肺部结节\n\n"
        f"{nodule_text}\n\n"
        f"【诊断结论】\n"
        f"{impression}\n\n"
        f"【建议】\n"
        f"{recommendation}\n\n"
        f"【免责声明】\n"
        f"本报告由AI自动生成，需经专业放射科医生审核确认。"
    )


def _build_template_research(
    image_name: str, total_nodules: int, nodules: list
) -> str:
    """生成科研版模板报告。"""
    if total_nodules == 0:
        nodule_text = "未检测到结节。"
        avg_diameter = 0.0
        avg_score = 0.0
        max_diameter = 0.0
        min_diameter = 0.0
    else:
        # 表格数据
        table_lines = ["索引 | 直径(mm) | 置信度 | X | Y | Z"]
        table_lines.append("-----|----------|--------|-----|-----|-----")
        for nodule in nodules:
            center = nodule.get("center", {})
            table_lines.append(
                f"{nodule['index']} | {nodule['diameter']:.2f} | "
                f"{nodule['score']:.4f} | {center.get('x', 0):.2f} | "
                f"{center.get('y', 0):.2f} | {center.get('z', 0):.2f}"
            )
        nodule_text = "\n".join(table_lines)

        # 统计分析
        diameters = [n["diameter"] for n in nodules]
        scores = [n["score"] for n in nodules]
        avg_diameter = sum(diameters) / len(diameters)
        avg_score = sum(scores) / len(scores)
        max_diameter = max(diameters)
        min_diameter = min(diameters)

    if total_nodules > 0:
        data_quality = (
            "高" if avg_score > 0.9 else "中" if avg_score > 0.7 else "低"
        )
        research_suggestion = (
            "建议进一步研究" if total_nodules > 0 else "未检测到异常"
        )
    else:
        data_quality = "无"
        research_suggestion = "未检测到异常"

    return (
        f"科研报告\n"
        f"========\n\n"
        f"【研究信息】\n"
        f"- 样本ID: {image_name}\n"
        f"- 报告类型: 科研版\n"
        f"- 生成日期: 自动生成\n\n"
        f"【扫描参数】\n"
        f"- 检查方式: 胸部CT\n"
        f"- 分析方法: AI结节检测\n\n"
        f"【检测统计】\n"
        f"- 结节总数: {total_nodules}\n"
        f"- 平均直径: {avg_diameter:.2f} mm\n"
        f"- 平均置信度: {avg_score:.4f}\n"
        f"- 最大直径: {max_diameter:.2f} mm\n"
        f"- 最小直径: {min_diameter:.2f} mm\n\n"
        f"【结节详细数据】\n"
        f"{nodule_text}\n\n"
        f"【数据质量评估】\n"
        f"- 图像质量: 良好\n"
        f"- 检测置信度: {data_quality}\n"
        f"- 建议: {research_suggestion}\n\n"
        f"【JSON格式数据（便于处理）】\n"
        f"{json.dumps(nodules, indent=2, ensure_ascii=False)}"
    )


# ─── 获取系统提示词 ──────────────────────────────────────────


def _get_system_prompt(report_type: str) -> str:
    """根据报告类型获取对应的系统提示词。

    Args:
        report_type: 报告类型，可选 brief / detailed / research。

    Returns:
        对应的系统提示词字符串。若类型无效，默认返回详细版提示词。
    """
    return _REPORT_TYPE_MAP.get(report_type.lower(), SYS_PROMPT_DETAILED)


# ─── LCEL 链构建 ─────────────────────────────────────────────


def create_diagnosis_chain():
    """创建 LCEL 诊断报告生成链。

    使用 LCEL（| 操作符）声明式编排处理流程：
    输入字典 → 并行处理（知识库检索 + 结节格式化）→ 构建 Prompt → LLM → 输出解析

    流程步骤：
    1. RunnablePassthrough.assign 并行注入 knowledge_context 和 nodules_detail
    2. 将系统提示词注入输入字典作为 system_prompt 字段
    3. 通过 diagnosis_prompt 构建完整的消息列表
    4. 调用 LLM 生成报告
    5. 使用 StrOutputParser 解析输出为字符串

    Returns:
        Runnable: 编译好的 LCEL Runnable 对象，可直接用 invoke() 调用。
    """
    model = get_chat_model()

    chain = (
        RunnablePassthrough.assign(
            knowledge_context=lambda x: _build_knowledge_context(
                x.get("detection_result"), config.top_k
            ),
            nodules_detail=lambda x: _build_nodules_detail(
                x.get("detection_result"), x.get("report_type", "detailed")
            ),
        )
        | diagnosis_prompt
        | model
        | StrOutputParser()
    )
    return chain


# ─── 主入口函数 ──────────────────────────────────────────────


def generate_report(
    detection_result: Dict, report_type: str = "detailed", language: str = "zh"
) -> str:
    """生成病例报告（最外层调用接口）。

    使用 LCEL 链生成 AI 驱动的病例报告，包含三级降级策略：
    1. 正常执行 LCEL 链 → 返回 LLM 生成的报告
    2. 若 LLM 调用失败 → 调用 _generate_template_report() 使用模板生成
    3. 若模板也失败 → 返回基本错误信息

    Args:
        detection_result: 检测结果字典，需包含以下字段：
            - image (str): 患者图像ID
            - total_nodules (int): 检测到的结节总数
            - nodules (list): 结节详情列表
        report_type: 报告类型，可选 brief / detailed / research，默认为 detailed。
        language: 报告语言，目前仅支持 zh（中文），默认为 zh。

    Returns:
        生成的病例报告字符串。
    """
    logger.info(
        "开始生成病例报告，类型: %s，语言: %s", report_type, language
    )

    report_type = report_type.lower()
    if report_type not in _REPORT_TYPE_MAP:
        logger.warning("未知报告类型 '%s'，使用默认类型 'detailed'", report_type)
        report_type = "detailed"

    # 构建链输入
    chain_input = {
        "system_prompt": _get_system_prompt(report_type),
        "image_name": detection_result.get("image", "unknown"),
        "total_nodules": detection_result.get("total_nodules", 0),
        "report_type": report_type,
        "detection_result": detection_result,
    }

    # 第一级：尝试 LCEL 链
    try:
        chain = create_diagnosis_chain()
        report = chain.invoke(chain_input)
        logger.info("LCEL 链执行成功，报告生成完成")
        return report
    except Exception as e:
        logger.warning("LCEL 链执行失败: %s，降级到模板生成", e)

    # 第二级：模板降级
    try:
        report = _generate_template_report(detection_result, report_type)
        logger.info("模板降级报告生成完成")
        return report
    except Exception as e:
        logger.error("模板降级报告生成失败: %s", e)

    # 第三级：基本错误信息
    logger.error("所有报告生成方式均失败，返回基本错误信息")
    return (
        f"报告生成失败。\n"
        f"患者ID: {detection_result.get('image', 'unknown')}\n"
        f"检测到 {detection_result.get('total_nodules', 0)} 个结节。\n"
        f"请稍后重试或联系系统管理员。"
    )
