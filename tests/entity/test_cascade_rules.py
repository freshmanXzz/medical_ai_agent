"""Database delete and version rules underlying the later service layer."""

import sqlite3

import pytest

from martin.db import connect, transaction
from martin.repositories.access import AccessRepository
from martin.repositories.attachments import AttachmentRepository
from martin.repositories.cases import CaseRepository
from martin.repositories.findings import FindingRepository
from martin.repositories.patients import PatientRepository
from martin.repositories.reports import ReportRepository
from martin.repositories.threads import ThreadRepository


def test_patient_delete_restricted_when_cases_exist(seeded_db_path):
    with pytest.raises(sqlite3.IntegrityError):
        with transaction(seeded_db_path) as connection:
            PatientRepository(connection).delete("P001")
    with connect(seeded_db_path) as connection:
        assert PatientRepository(connection).get_by_id("P001") is not None


def test_case_delete_restricted_when_threads_exist(seeded_db_path):
    with transaction(seeded_db_path) as connection:
        ThreadRepository(connection).create("D001", "C001")
    with pytest.raises(sqlite3.IntegrityError):
        with transaction(seeded_db_path) as connection:
            CaseRepository(connection).delete("C001")
    with connect(seeded_db_path) as connection:
        assert CaseRepository(connection).get_by_id("C001") is not None
        assert len(ThreadRepository(connection).list_by_case("C001")) == 1


def test_access_deleted_when_relationship_revoked(seeded_db_path):
    with transaction(seeded_db_path) as connection:
        access = AccessRepository(connection)
        assert access.revoke("D001", "P001")
        assert access.get_access("D001", "P001") is None
    with connect(seeded_db_path) as connection:
        assert PatientRepository(connection).get_by_id("P001") is not None


def test_attachment_delete_sets_finding_source_null(seeded_db_path):
    with transaction(seeded_db_path) as connection:
        attachments = AttachmentRepository(connection)
        findings = FindingRepository(connection)
        attachment_id = attachments.create("C001", "synthetic.nii.gz", "fixture")
        finding_id = findings.create(
            "C001", "nodule", "2026-09-28", source_attachment_id=attachment_id
        )
        assert attachments.delete(attachment_id)
        assert findings.get_by_id(finding_id)["source_attachment_id"] is None


def test_report_case_version_unique(seeded_db_path):
    with transaction(seeded_db_path) as connection:
        reports = ReportRepository(connection)
        first_id = reports.create_version("C001", "Version 1")
        second_id = reports.create_version("C001", "Version 2")
        assert reports.get_latest("C001")["id"] == second_id
        assert [row["version"] for row in reports.list_by_case("C001")] == [1, 2]
    with pytest.raises(sqlite3.IntegrityError):
        with transaction(seeded_db_path) as connection:
            ReportRepository(connection).create_version("C001", "Duplicate", version=1)
    with connect(seeded_db_path) as connection:
        assert [row["id"] for row in ReportRepository(connection).list_by_case("C001")] == [
            first_id,
            second_id,
        ]
