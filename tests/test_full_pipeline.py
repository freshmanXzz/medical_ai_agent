"""
完整流程测试：从CT图像推理到病例报告生成
"""
import os
import sys
import json

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


def main():
    print("=" * 60)
    print("步骤 1/2: CT图像检测推理")
    print("=" * 60)

    from martin.inference import LungNoduleDetector

    detector = LungNoduleDetector()
    test_file = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "data",
        "1.3.6.1.4.1.14519.5.2.1.6279.6001.395623571499047043765181005112.nii.gz"
    )

    if not os.path.exists(test_file):
        print(f"错误: 测试文件不存在: {test_file}")
        return

    result = detector.detect(test_file)

    # 保存检测结果
    output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "results")
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, "detection_results.json")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=4, ensure_ascii=False)

    print(f"\n检测结果已保存到: {output_file}")
    print(f"检测到 {result['total_nodules']} 个结节")

    # 步骤2: 生成病例报告
    print()
    print("=" * 60)
    print("步骤 2/2: 生成病例报告")
    print("=" * 60)

    from martin.llm import CaseGenerator

    generator = CaseGenerator()

    # 生成简洁版报告
    print("\n--- 简洁版报告 ---")
    brief_report = generator.generate_case(result, "brief", "zh")
    print(brief_report)

    # 生成详细版报告
    print("\n--- 详细版报告 ---")
    detailed_report = generator.generate_case(result, "detailed", "zh")
    print(detailed_report)

    # 生成科研版报告
    print("\n--- 科研版报告 ---")
    research_report = generator.generate_case(result, "research", "zh")
    print(research_report)

    # 生成英文版报告
    print("\n--- 英文版报告（简洁版） ---")
    en_report = generator.generate_case(result, "brief", "en")
    print(en_report)

    # 保存报告
    case_file = os.path.join(output_dir, "case_report_detailed.md")
    with open(case_file, "w", encoding="utf-8") as f:
        f.write(detailed_report)

    case_brief = os.path.join(output_dir, "case_report_brief.md")
    with open(case_brief, "w", encoding="utf-8") as f:
        f.write(brief_report)

    case_research = os.path.join(output_dir, "case_report_research.md")
    with open(case_research, "w", encoding="utf-8") as f:
        f.write(research_report)

    print()
    print("=" * 60)
    print("完整流程测试完成!")
    print("=" * 60)
    print(f"\n检测结果: {output_file}")
    print(f"详细版报告: {case_file}")
    print(f"简洁版报告: {case_brief}")
    print(f"科研版报告: {case_research}")


if __name__ == "__main__":
    main()
