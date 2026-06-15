"""
测试Embedding客户端
验证本地bge-small-zh-v1.5模型的向量化功能
"""
import unittest
import numpy as np


class TestEmbeddingClient(unittest.TestCase):
    """测试Embedding客户端"""
    
    def setUp(self):
        """测试前准备"""
        # 延迟导入以避免测试时加载模型
        pass
    
    def test_import(self):
        """测试导入"""
        from martin.rag import EmbeddingClient
        self.assertIsNotNone(EmbeddingClient)
    
    def test_embedding_dimension(self):
        """测试向量维度是否为512"""
        from martin.rag import EmbeddingClient
        
        client = EmbeddingClient()
        self.assertEqual(client.get_embedding_dimension(), 512)
    
    def test_encode_single(self):
        """测试单文本向量化"""
        from martin.rag import EmbeddingClient
        
        client = EmbeddingClient()
        embedding = client.encode_single("这是一段测试文本")
        
        self.assertIsInstance(embedding, np.ndarray)
        self.assertEqual(embedding.shape, (512,))
    
    def test_encode_batch(self):
        """测试批量向量化"""
        from martin.rag import EmbeddingClient
        
        client = EmbeddingClient()
        texts = ["文本1", "文本2", "文本3"]
        embeddings = client.encode(texts)
        
        self.assertIsInstance(embeddings, np.ndarray)
        self.assertEqual(embeddings.shape, (3, 512))
    
    def test_embedding_normalization(self):
        """测试向量归一化"""
        from martin.rag import EmbeddingClient
        
        client = EmbeddingClient()
        embedding = client.encode_single("测试文本")
        
        # 检查向量是否归一化（L2范数接近1）
        norm = np.linalg.norm(embedding)
        self.assertAlmostEqual(norm, 1.0, places=5)


if __name__ == "__main__":
    unittest.main()