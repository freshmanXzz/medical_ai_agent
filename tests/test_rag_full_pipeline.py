"""
RAG完整流程测试：检测结果 + RAG检索 + LLM生成病例报告
"""
import os
import sys
import json

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# 导入统一日志工具
from martin.util import AppLogger

logger = AppLogger.setup_logging(__name__)


def test_rag_full_pipeline():
    """测试完整的RAG流程"""
    logger.info("=" * 60)
    logger.info("RAG完整流程测试开始")
    logger.info("=" * 60)
    
    # 步骤1: CT图像检测推理
    logger.info("步骤 1/3: CT图像检测推理")
    
    from martin.inference import LungNoduleDetector
    
    detector = LungNoduleDetector()
    test_file = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "data",
        "1.3.6.1.4.1.14519.5.2.1.6279.6001.395623571499047043765181005112.nii.gz"
    )
    
    if not os.path.exists(test_file):
        logger.error(f"测试文件不存在: {test_file}")
        return
    
    result = detector.detect(test_file)
    logger.info(f"检测完成，共检测到 {result['total_nodules']} 个结节")
    
    # 步骤2: RAG知识库检索
    logger.info("步骤 2/3: RAG知识库检索")
    
    from martin.rag import Retriever, EmbeddingClient, VectorStore
    
    # 初始化检索器
    embedding_client = EmbeddingClient()
    vector_store = VectorStore()
    vector_store.connect()
    
    retriever = Retriever(embedding_client, vector_store, top_k=5, threshold=0.7)
    
    # 根据检测结果检索相关知识
    retrieved_knowledge = retriever.search_by_detection(result)
    logger.info(f"从知识库检索到 {len(retrieved_knowledge)} 条相关知识")
    
    # 显示检索结果摘要
    for i, knowledge in enumerate(retrieved_knowledge, 1):
        content = knowledge.get("content", "")[:150] + "..." if len(knowledge.get("content", "")) > 150 else knowledge.get("content", "")
        logger.info(f"知识{i} (相似度: {knowledge.get('similarity', 0):.4f})")
        logger.info(f"   来源: {knowledge.get('source', '')}")
        logger.info(f"   内容: {content}")
    
    # 步骤3: RAG增强报告生成
    logger.info("步骤 3/3: RAG增强病例报告生成")
    
    from martin.llm import CaseGenerator
    
    # 创建报告生成器，启用RAG
    generator = CaseGenerator(use_rag=True)
    logger.info("生成RAG增强报告...")
    
    # 生成RAG增强报告
    report = generator.generate_with_rag(result, "detailed", retrieved_knowledge)
    
    logger.info("RAG增强病例报告:")
    logger.info("=" * 60)
    logger.info(report)
    logger.info("=" * 60)
    
    # 保存报告
    output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "results")
    os.makedirs(output_dir, exist_ok=True)
    report_path = os.path.join(output_dir, "rag_enhanced_report.md")
    
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    
    logger.info(f"报告已保存到: {report_path}")
    
    # 关闭连接
    vector_store.disconnect()
    
    # 验证报告中引用了知识库来源
    logger.info("验证报告质量:")
    # 检查是否包含知识引用标记（如[知识1]）或知识库关键词
    has_knowledge_ref = "[知识" in report
    has_lungrads = "Lung-RADS" in report or "Lung RADS" in report
    has_guideline = any(keyword in report for keyword in ["共识", "指南", "标准", "分级"])
    
    logger.info(f"   - 报告包含知识引用标记: {'是' if has_knowledge_ref else '否'}")
    logger.info(f"   - 报告引用Lung-RADS标准: {'是' if has_lungrads else '否'}")
    logger.info(f"   - 报告包含医学指南关键词: {'是' if has_guideline else '否'}")
    
    # 检查报告结构完整性
    required_sections = ["患者信息", "检查方法", "检测结果", "诊断结论", "建议"]
    missing_sections = [section for section in required_sections if section not in report]
    if missing_sections:
        logger.warning(f"   - 缺失的报告部分: {', '.join(missing_sections)}")
    else:
        logger.info("   - 报告结构完整: 是")
    
    # 总体评估
    is_valid = has_knowledge_ref or (has_lungrads and has_guideline)
    logger.info(f"RAG报告质量评估: {'通过' if is_valid else '未通过'}")
    
    logger.info("RAG完整流程测试完成")


if __name__ == "__main__":
    test_rag_full_pipeline()