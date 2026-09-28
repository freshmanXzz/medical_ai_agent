"""Patient identifiers cannot be read without a current doctor grant."""


def test_patient_access_matrix(entity_client):
    entity_client.post(
        "/api/auth/login",
        json={"username": "doctor_b", "password": "TestDoctorB!2026"},
    )
    assert entity_client.get("/api/patients/P001").status_code == 403
    own = entity_client.get("/api/patients/P002")
    assert own.status_code == 200
    assert own.json()["id"] == "P002"
    assert entity_client.get("/api/patients/missing").status_code == 404


def test_patient_reads_require_login(entity_client):
    assert entity_client.get("/api/patients/P001").status_code == 401
    assert entity_client.get("/api/cases/C001").status_code == 401
    assert entity_client.get("/api/sessions").status_code == 401
