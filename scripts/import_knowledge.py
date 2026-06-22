"""
医学知识库向量化导入脚本

将knowledge_base目录下的文档向量化后存储到向量数据库
支持Markdown和CSV格式文档
"""
import os
import sys
from typing import List

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from martin.rag import DocumentLoader, EmbeddingClient, VectorStore
from martin.util import AppLogger

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
    # 设置默认路径
    if knowledge_dir is None:
        knowledge_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "knowledge_base")
    
    if persist_dir is None:
        persist_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ChromaDB")
    
    # 检查知识库目录
    if not os.path.isdir(knowledge_dir):
        logger.error(f"知识库目录不存在: {knowledge_dir}")
        raise FileNotFoundError(f"知识库目录不存在: {knowledge_dir}")
    
    logger.info(f"开始导入知识库: {knowledge_dir}")
    logger.info(f"向量数据库存储目录: {persist_dir}")
    
    # 初始化文档加载器
    loader = DocumentLoader(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    
    # 加载目录下所有文档
    logger.info("加载知识库文档...")
    document_chunks = loader.load_directory(knowledge_dir)
    logger.info(f"共加载 {len(document_chunks)} 个文档切分")
    
    if not document_chunks:
        logger.warning("未加载到任何文档")
        return 0
    
    # 初始化Embedding客户端
    logger.info("初始化Embedding客户端...")
    embedding_client = EmbeddingClient()
    
    # 向量化所有文档切分
    logger.info("开始向量化文档...")
    contents = [chunk.content for chunk in document_chunks]
    embeddings = embedding_client.encode(contents)
    logger.info(f"向量化完成，生成 {len(embeddings)} 个向量")
    
    # 准备元数据
    sources = [chunk.source for chunk in document_chunks]
    categories = [chunk.category for chunk in document_chunks]
    metadatas = [chunk.metadata for chunk in document_chunks]
    
    # 初始化向量数据库
    logger.info("初始化向量数据库...")
    vector_store = VectorStore(persist_directory=persist_dir)
    if not vector_store.connect():
        logger.error("无法连接到向量数据库")
        raise ConnectionError("无法连接到向量数据库")
    
    # 插入向量数据
    logger.info("插入向量数据到数据库...")
    inserted_count = vector_store.insert_chunks(
        contents=contents,
        embeddings=embeddings.tolist(),
        sources=sources,
        categories=categories,
        metadata=metadatas
    )
    
    logger.info(f"成功导入 {inserted_count} 条向量记录")
    
    # 关闭连接
    vector_store.disconnect()
    
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
    from martin.rag import Retriever
    
    logger.info(f"查询知识库: {query}")
    
    # 初始化检索器
    embedding_client = EmbeddingClient()
    vector_store = VectorStore()
    vector_store.connect()
    
    retriever = Retriever(embedding_client, vector_store, top_k=top_k)
    
    # 执行查询
    results = retriever.search(query)
    
    # 关闭连接
    vector_store.disconnect()
    
    return results


def main():
    """主函数"""
    print("=" * 60)
    print("医学知识库向量化工具")
    print("=" * 60)
    
    try:
        # 导入知识库
        inserted_count = import_knowledge_to_vector_db()
        
        print(f"\n✅ 成功导入 {inserted_count} 条向量记录")
        print(f"📁 知识库目录: knowledge_base/")
        print(f"💾 向量数据库: data/chroma_db/")
        
        # 测试查询
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
                print(f"  {i}. 相似度: {result.get('similarity', 0):.4f}")
                print(f"     来源: {result.get('source', '')}")
                print(f"     内容: {content}")
        
        print("\n✅ 知识库向量化完成!")
        
    except Exception as e:
        logger.error(f"向量化失败: {e}")
        print(f"\n❌ 向量化失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()