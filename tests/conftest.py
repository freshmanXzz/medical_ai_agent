"""Shared isolated Entity V0 API fixtures."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import app
from martin.db import init_schema
from martin.memory.store import close_default_store
from martin.memory.vector_index import close_default_vector_index
from scripts.seed_entity_v0 import seed_entity_v0


@pytest.fixture
def entity_db(tmp_path: Path, monkeypatch) -> Path:
    db_path = tmp_path / "app.sqlite"
    monkeypatch.setenv("MARTIN_APP_DB_PATH", str(db_path))
    monkeypatch.setenv("MARTIN_MEMORY_DB_PATH", str(tmp_path / "memory.sqlite"))
    monkeypatch.setenv("MARTIN_MEMORY_VECTOR_DB_PATH", str(tmp_path / "memory_vectors.sqlite"))
    close_default_store()
    close_default_vector_index()
    init_schema(db_path)
    seed_entity_v0(
        db_path,
        doctor_a_password="TestDoctorA!2026",
        doctor_b_password="TestDoctorB!2026",
    )
    yield db_path
    close_default_store()
    close_default_vector_index()


@pytest.fixture
def entity_client(entity_db: Path):
    with TestClient(app) as client:
        yield client
