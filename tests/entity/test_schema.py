"""Entity V0 schema contracts."""

import sqlite3

import pytest

from martin.db import connect, init_schema, transaction


EXPECTED_TABLES = {
    "users",
    "auth_sessions",
    "patients",
    "cases",
    "threads",
    "doctor_patient_access",
    "attachments",
    "findings",
    "reports",
    "case_change_audit",
}

EXPECTED_INDEXES = {
    "idx_auth_sessions_user",
    "idx_auth_sessions_token_hash",
    "idx_cases_patient",
    "idx_threads_doctor",
    "idx_threads_case",
    "idx_access_patient",
    "idx_attachments_case",
    "idx_attachments_case_storage_path",
    "idx_findings_case",
    "idx_findings_observed_at",
    "idx_reports_case",
    "idx_case_change_target",
    "idx_case_change_actor",
}


def test_schema_is_idempotent(db_path):
    init_schema(db_path)
    init_schema(db_path)
    with connect(db_path) as connection:
        count = connection.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='users'"
        ).fetchone()[0]
    assert count == 1


def test_foreign_keys_are_enabled(db_path):
    for _ in range(2):
        connection = connect(db_path)
        try:
            assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    """INSERT INTO cases (id, patient_id, created_at, updated_at)
                       VALUES ('orphan', 'missing', 'now', 'now')"""
                )
        finally:
            connection.close()


def test_expected_tables_exist(connection):
    tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    }
    assert tables == EXPECTED_TABLES
    assert "memories" not in tables


def test_expected_indexes_exist(connection):
    indexes = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        )
    }
    assert EXPECTED_INDEXES <= indexes


def test_invalid_role_rejected(connection):
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """INSERT INTO users
               (id, username, display_name, role, password_hash, created_at, updated_at)
               VALUES ('U-invalid', 'invalid', 'Invalid', 'admin', 'hash', 'now', 'now')"""
        )


def test_invalid_access_level_rejected(connection):
    connection.execute(
        """INSERT INTO users
           (id, username, display_name, role, password_hash, created_at, updated_at)
           VALUES ('D-test', 'test', 'Test', 'doctor', 'hash', 'now', 'now')"""
    )
    connection.execute(
        """INSERT INTO patients (id, name, created_at, updated_at)
           VALUES ('P-test', 'Patient', 'now', 'now')"""
    )
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """INSERT INTO doctor_patient_access
               (doctor_id, patient_id, access_level, created_at)
               VALUES ('D-test', 'P-test', 'all', 'now')"""
        )


def test_transaction_rolls_back_on_error(db_path):
    with pytest.raises(RuntimeError, match="abort"):
        with transaction(db_path) as connection:
            connection.execute(
                """INSERT INTO patients (id, name, created_at, updated_at)
                   VALUES ('P-rollback', 'Test', 'now', 'now')"""
            )
            raise RuntimeError("abort")
    with connect(db_path) as connection:
        assert connection.execute(
            "SELECT 1 FROM patients WHERE id = 'P-rollback'"
        ).fetchone() is None


def test_schema_adds_fact_columns_to_existing_v0_database(tmp_path):
    path = tmp_path / "legacy.sqlite"
    with sqlite3.connect(path) as connection:
        connection.execute(
            """CREATE TABLE cases (
               id TEXT PRIMARY KEY, patient_id TEXT NOT NULL,
               case_type TEXT NOT NULL, status TEXT NOT NULL,
               created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"""
        )
        connection.execute(
            """CREATE TABLE attachments (
               id TEXT PRIMARY KEY, case_id TEXT NOT NULL, uploaded_by TEXT,
               original_name TEXT NOT NULL, storage_path TEXT NOT NULL,
               mime_type TEXT, sha256 TEXT, created_at TEXT NOT NULL)"""
        )
    init_schema(path)
    init_schema(path)
    with connect(path) as connection:
        case_columns = {row["name"] for row in connection.execute("PRAGMA table_info(cases)")}
        attachment_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(attachments)")
        }
    assert {
        "age_at_encounter_years",
        "age_recorded_at",
        "smoking_history",
        "family_history",
        "clinical_notes_json",
    } <= case_columns
    assert "analyzed_at" in attachment_columns
