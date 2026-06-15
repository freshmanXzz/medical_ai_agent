"""
RAG完整流程测试：检测结果 + RAG检索 + LLM生成病例报告
"""
import os
import sys
import json

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


def test_rag_full_pipeline():
    """测试完整的RAG流程"""
    print("=" * 60)
    print("RAG完整流程测试")
    print("=" * 60)
    
    # 步骤1: CT图像检测推理
    print("\n步骤 1/3: CT图像检测推理")
    print("-" * 60)
    
    from martin.inference import LungNoduleDetector
    
    detector = LungNoduleDetector()
    test_file = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "data",
        "1.3.6.1.4.1.14519.5.2.1.6279.6001.395623571499047043765181005112.nii.gz"
    )
    
    if not os.path.exists(test_file):
        print(f"❌ 测试文件不存在: {test_file}")
        return
    
    result = detector.detect(test_file)
    print(f"✅ 检测完成，共检测到 {result['total_nodules']} 个结节")
    
    # 步骤2: RAG知识库检索
    print("\n步骤 2/3: RAG知识库检索")
    print("-" * 60)
    
    from martin.rag import Retriever, EmbeddingClient, VectorStore
    
    # 初始化检索器
    embedding_client = EmbeddingClient()
    vector_store = VectorStore()
    vector_store.connect()
    
    retriever = Retriever(embedding_client, vector_store, top_k=5, threshold=0.7)
    
    # 根据检测结果检索相关知识
    retrieved_knowledge = retriever.search_by_detection(result)
    print(f"✅ 从知识库检索到 {len(retrieved_knowledge)} 条相关知识")
    
    # 显示检索结果摘要
    for i, knowledge in enumerate(retrieved_knowledge, 1):
        content = knowledge.get("content", "")[:150] + "..." if len(knowledge.get("content", "")) > 150 else knowledge.get("content", "")
        print(f"\n📚 知识{i} (相似度: {knowledge.get('similarity', 0):.4f})")
        print(f"   来源: {knowledge.get('source', '')}")
        print(f"   内容: {content}")
    
    # 步骤3: RAG增强报告生成
    print("\n步骤 3/3: RAG增强病例报告生成")
    print("-" * 60)
    
    from martin.llm import CaseGenerator
    
    # 创建报告生成器，启用RAG
    generator = CaseGenerator(use_rag=True)
    
    # 生成RAG增强报告
    print("\n🔄 生成RAG增强报告...")
    report = generator.generate_with_rag(result, "detailed", retrieved_knowledge)
    
    print("\n📝 RAG增强病例报告:")
    print("=" * 60)
    print(report)
    print("=" * 60)
    
    # 保存报告
    output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "results")
    os.makedirs(output_dir, exist_ok=True)
    report_path = os.path.join(output_dir, "rag_enhanced_report.md")
    
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    
    print(f"\n✅ 报告已保存到: {report_path}")
    
    # 关闭连接
    vector_store.disconnect()
    
    # 验证报告中引用了知识库来源
    print("\n🔍 验证报告质量:")
    has_source_reference = any(source in report for source in [k.get("source", "") for k in retrieved_knowledge])
    print(f"   - 报告是否引用知识库来源: {'✅ 是' if has_source_reference else '❌ 否'}")
    
    # 检查报告结构完整性
    required_sections = ["患者信息", "检查方法", "检测结果", "诊断结论", "建议"]
    missing_sections = [section for section in required_sections if section not in report]
    if missing_sections:
        print(f"   - 缺失的报告部分: {', '.join(missing_sections)}")
    else:
        print(f"   - 报告结构完整: ✅")


if __name__ == "__main__":
    test_rag_full_pipeline()