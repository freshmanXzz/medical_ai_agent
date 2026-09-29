"""Lifecycle for the independent LangGraph SqliteStore database."""

import os
from pathlib import Path

from langgraph.store.sqlite import SqliteStore


PROJECT_ROOT = Path(__file__).resolve().parents[2]
_default_context = None
_default_store: SqliteStore | None = None


def get_memory_db_path() -> Path:
    configured = os.environ.get("MARTIN_MEMORY_DB_PATH")
    path = Path(configured).expanduser() if configured else Path("data/memory.sqlite")
    return path if path.is_absolute() else PROJECT_ROOT / path


def get_default_store() -> SqliteStore:
    global _default_context, _default_store
    if _default_store is None:
        path = get_memory_db_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        context = SqliteStore.from_conn_string(str(path))
        store = context.__enter__()
        try:
            store.setup()
        except Exception:
            context.__exit__(None, None, None)
            raise
        _default_context = context
        _default_store = store
    return _default_store


def close_default_store() -> None:
    global _default_context, _default_store
    if _default_context is not None:
        _default_context.__exit__(None, None, None)
        _default_context = None
        _default_store = None
