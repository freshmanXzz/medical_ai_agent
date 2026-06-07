"""
Martin - Medical AI Agent 入口文件

运行方式：
python -m martin [命令] [参数]

命令列表：
- detect: 检测肺部结节
- analyze: 分析检测结果
- report: 生成医学报告
- convert: 转换图像格式
"""
import argparse
import sys
import os

def main():
    parser = argparse.ArgumentParser(
        prog="Martin",
        description="Medical AI Agent - 肺部结节检测系统",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
    subparsers = parser.add_subparsers(dest="command", help="可用命令")
    
    # detect 命令
    detect_parser = subparsers.add_parser("detect", help="检测肺部结节")
    detect_parser.add_argument("-i", "--input", required=True, help="输入图像文件路径")
    detect_parser.add_argument("-o", "--output", default="results/detection_results.json", 
                              help="输出结果文件路径")
    detect_parser.add_argument("--device", default=None, help="运行设备 (cuda/cpu)")
    
    # analyze 命令
    analyze_parser = subparsers.add_parser("analyze", help="分析检测结果")
    analyze_parser.add_argument("-i", "--input", required=True, help="检测结果JSON文件")
    analyze_parser.add_argument("--api-key", help="DeepSeek API密钥")
    
    # report 命令
    report_parser = subparsers.add_parser("report", help="生成医学报告")
    report_parser.add_argument("-i", "--input", required=True, help="检测结果JSON文件")
    report_parser.add_argument("-o", "--output", default="results/report.txt", 
                              help="输出报告文件路径")
    report_parser.add_argument("--api-key", help="DeepSeek API密钥")
    
    # convert 命令
    convert_parser = subparsers.add_parser("convert", help="转换图像格式")
    convert_parser.add_argument("-i", "--input", required=True, help="输入文件路径")
    convert_parser.add_argument("-o", "--output", required=True, help="输出文件路径")
    
    # info 命令
    info_parser = subparsers.add_parser("info", help="查看图像信息")
    info_parser.add_argument("-i", "--input", required=True, help="输入图像文件路径")
    
    args = parser.parse_args()
    
    if args.command is None:
        parser.print_help()
        sys.exit(1)
    
    # 执行命令
    if args.command == "detect":
        run_detect(args)
    elif args.command == "analyze":
        run_analyze(args)
    elif args.command == "report":
        run_report(args)
    elif args.command == "convert":
        run_convert(args)
    elif args.command == "info":
        run_info(args)

def run_detect(args):
    """执行结节检测"""
    from martin.monai import NoduleDetector
    
    print(f"正在检测: {args.input}")
    
    detector = NoduleDetector(device=args.device)
    nodules = detector.detect(args.input)
    
    detector.save_results(nodules, args.output)
    print(f"检测完成！结果已保存到: {args.output}")
    print(f"检测到 {len(nodules)} 个结节")
    
    for nodule in nodules:
        print(f"  结节 {nodule['index']}: 置信度 {nodule['score']:.2%}, "
              f"直径 {nodule['diameter']:.2f}mm")

def run_analyze(args):
    """分析检测结果"""
    import json
    
    with open(args.input, 'r', encoding='utf-8') as f:
        report_data = json.load(f)
    
    from martin.llm import DeepSeekClient
    
    client = DeepSeekClient(api_key=args.api_key)
    analysis = client.analyze_report(report_data)
    
    print("\n=== 分析结果 ===")
    print(analysis)
    print("=" * 50)

def run_report(args):
    """生成医学报告"""
    import json
    
    with open(args.input, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    from martin.llm import DeepSeekClient
    
    client = DeepSeekClient(api_key=args.api_key)
    report = client.generate_report(data.get('nodules', []))
    
    with open(args.output, 'w', encoding='utf-8') as f:
        f.write(report)
    
    print(f"报告已生成并保存到: {args.output}")

def run_convert(args):
    """转换图像格式"""
    from martin.monai import ImageProcessor
    
    if args.input.endswith('.mhd') and (args.output.endswith('.nii.gz') or args.output.endswith('.nii')):
        ImageProcessor.metaimage_to_nifti(args.input, args.output)
        print(f"转换完成！已保存到: {args.output}")
    else:
        print("不支持的转换格式")

def run_info(args):
    """查看图像信息"""
    from martin.monai import ImageProcessor
    
    info = ImageProcessor.get_image_info(args.input)
    
    print("=== 图像信息 ===")
    print(f"尺寸: {info['dim_size']}")
    print(f"像素间距: {info['spacing']} mm")
    print(f"总像素数: {info['voxel_count']:,}")
    print(f"数据范围: [{info['data_range'][0]}, {info['data_range'][1]}]")

if __name__ == "__main__":
    main()
