"""
测试病例生成器
"""
import os
import sys
import pytest

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from martin.llm import CaseGenerator


# 模拟检测结果数据
TEST_DETECTION_RESULT = {
    "image": "test_scan.nii.gz",
    "total_nodules": 2,
    "nodules": [
        {
            "index": 1,
            "score": 0.9947,
            "center": {"x": -64.0, "y": -5.09, "z": -85.45},
            "dimensions": {"width": 4.89, "height": 4.94, "depth": 4.94},
            "diameter": 4.94
        },
        {
            "index": 2,
            "score": 0.8523,
            "center": {"x": 32.1, "y": 15.6, "z": -45.2},
            "dimensions": {"width": 6.2, "height": 5.8, "depth": 6.0},
            "diameter": 6.2
        }
    ]
}

TEST_NO_NODULES_RESULT = {
    "image": "test_scan.nii.gz",
    "total_nodules": 0,
    "nodules": []
}


class TestCaseGenerator:
    """测试CaseGenerator类"""
    
    def test_generate_brief_report_zh(self):
        """测试生成中文简洁版报告"""
        generator = CaseGenerator()
        report = generator.generate_case(TEST_DETECTION_RESULT, "brief", "zh")
        
        assert isinstance(report, str)
        assert "医学报告摘要" in report
        assert "test_scan.nii.gz" in report
        assert "检测到结节总数: 2 个" in report
        assert "结节 1" in report
    
    def test_generate_brief_report_en(self):
        """测试生成英文简洁版报告"""
        generator = CaseGenerator()
        report = generator.generate_case(TEST_DETECTION_RESULT, "brief", "en")
        
        assert isinstance(report, str)
        assert "Medical Report Summary" in report
        assert "test_scan.nii.gz" in report
        assert "Total nodules detected: 2" in report
        assert "Nodule 1" in report
    
    def test_generate_detailed_report_zh(self):
        """测试生成中文详细版报告"""
        generator = CaseGenerator()
        report = generator.generate_case(TEST_DETECTION_RESULT, "detailed", "zh")
        
        assert isinstance(report, str)
        assert "医学报告" in report
        assert "患者信息" in report
        assert "检查方法" in report
        assert "检测结果" in report
        assert "诊断结论" in report
        assert "建议" in report
    
    def test_generate_detailed_report_en(self):
        """测试生成英文详细版报告"""
        generator = CaseGenerator()
        report = generator.generate_case(TEST_DETECTION_RESULT, "detailed", "en")
        
        assert isinstance(report, str)
        assert "MEDICAL REPORT" in report
        assert "[Patient Information]" in report
        assert "[Examination Method]" in report
        assert "[Findings]" in report
        assert "[Impression]" in report
        assert "[Recommendation]" in report
    
    def test_generate_research_report_zh(self):
        """测试生成中文科研版报告"""
        generator = CaseGenerator()
        report = generator.generate_case(TEST_DETECTION_RESULT, "research", "zh")
        
        assert isinstance(report, str)
        assert "科研报告" in report
        assert "检测统计" in report
        assert "结节详细数据" in report
        assert "平均直径" in report
        assert "平均置信度" in report
    
    def test_generate_research_report_en(self):
        """测试生成英文科研版报告"""
        generator = CaseGenerator()
        report = generator.generate_case(TEST_DETECTION_RESULT, "research", "en")
        
        assert isinstance(report, str)
        assert "RESEARCH REPORT" in report
        assert "[Detection Statistics]" in report
        assert "[Detailed Nodule Data]" in report
        assert "Average diameter" in report
        assert "Average confidence" in report
    
    def test_no_nodules_report(self):
        """测试无结节情况"""
        generator = CaseGenerator()
        report = generator.generate_case(TEST_NO_NODULES_RESULT, "detailed", "zh")
        
        assert isinstance(report, str)
        assert "未检测到肺部结节" in report
    
    def test_report_type_default(self):
        """测试默认报告类型"""
        generator = CaseGenerator()
        report = generator.generate_case(TEST_DETECTION_RESULT)
        
        assert isinstance(report, str)
        assert "医学报告" in report
    
    def test_language_default(self):
        """测试默认语言"""
        generator = CaseGenerator()
        report = generator.generate_case(TEST_DETECTION_RESULT, "brief")
        
        assert isinstance(report, str)
        assert "医学报告摘要" in report
    
    def test_report_contains_nodule_info(self):
        """测试报告包含结节信息"""
        generator = CaseGenerator()
        report = generator.generate_case(TEST_DETECTION_RESULT, "detailed", "zh")
        
        # 检查是否包含结节尺寸信息
        assert "4.94" in report  # 第一个结节直径
        assert "6.2" in report   # 第二个结节直径
        
        # 检查是否包含置信度信息
        assert "0.99" in report
        assert "0.85" in report
    
    def test_generate_with_llm_fallback(self):
        """测试LLM生成失败时的降级机制"""
        generator = CaseGenerator(api_key="invalid_key")
        
        # 应该降级使用模板生成
        report = generator.generate_with_llm(TEST_DETECTION_RESULT, "brief")
        
        assert isinstance(report, str)
        assert "医学报告摘要" in report


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
