"""LangChain Agent 工具封装模块

使用 langchain_core.tools.tool 装饰器将检测、检索、报告生成功能
封装为 Agent 可调用的 Tool，每个工具均返回格式化的字符串。
"""

import json
import logging
from typing import Dict

from langchain_core.tools import tool

from martin.inference import LungNoduleDetector
from martin.llm.chain import (
    _generate_template_report,
    generate_report as chain_generate_report,
)
from martin.rag.retriever import format_results, search_by_detection
from martin.rag.vector_store import get_vector_store

logger = logging.getLogger(__name__)


def _normalize_detection_result(result: Dict) -> None:
    """归一化检测结果字段名，兼容 Agent 自动构建 JSON 时的不同命名习惯。

    将 Agent 可能使用的不同字段名映射到 chain.py 期望的标准格式（就地修改）。
    支持以下别名：
    - total_count / total_nodules_found → total_nodules
    - confidence → score
    - diameter_mm → diameter
    - nodule_1, nodule_2... → 合并为 nodules list
    """
    # 归一化 total_nodules
    if "total_nodules" not in result:
        for alias in ("total_count", "total_nodules_found", "nodule_count"):
            if alias in result:
                result["total_nodules"] = result[alias]
                break

    # 归一化 nodules list
    if "nodules" not in result or not result.get("nodules"):
        # 尝试从 nodule_1, nodule_2, ... 单键重建
        nodule_list = []
        i = 1
        while f"nodule_{i}" in result:
            nodule_list.append(result[f"nodule_{i}"])
            i += 1
        if nodule_list:
            result["nodules"] = nodule_list
            if "total_nodules" not in result:
                result["total_nodules"] = len(nodule_list)
        else:
            result.setdefault("nodules", [])

    # 确保 total_nodules 存在
    result.setdefault("total_nodules", 0)

    # 归一化每个结节的字段
    for nodule in result.get("nodules", []):
        # confidence -> score
        if "score" not in nodule and "confidence" in nodule:
            nodule["score"] = nodule["confidence"]
        # diameter_mm / max_diameter_mm -> diameter
        if "diameter" not in nodule:
            for alias in ("max_diameter_mm", "diameter_mm", "max_diameter"):
                if alias in nodule:
                    nodule["diameter"] = nodule[alias]
                    break
        # confidence_percent -> score
        if "score" not in nodule and "confidence_percent" in nodule:
            nodule["score"] = nodule["confidence_percent"] / 100.0
        # id -> index（模型输出用 id 而非 index）
        if "index" not in nodule and "id" in nodule:
            nodule["index"] = nodule["id"]
        # 确保 index
        if "index" not in nodule:
            nodule["index"] = result["nodules"].index(nodule) + 1

    logger.debug(
        "归一化后: total_nodules=%d, nodules=%d",
        result.get("total_nodules", 0),
        len(result.get("nodules", [])),
    )


@tool
def analyze_image(image_path: str, reasoning: str = "") -> str:
    """对肺部CT图像进行结节检测分析，返回检测到的结节信息列表。

    Args:
        image_path: CT图像文件路径（支持NIfTI格式）。
        reasoning: 推理过程记录（不参与业务逻辑）。

    Returns:
        格式化文本，包含结节数量、每个结节的直径/置信度/位置信息。
    """
    logger.info("调用 analyze_image 工具，图像路径: %s", image_path)

    try:
        detector = LungNoduleDetector()
        result = detector.detect(image_path)
    except FileNotFoundError:
        logger.error("图像文件不存在: %s", image_path)
        return f"错误: 图像文件不存在: {image_path}"
    except Exception as e:
        logger.error("图像检测失败: %s", e, exc_info=True)
        return f"错误: 图像分析失败: {e}"

    nodules = result.get("nodules", [])
    total = result.get("total_nodules", 0)
    image_name = result.get("image", image_path)

    lines = [f"图像: {image_name}", f"检测到结节总数: {total} 个\n"]

    if not nodules:
        lines.append("未检测到肺部结节。")
        return "\n".join(lines)

    for nodule in nodules:
        lines.append(f"结节 {nodule['index']}:")
        lines.append(f"  - 最大直径: {nodule['diameter']:.2f} mm")
        lines.append(
            f"  - 检测置信度: {nodule['score']:.4f} ({nodule['score']:.2%})"
        )
        center = nodule.get("center", {})
        lines.append(
            f"  - 中心位置: ({center.get('x', 0):.2f}, "
            f"{center.get('y', 0):.2f}, {center.get('z', 0):.2f}) mm"
        )
        dims = nodule.get("dimensions", {})
        lines.append(
            f"  - 三维尺寸: {dims.get('width', 0):.2f} x "
            f"{dims.get('height', 0):.2f} x {dims.get('depth', 0):.2f} mm"
        )
        lines.append("")

    return "\n".join(lines)


@tool
def retrieve_knowledge(detection_context: str, reasoning: str = "") -> str:
    """根据CT检测结果检索医学知识库，获取诊断标准和随访建议。

    Args:
        detection_context: 检测结果的 JSON 格式字符串。
        reasoning: 推理过程记录（不参与业务逻辑）。

    Returns:
        格式化的知识库相关片段，包含来源标注。
    """
    logger.info("调用 retrieve_knowledge 工具")

    # 检查向量库是否已初始化
    vector_store = get_vector_store()
    if vector_store is None:
        logger.warning("向量数据库未初始化")
        return "知识库未初始化，请先执行 scripts/import_knowledge.py"

    # 尝试将文本解析为 dict
    detection_result: Dict
    try:
        detection_result = json.loads(detection_context)
    except (json.JSONDecodeError, TypeError):
        logger.warning("无法解析检测结果 JSON，构建默认结构")
        detection_result = {
            "image": "unknown",
            "total_nodules": 0,
            "nodules": [],
        }

    _normalize_detection_result(detection_result)

    try:
        results = search_by_detection(
            detection_result, top_k=5, threshold=0.7
        )
    except Exception as e:
        logger.warning("知识库检索失败: %s", e)
        return f"错误: 知识库检索失败: {e}"

    context = format_results(results)
    logger.info("检索到 %d 条相关知识", len(results))
    return context


@tool
def generate_report(
    detection_result: str,
    report_type: str = "detailed",
    language: str = "zh",
    reasoning: str = "",
) -> str:
    """根据检测结果和知识库资料生成结构化病例报告。

    Args:
        detection_result: 检测结果的 JSON 格式字符串。
        report_type: 报告类型，可选 brief / detailed / research，默认为 detailed。
        language: 报告语言，zh（中文）或 en（英文），默认为 zh。
        reasoning: 推理过程记录（不参与业务逻辑）。

    Returns:
        Markdown 格式的病例报告。
    """
    logger.info(
        "调用 generate_report 工具，类型: %s，语言: %s",
        report_type,
        language,
    )

    # 解析检测结果 JSON
    try:
        result_dict = json.loads(detection_result)
    except (json.JSONDecodeError, TypeError):
        logger.warning("无法解析检测结果 JSON")
        return "报告生成失败：检测结果格式无效，请提供有效的 JSON 格式检测结果。"

    # 归一化字段名：兼容 Agent 自动构建 JSON 时的不同命名习惯
    _normalize_detection_result(result_dict)

    # 第一级：尝试 LLM 链生成报告
    try:
        report = chain_generate_report(
            result_dict,
            report_type=report_type,
            language=language,
        )
        logger.info("LLM 报告生成完成")
        return report
    except Exception as e:
        logger.warning("LLM 报告生成失败: %s，降级到模板生成", e)

    # 第二级：降级到模板生成
    try:
        report = _generate_template_report(result_dict, report_type)
        logger.info("模板降级报告生成完成")
        return report
    except Exception as e:
        logger.error("模板降级报告生成失败: %s", e, exc_info=True)
        return (
            f"报告生成失败：{e}\n\n"
            f"请稍后重试，或联系系统管理员。"
        )
