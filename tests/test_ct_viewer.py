"""CT 轴位阅片的无模型单元与 API 测试。"""

from io import BytesIO
import shutil

import nibabel as nib
import numpy as np
from PIL import Image
from fastapi.testclient import TestClient

from api.main import app
from martin.vision.viewer import (
    ViewerStudyCache,
    nodule_display_geometry,
    render_axial_png,
)


def test_nodule_geometry_converts_ras_world_coordinates_to_display_pixels():
    geometry = nodule_display_geometry(
        {
            "index": 7,
            "center": {"x": 2, "y": 3, "z": 4},
            "dimensions": {"width": 2, "height": 2, "depth": 2},
        },
        np.eye(4),
        (10, 11, 12),
    )

    assert geometry["spatial_status"] == "located"
    assert geometry["display_center"] == {"x": 7.0, "y": 7.0, "z": 4.0}
    assert geometry["display_bbox"] == {
        "x_min": 6.0,
        "x_max": 8.0,
        "y_min": 6.0,
        "y_max": 8.0,
        "z_min": 3.0,
        "z_max": 5.0,
    }
    assert "diameter" not in geometry
    assert "score" not in geometry


def test_nodule_geometry_keeps_only_safe_display_metadata():
    geometry = nodule_display_geometry(
        {
            "index": 7,
            "diameter": 6.4,
            "score": 0.91,
            "object_name": "ct/secret.nii.gz",
            "center": {"x": 2, "y": 3, "z": 4},
            "dimensions": {"width": 2, "height": 2, "depth": 2},
        },
        np.eye(4),
        (10, 11, 12),
    )

    assert geometry["diameter"] == 6.4
    assert geometry["score"] == 0.91
    assert "object_name" not in geometry


def test_nodule_geometry_clips_to_volume_and_rejects_invalid_coordinates():
    clipped = nodule_display_geometry(
        {
            "index": 1,
            "center": {"x": 0, "y": 0, "z": 0},
            "dimensions": {"width": 4, "height": 4, "depth": 4},
        },
        np.eye(4),
        (5, 5, 5),
    )
    invalid = nodule_display_geometry(
        {"index": 2, "center": {"x": "bad", "y": 1, "z": 1}, "dimensions": {}},
        np.eye(4),
        (5, 5, 5),
    )

    assert clipped["display_bbox"]["x_max"] == 4.0
    assert clipped["display_bbox"]["y_max"] == 4.0
    assert clipped["display_bbox"]["z_min"] == 0.0
    assert invalid == {"index": 2, "spatial_status": "unavailable"}


def test_render_axial_png_applies_window_and_radiological_orientation():
    data = np.full((3, 4, 1), -1350, dtype=np.int16)
    data[0, 0, 0] = -600
    rendered = render_axial_png(data, 0, -600, 1500)
    image = Image.open(BytesIO(rendered))

    assert image.size == (3, 4)
    # 原始 [x=0,y=0] 经双向翻转显示在右下角；-600 位于肺窗中点。
    assert image.getpixel((2, 3)) in (127, 128)
    assert image.getpixel((0, 0)) == 0


def test_known_ras_point_matches_the_rendered_png_pixel():
    """同一 RAS 点必须在 PNG 高亮体素和 SVG 显示坐标中重合。"""
    data = np.full((3, 4, 1), -1350, dtype=np.int16)
    data[2, 1, 0] = -600
    image = Image.open(BytesIO(render_axial_png(data, 0, -600, 1500)))
    geometry = nodule_display_geometry(
        {
            "index": 1,
            "center": {"x": 2, "y": 1, "z": 0},
            "dimensions": {"width": 0, "height": 0, "depth": 0},
        },
        np.eye(4),
        data.shape,
    )

    assert geometry["display_center"] == {"x": 0.0, "y": 2.0, "z": 0.0}
    assert image.getpixel((0, 2)) in (127, 128)


def test_cache_rejects_non_minio_or_unsafe_object_source_without_downloading():
    cache = ViewerStudyCache()
    for image_info in (
        {"source_type": "minio_object", "object_name": "../../secret.nii.gz"},
        {"source_type": "local", "object_name": "ct/abc.nii.gz"},
        {"source_type": "minio_object", "object_name": "ct/a/b.nii.gz"},
    ):
        try:
            cache.get("case-1", image_info)
        except Exception as exc:
            assert "可恢复的影像源" in str(exc)
        else:
            raise AssertionError("unsafe image source must be rejected")


def test_cache_loads_synthetic_nifti_as_ras_and_cleans_temp_file(monkeypatch, tmp_path):
    """真实 NIfTI 文件必须先规范化为 RAS+，缓存关闭后删除下载副本。"""
    source = tmp_path / "source.nii.gz"
    nib.save(
        nib.Nifti1Image(np.zeros((3, 4, 2), dtype=np.int16), np.diag([-1, 1, 1, 1])),
        source,
    )
    downloaded = tmp_path / "downloaded.nii.gz"

    class FakeOss:
        def download_file(self, object_name):
            assert object_name == "ct/study.nii.gz"
            shutil.copyfile(source, downloaded)
            return str(downloaded)

    import martin.utils.oss_client as oss_client

    monkeypatch.setattr(oss_client, "get_oss_client", lambda: FakeOss())
    cache = ViewerStudyCache()
    study = cache.get("case-1", {"source_type": "minio_object", "object_name": "ct/study.nii.gz"})

    assert nib.aff2axcodes(study.image.affine) == ("R", "A", "S")
    assert study.shape == (3, 4, 2)
    assert cache.png(study, 0, -600, 1500).startswith(b"\x89PNG")
    cache.close()
    assert not downloaded.exists()


def test_viewer_api_does_not_expose_source_identifiers(monkeypatch):
    import martin.vision.viewer as viewer

    monkeypatch.setattr(
        viewer,
        "viewer_manifest",
        lambda thread_id: {
            "shape": [8, 9, 10],
            "axial_slice_count": 10,
            "default_window": {"center": -600, "width": 1500},
            "nodules": [],
        },
    )
    monkeypatch.setattr(viewer, "viewer_slice", lambda *args: b"png-bytes")

    with TestClient(app) as client:
        manifest = client.get("/api/sessions/case-1/viewer/manifest")
        png = client.get("/api/sessions/case-1/viewer/axial/2.png")
        invalid_window = client.get("/api/sessions/case-1/viewer/axial/2.png?window_width=0")

    assert manifest.status_code == 200
    assert manifest.json() == {
        "shape": [8, 9, 10],
        "axial_slice_count": 10,
        "default_window": {"center": -600.0, "width": 1500.0},
        "nodules": [],
    }
    assert "object_name" not in manifest.text
    assert "image_path" not in manifest.text
    assert png.status_code == 200
    assert png.headers["cache-control"] == "no-store"
    assert png.headers["content-type"] == "image/png"
    assert invalid_window.status_code == 422
