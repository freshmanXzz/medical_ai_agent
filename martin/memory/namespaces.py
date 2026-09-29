"""Single source of namespace names for SqliteStore V1."""


def _id(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Memory namespace requires a non-empty entity ID")
    return value


def doctor_preferences_ns(doctor_id: str) -> tuple[str, ...]:
    return ("doctor", _id(doctor_id), "preferences")


def doctor_patient_private_ns(doctor_id: str, patient_id: str) -> tuple[str, ...]:
    return ("doctor", _id(doctor_id), "patient", _id(patient_id), "private")


def patient_memory_ns(patient_id: str) -> tuple[str, ...]:
    return ("patient", _id(patient_id), "memory")


def case_memory_ns(case_id: str) -> tuple[str, ...]:
    return ("case", _id(case_id), "memory")
