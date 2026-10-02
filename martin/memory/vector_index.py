"""A rebuildable semantic projection, isolated from exact memory and knowledge."""

from __future__ import annotations

import os
from pathlib import Path
from threading import RLock
from typing import Any, Iterable

from langgraph.store.sqlite import SqliteStore

from martin.config import config
from martin.db import get_app_db_path

from .models import normalize_time
from .store import PROJECT_ROOT, get_memory_db_path


SEMANTIC_MEMORY_TYPES = frozenset(
    {"clinical_decision", "historical_discussion", "workflow_preference"}
)


def get_memory_vector_db_path() -> Path:
    configured = os.environ.get("MARTIN_MEMORY_VECTOR_DB_PATH")
    path = Path(configured).expanduser() if configured else Path(
        "data/memory_vectors.sqlite"
    )
    return path if path.is_absolute() else PROJECT_ROOT / path


def _path_identity(path: str | Path) -> str:
    return os.path.normcase(str(Path(path).expanduser().resolve()))


def _namespace(scope) -> tuple[str, ...]:
    doctor_id, patient_id = scope.doctor_id, scope.patient_id
    if not all(
        isinstance(value, str) and value.strip()
        for value in (doctor_id, patient_id)
    ):
        raise ValueError("Semantic memory requires doctor and patient identities")
    # SqliteStore serializes namespace components with a dot separator.
    if "." in doctor_id or "." in patient_id:
        raise ValueError("Semantic namespace identities cannot contain a dot")
    return ("memory_vector", doctor_id, patient_id)


class MemoryVectorIndex:
    """Native SQLite vector search; source records remain authoritative.

    Opening the embedding model and SQLite connection is deferred until use.
    A failed write leaves source memory intact and can be retried by ``sync``.
    """

    def __init__(self, db_path=None, *, embeddings=None, dims: int = 512):
        self.db_path = (
            Path(db_path) if db_path is not None else get_memory_vector_db_path()
        )
        self.embeddings = embeddings
        self.dims = dims
        self._context = None
        self._store = None
        self._lock = RLock()

    def _check_path(self, reserved_paths: Iterable[str | Path] = ()) -> None:
        reserved = [
            get_app_db_path(),
            get_memory_db_path(),
            PROJECT_ROOT / "data" / "sessions.sqlite",
            Path(config.chroma_persist_dir) / "chroma.sqlite3",
            *reserved_paths,
        ]
        identity = _path_identity(self.db_path)
        if any(identity == _path_identity(path) for path in reserved if path):
            raise ValueError("Memory vector database must use an independent file")

    def _open(self, reserved_paths: Iterable[str | Path] = ()):
        self._check_path(reserved_paths)
        if self._store is None:
            embeddings = self.embeddings
            if embeddings is None:
                from martin.rag.embeddings import get_embeddings

                embeddings = get_embeddings()
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            context = SqliteStore.from_conn_string(
                str(self.db_path),
                index={
                    "dims": self.dims,
                    "embed": embeddings,
                    "text_fields": ["text"],
                    "distance_type": "cosine",
                },
            )
            store = context.__enter__()
            try:
                store.setup()
            except Exception:
                context.__exit__(None, None, None)
                raise
            self._context, self._store = context, store
        return self._store

    @staticmethod
    def _projection(scope, record: dict[str, Any]) -> dict[str, Any]:
        if (
            record.get("doctor_id") != scope.doctor_id
            or record.get("patient_id") != scope.patient_id
            or record.get("status") != "active"
            or record.get("memory_type") not in SEMANTIC_MEMORY_TYPES
            or not isinstance(record.get("text"), str)
            or not record["text"].strip()
            or not record.get("memory_id")
        ):
            raise ValueError("Cannot index an inactive or out-of-scope memory")
        return {
            key: record.get(key)
            for key in (
                "memory_id", "memory_type", "doctor_id", "patient_id", "case_id",
                "thread_id", "source_type", "source_id", "created_at",
                "observed_at", "status", "text",
            )
        }

    def sync(self, scope, records, *, reserved_paths=()) -> None:
        """Reconcile one authorized scope, never the whole semantic database."""
        namespace = _namespace(scope)
        projections = {}
        for record in records:
            if (
                record.get("memory_type") not in SEMANTIC_MEMORY_TYPES
                or record.get("status") != "active"
                or record.get("patient_id") is None
                or not record.get("text", "").strip()
            ):
                continue
            projection = self._projection(scope, record)
            projection["observed_at"] = normalize_time(record["observed_at"])
            projection["index_dimensions"] = self.dims
            projection["index_format_version"] = 1
            projections[record["memory_id"]] = projection
        with self._lock:
            store = self._open(reserved_paths)
            existing = {}
            offset = 0
            while True:
                page = store.search(namespace, limit=1000, offset=offset)
                existing.update({item.key: item.value for item in page})
                if len(page) < 1000:
                    break
                offset += len(page)
            # Recreate missing derived vectors even when their cached text survived.
            indexed_keys = {
                row[0] for row in store.conn.execute(
                    "SELECT key FROM store_vectors WHERE prefix = ?",
                    (".".join(namespace),),
                )
            }
            for key in existing.keys() - projections.keys():
                store.delete(namespace, key)
            for key, projection in projections.items():
                if existing.get(key) != projection or key not in indexed_keys:
                    store.put(namespace, key, projection)

    def search(
        self, scope, query: str, *, limit: int = 5, case_id=None,
        observed_after=None, observed_before=None, memory_types=None,
    ) -> list[dict[str, Any]]:
        """Apply identity, status, type and time restrictions before Top-K."""
        namespace = _namespace(scope)
        if not query.strip() or limit < 1:
            return []
        types = tuple(memory_types or ("clinical_decision", "historical_discussion"))
        if any(kind not in SEMANTIC_MEMORY_TYPES for kind in types):
            raise ValueError("Unsupported semantic memory type")
        filters = {
            "doctor_id": scope.doctor_id,
            "patient_id": scope.patient_id,
            "status": "active",
        }
        if case_id is not None:
            filters["case_id"] = case_id
        time_filter = {}
        if observed_after is not None:
            time_filter["$gte"] = observed_after
        if observed_before is not None:
            time_filter["$lte"] = observed_before
        if time_filter:
            filters["observed_at"] = time_filter
        candidates = {}
        with self._lock:
            store = self._open()
            for memory_type in types:
                for item in store.search(
                    namespace, query=query,
                    filter={**filters, "memory_type": memory_type}, limit=limit,
                ):
                    if item.score is None:
                        continue
                    candidate = {"memory_id": item.key, "score": float(item.score)}
                    prior = candidates.get(item.key)
                    if prior is None or candidate["score"] > prior["score"]:
                        candidates[item.key] = candidate
        return sorted(
            candidates.values(),
            key=lambda item: (-item["score"], item["memory_id"]),
        )[:limit]

    def close(self) -> None:
        with self._lock:
            if self._context is not None:
                self._context.__exit__(None, None, None)
                self._context, self._store = None, None


_default_index: MemoryVectorIndex | None = None
_default_lock = RLock()


def get_default_vector_index() -> MemoryVectorIndex:
    global _default_index
    path = get_memory_vector_db_path()
    with _default_lock:
        if (
            _default_index is not None
            and _path_identity(_default_index.db_path) != _path_identity(path)
        ):
            _default_index.close()
            _default_index = None
        if _default_index is None:
            _default_index = MemoryVectorIndex(path)
        return _default_index


def close_default_vector_index() -> None:
    global _default_index
    with _default_lock:
        if _default_index is not None:
            _default_index.close()
            _default_index = None
