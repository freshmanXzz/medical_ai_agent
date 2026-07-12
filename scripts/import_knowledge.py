"""
医学知识库向量化导入脚本

使用 LangChain 组件将 knowledge_base 目录下的文档向量化后存储到向量数据库
支持 Markdown、CSV、PDF、DOCX 格式文档
"""
import argparse
import os
import sys
from typing import List

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from martin.rag.document_loader import load_knowledge_base
from martin.rag.text_splitter import split_documents
from martin.rag.embeddings import get_embeddings
from martin.rag.vector_store import create_vector_store, get_vector_store
from martin.rag.retriever import search_by_detection
from martin.utils import AppLogger

logger = AppLogger.setup_logging(__name__)


def import_knowledge_to_vector_db(
    knowledge_dir: str = None,
    persist_dir: str = None,
    chunk_size: int = 500,
    chunk_overlap: int = 50
) -> int:
    """
    将知识库文档导入向量数据库

    Args:
        knowledge_dir: 知识库目录路径
        persist_dir: 向量数据库持久化目录
        chunk_size: 切分大小
        chunk_overlap: 切分重叠

    Returns:
        导入的向量数量
    """
    logger.info(f"开始导入知识库")

    # 加载知识库文档
    logger.info("加载知识库文档...")
    documents = load_knowledge_base()
    logger.info(f"共加载 {len(documents)} 个文档")

    if not documents:
        logger.warning("未加载到任何文档")
        return 0

    # 切分文档
    logger.info("切分文档...")
    document_chunks = split_documents(documents)
    logger.info(f"切分完成，生成 {len(document_chunks)} 个文档块")

    # 初始化Embedding模型
    logger.info("初始化Embedding模型...")
    embeddings = get_embeddings()

    # 创建向量数据库并插入数据
    logger.info("创建向量数据库并插入数据...")
    vector_store = create_vector_store(documents=document_chunks, embeddings=embeddings)
    inserted_count = len(document_chunks)

    logger.info(f"成功导入 {inserted_count} 条向量记录")

    return inserted_count


def query_knowledge(query: str, top_k: int = 5) -> List:
    """
    查询知识库

    Args:
        query: 查询文本
        top_k: 返回结果数量

    Returns:
        检索结果列表
    """
    logger.info(f"查询知识库: {query}")

    vector_store = get_vector_store()
    if vector_store is None:
        logger.error("向量数据库未初始化")
        return []

    retriever = vector_store.as_retriever(search_kwargs={"k": top_k})
    results = retriever.invoke(query)

    return [
        {
            "content": doc.page_content,
            "metadata": doc.metadata,
            "score": doc.metadata.get("score", 0),
            "source": doc.metadata.get("source", ""),
        }
        for doc in results
    ]


def main():
    """主函数"""
    print("=" * 60)
    print("医学知识库向量化工具")
    print("=" * 60)

    try:
        inserted_count = import_knowledge_to_vector_db()

        print(f"\n✅ 成功导入 {inserted_count} 条向量记录")
        print(f"📁 知识库目录: knowledge_base/")
        print(f"💾 向量数据库: data/chroma_db/")

        print("\n" + "=" * 60)
        print("测试向量查询")
        print("=" * 60)

        test_queries = [
            "肺部结节Lung-RADS分级标准",
            "肺结节随访建议",
            "CT肺结节诊断标准"
        ]

        for query in test_queries:
            print(f"\n🔍 查询: {query}")
            results = query_knowledge(query, top_k=3)
            print(f"📊 返回 {len(results)} 条结果")

            for i, result in enumerate(results, 1):
                content = result.get("content", "")[:100] + "..." if len(result.get("content", "")) > 100 else result.get("content", "")
                print(f"  {i}. 相似度: {result.get('score', 0):.4f}")
                print(f"     来源: {result.get('source', '')}")
                print(f"     内容: {content}")

        print("\n✅ 知识库向量化完成!")

    except Exception as e:
        logger.error(f"向量化失败: {e}")
        print(f"\n❌ 向量化失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()