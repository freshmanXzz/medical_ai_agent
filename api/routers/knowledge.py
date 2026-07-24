"""知识库原文档查看 API 路由。"""

import logging
import os
from pathlib import Path
import tempfile

from fastapi import APIRouter, File, HTTPException, UploadFile

from api.models import (
    KnowledgeDocumentListResponse,
    KnowledgeDocumentResponse,
    KnowledgeDocumentSummary,
    KnowledgeRebuildResponse,
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
    KnowledgeSearchResult,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["知识库"])

# 知识库目录位于项目根目录下
_KNOWLEDGE_BASE_DIR = Path(__file__).resolve().parents[2] / "knowledge_base"
# 仅允许读取 Markdown 文件
_ALLOWED_EXTENSION = ".md"


@router.get("/documents", response_model=KnowledgeDocumentListResponse)
def list_knowledge_documents():
    """列出内置指南及用户上传的知识库资料。"""
    from martin.rag.knowledge_manager import KnowledgeManager

    documents = KnowledgeManager().list_documents()
    return KnowledgeDocumentListResponse(
        documents=[KnowledgeDocumentSummary(**document) for document in documents],
        total=len(documents),
    )


@router.post("/documents", response_model=KnowledgeDocumentSummary)
def upload_knowledge_document(file: UploadFile = File(...)):
    """上传一份资料并立即写入向量库。"""
    filename = file.filename or ""
    suffix = Path(filename).suffix.lower()
    if suffix not in {".md", ".txt", ".pdf", ".docx", ".csv"}:
        raise HTTPException(status_code=400, detail="仅支持 .md、.txt、.pdf、.docx、.csv 文件")

    temp_path = ""
    try:
        fd, temp_path = tempfile.mkstemp(suffix=suffix)
        with os.fdopen(fd, "wb") as output:
            while chunk := file.file.read(1024 * 1024):
                output.write(chunk)
        from martin.rag.knowledge_manager import KnowledgeManager

        record = KnowledgeManager().upload_and_index(filename, Path(temp_path))
        if record["status"] == "failed":
            raise HTTPException(status_code=500, detail=record.get("error", "向量化失败"))
        return KnowledgeDocumentSummary(**record)
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


@router.delete("/documents/{document_id}")
def delete_knowledge_document(document_id: str):
    """删除用户上传资料及其对应向量。"""
    if document_id.startswith("builtin:"):
        raise HTTPException(status_code=403, detail="项目内置资料为只读，不能删除")
    from martin.rag.knowledge_manager import KnowledgeManager

    if not KnowledgeManager().delete_uploaded_document(document_id):
        raise HTTPException(status_code=404, detail="知识库文档不存在")
    return {"status": "deleted", "document_id": document_id}


@router.post("/rebuild", response_model=KnowledgeRebuildResponse)
def rebuild_knowledge_base():
    """重建内置资料和全部上传资料的向量。"""
    from martin.rag.knowledge_manager import KnowledgeManager

    try:
        result = KnowledgeManager().rebuild_all()
    except Exception as exc:
        logger.error("重建知识库向量失败: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"重建向量失败: {exc}") from exc
    return KnowledgeRebuildResponse(**result)


@router.post("/search", response_model=KnowledgeSearchResponse)
def search_knowledge_vectors(request: KnowledgeSearchRequest):
    """返回共享 Chroma 集合的原始向量召回结果，用于 RAG 调试。"""
    query = request.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="检索文本不能为空")

    from martin.rag.knowledge_manager import KnowledgeManager, VectorStoreUnavailableError

    try:
        results = KnowledgeManager().search_raw_vectors(query, top_k=5)
    except VectorStoreUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("知识库向量检索失败: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="知识库向量检索失败") from exc

    return KnowledgeSearchResponse(
        query=query,
        results=[KnowledgeSearchResult(**result) for result in results],
        total=len(results),
    )


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
