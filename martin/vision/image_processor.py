"""
ImageProcessor - 医学图像处理模块
提供CT图像读取、预处理和格式转换功能
"""
import os
import numpy as np
import nibabel as nib

class ImageProcessor:
    """
    医学图像处理类
    
    支持格式：
    - NIfTI (.nii, .nii.gz)
    - MetaImage (.mhd/.raw)
    """
    
    @staticmethod
    def read_nifti(file_path: str) -> tuple:
        """
        读取NIfTI格式图像
        
        Args:
            file_path: NIfTI文件路径
        
        Returns:
            (数据数组, 仿射矩阵, 元数据)
        """
        img = nib.load(file_path)
        data = img.get_fdata()
        affine = img.affine
        header = img.header
        
        return data, affine, header
    
    @staticmethod
    def read_metaimage(mhd_path: str) -> tuple:
        """
        读取MetaImage格式图像
        
        Args:
            mhd_path: .mhd文件路径
        
        Returns:
            (数据数组, 像素间距, 元数据)
        """
        # 解析头文件
        metadata = {}
        with open(mhd_path, 'r') as f:
            for line in f:
                line = line.strip()
                if '=' in line:
                    key, value = line.split('=', 1)
                    metadata[key.strip()] = value.strip()
        
        # 获取数据文件路径
        raw_filename = metadata['ElementDataFile']
        raw_path = os.path.join(os.path.dirname(mhd_path), raw_filename)
        
        # 解析尺寸
        dim_size = [int(x) for x in metadata['DimSize'].split()]
        spacing = [float(x) for x in metadata['ElementSpacing'].split()]
        
        # 读取二进制数据
        data = np.fromfile(raw_path, dtype=np.int16)
        data = data.reshape(dim_size[2], dim_size[1], dim_size[0])  # (z, y, x)
        
        return data, spacing, metadata
    
    @staticmethod
    def metaimage_to_nifti(mhd_path: str, output_path: str):
        """
        将MetaImage转换为NIfTI格式
        
        Args:
            mhd_path: .mhd文件路径
            output_path: 输出NIfTI文件路径
        """
        data, spacing, metadata = ImageProcessor.read_metaimage(mhd_path)
        
        # 创建仿射矩阵
        affine = np.diag([spacing[0], spacing[1], spacing[2], 1.0])
        
        # 处理方向
        orientation = metadata.get('AnatomicalOrientation', 'RAI')
        if orientation == "RAI":
            data = data[::-1, :, :].copy()
        
        # 创建NIfTI图像
        img = nib.Nifti1Image(data, affine)
        nib.save(img, output_path)
    
    @staticmethod
    def normalize_intensity(data: np.ndarray, a_min: float = -1024.0, 
                           a_max: float = 300.0, b_min: float = 0.0, 
                           b_max: float = 1.0) -> np.ndarray:
        """
        灰度值归一化
        
        Args:
            data: 输入数据
            a_min, a_max: 输入范围
            b_min, b_max: 输出范围
        
        Returns:
            归一化后的数据
        """
        output = data.copy().astype(np.float32)
        output[output < a_min] = a_min
        output[output > a_max] = a_max
        output = (output - a_min) / (a_max - a_min) * (b_max - b_min) + b_min
        
        return output
    
    @staticmethod
    def resample(data: np.ndarray, original_spacing: list, 
                target_spacing: list) -> np.ndarray:
        """
        图像重采样
        
        Args:
            data: 输入数据
            original_spacing: 原始像素间距
            target_spacing: 目标像素间距
        
        Returns:
            重采样后的数据
        """
        import scipy.ndimage
        
        # 计算缩放比例
        scale = [os / ts for os, ts in zip(original_spacing, target_spacing)]
        
        # 重采样
        resampled = scipy.ndimage.zoom(data, scale, order=3)
        
        return resampled
    
    @staticmethod
    def get_image_info(file_path: str) -> dict:
        """
        获取图像信息
        
        Args:
            file_path: 图像文件路径
        
        Returns:
            图像信息字典
        """
        if file_path.endswith('.nii.gz') or file_path.endswith('.nii'):
            data, affine, header = ImageProcessor.read_nifti(file_path)
            spacing = np.diag(affine)[:3]
            dim_size = data.shape
        elif file_path.endswith('.mhd'):
            data, spacing, metadata = ImageProcessor.read_metaimage(file_path)
            dim_size = data.shape
        
        return {
            'dim_size': dim_size,
            'spacing': spacing.tolist() if hasattr(spacing, 'tolist') else spacing,
            'voxel_count': np.prod(dim_size),
            'data_range': [float(data.min()), float(data.max())]
        }
