"""
推理模块使用示例
展示如何使用 LungNoduleDetector 类进行肺部结节检测
"""
import os
import sys

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(__file__))

from martin.inference import LungNoduleDetector, detect_nodules


def example_1_basic_usage():
    """示例1: 基本用法 - 使用类接口"""
    print("=" * 60)
    print("示例1: 基本用法 - 使用类接口")
    print("=" * 60)
    
    # 初始化检测器（使用默认模型路径）
    detector = LungNoduleDetector()
    
    # 检测图像
    image_path = os.path.join("data", "1.3.6.1.4.1.14519.5.2.1.6279.6001.395623571499047043765181005112.nii.gz")
    
    if os.path.exists(image_path):
        result = detector.detect(image_path)
        
        # 使用检测结果
        print(f"\n检测结果摘要:")
        print(f"  图像: {result['image']}")
        print(f"  结节数量: {result['total_nodules']}")
        
        # 对结果进行进一步处理
        if result['nodules']:
            # 获取置信度最高的结节
            top_nodule = max(result['nodules'], key=lambda x: x['score'])
            print(f"\n  置信度最高的结节:")
            print(f"    置信度: {top_nodule['score']:.4f}")
            print(f"    直径: {top_nodule['diameter']:.2f}mm")
    else:
        print(f"示例图像不存在: {image_path}")


def example_2_convenience_function():
    """示例2: 使用便捷函数"""
    print("\n" + "=" * 60)
    print("示例2: 使用便捷函数")
    print("=" * 60)
    
    image_path = os.path.join("data", "1.3.6.1.4.1.14519.5.2.1.6279.6001.395623571499047043765181005112.nii.gz")
    
    if os.path.exists(image_path):
        # 直接调用函数，一行代码完成检测
        result = detect_nodules(image_path)
        
        print(f"\n检测结果:")
        print(f"  共发现 {result['total_nodules']} 个结节")
    else:
        print(f"示例图像不存在: {image_path}")


def example_3_auto_detection():
    """示例3: 自动化检测"""
    print("\n" + "=" * 60)
    print("示例3: 自动化检测（设备+模型自动选择）")
    print("=" * 60)
    
    # 完全自动化，不需要任何参数
    detector = LungNoduleDetector()
    print("检测器已自动选择最佳设备和模型路径")


def example_4_batch_detection():
    """示例4: 批量检测"""
    print("\n" + "=" * 60)
    print("示例4: 批量检测")
    print("=" * 60)
    
    detector = LungNoduleDetector()
    
    # 准备图像列表
    image_dir = "data"
    image_paths = []
    
    if os.path.exists(image_dir):
        # 查找所有 .nii.gz 文件
        for filename in os.listdir(image_dir):
            if filename.endswith(".nii.gz"):
                image_paths.append(os.path.join(image_dir, filename))
    
    if image_paths:
        print(f"找到 {len(image_paths)} 张图像")
        
        # 批量检测
        results = detector.detect_batch(image_paths)
        
        # 输出结果
        total_nodules = 0
        for result in results:
            if 'error' in result:
                print(f"  {result['image']}: 错误 - {result['error']}")
            else:
                print(f"  {result['image']}: {result['total_nodules']} 个结节")
                total_nodules += result['total_nodules']
        
        print(f"\n总计: {total_nodules} 个结节")
    else:
        print("没有找到图像文件")


def example_5_logging_config():
    """示例5: 配置日志"""
    print("\n" + "=" * 60)
    print("示例5: 配置日志")
    print("=" * 60)
    
    import logging
    
    # 配置日志级别和输出
    logging.basicConfig(
        level=logging.DEBUG,  # 设置为 DEBUG 以获得更详细的日志
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            # 可以添加文件处理器
            # logging.FileHandler('inference.log')
        ]
    )
    
    # 初始化检测器，会看到更详细的日志
    detector = LungNoduleDetector()
    print("日志配置完成")


if __name__ == "__main__":
    print("肺部结节检测推理模块使用示例\n")
    
    # 运行各个示例
    example_1_basic_usage()
    
    try:
        example_2_convenience_function()
    except Exception as e:
        print(f"示例2执行失败: {e}")
    
    try:
        example_3_auto_detection()
    except Exception as e:
        print(f"示例3执行失败: {e}")
    
    try:
        example_4_batch_detection()
    except Exception as e:
        print(f"示例4执行失败: {e}")
    
    try:
        example_5_logging_config()
    except Exception as e:
        print(f"示例5执行失败: {e}")
    
    print("\n" + "=" * 60)
    print("所有示例执行完毕")
    print("=" * 60)
