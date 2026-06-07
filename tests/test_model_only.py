"""
快速验证：仅测试模型和权重加载，不执行完整推理
"""
import os
import sys
import torch
from datetime import datetime

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

print("=" * 60)
print("肺部结节检测 - 快速验证 (仅模型加载，不推理)")
print("=" * 60)
print(f"开始时间: {datetime.now()}")

print("\n" + "=" * 60)
print("1. 检查模型文件")
print("=" * 60)

model_path = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "model", "lung_nodule_ct_detection-0.6.8", 
    "lung_nodule_ct_detection-0.6.8", "models", "model.pt"
)

print(f"模型路径: {model_path}")

if os.path.exists(model_path):
    file_size = os.path.getsize(model_path) / (1024 * 1024)
    print(f"[OK] 模型文件存在: {file_size:.2f} MB")
else:
    print(f"[ERROR] 模型文件不存在！")
    sys.exit(1)

print("\n" + "=" * 60)
print("2. 测试依赖导入")
print("=" * 60)

try:
    import torch
    print(f"[OK] PyTorch 版本: {torch.__version__}")
    
    if torch.cuda.is_available():
        print(f"[OK] CUDA 可用: {torch.cuda.get_device_name(0)}")
        print(f"   显存: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.2f} GB")
    else:
        print(f"[WARN] CUDA 不可用，将使用CPU")
        
except Exception as e:
    print(f"[ERROR] PyTorch 导入失败: {e}")
    sys.exit(1)

try:
    import monai
    print(f"[OK] MONAI 版本: {monai.__version__}")
except Exception as e:
    print(f"[ERROR] MONAI 导入失败: {e}")
    sys.exit(1)

try:
    import torchvision
    print(f"[OK] torchvision 版本: {torchvision.__version__}")
except Exception as e:
    print(f"[WARN] torchvision 未找到: {e}")
    print("   这在某些情况下可能是可接受的")

print("\n" + "=" * 60)
print("3. 尝试加载权重文件")
print("=" * 60)

try:
    device = torch.device('cuda:0' if torch.cuda.is_available() else 'cpu')
    print(f"使用设备: {device}")
    
    checkpoint = torch.load(model_path, map_location=device, weights_only=False)
    
    if isinstance(checkpoint, dict):
        print(f"[OK] 权重加载成功，是一个字典")
        print(f"   键: {list(checkpoint.keys())[:10]}...")
        
        if 'state_dict' in checkpoint:
            print(f"   包含 state_dict")
    else:
        print(f"[OK] 权重加载成功，类型: {type(checkpoint)}")
        
except Exception as e:
    print(f"[ERROR] 权重加载失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 60)
print("4. 快速测试 LungNoduleDetector 初始化")
print("=" * 60)

try:
    from martin.inference import LungNoduleDetector
    
    print("正在初始化检测器...")
    detector = LungNoduleDetector()
    
    print(f"[OK] 检测器初始化成功！")
    print(f"   设备: {detector.device}")
    
except Exception as e:
    print(f"[ERROR] 检测器初始化失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 60)
print("[SUCCESS] 所有验证通过！")
print("=" * 60)
print(f"完成时间: {datetime.now()}")
print("\n提示: 完整推理需要较长时间处理3D图像，请耐心等待")
