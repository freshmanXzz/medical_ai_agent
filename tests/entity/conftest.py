"""Isolated SQLite fixtures for Entity V0 tests."""

import sqlite3
from pathlib import Path
from typing import Iterator

import pytest

from martin.db import connect, init_schema
from scripts.seed_entity_v0 import seed_entity_v0


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "app.sqlite"
    init_schema(path)
    return path


@pytest.fixture
def connection(db_path: Path) -> Iterator[sqlite3.Connection]:
    opened = connect(db_path)
    try:
        yield opened
    finally:
        opened.close()


@pytest.fixture
def seeded_db_path(db_path: Path) -> Path:
    seed_entity_v0(
        db_path,
        doctor_a_password="TestDoctorA!2026",
        doctor_b_password="TestDoctorB!2026",
    )
    return db_path
