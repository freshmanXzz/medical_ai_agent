"""
测试RAG报告生成
验证CaseGenerator的RAG增强功能
"""
import unittest
import json


class TestRagReport(unittest.TestCase):
    """测试RAG报告生成"""
    
    def setUp(self):
        """测试前准备"""
        pass
    
    def test_import(self):
        """测试导入"""
        from martin.llm import CaseGenerator
        self.assertIsNotNone(CaseGenerator)
    
    def test_case_generator_with_rag(self):
        """测试RAG增强报告生成（需要启动Docker容器和API密钥）"""
        from martin.llm import CaseGenerator
        
        # 测试CaseGenerator初始化
        generator = CaseGenerator(use_rag=False)
        self.assertIsNotNone(generator)
        
        # 测试RAG模式初始化
        generator_rag = CaseGenerator(use_rag=True)
        self.assertTrue(generator_rag._use_rag)
    
    def test_generate_case_template(self):
        """测试模板报告生成"""
        from martin.llm import CaseGenerator
        
        generator = CaseGenerator()
        
        detection_result = {
            "image": "test.nii.gz",
            "total_nodules": 2,
            "nodules": [
                {"index": 1, "diameter": 8.5, "score": 0.92, 
                 "center": {"x": -64.0, "y": -5.0, "z": -85.0},
                 "dimensions": {"width": 8.0, "height": 8.5, "depth": 9.0}},
                {"index": 2, "diameter": 4.2, "score": 0.85,
                 "center": {"x": -32.0, "y": 10.0, "z": -45.0},
                 "dimensions": {"width": 4.0, "height": 4.2, "depth": 4.5}}
            ]
        }
        
        report = generator.generate_case(detection_result, "detailed", "zh")
        
        self.assertIsInstance(report, str)
        self.assertGreater(len(report), 0)
        self.assertIn("医学报告", report)
    
    def test_rag_prompt_contains_knowledge_requirement(self):
        """测试RAG提示词包含强制知识库引用要求"""
        from martin.llm import CaseGenerator
        
        generator = CaseGenerator(use_rag=True)
        
        detection_result = {
            "total_nodules": 1,
            "nodules": [{"index": 1, "diameter": 5.0, "score": 0.85,
                        "center": {"x": 0, "y": 0, "z": 0},
                        "dimensions": {"width": 5, "height": 5, "depth": 5}}]
        }
        
        # 测试提示词构建
        context = "测试知识库内容"
        prompt = generator._build_rag_prompt(detection_result, "detailed", context)
        
        self.assertIn("必须完全按照知识库里面的资料来生成病例报告", prompt)


if __name__ == "__main__":
    unittest.main()