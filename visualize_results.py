import os
import json
import numpy as np
import nibabel as nib
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from mpl_toolkits.mplot3d import Axes3D

print("=" * 60)
print("肺部结节检测结果可视化")
print("=" * 60)

# 加载检测结果
with open("results/detection_results.json", "r") as f:
    results = json.load(f)

# 加载原始CT图像
data_path = os.path.join("data", "1.3.6.1.4.1.14519.5.2.1.6279.6001.395623571499047043765181005112.nii.gz")
nii_img = nib.load(data_path)
ct_data = nii_img.get_fdata()
affine = nii_img.affine

print(f"CT图像形状: {ct_data.shape}")
print(f"检测到结节数量: {results[0]['total_nodules']}")

# 创建输出目录
output_dir = "visualization"
os.makedirs(output_dir, exist_ok=True)

# 可视化方案1: 在结节中心位置的三个正交切片上绘制检测框
fig, axes = plt.subplots(2, 3, figsize=(18, 12))
fig.suptitle('肺部结节检测结果可视化', fontsize=16, fontweight='bold')

nodules = results[0]['nodules']

for idx, nodule in enumerate(nodules):
    # 结节中心坐标（世界坐标系）
    center_world = np.array([nodule['center']['x'], nodule['center']['y'], nodule['center']['z']])
    
    # 结节尺寸
    width = nodule['dimensions']['width']
    height = nodule['dimensions']['height']
    depth = nodule['dimensions']['depth']
    
    # 将世界坐标转换为图像坐标
    # 逆仿射变换矩阵
    inv_affine = np.linalg.inv(affine)
    center_img = inv_affine @ np.append(center_world, 1)
    center_img = center_img[:3].astype(int)
    
    print(f"\n结节 {idx + 1}:")
    print(f"  世界坐标: ({nodule['center']['x']:.2f}, {nodule['center']['y']:.2f}, {nodule['center']['z']:.2f})")
    print(f"  图像坐标: ({center_img[0]}, {center_img[1]}, {center_img[2]})")
    print(f"  尺寸: {width:.2f} x {height:.2f} x {depth:.2f} mm")
    print(f"  置信度: {nodule['score']:.4f}")
    
    # 确保坐标在图像范围内
    z_slice = np.clip(center_img[2], 0, ct_data.shape[2] - 1)
    y_slice = np.clip(center_img[1], 0, ct_data.shape[1] - 1)
    x_slice = np.clip(center_img[0], 0, ct_data.shape[0] - 1)
    
    # 绘制轴向切片 (Axial - Z轴)
    ax = axes[idx, 0]
    axial_slice = ct_data[:, :, z_slice].T
    im = ax.imshow(axial_slice, cmap='gray', origin='lower', 
                   vmin=-1000, vmax=400)
    ax.set_title(f'结节{idx+1} - 轴向切片 (Z={z_slice})\n置信度: {nodule["score"]:.4f}', fontsize=12)
    ax.set_xlabel('X')
    ax.set_ylabel('Y')
    plt.colorbar(im, ax=ax, label='HU')
    
    # 绘制冠状切片 (Coronal - Y轴)
    ax = axes[idx, 1]
    coronal_slice = ct_data[:, y_slice, :].T
    im = ax.imshow(coronal_slice, cmap='gray', origin='lower',
                   vmin=-1000, vmax=400)
    ax.set_title(f'结节{idx+1} - 冠状切片 (Y={y_slice})\n置信度: {nodule["score"]:.4f}', fontsize=12)
    ax.set_xlabel('Z')
    ax.set_ylabel('X')
    plt.colorbar(im, ax=ax, label='HU')
    
    # 绘制矢状切片 (Sagittal - X轴)
    ax = axes[idx, 2]
    sagittal_slice = ct_data[x_slice, :, :].T
    im = ax.imshow(sagittal_slice, cmap='gray', origin='lower',
                   vmin=-1000, vmax=400)
    ax.set_title(f'结节{idx+1} - 矢状切片 (X={x_slice})\n置信度: {nodule["score"]:.4f}', fontsize=12)
    ax.set_xlabel('Z')
    ax.set_ylabel('Y')
    plt.colorbar(im, ax=ax, label='HU')

plt.tight_layout()
output_path = os.path.join(output_dir, "nodule_slices.png")
plt.savefig(output_path, dpi=150, bbox_inches='tight')
print(f"\n切片可视化已保存到: {output_path}")
plt.close()

# 可视化方案2: 最大密度投影 (MIP) 显示
fig, axes = plt.subplots(1, 3, figsize=(18, 6))
fig.suptitle('肺部结节检测 - 最大密度投影 (MIP)', fontsize=16, fontweight='bold')

# 轴向MIP
ax = axes[0]
mip_axial = np.max(ct_data, axis=2).T
ax.imshow(mip_axial, cmap='gray', origin='lower', vmin=-1000, vmax=400)
ax.set_title('轴向MIP', fontsize=12)
ax.set_xlabel('X')
ax.set_ylabel('Y')

# 在MIP上标注结节位置
for idx, nodule in enumerate(nodules):
    center_world = np.array([nodule['center']['x'], nodule['center']['y'], nodule['center']['z']])
    inv_affine = np.linalg.inv(affine)
    center_img = inv_affine @ np.append(center_world, 1)
    center_img = center_img[:3]
    
    # 绘制结节中心点
    ax.plot(center_img[0], center_img[1], 'r*', markersize=15, label=f'结节{idx+1}')
    ax.annotate(f'结节{idx+1}\n({nodule["score"]:.3f})', 
                xy=(center_img[0], center_img[1]),
                xytext=(center_img[0]+30, center_img[1]+30),
                fontsize=10, color='red',
                arrowprops=dict(arrowstyle='->', color='red', lw=2))

# 冠状MIP
ax = axes[1]
mip_coronal = np.max(ct_data, axis=1).T
ax.imshow(mip_coronal, cmap='gray', origin='lower', vmin=-1000, vmax=400)
ax.set_title('冠状MIP', fontsize=12)
ax.set_xlabel('Z')
ax.set_ylabel('X')

for idx, nodule in enumerate(nodules):
    center_world = np.array([nodule['center']['x'], nodule['center']['y'], nodule['center']['z']])
    inv_affine = np.linalg.inv(affine)
    center_img = inv_affine @ np.append(center_world, 1)
    center_img = center_img[:3]
    
    ax.plot(center_img[2], center_img[0], 'r*', markersize=15)
    ax.annotate(f'结节{idx+1}', 
                xy=(center_img[2], center_img[0]),
                xytext=(center_img[2]+10, center_img[0]+10),
                fontsize=10, color='red',
                arrowprops=dict(arrowstyle='->', color='red', lw=2))

# 矢状MIP
ax = axes[2]
mip_sagittal = np.max(ct_data, axis=0).T
ax.imshow(mip_sagittal, cmap='gray', origin='lower', vmin=-1000, vmax=400)
ax.set_title('矢状MIP', fontsize=12)
ax.set_xlabel('Z')
ax.set_ylabel('Y')

for idx, nodule in enumerate(nodules):
    center_world = np.array([nodule['center']['x'], nodule['center']['y'], nodule['center']['z']])
    inv_affine = np.linalg.inv(affine)
    center_img = inv_affine @ np.append(center_world, 1)
    center_img = center_img[:3]
    
    ax.plot(center_img[2], center_img[1], 'r*', markersize=15)
    ax.annotate(f'结节{idx+1}', 
                xy=(center_img[2], center_img[1]),
                xytext=(center_img[2]+10, center_img[1]+10),
                fontsize=10, color='red',
                arrowprops=dict(arrowstyle='->', color='red', lw=2))

plt.tight_layout()
output_path = os.path.join(output_dir, "mip_visualization.png")
plt.savefig(output_path, dpi=150, bbox_inches='tight')
print(f"MIP可视化已保存到: {output_path}")
plt.close()

# 可视化方案3: 结节区域放大显示
fig, axes = plt.subplots(2, 2, figsize=(12, 12))
fig.suptitle('肺部结节放大显示', fontsize=16, fontweight='bold')

for idx, nodule in enumerate(nodules):
    # 结节中心坐标
    center_world = np.array([nodule['center']['x'], nodule['center']['y'], nodule['center']['z']])
    inv_affine = np.linalg.inv(affine)
    center_img = inv_affine @ np.append(center_world, 1)
    center_img = center_img[:3].astype(int)
    
    # 定义ROI区域 (以结节为中心，扩展30像素)
    roi_size = 30
    z_slice = np.clip(center_img[2], 0, ct_data.shape[2] - 1)
    
    x_min = max(0, center_img[0] - roi_size)
    x_max = min(ct_data.shape[0], center_img[0] + roi_size)
    y_min = max(0, center_img[1] - roi_size)
    y_max = min(ct_data.shape[1], center_img[1] + roi_size)
    
    # 提取ROI
    roi = ct_data[x_min:x_max, y_min:y_max, z_slice]
    
    # 绘制ROI
    ax = axes[idx, 0]
    im = ax.imshow(roi.T, cmap='gray', origin='lower', vmin=-1000, vmax=400)
    ax.set_title(f'结节{idx+1} - 轴向切片放大\n置信度: {nodule["score"]:.4f}', fontsize=12)
    ax.set_xlabel('X')
    ax.set_ylabel('Y')
    plt.colorbar(im, ax=ax, label='HU')
    
    # 绘制ROI的窗宽窗位调整版本 (肺窗)
    ax = axes[idx, 1]
    im = ax.imshow(roi.T, cmap='gray', origin='lower', vmin=-1500, vmax=400)
    ax.set_title(f'结节{idx+1} - 肺窗显示', fontsize=12)
    ax.set_xlabel('X')
    ax.set_ylabel('Y')
    plt.colorbar(im, ax=ax, label='HU')

plt.tight_layout()
output_path = os.path.join(output_dir, "nodule_enlarged.png")
plt.savefig(output_path, dpi=150, bbox_inches='tight')
print(f"结节放大图已保存到: {output_path}")
plt.close()

print("\n" + "=" * 60)
print("可视化完成！")
print("=" * 60)
print(f"\n生成的可视化文件:")
print(f"  1. {os.path.join(output_dir, 'nodule_slices.png')} - 结节切片视图")
print(f"  2. {os.path.join(output_dir, 'mip_visualization.png')} - 最大密度投影")
print(f"  3. {os.path.join(output_dir, 'nodule_enlarged.png')} - 结节放大显示")
