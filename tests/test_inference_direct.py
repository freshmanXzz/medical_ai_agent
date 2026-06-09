"""
直接测试推理功能，不使用unittest框架
"""
import os
import sys
from datetime import datetime

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from martin.inference import LungNoduleDetector, detect_nodules, logger

def main():
    print("=" * 60)
    print("肺部结节检测 - 直接推理测试")
    print("=" * 60)
    print(f"开始时间: {datetime.now()}")
    
    # 测试文件
    test_file = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "data",
        "1.3.6.1.4.1.14519.5.2.1.6279.6001.395623571499047043765181005112.nii.gz"
    )
    
    if not os.path.exists(test_file):
        print(f"错误: 测试文件不存在: {test_file}")
        return
    
    print(f"\n测试文件: {test_file}")
    print("\n开始推理...")
    print("-" * 60)
    
    try:
        # 使用便捷函数
        result = detect_nodules(test_file)
        
        print("\n" + "=" * 60)
        print("推理完成!")
        print("=" * 60)
        print(f"图像: {result['image']}")
        print(f"检测到结节数: {result['total_nodules']}")
        
        if result['nodules']:
            print(f"\n{len(result['nodules'])} 个结节详情:")
            for i, nodule in enumerate(result['nodules'], 1):
                print(f"\n结节 {i}:")
                print(f"  置信度: {nodule['score']:.4f}")
                print(f"  直径: {nodule['diameter']:.2f} mm")
                print(f"  中心位置: ({nodule['center']['x']:.2f}, {nodule['center']['y']:.2f}, {nodule['center']['z']:.2f})")
                print(f"  尺寸: {nodule['dimensions']['width']:.2f} x {nodule['dimensions']['height']:.2f} x {nodule['dimensions']['depth']:.2f}")
        
        print(f"\n结束时间: {datetime.now()}")
        
    except Exception as e:
        logger.error(f"推理失败: {e}")
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
