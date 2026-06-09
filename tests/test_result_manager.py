"""
测试结果管理器
"""
import os
import sys
import json
from datetime import datetime

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from martin.util import ResultManager, get_result_manager


def test_result_manager():
    """测试结果管理器功能"""
    print("=" * 60)
    print("测试结果管理器")
    print("=" * 60)
    
    # 创建结果管理器
    manager = ResultManager()
    print(f"结果目录: {manager._base_dir}")
    
    # 测试获取今天的目录
    today_dir = manager.get_today_dir()
    print(f"今天目录: {today_dir}")
    assert os.path.exists(today_dir), "今天目录应该存在"
    
    # 测试生成文件名
    filename = manager.generate_filename("detection", ".json")
    print(f"生成文件名: {filename}")
    assert filename.startswith("detection_"), "文件名应该以detection_开头"
    assert filename.endswith(".json"), "文件名应该以.json结尾"
    
    # 测试保存检测结果
    test_result = {
        "image": "test.nii.gz",
        "nodules": [
            {
                "index": 1,
                "score": 0.95,
                "center": {"x": 0, "y": 0, "z": 0},
                "dimensions": {"width": 5, "height": 5, "depth": 5},
                "diameter": 5.0
            }
        ],
        "total_nodules": 1
    }
    
    saved_path = manager.save_detection_result(test_result)
    print(f"检测结果已保存到: {saved_path}")
    assert os.path.exists(saved_path), "检测结果文件应该存在"
    
    # 验证保存的内容
    with open(saved_path, 'r', encoding='utf-8') as f:
        loaded = json.load(f)
    assert loaded["total_nodules"] == 1, "加载的数据应该正确"
    
    # 测试保存报告
    test_report = "# 测试报告\n\n这是一个测试报告。"
    report_path = manager.save_report(test_report)
    print(f"报告已保存到: {report_path}")
    assert os.path.exists(report_path), "报告文件应该存在"
    
    # 测试列出结果
    files = manager.list_results()
    print(f"今天的结果文件: {len(files)} 个")
    assert len(files) >= 2, "应该至少有2个文件"
    
    # 测试加载检测结果
    loaded_result = manager.load_detection_result(saved_path)
    assert loaded_result["total_nodules"] == 1, "加载的检测结果应该正确"
    
    print("\n" + "=" * 60)
    print("所有测试通过!")
    print("=" * 60)
    
    return True


def test_inference_with_date_dir():
    """测试推理模块的日期目录保存功能"""
    print("\n" + "=" * 60)
    print("测试推理模块日期目录保存")
    print("=" * 60)
    
    from martin.inference import LungNoduleDetector
    
    # 检查测试文件
    test_file = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "data",
        "1.3.6.1.4.1.14519.5.2.1.6279.6001.395623571499047043765181005112.nii.gz"
    )
    
    if not os.path.exists(test_file):
        print(f"跳过测试：测试文件不存在")
        return False
    
    print(f"测试文件: {test_file}")
    
    # 初始化检测器
    detector = LungNoduleDetector()
    
    # 执行检测
    print("执行检测...")
    result = detector.detect(test_file)
    print(f"检测到 {result['total_nodules']} 个结节")
    
    # 保存结果（使用日期目录）
    saved_path = detector.save_result(result)
    print(f"结果已保存到: {saved_path}")
    
    # 验证保存路径包含日期目录
    today = datetime.now().strftime("%Y-%m-%d")
    assert today in saved_path, f"保存路径应该包含今天的日期: {today}"
    
    print("\n" + "=" * 60)
    print("推理模块测试通过!")
    print("=" * 60)
    
    return True


def test_case_generator_with_date_dir():
    """测试病例生成器的日期目录保存功能"""
    print("\n" + "=" * 60)
    print("测试病例生成器日期目录保存")
    print("=" * 60)
    
    from martin.llm import CaseGenerator
    
    # 创建测试数据
    test_result = {
        "image": "test.nii.gz",
        "nodules": [
            {
                "index": 1,
                "score": 0.95,
                "center": {"x": 0, "y": 0, "z": 0},
                "dimensions": {"width": 5, "height": 5, "depth": 5},
                "diameter": 5.0
            }
        ],
        "total_nodules": 1
    }
    
    # 初始化生成器
    generator = CaseGenerator()
    
    # 生成报告
    report = generator.generate_case(test_result, "detailed", "zh")
    
    # 保存报告（使用日期目录）
    saved_path = generator.save_report(report)
    print(f"报告已保存到: {saved_path}")
    
    # 验证保存路径包含日期目录
    today = datetime.now().strftime("%Y-%m-%d")
    assert today in saved_path, f"保存路径应该包含今天的日期: {today}"
    
    # 测试便捷函数
    report2, path2 = CaseGenerator.generate_and_save(
        test_result,
        report_type="brief",
        language="en"
    )
    print(f"便捷函数报告已保存到: {path2}")
    
    print("\n" + "=" * 60)
    print("病例生成器测试通过!")
    print("=" * 60)
    
    return True


if __name__ == "__main__":
    try:
        # 测试结果管理器
        test_result_manager()
        
        # 测试推理模块
        test_inference_with_date_dir()
        
        # 测试病例生成器
        test_case_generator_with_date_dir()
        
        print("\n" + "=" * 60)
        print("所有测试完成!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n测试失败: {e}")
        import traceback
        traceback.print_exc()
