"""CT 影像检测 API 路由。"""

import logging
import os
import re
import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File

from api.models import DetectRequest, DetectResponse, NoduleInfo, UploadResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["影像检测"])

# 支持的影像文件扩展名
_ALLOWED_EXTENSIONS = (".nii", ".nii.gz")


def _is_allowed_filename(filename: str) -> bool:
    """检查文件名是否为支持的影像格式。"""
    lower = filename.lower()
    return lower.endswith(_ALLOWED_EXTENSIONS)


def _resolve_image_path(image_path: str) -> Path:
    """解析本地影像文件路径，兼容 OSS 对象名。

    当输入为 OSS 路径时，先下载到临时目录再返回本地路径。
    """
    from martin.utils.oss_client import is_oss_path, parse_oss_path, get_oss_client

    # OSS 路径：下载到临时目录
    if is_oss_path(image_path):
        logger.info("检测到 OSS 路径，开始下载: %s", image_path)
        _, object_name = parse_oss_path(image_path)
        try:
            client = get_oss_client()
            local_path = client.download_file(object_name)
            return Path(local_path)
        except Exception as e:
            logger.error("从 OSS 下载文件失败: %s", e, exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"从 OSS 下载文件失败: {e}",
            )

    # 本地路径解析
    path = Path(image_path).expanduser()
    if not path.is_absolute():
        path = Path(__file__).resolve().parents[2] / path
    path = path.resolve()
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"图像文件不存在: {image_path}")
    if not _is_allowed_filename(path.name):
        raise HTTPException(status_code=400, detail="仅支持 .nii 或 .nii.gz CT 图像")
    return path


@router.post("/image/upload", response_model=UploadResponse)
def upload_ct_image(file: UploadFile = File(...)):
    """上传 CT 影像文件到 OSS，返回对象名。"""
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

        logger.info(
            "影像文件上传成功: %s → %s/%s, %d bytes",
            file.filename,
            client.bucket,
            object_name,
            file_size,
        )

        return UploadResponse(
            object_name=object_name,
            bucket=client.bucket,
            size=file_size,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("影像文件上传失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"上传失败: {e}")
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


@router.post("/image/analyze", response_model=DetectResponse)
def analyze_ct_image(request: DetectRequest):
    """检测 CT 图像，并将结果绑定到当前 Agent 会话。

    支持本地路径和 OSS 对象名作为输入。OSS 路径会自动下载到临时目录。
    """
    from martin.utils.oss_client import is_oss_path

    resolved_path = _resolve_image_path(request.image_path)
    is_from_oss = is_oss_path(request.image_path)

    from martin.agent.agent import create_agent
    from martin.agent.sessions import get_default_checkpointer
    from martin.agent.tools import analyze_image, reset_case_context, set_case_context

    # 创建 Agent 实例，从 Checkpointer state 恢复 CaseContext
    agent = create_agent(
        thread_id=request.session_id,
        checkpointer=get_default_checkpointer(),
        verbose=False,
    )
    case_context = agent.case_context
    token = set_case_context(case_context)
    try:
        raw_text = analyze_image.invoke({"image_path": str(resolved_path)})
    finally:
        reset_case_context(token)
        # 清理 OSS 下载的临时文件
        if is_from_oss and os.path.exists(resolved_path):
            try:
                os.remove(str(resolved_path))
                logger.info("已清理临时下载文件: %s", resolved_path)
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
        image=request.image_path,
        total_nodules=total,
        nodules=nodules,
        raw_text=raw_text,
        case_context=case_context.to_dict(),
    )
