"""Patient longitudinal observations and CaseContext conversion."""

import json

from martin.db import connect
from martin.services.fact_service import FactService


def test_two_observations_do_not_overwrite(entity_db):
    service = FactService(entity_db)
    observations = service.list_findings_by_patient("D001", "P001")
    assert [(row["id"], row["diameter_mm"]) for row in observations] == [
        ("F001", 6.0),
        ("F002", 8.0),
    ]
    assert observations[0]["observed_at"] < observations[1]["observed_at"]


def test_clinical_context_preserves_age_without_fabricating_birth_date(entity_db):
    service = FactService(entity_db)
    case = service.update_clinical_context(
        "D001",
        "C001",
        age=62,
        gender="男",
        smoking_history="吸烟 10 年",
        family_history="无家族史",
        clinical_note="合成测试备注",
    )
    assert case["age_at_encounter_years"] == 62
    assert case["age_recorded_at"]
    assert case["smoking_history"] == "吸烟 10 年"
    assert case["family_history"] == "无家族史"
    assert json.loads(case["clinical_notes_json"]) == ["合成测试备注"]
    with connect(entity_db) as connection:
        patient = connection.execute(
            "SELECT sex, birth_date FROM patients WHERE id = 'P001'"
        ).fetchone()
    assert tuple(patient) == ("male", None)


def test_case_fact_api_requires_doctor_and_preserves_versions(entity_client, entity_db):
    assert entity_client.get("/api/patients/P001/findings").status_code == 401
    assert entity_client.post(
        "/api/auth/login",
        json={"username": "doctor_a", "password": "TestDoctorA!2026"},
    ).status_code == 200
    updated = entity_client.patch(
        "/api/cases/C001/clinical-context",
        json={"age": 62, "gender": "女", "clinical_note": "合成备注"},
    )
    assert updated.status_code == 200
    assert updated.json()["age_at_encounter_years"] == 62
    created = entity_client.post(
        "/api/cases/C001/findings",
        json={
            "finding_type": "nodule",
            "observed_at": "2026-09-28T00:00:00+00:00",
            "diameter_mm": 9.0,
        },
    )
    assert created.status_code == 200
    findings = entity_client.get("/api/patients/P001/findings").json()
    assert [row["diameter_mm"] for row in findings] == [6.0, 8.0, 9.0]
    for content in ("Synthetic v1", "Synthetic v2"):
        assert entity_client.post(
            "/api/cases/C001/reports", json={"content": content}
        ).status_code == 200
    reports = entity_client.get("/api/cases/C001/reports").json()
    assert [(row["version"], row["content"]) for row in reports] == [
        (1, "Synthetic v1"),
        (2, "Synthetic v2"),
    ]
    entity_client.post(
        "/api/auth/login",
        json={"username": "doctor_b", "password": "TestDoctorB!2026"},
    )
    assert entity_client.get("/api/patients/P001/findings").status_code == 403
    assert entity_client.get("/api/cases/C001/reports").status_code == 403
