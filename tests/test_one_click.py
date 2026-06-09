"""
Martin - Medical AI Agent 一键测试脚本

使用方法：
    python tests/test_one_click.py

此脚本会依次测试：
1. 检测推理功能
2. 病例报告生成（模板）
3. 病例报告生成（LLM，需要API密钥）
4. 结果管理器
"""
import os
import sys
from datetime import datetime

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


def test_header():
    """打印测试标题"""
    print()
    print("=" * 70)
    print("  Martin - Medical AI Agent 一键测试")
    print("=" * 70)
    print(f"  开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)


def test_inference():
    """测试1: 检测推理功能"""
    print()
    print("-" * 70)
    print("  测试 1/4: CT图像检测推理")
    print("-" * 70)
    
    from martin.inference import LungNoduleDetector
    
    # 测试文件
    test_file = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "data",
        "1.3.6.1.4.1.14519.5.2.1.6279.6001.395623571499047043765181005112.nii.gz"
    )
    
    if not os.path.exists(test_file):
        print(f"  [跳过] 测试文件不存在: {test_file}")
        return None
    
    print(f"  测试文件: {os.path.basename(test_file)}")
    
    # 初始化检测器
    detector = LungNoduleDetector()
    print(f"  检测器设备: {detector.device}")
    
    # 执行检测
    print("  开始推理...")
    result = detector.detect(test_file)
    
    # 保存结果
    saved_path = detector.save_result(result)
    print(f"  结果已保存: {os.path.basename(saved_path)}")
    
    print(f"  [通过] 检测到 {result['total_nodules']} 个结节")
    
    for i, nodule in enumerate(result['nodules'], 1):
        print(f"    结节 {i}: 置信度={nodule['score']:.4f}, 直径={nodule['diameter']:.2f}mm")
    
    return result


def test_case_generator(result):
    """测试2: 病例报告生成（模板）"""
    print()
    print("-" * 70)
    print("  测试 2/4: 病例报告生成（模板）")
    print("-" * 70)
    
    from martin.llm import CaseGenerator
    
    generator = CaseGenerator()
    
    # 生成三种报告
    report_types = ["brief", "detailed", "research"]
    saved_paths = []
    
    for report_type in report_types:
        print(f"  生成 {report_type} 报告...")
        report = generator.generate_case(result, report_type, "zh")
        saved_path = generator.save_report(report)
        saved_paths.append(saved_path)
        print(f"    已保存: {os.path.basename(saved_path)}")
    
    print(f"  [通过] 生成了 {len(report_types)} 种报告")
    return saved_paths


def test_llm_generation(result):
    """测试3: 病例报告生成（LLM）"""
    print()
    print("-" * 70)
    print("  测试 3/4: 病例报告生成（LLM）")
    print("-" * 70)
    
    # 检查API密钥
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    
    if not api_key:
        print("  [跳过] 未设置 DEEPSEEK_API_KEY 环境变量")
        print("  设置方式:")
        print("    Windows: set DEEPSEEK_API_KEY=your-key")
        print("    Linux/Mac: export DEEPSEEK_API_KEY=your-key")
        return None
    
    from martin.llm import CaseGenerator
    
    generator = CaseGenerator()
    
    print("  使用 DeepSeek LLM 生成智能报告...")
    print(f"  API端点: {generator._get_client().base_url}")
    print(f"  模型: {generator._get_client().model}")
    
    report = generator.generate_with_llm(result, "detailed")
    saved_path = generator.save_report(report)
    
    print(f"  [通过] LLM报告已保存: {os.path.basename(saved_path)}")
    print()
    print("  LLM报告预览:")
    print("  " + "-" * 50)
    lines = report.split('\n')[:20]
    for line in lines:
        print(f"  {line}")
    if len(report.split('\n')) > 20:
        print("  ...")
    print("  " + "-" * 50)
    
    return saved_path


def test_result_manager():
    """测试4: 结果管理器"""
    print()
    print("-" * 70)
    print("  测试 4/4: 结果管理器")
    print("-" * 70)
    
    from martin.util import ResultManager
    
    manager = ResultManager()
    
    # 获取今天的目录
    today_dir = manager.get_today_dir()
    print(f"  今天目录: {today_dir}")
    
    # 列出今天的结果
    files = manager.list_results()
    print(f"  今天结果数: {len(files)} 个文件")
    
    # 测试加载检测结果
    if files:
        for f in files[:3]:
            if f.endswith('.json'):
                result = manager.load_detection_result(f)
                print(f"  加载结果: {os.path.basename(f)} -> {result['total_nodules']} 个结节")
                break
    
    print(f"  [通过] 结果管理器正常工作")
    return today_dir


def test_summary():
    """打印测试总结"""
    print()
    print("=" * 70)
    print("  测试完成!")
    print("=" * 70)
    print(f"  结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    print("  结果文件位置: results/YYYY-MM-DD/")
    print("  日志文件位置: log/YYYY-MM-DD.log")
    print()
    print("=" * 70)


def main():
    """主函数"""
    test_header()
    
    try:
        # 测试1: 检测推理
        result = test_inference()
        
        if result:
            # 测试2: 病例报告生成（模板）
            test_case_generator(result)
            
            # 测试3: LLM生成
            test_llm_generation(result)
        
        # 测试4: 结果管理器
        test_result_manager()
        
        # 打印总结
        test_summary()
        
        print("  所有测试完成!")
        return True
        
    except Exception as e:
        print()
        print("=" * 70)
        print(f"  测试失败: {e}")
        print("=" * 70)
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
