"""Synthetic Entity V0 seed contracts."""

from argon2 import PasswordHasher

from martin.db import connect
from scripts.seed_entity_v0 import seed_entity_v0


def test_seed_contains_two_doctors(seeded_db_path):
    with connect(seeded_db_path) as connection:
        doctors = connection.execute(
            "SELECT id, username, role, password_hash FROM users ORDER BY id"
        ).fetchall()
    assert [(row["id"], row["username"], row["role"]) for row in doctors] == [
        ("D001", "doctor_a", "doctor"),
        ("D002", "doctor_b", "doctor"),
    ]
    hasher = PasswordHasher()
    assert hasher.verify(doctors[0]["password_hash"], "TestDoctorA!2026")
    assert hasher.verify(doctors[1]["password_hash"], "TestDoctorB!2026")
    assert "TestDoctorA!2026" not in doctors[0]["password_hash"]


def test_seed_access_matrix(seeded_db_path):
    with connect(seeded_db_path) as connection:
        patients = connection.execute("SELECT id, name FROM patients ORDER BY id").fetchall()
        cases = connection.execute("SELECT id, patient_id FROM cases ORDER BY id").fetchall()
        access = connection.execute(
            "SELECT doctor_id, patient_id, access_level FROM doctor_patient_access ORDER BY doctor_id"
        ).fetchall()
    assert [tuple(row) for row in patients] == [
        ("P001", "Patient Alpha"),
        ("P002", "Patient Beta"),
    ]
    assert [tuple(row) for row in cases] == [
        ("C001", "P001"),
        ("C002", "P001"),
        ("C003", "P002"),
    ]
    assert [tuple(row) for row in access] == [
        ("D001", "P001", "read_write"),
        ("D002", "P002", "read_write"),
    ]


def test_seed_is_idempotent(seeded_db_path):
    seed_entity_v0(
        seeded_db_path,
        doctor_a_password="TestDoctorA!2026",
        doctor_b_password="TestDoctorB!2026",
    )
    with connect(seeded_db_path) as connection:
        assert connection.execute("SELECT count(*) FROM users").fetchone()[0] == 2
        assert connection.execute("SELECT count(*) FROM patients").fetchone()[0] == 2
        assert connection.execute("SELECT count(*) FROM cases").fetchone()[0] == 3
        assert connection.execute("SELECT count(*) FROM doctor_patient_access").fetchone()[0] == 2
