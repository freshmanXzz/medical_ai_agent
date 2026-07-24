"""知识库运行时管理测试，不加载真实 embedding 或 Chroma。"""

from pathlib import Path

from langchain_core.documents import Document


def test_upload_indexes_document_and_records_manifest(monkeypatch, tmp_path):
    from martin.rag.knowledge_manager import KnowledgeManager

    manager = KnowledgeManager()
    manager.data_dir = tmp_path / "uploads"
    manager.manifest_path = manager.data_dir / "manifest.json"
    source = tmp_path / "guide.txt"
    source.write_text("肺结节随访建议", encoding="utf-8")

    monkeypatch.setattr(
        "martin.rag.knowledge_manager.split_documents",
        lambda docs: docs,
    )
    indexed = []
    monkeypatch.setattr(
        "martin.rag.knowledge_manager.add_documents",
        lambda docs, document_id: indexed.append((docs, document_id)) or len(docs),
    )

    record = manager.upload_and_index("guide.txt", source)

    assert record["status"] == "ready"
    assert record["chunk_count"] == 1
    assert record["deletable"] is True
    assert indexed[0][0][0].metadata["document_id"] == record["document_id"]
    assert manager.list_documents()[-1]["filename"] == "guide.txt"


def test_delete_removes_uploaded_file_and_vectors(monkeypatch, tmp_path):
    from martin.rag.knowledge_manager import KnowledgeManager

    manager = KnowledgeManager()
    manager.data_dir = tmp_path / "uploads"
    manager.data_dir.mkdir()
    manager.manifest_path = manager.data_dir / "manifest.json"
    stored = manager.data_dir / "stored.txt"
    stored.write_text("test", encoding="utf-8")
    manager._write_manifest([{
        "document_id": "upload:test", "filename": "test.txt", "stored_name": "stored.txt",
        "source_type": "upload", "status": "ready", "created_at": "", "chunk_count": 1,
        "deletable": True,
    }])
    deleted = []
    monkeypatch.setattr("martin.rag.knowledge_manager.delete_document_vectors", deleted.append)

    assert manager.delete_uploaded_document("upload:test") is True
    assert deleted == ["upload:test"]
    assert not stored.exists()
    assert manager._read_manifest() == []


def test_raw_vector_search_returns_ranked_metadata(monkeypatch):
    from martin.rag.knowledge_manager import KnowledgeManager

    class FakeStore:
        def similarity_search_with_relevance_scores(self, query, k):
            assert query == "分叶结节"
            assert k == 5
            return [
                (Document(page_content="第一段", metadata={"source": "guide.md", "document_id": "builtin:guide.md"}), 0.92),
                (Document(page_content="第二段", metadata={"source": "upload.txt", "document_id": "upload:abc", "source_type": "upload"}), 0.31),
            ]

    monkeypatch.setattr("martin.rag.knowledge_manager.get_vector_store", lambda: FakeStore())

    results = KnowledgeManager().search_raw_vectors("分叶结节")

    assert results == [
        {"rank": 1, "score": 0.92, "source": "guide.md", "source_type": "builtin", "document_id": "builtin:guide.md", "content": "第一段"},
        {"rank": 2, "score": 0.31, "source": "upload.txt", "source_type": "upload", "document_id": "upload:abc", "content": "第二段"},
    ]


def test_raw_vector_search_requires_initialized_store(monkeypatch):
    import pytest

    from martin.rag.knowledge_manager import KnowledgeManager, VectorStoreUnavailableError

    monkeypatch.setattr("martin.rag.knowledge_manager.get_vector_store", lambda: None)

    with pytest.raises(VectorStoreUnavailableError, match="尚未初始化"):
        KnowledgeManager().search_raw_vectors("肺结节")


def test_rebuild_marks_document_metadata_and_refreshes_cache(monkeypatch, tmp_path):
    from martin.rag.knowledge_manager import KnowledgeManager

    manager = KnowledgeManager()
    manager.data_dir = tmp_path / "uploads"
    manager.data_dir.mkdir()
    manager.manifest_path = manager.data_dir / "manifest.json"
    (manager.data_dir / "guide.txt").write_text("uploaded", encoding="utf-8")
    manager._write_manifest([{
        "document_id": "upload:test", "filename": "guide.txt", "stored_name": "guide.txt",
        "source_type": "upload", "status": "ready", "created_at": "", "chunk_count": 0,
        "deletable": True,
    }])
    monkeypatch.setattr(
        "martin.rag.knowledge_manager.load_knowledge_base",
        lambda *, strict=False: [Document(page_content="builtin", metadata={"source": "builtin.md"})],
    )
    monkeypatch.setattr("martin.rag.knowledge_manager.split_documents", lambda docs: docs)
    captured = {}
    monkeypatch.setattr(
        "martin.rag.knowledge_manager.create_vector_store",
        lambda docs, embeddings: captured.setdefault("documents", docs),
    )
    monkeypatch.setattr("martin.rag.knowledge_manager.reset_vector_store_cache", lambda: captured.setdefault("reset", True))
    monkeypatch.setattr("martin.rag.embeddings.get_embeddings", lambda: object())

    result = manager.rebuild_all()

    assert result == {"documents": 2, "chunks": 2}
    assert captured["reset"] is True
    assert captured["documents"][0].metadata["document_id"] == "builtin:builtin.md"
