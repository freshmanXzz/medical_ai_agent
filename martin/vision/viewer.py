"""安全的 NIfTI 轴位阅片支持。

该模块只接受由病例上下文保存的 MinIO 对象键，不暴露对象键或本地文件路径给
浏览器。影像以 RAS+ 规范化后读取，检测器输出的 RAS 世界坐标在此转换成画布
使用的像素坐标。
"""

from __future__ import annotations

import os
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from itertools import product
from typing import Any

import nibabel as nib
import numpy as np
from PIL import Image


DEFAULT_WINDOW_CENTER = -600.0
DEFAULT_WINDOW_WIDTH = 1500.0
MAX_DECODED_BYTES = 512 * 1024 * 1024
STUDY_CACHE_TTL_SECONDS = 10 * 60
MAX_PNG_CACHE_ITEMS = 128


class ViewerStudyError(RuntimeError):
    """用户可诊断的阅片影像错误。"""


def _valid_object_name(value: Any) -> bool:
    """仅允许上传接口生成的 CT 对象键。"""
    return (
        isinstance(value, str)
        and value.startswith("ct/")
        and ".." not in value
        and "\\" not in value
        and value.count("/") == 1
    )


def _finite_triplet(value: Any) -> np.ndarray | None:
    if not isinstance(value, dict):
        return None
    try:
        triplet = np.array([value["x"], value["y"], value["z"]], dtype=float)
    except (KeyError, TypeError, ValueError):
        return None
    return triplet if np.isfinite(triplet).all() else None


def _as_display_coordinates(voxel: np.ndarray, shape: tuple[int, int, int]) -> np.ndarray:
    """将 RAS+ 体素坐标映射至放射学显示的图像像素坐标。"""
    return np.array([shape[0] - 1 - voxel[0], shape[1] - 1 - voxel[1], voxel[2]])


def nodule_display_geometry(
    nodule: dict[str, Any], affine: np.ndarray, shape: tuple[int, int, int]
) -> dict[str, Any]:
    """将一个 RAS 世界坐标结节转换为当前轴位画布的几何信息。"""
    center = _finite_triplet(nodule.get("center"))
    dimensions = nodule.get("dimensions") if isinstance(nodule.get("dimensions"), dict) else {}
    try:
        size = np.array(
            [dimensions["width"], dimensions["height"], dimensions["depth"]], dtype=float
        )
    except (KeyError, TypeError, ValueError):
        size = None

    result: dict[str, Any] = {"index": nodule.get("index")}
    for key in ("diameter", "score"):
        try:
            value = float(nodule[key])
        except (KeyError, TypeError, ValueError):
            continue
        if np.isfinite(value):
            result[key] = value
    if center is None or size is None or not np.isfinite(size).all() or (size < 0).any():
        result["spatial_status"] = "unavailable"
        return result

    offsets = np.array(list(product((-0.5, 0.5), repeat=3))) * size
    world_corners = center + offsets
    try:
        inverse_affine = np.linalg.inv(affine)
        voxel_corners = nib.affines.apply_affine(inverse_affine, world_corners)
        voxel_center = nib.affines.apply_affine(inverse_affine, center)
    except (np.linalg.LinAlgError, ValueError):
        result["spatial_status"] = "unavailable"
        return result

    if not np.isfinite(voxel_corners).all() or not np.isfinite(voxel_center).all():
        result["spatial_status"] = "unavailable"
        return result

    minimum = np.floor(voxel_corners.min(axis=0))
    maximum = np.ceil(voxel_corners.max(axis=0))
    limits = np.array(shape, dtype=float) - 1
    if (maximum < 0).any() or (minimum > limits).any():
        result["spatial_status"] = "outside_volume"
        return result

    minimum = np.clip(minimum, 0, limits)
    maximum = np.clip(maximum, 0, limits)
    display_minimum = _as_display_coordinates(maximum, shape)
    display_maximum = _as_display_coordinates(minimum, shape)
    display_center = _as_display_coordinates(np.clip(voxel_center, 0, limits), shape)
    result.update(
        {
            "spatial_status": "located",
            "display_center": {key: float(value) for key, value in zip(("x", "y", "z"), display_center)},
            "display_bbox": {
                "x_min": float(display_minimum[0]),
                "x_max": float(display_maximum[0]),
                "y_min": float(display_minimum[1]),
                "y_max": float(display_maximum[1]),
                "z_min": float(minimum[2]),
                "z_max": float(maximum[2]),
            },
        }
    )
    return result


def render_axial_png(data: Any, slice_index: int, window_center: float, window_width: float) -> bytes:
    """按指定窗位/窗宽渲染一张 RAS+ 轴位切片为 PNG。"""
    if window_width <= 0:
        raise ValueError("窗宽必须大于 0")
    slice_data = np.asarray(data[..., slice_index], dtype=np.float32)
    lower = window_center - window_width / 2
    pixels = np.clip((slice_data - lower) / window_width, 0.0, 1.0)
    grayscale = np.rint(pixels * 255).astype(np.uint8)
    # NIfTI 的前两轴为 x/y；转置并双向翻转，得到放射学方向的二维显示。
    display = np.flipud(np.fliplr(grayscale.T))
    image = Image.fromarray(display, mode="L")
    from io import BytesIO

    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


@dataclass
class _CachedStudy:
    thread_id: str
    object_name: str
    local_path: str
    image: Any
    loaded_at: float
    png_cache: OrderedDict[tuple[int, float, float], bytes] = field(default_factory=OrderedDict)

    @property
    def shape(self) -> tuple[int, int, int]:
        return tuple(int(value) for value in self.image.shape[:3])


class ViewerStudyCache:
    """只缓存一个短生命周期研究，避免保留病例影像和无界内存。"""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._study: _CachedStudy | None = None

    def close(self) -> None:
        with self._lock:
            self._evict_locked()

    def get(self, thread_id: str, image_info: dict[str, Any]) -> _CachedStudy:
        object_name = image_info.get("object_name")
        if image_info.get("source_type") != "minio_object" or not _valid_object_name(object_name):
            raise ViewerStudyError("该历史病例没有可恢复的影像源，请重新上传影像。")

        with self._lock:
            if (
                self._study
                and self._study.thread_id == thread_id
                and self._study.object_name == object_name
                and time.monotonic() - self._study.loaded_at <= STUDY_CACHE_TTL_SECONDS
            ):
                return self._study
            self._evict_locked()

            from martin.utils.oss_client import get_oss_client

            try:
                local_path = get_oss_client().download_file(object_name)
                image = nib.as_closest_canonical(nib.load(local_path))
            except Exception as exc:
                if "local_path" in locals() and os.path.exists(local_path):
                    os.remove(local_path)
                raise ViewerStudyError("影像读取失败，无法打开当前病例的 NIfTI 文件。") from exc

            if len(image.shape) < 3 or len(image.shape) > 3:
                if os.path.exists(local_path):
                    os.remove(local_path)
                raise ViewerStudyError("仅支持三维 NIfTI CT 影像。")
            declared_size = int(np.prod(image.shape[:3])) * int(image.get_data_dtype().itemsize)
            if declared_size > MAX_DECODED_BYTES:
                if os.path.exists(local_path):
                    os.remove(local_path)
                raise ViewerStudyError("影像解码后体积过大，无法在阅片服务中安全打开。")

            self._study = _CachedStudy(
                thread_id=thread_id,
                object_name=object_name,
                local_path=local_path,
                image=image,
                loaded_at=time.monotonic(),
            )
            return self._study

    def png(self, study: _CachedStudy, slice_index: int, center: float, width: float) -> bytes:
        cache_key = (slice_index, center, width)
        with self._lock:
            cached = study.png_cache.get(cache_key)
            if cached is not None:
                study.png_cache.move_to_end(cache_key)
                return cached
            rendered = render_axial_png(study.image.dataobj, slice_index, center, width)
            study.png_cache[cache_key] = rendered
            if len(study.png_cache) > MAX_PNG_CACHE_ITEMS:
                study.png_cache.popitem(last=False)
            return rendered

    def _evict_locked(self) -> None:
        if self._study is not None:
            local_path = self._study.local_path
            self._study = None
            if local_path and os.path.exists(local_path):
                try:
                    os.remove(local_path)
                except OSError:
                    pass


viewer_study_cache = ViewerStudyCache()


def get_viewer_study(thread_id: str) -> _CachedStudy:
    """仅从该会话的 checkpoint 读取并加载已保存的影像来源。"""
    from martin.agent.sessions import SessionManager, get_default_checkpointer

    context = SessionManager(get_default_checkpointer()).get_case_context(thread_id)
    if not context:
        raise ViewerStudyError("病例会话不存在或尚未保存影像。")
    image_info = context.get("image_info")
    if not isinstance(image_info, dict):
        raise ViewerStudyError("该病例没有可恢复的影像源，请重新上传影像。")
    return viewer_study_cache.get(thread_id, image_info)


def viewer_manifest(thread_id: str) -> dict[str, Any]:
    """构造不会泄露影像来源的阅片元数据。"""
    study = get_viewer_study(thread_id)
    from martin.agent.sessions import SessionManager, get_default_checkpointer

    context = SessionManager(get_default_checkpointer()).get_case_context(thread_id)
    nodules = context.get("nodules", []) if isinstance(context, dict) else []
    affine = np.asarray(study.image.affine, dtype=float)
    return {
        "shape": list(study.shape),
        "axial_slice_count": study.shape[2],
        "default_window": {"center": DEFAULT_WINDOW_CENTER, "width": DEFAULT_WINDOW_WIDTH},
        "nodules": [
            nodule_display_geometry(nodule, affine, study.shape)
            for nodule in nodules
            if isinstance(nodule, dict)
        ],
    }


def viewer_slice(thread_id: str, slice_index: int, center: float, width: float) -> bytes:
    study = get_viewer_study(thread_id)
    if slice_index < 0 or slice_index >= study.shape[2]:
        raise ViewerStudyError("切片索引超出当前影像范围。")
    return viewer_study_cache.png(study, slice_index, center, width)
