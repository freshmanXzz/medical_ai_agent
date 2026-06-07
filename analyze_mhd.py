"""
MetaImage (.mhd) 文件分析脚本
用于解析医学影像头文件并提取关键信息
"""
import os
import numpy as np

def parse_mhd_file(mhd_path):
    """解析.mhd头文件"""
    metadata = {}

    with open(mhd_path, 'r') as f:
        for line in f:
            line = line.strip()
            if '=' in line:
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip()
                metadata[key] = value

    return metadata

def parse_value(value_str):
    """将字符串值转换为适当的Python类型"""
    parts = value_str.split()
    if len(parts) == 1:
        # 单个值
        try:
            if '.' in parts[0]:
                return float(parts[0])
            else:
                return int(parts[0])
        except ValueError:
            return value_str
    else:
        # 多个值（列表）
        try:
            return [float(x) if '.' in x else int(x) for x in parts]
        except ValueError:
            return parts

def analyze_mhd(mhd_path):
    """分析MetaImage文件"""
    print("=" * 70)
    print("MetaImage 文件分析")
    print("=" * 70)
    print(f"\n文件路径: {mhd_path}")
    print(f"文件大小: {os.path.getsize(mhd_path) / 1024:.2f} KB\n")

    # 解析元数据
    metadata = parse_mhd_file(mhd_path)

    # 解析所有值
    parsed = {k: parse_value(v) for k, v in metadata.items()}

    # ========== 基本信息 ==========
    print("=" * 70)
    print("【基本信息】")
    print("=" * 70)
    print(f"对象类型: {metadata.get('ObjectType', 'N/A')}")
    print(f"维度: {parsed.get('NDims', 'N/A')}D")
    print(f"数据类型: {metadata.get('ElementType', 'N/A')}")
    print(f"二进制数据: {metadata.get('BinaryData', 'N/A')}")
    print(f"字节序: {'小端 (LSB)' if metadata.get('BinaryDataByteOrderMSB') == 'False' else '大端 (MSB)'}")
    print(f"数据压缩: {metadata.get('CompressedData', 'N/A')}")

    # ========== 图像尺寸 ==========
    print("\n" + "=" * 70)
    print("【图像尺寸】")
    print("=" * 70)
    dim_size = parsed.get('DimSize', [0, 0, 0])
    if len(dim_size) == 3:
        print(f"宽度 (x): {dim_size[0]} 像素")
        print(f"高度 (y): {dim_size[1]} 像素")
        print(f"深度 (z): {dim_size[2]} 切片")
        print(f"总像素数: {dim_size[0] * dim_size[1] * dim_size[2]:,}")
        print(f"数据大小: {dim_size[0] * dim_size[1] * dim_size[2] * 2 / (1024**2):.2f} MB (假设16位)")

    # ========== 像素间距 ==========
    print("\n" + "=" * 70)
    print("【像素间距 (ElementSpacing)】")
    print("=" * 70)
    spacing = parsed.get('ElementSpacing', [0, 0, 0])
    if len(spacing) == 3:
        print(f"x方向: {spacing[0]:.6f} mm")
        print(f"y方向: {spacing[1]:.6f} mm")
        print(f"z方向: {spacing[2]:.6f} mm (层厚)")

    # ========== 物理尺寸 ==========
    print("\n" + "=" * 70)
    print("【物理尺寸】")
    print("=" * 70)
    if len(dim_size) == 3 and len(spacing) == 3:
        physical_x = dim_size[0] * spacing[0]
        physical_y = dim_size[1] * spacing[1]
        physical_z = dim_size[2] * spacing[2]
        print(f"x方向: {physical_x:.2f} mm = {physical_x/10:.2f} cm")
        print(f"y方向: {physical_y:.2f} mm = {physical_y/10:.2f} cm")
        print(f"z方向: {physical_z:.2f} mm = {physical_z/10:.2f} cm")
        print(f"扫描范围: {physical_x/10:.1f} × {physical_y/10:.1f} × {physical_z/10:.1f} cm³")

    # ========== 坐标信息 ==========
    print("\n" + "=" * 70)
    print("【坐标信息】")
    print("=" * 70)
    offset = parsed.get('Offset', [0, 0, 0])
    if len(offset) == 3:
        print(f"图像原点: ({offset[0]:.2f}, {offset[1]:.2f}, {offset[2]:.2f}) mm")

    orientation = metadata.get('AnatomicalOrientation', 'N/A')
    print(f"解剖学方向: {orientation}")
    if orientation == 'RAI':
        print("  - R (Right): x轴正方向指向右侧")
        print("  - A (Anterior): y轴正方向指向前方")
        print("  - I (Inferior): z轴正方向指向下方")
    elif orientation == 'RAS':
        print("  - R (Right): x轴正方向指向右侧")
        print("  - A (Anterior): y轴正方向指向前方")
        print("  - S (Superior): z轴正方向指向上方")

    # ========== 变换矩阵 ==========
    print("\n" + "=" * 70)
    print("【变换矩阵】")
    print("=" * 70)
    transform = parsed.get('TransformMatrix', [])
    if len(transform) == 9:
        print("变换矩阵 (3×3):")
        print(f"  [{transform[0]:.1f}  {transform[1]:.1f}  {transform[2]:.1f}]")
        print(f"  [{transform[3]:.1f}  {transform[4]:.1f}  {transform[5]:.1f}]")
        print(f"  [{transform[6]:.1f}  {transform[7]:.1f}  {transform[8]:.1f}]")

        # 检查是否为单位矩阵
        identity = [1, 0, 0, 0, 1, 0, 0, 0, 1]
        if transform == identity:
            print("  → 单位矩阵（无旋转）")

    # ========== 数据文件 ==========
    print("\n" + "=" * 70)
    print("【数据文件】")
    print("=" * 70)
    data_file = metadata.get('ElementDataFile', 'N/A')
    print(f"数据文件: {data_file}")

    # 检查数据文件是否存在
    data_path = os.path.join(os.path.dirname(mhd_path), data_file)
    if os.path.exists(data_path):
        data_size = os.path.getsize(data_path) / (1024**2)
        print(f"数据文件大小: {data_size:.2f} MB")
        print(f"数据文件状态: ✅ 存在")
    else:
        print(f"数据文件状态: ❌ 不存在")

    # ========== 与预处理参数对比 ==========
    print("\n" + "=" * 70)
    print("【与预处理参数对比】")
    print("=" * 70)
    target_spacing = [0.703125, 0.703125, 1.25]
    print("目标像素间距: [0.703125, 0.703125, 1.25] mm")
    print(f"当前像素间距: {spacing}")
    print()

    if len(spacing) == 3:
        print("重采样比例:")
        for i, (cur, tgt) in enumerate(zip(spacing, target_spacing)):
            ratio = cur / tgt
            axis = ['x', 'y', 'z'][i]
            print(f"  {axis}方向: {cur:.6f} / {tgt:.6f} = {ratio:.4f}")

        print("\n重采样后图像尺寸:")
        for i, (dim, cur, tgt) in enumerate(zip(dim_size, spacing, target_spacing)):
            new_dim = int(dim * cur / tgt)
            axis = ['宽度', '高度', '深度'][i]
            print(f"  {axis}: {dim} × {cur/tgt:.4f} ≈ {new_dim}")

    # ========== 所有元数据 ==========
    print("\n" + "=" * 70)
    print("【所有元数据】")
    print("=" * 70)
    for key, value in metadata.items():
        print(f"{key:30s} = {value}")

    print("\n" + "=" * 70)
    print("分析完成！")
    print("=" * 70)

    return metadata, parsed

if __name__ == "__main__":
    # 分析当前目录下的.mhd文件
    mhd_file = "1.3.6.1.4.1.14519.5.2.1.6279.6001.395623571499047043765181005112.mhd"

    if os.path.exists(mhd_file):
        analyze_mhd(mhd_file)
    else:
        print(f"错误: 找不到文件 {mhd_file}")
