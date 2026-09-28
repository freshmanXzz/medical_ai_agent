"""Insert synthetic Entity V0 records with ``python -m scripts.seed_entity_v0``."""

import argparse
import os
from datetime import datetime, timezone
from pathlib import Path

from argon2 import PasswordHasher
from argon2.low_level import Type

from martin.db import init_schema, transaction


def seed_entity_v0(
    db_path: str | Path | None,
    *,
    doctor_a_password: str,
    doctor_b_password: str,
) -> None:
    """Seed deterministic fixture IDs without overwriting existing records."""
    if not doctor_a_password or not doctor_b_password:
        raise ValueError("Both demo doctor passwords are required")

    init_schema(db_path)
    now = datetime.now(timezone.utc).isoformat()
    hasher = PasswordHasher(type=Type.ID)
    with transaction(db_path) as connection:
        for user_id, username, display_name, password in (
            ("D001", "doctor_a", "Doctor A", doctor_a_password),
            ("D002", "doctor_b", "Doctor B", doctor_b_password),
        ):
            if connection.execute(
                "SELECT 1 FROM users WHERE id = ?", (user_id,)
            ).fetchone():
                continue
            connection.execute(
                """INSERT INTO users
                   (id, username, display_name, role, password_hash, created_at, updated_at)
                   VALUES (?, ?, ?, 'doctor', ?, ?, ?)""",
                (user_id, username, display_name, hasher.hash(password), now, now),
            )

        for patient_id, name in (
            ("P001", "Patient Alpha"),
            ("P002", "Patient Beta"),
        ):
            connection.execute(
                """INSERT INTO patients (id, name, created_at, updated_at)
                   VALUES (?, ?, ?, ?) ON CONFLICT(id) DO NOTHING""",
                (patient_id, name, now, now),
            )

        for case_id, patient_id in (
            ("C001", "P001"),
            ("C002", "P001"),
            ("C003", "P002"),
        ):
            connection.execute(
                """INSERT INTO cases (id, patient_id, created_at, updated_at)
                   VALUES (?, ?, ?, ?) ON CONFLICT(id) DO NOTHING""",
                (case_id, patient_id, now, now),
            )

        for doctor_id, patient_id in (("D001", "P001"), ("D002", "P002")):
            connection.execute(
                """INSERT INTO doctor_patient_access
                   (doctor_id, patient_id, access_level, created_at)
                   VALUES (?, ?, 'read_write', ?)
                   ON CONFLICT(doctor_id, patient_id) DO NOTHING""",
                (doctor_id, patient_id, now),
            )

        for finding_id, case_id, observed_at, diameter_mm in (
            ("F001", "C001", "2026-06-01T00:00:00+00:00", 6.0),
            ("F002", "C002", "2026-09-01T00:00:00+00:00", 8.0),
        ):
            connection.execute(
                """INSERT INTO findings
                   (id, case_id, finding_type, anatomy, diameter_mm,
                    observed_at, status, payload_json, created_at, updated_at)
                   VALUES (?, ?, 'nodule', 'RUL', ?, ?, 'confirmed',
                           '{"source":"synthetic_fixture"}', ?, ?)
                   ON CONFLICT(id) DO NOTHING""",
                (finding_id, case_id, diameter_mm, observed_at, now, now),
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", help="SQLite path (default: MARTIN_APP_DB_PATH)")
    args = parser.parse_args()
    password_a = os.environ.get("MARTIN_SEED_DOCTOR_A_PASSWORD")
    password_b = os.environ.get("MARTIN_SEED_DOCTOR_B_PASSWORD")
    if not password_a or not password_b:
        parser.error("Set both MARTIN_SEED_DOCTOR_A_PASSWORD and MARTIN_SEED_DOCTOR_B_PASSWORD")
    seed_entity_v0(
        args.db_path,
        doctor_a_password=password_a,
        doctor_b_password=password_b,
    )
    print("Seeded synthetic Entity V0 records")


if __name__ == "__main__":
    main()
