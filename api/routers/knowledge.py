"""知识库原文档查看 API 路由。"""

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException

from api.models import KnowledgeDocumentResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["知识库"])

# 知识库目录位于项目根目录下
_KNOWLEDGE_BASE_DIR = Path(__file__).resolve().parents[2] / "knowledge_base"
# 仅允许读取 Markdown 文件
_ALLOWED_EXTENSION = ".md"


@router.get("/document/{filename}", response_model=KnowledgeDocumentResponse)
def get_knowledge_document(filename: str):
    """读取知识库中指定的 Markdown 原文档内容。"""
    # 路径遍历攻击防护：拒绝包含 ".." 的参数
    if ".." in filename:
        raise HTTPException(status_code=400, detail="非法的文件名参数")

    # 仅允许读取 .md 文件
    if not filename.lower().endswith(_ALLOWED_EXTENSION):
        raise HTTPException(status_code=400, detail="仅支持读取 Markdown 文件")

    # 解析最终路径，防御性校验：必须仍位于知识库目录内
    target_path = (_KNOWLEDGE_BASE_DIR / filename).resolve()
    try:
        target_path.relative_to(_KNOWLEDGE_BASE_DIR.resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail="非法的文件名参数")

    if not target_path.is_file():
        raise HTTPException(status_code=404, detail="文档不存在")

    try:
        content = target_path.read_text(encoding="utf-8")
    except OSError as e:
        logger.error("读取知识库文档失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"读取文档失败: {e}")

    logger.info("成功读取知识库文档: %s", filename)
    return KnowledgeDocumentResponse(filename=filename, content=content)
