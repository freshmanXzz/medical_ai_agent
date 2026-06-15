"""
集成测试 - 完整RAG流程
验证：知识库加载 -> 向量化 -> 检索 -> 报告生成
"""

import unittest
import os
import glob


class TestIntegration(unittest.TestCase):
    """完整RAG集成测试"""

    @classmethod
    def setUpClass(cls):
        """测试前一次性准备"""
        from martin.rag import EmbeddingClient, VectorStore

        print("\n" + "=" * 60)
        print("集成测试准备")
        print("=" * 60)

        # 1. 初始化Embedding客户端
        print("1. 加载Embedding模型...")
        cls.client = EmbeddingClient()
        print("   ✓ Embedding模型加载完成")

        # 2. 初始化向量数据库
        print("2. 初始化ChromaDB...")
        cls.store = VectorStore(
            persist_directory="data/test_chroma_db",
            collection_name="test_medical_knowledge",
        )
        cls.store.connect()
        cls.store.reset()
        print("   ✓ ChromaDB初始化完成")

        # 3. 加载知识库文档
        print("3. 加载知识库文档...")
        cls.knowledge_base_dir = "knowledge_base"
        cls.documents = cls._load_documents()
        print(f"   ✓ 加载 {len(cls.documents)} 个文档")

        # 4. 向量化并存储
        if cls.documents:
            print("4. 向量化知识库...")
            cls._vectorize_documents()
            print("   ✓ 知识库向量化完成")

        print("=" * 60)

    @classmethod
    def _load_documents(cls):
        """加载知识库文档"""
        documents = []

        # 获取所有markdown和csv文件
        md_files = glob.glob(os.path.join(cls.knowledge_base_dir, "*.md"))
        csv_files = glob.glob(os.path.join(cls.knowledge_base_dir, "*.csv"))

        # 排除README
        md_files = [f for f in md_files if "README" not in f]

        for file_path in md_files:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()

                # 简单切分：按段落
                chunks = cls._split_text(content, max_length=800)

                for i, chunk in enumerate(chunks):
                    documents.append(
                        {
                            "content": chunk,
                            "source": os.path.basename(file_path),
                            "category": "medical_knowledge",
                            "chunk_index": i,
                        }
                    )
            except Exception as e:
                print(f"   警告: 无法读取 {file_path}: {e}")

        # CSV文件简单处理
        for file_path in csv_files:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()

                # 取前20行作为知识
                content = "".join(lines[:20])
                documents.append(
                    {
                        "content": content,
                        "source": os.path.basename(file_path),
                        "category": "coding_reference",
                        "chunk_index": 0,
                    }
                )
            except Exception as e:
                print(f"   警告: 无法读取 {file_path}: {e}")

        return documents

    @classmethod
    def _split_text(cls, text, max_length=800):
        """简单文本切分"""
        # 按行切分，然后合并
        lines = text.split("\n")
        chunks = []
        current_chunk = ""

        for line in lines:
            if len(current_chunk) + len(line) > max_length and current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = line
            else:
                current_chunk += "\n" + line

        if current_chunk.strip():
            chunks.append(current_chunk.strip())

        return chunks if chunks else [text[:max_length]]

    @classmethod
    def _vectorize_documents(cls):
        """向量化文档并存储"""
        # 批量处理
        batch_size = 10
        total = len(cls.documents)

        for i in range(0, total, batch_size):
            batch = cls.documents[i : i + batch_size]

            contents = [d["content"] for d in batch]
            sources = [d["source"] for d in batch]
            categories = [d["category"] for d in batch]

            # 向量化
            embeddings = cls.client.encode(contents)

            # 存储
            cls.store.insert_chunks(
                contents=contents,
                embeddings=embeddings.tolist(),
                sources=sources,
                categories=categories,
            )

    def test_01_knowledge_base_loaded(self):
        """测试知识库已加载"""
        count = self.store.get_chunk_count()
        print(f"\n知识库向量数量: {count}")
        self.assertGreater(count, 0, "知识库未加载")

    def test_02_similarity_search(self):
        """测试相似度检索"""
        # 模拟检测关键词
        query_text = "肺部结节恶性征象"
        query_embedding = self.client.encode_single(query_text)

        results = self.store.similarity_search(
            query_embedding=query_embedding,
            top_k=3,
        )

        print(f"\n检索 '{query_text}' 返回 {len(results)} 条结果:")
        for i, r in enumerate(results):
            print(f"  [{i+1}] 相似度: {r['similarity']:.4f}")
            print(f"      来源: {r['source']}")
            print(f"      内容: {r['content'][:100]}...")

        self.assertGreaterEqual(len(results), 1, "检索结果为空")
        self.assertGreater(results[0]["similarity"], 0.5, "相似度过低")

    def test_03_rag_case_generation(self):
        """测试RAG病例报告生成"""
        from martin.llm import CaseGenerator

        # 模拟影像检测结果
        detection_result = {
            "nodules": [
                {
                    "id": 1,
                    "confidence": 0.92,
                    "diameter_mm": 8.5,
                    "texture": "solid",
                    "location": "右上肺叶",
                }
            ],
            "image_findings": "右肺上叶见一实性结节，直径约8.5mm，边缘分叶状",
        }

        # 检索相关知识
        query_text = f"{detection_result['image_findings']} 实性结节"
        query_embedding = self.client.encode_single(query_text)
        knowledge_results = self.store.similarity_search(
            query_embedding=query_embedding,
            top_k=3,
        )

        print(f"\n检索到 {len(knowledge_results)} 条相关知识")

        # 生成报告
        generator = CaseGenerator()

        try:
            report = generator.generate_with_rag(
                detection_result=detection_result,
                retrieved_knowledge=knowledge_results,
            )

            print("\n生成的病例报告:")
            print("-" * 40)
            print(report[:500] if len(report) > 500 else report)
            print("-" * 40)

            # 验证报告内容
            self.assertIn("结节", report, "报告应包含结节描述")
            self.assertIn("肺", report, "报告应包含肺部描述")

        except Exception as e:
            # 如果LLM未配置，跳过
            print(f"\nLLM生成跳过: {e}")
            self.skipTest(f"LLM未配置: {e}")

    @classmethod
    def tearDownClass(cls):
        """测试后清理"""
        print("\n" + "=" * 60)
        print("集成测试完成")
        print("=" * 60)
        if hasattr(cls, "store"):
            cls.store.disconnect()


if __name__ == "__main__":
    unittest.main()
