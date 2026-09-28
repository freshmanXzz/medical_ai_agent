"""Pure SQL repository contracts on an isolated Entity V0 database."""

import uuid

from martin.db import connect, transaction
from martin.repositories.access import AccessRepository
from martin.repositories.attachments import AttachmentRepository
from martin.repositories.audit import AuditRepository
from martin.repositories.auth_sessions import AuthSessionRepository
from martin.repositories.cases import CaseRepository
from martin.repositories.findings import FindingRepository
from martin.repositories.patients import PatientRepository
from martin.repositories.reports import ReportRepository
from martin.repositories.threads import ThreadRepository
from martin.repositories.users import UserRepository


def test_repository_crud(seeded_db_path):
    with transaction(seeded_db_path) as connection:
        users = UserRepository(connection)
        patients = PatientRepository(connection)
        cases = CaseRepository(connection)
        threads = ThreadRepository(connection)
        access = AccessRepository(connection)
        attachments = AttachmentRepository(connection)
        findings = FindingRepository(connection)
        reports = ReportRepository(connection)
        audits = AuditRepository(connection)
        sessions = AuthSessionRepository(connection)

        doctor_id = users.create("doctor_c", "Doctor C", "argon2-hash")
        patient_id = patients.create("Synthetic Patient", sex="unknown")
        case_id = cases.create(patient_id)
        thread_id = threads.create(doctor_id, case_id)
        access.grant(doctor_id, patient_id, access_level="read_only")
        attachment_id = attachments.create(case_id, "scan.nii.gz", "synthetic/scan")
        finding_id = findings.create(
            case_id,
            "nodule",
            "2026-09-28",
            source_attachment_id=attachment_id,
            diameter_mm=8.0,
        )
        report_id = reports.create_version(case_id, "Synthetic report")
        audit_id = audits.append("case", case_id, "created", actor_user_id=doctor_id)
        session_id = sessions.create(doctor_id, "hashed-token", "2099-01-01T00:00:00+00:00")

        for identifier in (
            doctor_id,
            patient_id,
            case_id,
            thread_id,
            attachment_id,
            finding_id,
            report_id,
            audit_id,
            session_id,
        ):
            uuid.UUID(identifier)

        assert users.get_by_username("doctor_c")["id"] == doctor_id
        assert patients.get_by_id(patient_id)["name"] == "Synthetic Patient"
        assert cases.get_by_id(case_id)["patient_id"] == patient_id
        assert [row["id"] for row in cases.list_by_patient(patient_id)] == [case_id]
        assert threads.get_by_id(thread_id)["doctor_id"] == doctor_id
        assert [row["id"] for row in threads.list_by_case(case_id)] == [thread_id]
        assert access.get_access(doctor_id, patient_id)["access_level"] == "read_only"
        assert attachments.get_by_id(attachment_id)["case_id"] == case_id
        assert [row["id"] for row in attachments.list_by_case(case_id)] == [
            attachment_id
        ]
        assert findings.get_by_id(finding_id)["diameter_mm"] == 8.0
        assert [row["id"] for row in findings.list_by_patient(patient_id)] == [
            finding_id
        ]
        assert reports.get_latest(case_id)["id"] == report_id
        assert audits.list_for_target("case", case_id)[0]["id"] == audit_id
        assert sessions.get_by_token_hash("hashed-token")["id"] == session_id
        assert sessions.revoke(session_id)
        assert users.deactivate(doctor_id)

    with connect(seeded_db_path) as connection:
        assert UserRepository(connection).get_by_id(doctor_id)["is_active"] == 0
        assert AuthSessionRepository(connection).get_by_id(session_id)["revoked_at"]
        assert FindingRepository(connection).list_by_case(case_id)[0]["id"] == finding_id


def test_repository_uses_caller_transaction(db_path):
    try:
        with transaction(db_path) as connection:
            PatientRepository(connection).create("Rolled back", patient_id="P-rollback")
            raise RuntimeError("abort")
    except RuntimeError:
        pass
    with connect(db_path) as connection:
        assert PatientRepository(connection).get_by_id("P-rollback") is None
