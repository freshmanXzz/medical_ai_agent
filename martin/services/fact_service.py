"""Authorized business facts for attachments, findings and reports."""

import json
from pathlib import Path

from martin.db import transaction
from martin.repositories.attachments import AttachmentRepository
from martin.repositories.audit import AuditRepository
from martin.repositories.cases import CaseRepository
from martin.repositories.findings import FindingRepository
from martin.repositories.patients import PatientRepository
from martin.repositories.reports import ReportRepository
from martin.repositories.base import now_utc

from .access_service import AccessService


GENDER_TO_SEX = {
    "男": "male",
    "男性": "male",
    "女": "female",
    "女性": "female",
    "male": "male",
    "female": "female",
    "other": "other",
    "unknown": "unknown",
}


class FactService:
    def __init__(self, db_path: str | Path | None = None):
        self.db_path = db_path

    def update_clinical_context(
        self,
        doctor_id: str,
        case_id: str,
        *,
        age: int | None = None,
        gender: str | None = None,
        smoking_history: str | None = None,
        family_history: str | None = None,
        clinical_note: str | None = None,
    ) -> dict:
        if age is not None and not 0 <= age <= 130:
            raise ValueError("Age out of range")
        sex = GENDER_TO_SEX.get(gender) if gender is not None else None
        if gender is not None and sex is None:
            raise ValueError("Unknown gender")
        with transaction(self.db_path) as connection:
            access = AccessService(connection)
            case = access.get_case_authorized(doctor_id, case_id, write=True)
            if sex is not None:
                PatientRepository(connection).update_sex(case["patient_id"], sex)
            changes: dict[str, object] = {}
            if age is not None:
                changes["age_at_encounter_years"] = age
                changes["age_recorded_at"] = now_utc()
            if smoking_history is not None:
                changes["smoking_history"] = smoking_history
            if family_history is not None:
                changes["family_history"] = family_history
            if clinical_note is not None and clinical_note.strip():
                notes = json.loads(case["clinical_notes_json"] or "[]")
                notes.append(clinical_note.strip())
                changes["clinical_notes_json"] = json.dumps(notes, ensure_ascii=False)
            if changes:
                CaseRepository(connection).update_clinical_fields(case_id, changes)
            if changes or sex is not None:
                AuditRepository(connection).append(
                    "case", case_id, "clinical_context_updated", actor_user_id=doctor_id
                )
            return dict(CaseRepository(connection).get_by_id(case_id))

    def add_attachment(
        self, doctor_id: str, case_id: str, original_name: str, storage_path: str
    ) -> str:
        with transaction(self.db_path) as connection:
            AccessService(connection).get_case_authorized(doctor_id, case_id, write=True)
            attachments = AttachmentRepository(connection)
            existing = attachments.get_by_storage_path(case_id, storage_path)
            if existing:
                return existing["id"]
            attachment_id = attachments.create(
                case_id, original_name, storage_path, uploaded_by=doctor_id
            )
            AuditRepository(connection).append(
                "attachment", attachment_id, "created", actor_user_id=doctor_id
            )
            return attachment_id

    def record_analysis(
        self,
        doctor_id: str,
        thread_id: str,
        storage_path: str,
        nodules: list[dict],
        *,
        observed_at: str | None = None,
    ) -> list[str]:
        observed_at = observed_at or now_utc()
        with transaction(self.db_path) as connection:
            thread = AccessService(connection).get_thread_authorized(
                doctor_id, thread_id, write=True
            )
            attachment = AttachmentRepository(connection).get_by_storage_path(
                thread["case_id"], storage_path
            )
            if attachment is None:
                raise ValueError("Analyzed image is not a registered case attachment")
            findings = FindingRepository(connection)
            finding_ids = []
            for nodule in nodules:
                payload = {
                    key: nodule[key]
                    for key in ("index", "diameter", "score", "center", "dimensions", "anatomy")
                    if key in nodule
                }
                finding_ids.append(
                    findings.create(
                        thread["case_id"],
                        "nodule",
                        observed_at,
                        source_attachment_id=attachment["id"],
                        created_by=doctor_id,
                        anatomy=nodule.get("anatomy"),
                        diameter_mm=nodule.get("diameter"),
                        payload_json=json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    )
                )
            AttachmentRepository(connection).mark_analyzed(attachment["id"], observed_at)
            AuditRepository(connection).append(
                "attachment", attachment["id"], "analyzed", actor_user_id=doctor_id
            )
            return finding_ids

    def add_finding(
        self,
        doctor_id: str,
        case_id: str,
        finding_type: str,
        observed_at: str,
        *,
        source_attachment_id: str | None = None,
        anatomy: str | None = None,
        diameter_mm: float | None = None,
    ) -> str:
        with transaction(self.db_path) as connection:
            AccessService(connection).get_case_authorized(doctor_id, case_id, write=True)
            if source_attachment_id:
                attachment = AttachmentRepository(connection).get_by_id(source_attachment_id)
                if attachment is None or attachment["case_id"] != case_id:
                    raise ValueError("Attachment does not belong to this case")
            finding_id = FindingRepository(connection).create(
                case_id,
                finding_type,
                observed_at,
                source_attachment_id=source_attachment_id,
                created_by=doctor_id,
                anatomy=anatomy,
                diameter_mm=diameter_mm,
            )
            AuditRepository(connection).append(
                "finding", finding_id, "created", actor_user_id=doctor_id
            )
            return finding_id

    def list_findings_by_patient(self, doctor_id: str, patient_id: str) -> list[dict]:
        with transaction(self.db_path) as connection:
            AccessService(connection).get_patient_authorized(doctor_id, patient_id)
            return [dict(row) for row in FindingRepository(connection).list_by_patient(patient_id)]

    def list_findings_by_case(self, doctor_id: str, case_id: str) -> list[dict]:
        with transaction(self.db_path) as connection:
            AccessService(connection).get_case_authorized(doctor_id, case_id)
            return [dict(row) for row in FindingRepository(connection).list_by_case(case_id)]

    def list_attachments_by_case(self, doctor_id: str, case_id: str) -> list[dict]:
        with transaction(self.db_path) as connection:
            AccessService(connection).get_case_authorized(doctor_id, case_id)
            return [dict(row) for row in AttachmentRepository(connection).list_by_case(case_id)]

    def add_report(self, doctor_id: str, case_id: str, content: str) -> str:
        with transaction(self.db_path) as connection:
            AccessService(connection).get_case_authorized(doctor_id, case_id, write=True)
            report_id = ReportRepository(connection).create_version(
                case_id, content, created_by=doctor_id
            )
            AuditRepository(connection).append(
                "report", report_id, "created", actor_user_id=doctor_id
            )
            return report_id

    def list_reports_by_case(self, doctor_id: str, case_id: str) -> list[dict]:
        with transaction(self.db_path) as connection:
            AccessService(connection).get_case_authorized(doctor_id, case_id)
            return [dict(row) for row in ReportRepository(connection).list_by_case(case_id)]
