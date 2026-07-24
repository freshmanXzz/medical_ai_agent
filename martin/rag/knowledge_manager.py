"""运行时知识库文档的保存、向量化与维护服务。"""

from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from langchain_core.documents import Document

from martin.config import config
from martin.rag.document_loader import SUPPORTED_EXTENSIONS, _get_loader, load_knowledge_base
from martin.rag.embeddings import get_embeddings
from martin.rag.text_splitter import split_documents
from martin.rag.vector_store import (
    add_documents,
    create_vector_store,
    delete_document_vectors,
    get_vector_store,
    reset_vector_store_cache,
)


class VectorStoreUnavailableError(RuntimeError):
    """请求检索时当前知识库尚未初始化。"""


class KnowledgeManager:
    """管理内置只读资料和用户上传资料。"""

    def __init__(self) -> None:
        self.data_dir = config.project_root / "data" / "knowledge_uploads"
        self.manifest_path = self.data_dir / "manifest.json"

    def _read_manifest(self) -> list[dict[str, Any]]:
        if not self.manifest_path.exists():
            return []
        try:
            return json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []

    def _write_manifest(self, records: list[dict[str, Any]]) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path.write_text(
            json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _built_in_documents(self) -> list[dict[str, Any]]:
        path = config.project_root / "configs" / "knowledge_base.yaml"
        if not path.exists():
            return []
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return [
            {
                "document_id": f"builtin:{entry['filename']}",
                "filename": entry["filename"],
                "source_type": "builtin",
                "status": "ready",
                "created_at": "",
                "chunk_count": None,
                "deletable": False,
            }
            for entry in raw.get("knowledge_base", {}).get("documents", [])
            if entry.get("filename")
        ]

    def list_documents(self) -> list[dict[str, Any]]:
        uploaded = self._read_manifest()
        return self._built_in_documents() + uploaded

    @staticmethod
    def _safe_filename(filename: str) -> str:
        return Path(filename).name

    def _load_uploaded(self, path: Path, document_id: str, filename: str) -> list[Document]:
        loader = _get_loader(str(path))
        if loader is None:
            raise ValueError("不支持的文件格式")
        documents = loader.load()
        for document in documents:
            document.metadata.update(
                {"source": filename, "document_id": document_id, "source_type": "upload"}
            )
        return documents

    def upload_and_index(self, filename: str, source_path: Path) -> dict[str, Any]:
        safe_name = self._safe_filename(filename)
        if Path(safe_name).suffix.lower() not in SUPPORTED_EXTENSIONS:
            raise ValueError("仅支持 .md、.txt、.pdf、.docx、.csv 文件")

        document_id = f"upload:{uuid.uuid4().hex}"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        stored_name = f"{uuid.uuid4().hex}_{safe_name}"
        target = self.data_dir / stored_name
        shutil.copyfile(source_path, target)
        record: dict[str, Any] = {
            "document_id": document_id,
            "filename": safe_name,
            "stored_name": stored_name,
            "source_type": "upload",
            "status": "indexing",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "chunk_count": 0,
            "deletable": True,
        }
        records = self._read_manifest()
        records.append(record)
        self._write_manifest(records)
        try:
            chunks = split_documents(self._load_uploaded(target, document_id, safe_name))
            if not chunks:
                raise ValueError("文档没有可向量化的文本内容")
            record["chunk_count"] = add_documents(chunks, document_id)
            record.update(status="ready", error=None)
        except Exception as exc:
            record["status"] = "failed"
            record["error"] = str(exc)
        self._write_manifest(records)
        return record

    def delete_uploaded_document(self, document_id: str) -> bool:
        records = self._read_manifest()
        record = next((item for item in records if item["document_id"] == document_id), None)
        if record is None:
            return False
        delete_document_vectors(document_id)
        path = self.data_dir / record["stored_name"]
        if path.exists():
            path.unlink()
        self._write_manifest([item for item in records if item["document_id"] != document_id])
        return True

    def search_raw_vectors(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """直接查询共享 Chroma 集合，供知识库诊断页核验原始召回结果。"""
        vector_store = get_vector_store()
        if vector_store is None:
            raise VectorStoreUnavailableError("向量库尚未初始化，请先重建知识库向量")

        matches = vector_store.similarity_search_with_relevance_scores(query, k=top_k)
        results = []
        for rank, (document, score) in enumerate(matches, start=1):
            document_id = document.metadata.get("document_id", "")
            results.append(
                {
                    "rank": rank,
                    "score": max(0.0, min(1.0, float(score))),
                    "source": document.metadata.get("source", ""),
                    "source_type": document.metadata.get("source_type")
                    or ("upload" if document_id.startswith("upload:") else "builtin"),
                    "document_id": document_id,
                    "content": document.page_content,
                }
            )
        return results

    def rebuild_all(self) -> dict[str, int]:
        # 重建不能悄悄跳过配置中的内置循证资料，否则向量库会处于
        # "构建成功"但医学依据不完整的危险状态。
        documents = load_knowledge_base(strict=True)
        built_in_count = len(
            {document.metadata.get("source") for document in documents if document.metadata.get("source")}
        )
        for document in documents:
            document.metadata.update(
                {
                    "document_id": f"builtin:{document.metadata.get('source', '')}",
                    "source_type": "builtin",
                }
            )
        records = self._read_manifest()
        for record in records:
            path = self.data_dir / record["stored_name"]
            if not path.exists():
                record.update(status="failed", error="上传文件不存在", chunk_count=0)
                continue
            try:
                documents.extend(self._load_uploaded(path, record["document_id"], record["filename"]))
                record.update(status="ready", error=None)
            except Exception as exc:
                record.update(status="failed", error=str(exc), chunk_count=0)
        chunks = split_documents(documents)
        if not chunks:
            raise ValueError("没有可用于重建的知识库文本")
        create_vector_store(chunks, get_embeddings())
        for record in records:
            record["chunk_count"] = sum(
                chunk.metadata.get("document_id") == record["document_id"] for chunk in chunks
            )
        self._write_manifest(records)
        reset_vector_store_cache()
        uploaded_count = sum(record["status"] == "ready" for record in records)
        return {"documents": built_in_count + uploaded_count, "chunks": len(chunks)}
