"""CT 影像检测 API 路由。"""

import logging
import os
import re
import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Query, Response

from api.models import (
    DetectRequest,
    DetectResponse,
    NoduleInfo,
    UploadResponse,
    ViewerManifestResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["影像检测"])

# 支持的影像文件扩展名
_ALLOWED_EXTENSIONS = (".nii", ".nii.gz")


def _is_allowed_filename(filename: str) -> bool:
    """检查文件名是否为支持的影像格式。"""
    lower = filename.lower()
    return lower.endswith(_ALLOWED_EXTENSIONS)


def _is_safe_ct_object_name(value: object) -> bool:
    """仅接受上传接口生成的单层 CT 对象键。"""
    return (
        isinstance(value, str)
        and value.startswith("ct/")
        and ".." not in value
        and "\\" not in value
        and value.count("/") == 1
    )


def _create_session_agent(session_id: str):
    """用同一会话的 checkpoint 保存和读取服务端影像来源。"""
    from martin.agent.agent import create_agent
    from martin.agent.sessions import get_default_checkpointer

    return create_agent(
        thread_id=session_id,
        checkpointer=get_default_checkpointer(),
        verbose=False,
    )


@router.post("/image/upload", response_model=UploadResponse)
def upload_ct_image(file: UploadFile = File(...), session_id: str = Form(...)):
    """上传 CT 影像并将对象引用仅保存到指定会话。"""
    if not _is_allowed_filename(file.filename or ""):
        raise HTTPException(
            status_code=400,
            detail="仅支持 .nii 或 .nii.gz CT 图像",
        )

    # 保存到临时文件后上传到 OSS
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".nii.gz")
    try:
        os.close(tmp_fd)
        with open(tmp_path, "wb") as f:
            while True:
                chunk = file.file.read(1024 * 1024)
                if not chunk:
                    break
                f.write(chunk)

        file_size = os.path.getsize(tmp_path)

        from martin.utils.oss_client import get_oss_client

        client = get_oss_client()
        object_name = client.upload_file(tmp_path)

        if not _is_safe_ct_object_name(object_name):
            logger.error("上传接口返回了不安全的 CT 对象引用")
            raise HTTPException(status_code=500, detail="影像存储失败，请重新上传。")

        agent = _create_session_agent(session_id)
        agent.case_context.set_image_source(object_name, file.filename or "")
        agent.save_case_context()

        logger.info("影像文件上传成功: %s, %d bytes", file.filename, file_size)

        return UploadResponse(
            size=file_size,
            filename=file.filename or "",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("影像文件上传失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="影像上传失败，请检查本地 MinIO 服务后重试。") from e
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


@router.post("/image/analyze", response_model=DetectResponse)
def analyze_ct_image(request: DetectRequest):
    """仅分析该会话已保存的受控 MinIO 影像。"""
    from martin.agent.tools import analyze_image, reset_case_context, set_case_context

    agent = _create_session_agent(request.session_id)
    case_context = agent.case_context
    image_info = case_context.image_info
    object_name = image_info.get("object_name")
    if image_info.get("source_type") != "minio_object" or not _is_safe_ct_object_name(object_name):
        raise HTTPException(status_code=409, detail="当前会话没有可分析的影像，请先上传 NIfTI 文件。")

    try:
        from martin.utils.oss_client import get_oss_client

        resolved_path = Path(get_oss_client().download_file(object_name))
    except Exception as exc:
        logger.error("分析前下载会话影像失败: %s", exc, exc_info=True)
        raise HTTPException(status_code=502, detail="影像读取失败，请检查本地 MinIO 服务后重试。") from exc

    token = set_case_context(case_context)
    try:
        raw_text = analyze_image.invoke({"image_path": str(resolved_path)})
    finally:
        reset_case_context(token)
        if os.path.exists(resolved_path):
            try:
                os.remove(str(resolved_path))
            except OSError as e:
                logger.warning("清理临时文件失败: %s", e)

    if raw_text.startswith("错误:"):
        logger.error("影像检测失败: %s", raw_text)
        raise HTTPException(status_code=500, detail=raw_text)

    # 该接口直接调用检测工具，不经过 AgentExecutor.invoke；显式将工具更新后的
    # CaseContext 写回当前 thread 的 SqliteSaver checkpoint。
    agent.save_case_context()

    total_match = re.search(r"检测到结节总数:\s*(\d+)", raw_text)
    total = int(total_match.group(1)) if total_match else 0
    nodules = []

    for index, block in enumerate(re.split(r"结节\s+\d+:", raw_text)[1:], 1):
        diameter = re.search(r"最大直径:\s*([\d.]+)", block)
        score = re.search(r"检测置信度:\s*([\d.]+)", block)
        center = re.search(r"中心位置:\s*\(([\d.-]+),\s*([\d.-]+),\s*([\d.-]+)\)", block)
        dimensions = re.search(r"三维尺寸:\s*([\d.]+)\s*x\s*([\d.]+)\s*x\s*([\d.]+)", block)

        if not diameter or not score:
            logger.error("无法解析结节检测结果: %s", block)
            raise HTTPException(status_code=500, detail="检测结果格式异常")

        nodules.append(NoduleInfo(
            index=index,
            diameter=float(diameter.group(1)),
            score=float(score.group(1)),
            center={
                "x": float(center.group(1)),
                "y": float(center.group(2)),
                "z": float(center.group(3)),
            } if center else {},
            dimensions={
                "width": float(dimensions.group(1)),
                "height": float(dimensions.group(2)),
                "depth": float(dimensions.group(3)),
            } if dimensions else {},
        ))

    return DetectResponse(
        image=case_context.image_info.get("filename") or case_context.image_info.get("image_name") or "",
        total_nodules=total,
        nodules=nodules,
        raw_text=raw_text,
        case_context=case_context.to_public_dict(),
    )


def _viewer_error(exc: Exception) -> HTTPException:
    """将影像加载错误转换为不含路径和对象键的 API 错误。"""
    from martin.vision.viewer import ViewerStudyError

    if isinstance(exc, ViewerStudyError):
        return HTTPException(status_code=404, detail=str(exc))
    logger.error("阅片接口失败: %s", exc, exc_info=True)
    return HTTPException(status_code=500, detail="阅片影像处理失败，请稍后重试。")


@router.get(
    "/sessions/{thread_id}/viewer/manifest",
    response_model=ViewerManifestResponse,
)
def get_viewer_manifest(thread_id: str):
    """返回当前会话的轴位阅片元数据，不接受影像路径或对象键。"""
    from martin.vision.viewer import viewer_manifest

    try:
        return viewer_manifest(thread_id)
    except Exception as exc:
        raise _viewer_error(exc) from exc


@router.get("/sessions/{thread_id}/viewer/axial/{slice_index}.png")
def get_viewer_axial_slice(
    thread_id: str,
    slice_index: int,
    window_center: float = Query(default=-600.0, ge=-1500.0, le=3000.0),
    window_width: float = Query(default=1500.0, ge=1.0, le=5000.0),
):
    """渲染一张病例轴位 PNG；客户端不能控制影像来源。"""
    from martin.vision.viewer import viewer_slice

    try:
        content = viewer_slice(thread_id, slice_index, window_center, window_width)
    except Exception as exc:
        raise _viewer_error(exc) from exc
    return Response(
        content=content,
        media_type="image/png",
        headers={"Cache-Control": "no-store"},
    )
