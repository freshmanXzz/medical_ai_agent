"""LangChain 检索器封装模块

提供基于 langchain_chroma.Chroma 的向量检索功能，
封装了从检测结果构建查询、检索、去重过滤和结果格式化的完整流程。

使用方式:
    from martin.rag.retriever import search_by_detection, format_results

    results = search_by_detection(detection_result, top_k=5, threshold=0.7)
    context = format_results(results)
"""

import logging
from typing import List, Optional

from langchain_core.documents import Document

from martin.rag.vector_store import get_vector_store

logger = logging.getLogger(__name__)


def _build_query_from_detection(detection_result: dict) -> str:
    """从检测结果构建检索查询文本。

    根据结节数量和最大直径生成语义化的查询语句，
    用于在向量数据库中检索相关的 Lung-RADS 分级、诊断标准和随访建议。

    Args:
        detection_result: 检测结果字典，包含 total_nodules、nodules 等字段。

    Returns:
        查询文本字符串。
    """
    total_nodules = detection_result.get("total_nodules", 0)
    nodules = detection_result.get("nodules", [])

    if total_nodules == 0:
        return "肺部CT检查未见结节 正常报告解读"

    diameters = [n.get("diameter", 0) for n in nodules]
    max_diameter = max(diameters) if diameters else 0

    query_parts = []

    # 结节数量描述
    if total_nodules == 1:
        query_parts.append("单个肺部结节")
    elif total_nodules <= 3:
        query_parts.append(f"{total_nodules}个肺部结节")
    else:
        query_parts.append(f"多发肺部结节（{total_nodules}个）")

    # 结节大小描述
    if max_diameter > 0:
        if max_diameter < 6:
            query_parts.append("微小结节")
        elif max_diameter < 8:
            query_parts.append("小结节")
        elif max_diameter < 15:
            query_parts.append("中等大小结节")
        else:
            query_parts.append("大结节")
        query_parts.append(f"最大直径{max_diameter:.1f}mm")

    query_parts.append("Lung-RADS分级 诊断标准 随访建议")
    return " ".join(query_parts)


def _deduplicate_results(results: List[Document]) -> List[Document]:
    """对检索结果按 page_content 去重。

    保留首次出现的文档，去除内容重复的后续文档。
    使用 set 记录已出现的内容，时间复杂度 O(n)。

    Args:
        results: 待去重的文档列表。

    Returns:
        去重后的文档列表，保持原始顺序。
    """
    seen_contents = set()
    unique_results = []

    for doc in results:
        if doc.page_content not in seen_contents:
            seen_contents.add(doc.page_content)
            unique_results.append(doc)

    return unique_results


def search_by_detection(
    detection_result: dict,
    top_k: int = 5,
    threshold: float = 0.7,
) -> List[Document]:
    """根据检测结果检索相关医学知识。

    核心检索函数，流程如下：
    1. 从检测结果构建语义化查询文本
    2. 使用 VectorStoreRetriever 执行向量检索
    3. 若存在多个结节（>1），针对最大结节额外检索一次
    4. 合并结果并按 page_content 去重
    5. 过滤低相似度结果（metadata.score >= threshold）
    6. 限制返回数量不超过 top_k

    Args:
        detection_result: 检测结果字典，包含 total_nodules、nodules 等字段。
        top_k: 返回的最相关文档数量，默认为 5。
        threshold: 相似度阈值，低于此值的文档将被过滤，默认为 0.7。

    Returns:
        Document 列表，每项包含 page_content（文本内容）和 metadata（元数据）。
    """
    if not detection_result or not detection_result.get("nodules"):
        logger.warning("检测结果为空，无法构建检索")
        return []

    vector_store = get_vector_store()
    if vector_store is None:
        logger.warning("向量数据库未初始化，无法执行检索")
        return []

    retriever = vector_store.as_retriever(
        search_kwargs={"k": top_k * 2},
    )

    # 构建初次查询
    query = _build_query_from_detection(detection_result)
    logger.info("检测结果检索查询: %s", query)

    # 执行检索
    all_results: List[Document] = retriever.invoke(query)

    # 多结节（>1）时，针对最大结节额外检索一次
    nodules = detection_result.get("nodules", [])
    if len(nodules) > 1:
        max_nodule = max(nodules, key=lambda n: n.get("diameter", 0))
        max_diameter = max_nodule.get("diameter", 0)
        size_query = f"肺部结节直径{max_diameter:.1f}mm 大小分级 处理建议"
        logger.info("额外检索最大结节查询: %s", size_query)
        size_results = retriever.invoke(size_query)
        all_results.extend(size_results)

    # 去重
    all_results = _deduplicate_results(all_results)

    # 过滤低相似度结果
    filtered_results = [
        doc
        for doc in all_results
        if doc.metadata.get("score", 1.0) >= threshold
    ]

    # 限制返回数量
    return filtered_results[:top_k]


def search_by_query(
    query: str,
    top_k: int = 5,
    threshold: float = 0.5,
) -> List[Document]:
    """根据自由文本查询检索医学知识库。

    与 search_by_detection 不同，本函数接受任意文本查询，
    用于用户直接提问知识类问题（如"什么是 Lung-RADS"）。

    Args:
        query: 自由文本查询字符串。
        top_k: 返回的最相关文档数量，默认为 5。
        threshold: 相似度阈值，默认为 0.5（比检测结果检索更宽松）。

    Returns:
        Document 列表。
    """
    vector_store = get_vector_store()
    if vector_store is None:
        logger.warning("向量数据库未初始化，无法执行检索")
        return []

    retriever = vector_store.as_retriever(
        search_kwargs={"k": top_k * 2},
    )

    logger.info("自由文本查询: %s", query)
    all_results: List[Document] = retriever.invoke(query)
    all_results = _deduplicate_results(all_results)

    filtered_results = [
        doc
        for doc in all_results
        if doc.metadata.get("score", 1.0) >= threshold
    ]
    return filtered_results[:top_k]


def format_results(results: List[Document]) -> str:
    """格式化检索结果为 LLM 可用的上下文文本。

    将 Document 列表转换为结构化的文本上下文，
    包含序号、内容、来源和相似度信息。

    Args:
        results: 检索结果 Document 列表。

    Returns:
        格式化的上下文文本字符串，每项包含内容、来源和相似度。
    """
    if not results:
        return "未检索到相关医学知识。"

    context_parts = []
    for i, doc in enumerate(results, 1):
        source = doc.metadata.get("source", "")
        score = doc.metadata.get("score", 0)

        part = f"【参考资料{i}】\n"
        part += f"内容：{doc.page_content}\n"
        if source:
            part += f"来源：{source}\n"
        part += f"相似度：{score:.2f}\n"
        part += "---\n"
        context_parts.append(part)

    return "\n".join(context_parts)


def get_retriever_for_detection(top_k: int = 5) -> Optional[object]:
    """获取用于检测结果检索的 VectorStoreRetriever 实例。

    便捷函数，自动获取 VectorStore 并创建 Retriever。
    若向量数据库未初始化，则返回 None。

    Args:
        top_k: 检索返回的最相关文档数，默认为 5。

    Returns:
        VectorStoreRetriever 实例，若向量数据库未初始化则返回 None。
    """
    vector_store = get_vector_store()
    if vector_store is None:
        logger.warning("向量数据库未初始化，无法创建 Retriever")
        return None

    retriever = vector_store.as_retriever(
        search_kwargs={"k": top_k},
    )
    logger.info("Retriever 创建成功: top_k=%d", top_k)
    return retriever
