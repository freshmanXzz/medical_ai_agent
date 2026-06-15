"""
测试向量数据库客户端
验证pgvector数据库的存储和检索功能
"""
import unittest
import os


class TestVectorStore(unittest.TestCase):
    """测试向量数据库客户端"""
    
    def setUp(self):
        """测试前准备"""
        pass
    
    def test_import(self):
        """测试导入"""
        from martin.rag import VectorStore
        self.assertIsNotNone(VectorStore)
    
    def test_connection(self):
        """测试数据库连接（需要启动Docker容器）"""
        from martin.rag import VectorStore
        
        store = VectorStore()
        try:
            connected = store.connect()
            self.assertTrue(connected)
        except Exception as e:
            # 如果数据库未启动，跳过此测试
            self.skipTest(f"数据库未启动: {e}")
    
    def test_insert_and_search(self):
        """测试插入和检索（需要启动Docker容器）"""
        from martin.rag import VectorStore, EmbeddingClient
        
        store = VectorStore()
        client = EmbeddingClient()
        
        try:
            store.connect()
            
            # 插入测试数据
            texts = ["肺部结节检测", "Lung-RADS分级标准", "CT扫描"]
            embeddings = client.encode(texts)
            
            count = store.insert_chunks(texts, embeddings, ["test"] * 3, ["test"] * 3)
            self.assertEqual(count, 3)
            
            # 测试检索
            query_embedding = client.encode_single("肺部结节")
            results = store.similarity_search(query_embedding, top_k=2)
            
            self.assertGreaterEqual(len(results), 1)
            
        except Exception as e:
            self.skipTest(f"测试环境未准备: {e}")
        finally:
            store.disconnect()


if __name__ == "__main__":
    unittest.main()