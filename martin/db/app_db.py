"""Connection and schema management for the business SQLite database."""

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def get_app_db_path() -> Path:
    """Resolve the business database path without depending on the shell cwd."""
    configured = os.environ.get("MARTIN_APP_DB_PATH")
    path = Path(configured).expanduser() if configured else Path("data/app.sqlite")
    return path if path.is_absolute() else PROJECT_ROOT / path


def connect(path: str | Path | None = None) -> sqlite3.Connection:
    """Open a connection with foreign key enforcement on every connection."""
    db_path = Path(path) if path is not None else get_app_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path, timeout=5.0)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
    except Exception:
        connection.close()
        raise
    return connection


def init_schema(path: str | Path | None = None) -> None:
    """Create the ten Entity V0 tables and indexes; safe to call repeatedly."""
    connection = connect(path)
    try:
        connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        migrations = {
            "users": {
                "budget_admin": "INTEGER NOT NULL DEFAULT 0 CHECK (budget_admin IN (0, 1))",
            },
            "cases": {
                "age_at_encounter_years": "INTEGER CHECK (age_at_encounter_years IS NULL OR age_at_encounter_years BETWEEN 0 AND 130)",
                "age_recorded_at": "TEXT",
                "smoking_history": "TEXT",
                "family_history": "TEXT",
                "clinical_notes_json": "TEXT NOT NULL DEFAULT '[]'",
            },
            "attachments": {"analyzed_at": "TEXT"},
        }
        with connection:
            for table, columns in migrations.items():
                existing = {
                    row["name"] for row in connection.execute(f"PRAGMA table_info({table})")
                }
                for name, declaration in columns.items():
                    if name not in existing:
                        connection.execute(
                            f"ALTER TABLE {table} ADD COLUMN {name} {declaration}"
                        )
    finally:
        connection.close()


@contextmanager
def transaction(path: str | Path | None = None) -> Iterator[sqlite3.Connection]:
    """Keep local fact/permission commits outside a guarded model dispatch.

    The shared reentrant lock also lets the dispatch validator read the same
    database while holding it. This is a process-local coordination boundary;
    it does not claim serialization across multiple server workers.
    """
    from martin.memory.lifecycle import write_lock

    with write_lock:
        connection = connect(path)
        try:
            with connection:
                yield connection
        finally:
            connection.close()
