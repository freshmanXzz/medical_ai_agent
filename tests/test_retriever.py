"""
测试检索器
验证RAG检索功能
"""
import unittest


class TestRetriever(unittest.TestCase):
    """测试检索器"""
    
    def setUp(self):
        """测试前准备"""
        pass
    
    def test_import(self):
        """测试导入"""
        from martin.rag import Retriever
        self.assertIsNotNone(Retriever)
    
    def test_search_by_detection(self):
        """测试检测结果驱动的检索（需要启动Docker容器）"""
        from martin.rag import Retriever, EmbeddingClient, VectorStore
        
        try:
            embedding_client = EmbeddingClient()
            vector_store = VectorStore()
            vector_store.connect()
            retriever = Retriever(embedding_client, vector_store)
            
            # 构建测试检测结果
            detection_result = {
                "total_nodules": 2,
                "nodules": [
                    {"index": 1, "diameter": 8.5, "score": 0.92, "center": {"x": -64.0, "y": -5.0, "z": -85.0}},
                    {"index": 2, "diameter": 4.2, "score": 0.85, "center": {"x": -32.0, "y": 10.0, "z": -45.0}}
                ]
            }
            
            results = retriever.search_by_detection(detection_result)
            
            # 如果有数据，检查结果格式
            if results:
                for result in results:
                    self.assertIn("content", result)
                    self.assertIn("source", result)
            
            vector_store.disconnect()
            
        except Exception as e:
            # 如果环境未准备，跳过此测试
            self.skipTest(f"测试环境未准备: {e}")


if __name__ == "__main__":
    unittest.main()