PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA busy_timeout = 5000;

CREATE TABLE IF NOT EXISTS users (
    id              TEXT PRIMARY KEY,
    username        TEXT NOT NULL UNIQUE,
    display_name    TEXT NOT NULL,
    role            TEXT NOT NULL CHECK (role IN ('doctor')),
    password_hash   TEXT NOT NULL,
    is_active       INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS auth_sessions (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    token_hash      TEXT NOT NULL UNIQUE,
    created_at      TEXT NOT NULL,
    expires_at      TEXT NOT NULL,
    last_seen_at    TEXT,
    revoked_at      TEXT,
    FOREIGN KEY (user_id)
        REFERENCES users(id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_auth_sessions_user
    ON auth_sessions(user_id);

CREATE INDEX IF NOT EXISTS idx_auth_sessions_token_hash
    ON auth_sessions(token_hash);

CREATE TABLE IF NOT EXISTS patients (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    sex             TEXT CHECK (sex IN ('male', 'female', 'other', 'unknown') OR sex IS NULL),
    birth_date      TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cases (
    id              TEXT PRIMARY KEY,
    patient_id      TEXT NOT NULL,
    case_type       TEXT NOT NULL DEFAULT 'general',
    status          TEXT NOT NULL DEFAULT 'open'
                    CHECK (status IN ('open', 'closed', 'archived')),
    age_at_encounter_years INTEGER CHECK (age_at_encounter_years IS NULL OR age_at_encounter_years BETWEEN 0 AND 130),
    age_recorded_at TEXT,
    smoking_history TEXT,
    family_history TEXT,
    clinical_notes_json TEXT NOT NULL DEFAULT '[]',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    FOREIGN KEY (patient_id)
        REFERENCES patients(id)
        ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_cases_patient
    ON cases(patient_id);

CREATE TABLE IF NOT EXISTS threads (
    id              TEXT PRIMARY KEY,
    doctor_id       TEXT NOT NULL,
    case_id         TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'closed', 'archived')),
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    FOREIGN KEY (doctor_id)
        REFERENCES users(id)
        ON DELETE RESTRICT,
    FOREIGN KEY (case_id)
        REFERENCES cases(id)
        ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_threads_doctor
    ON threads(doctor_id);

CREATE INDEX IF NOT EXISTS idx_threads_case
    ON threads(case_id);

CREATE TABLE IF NOT EXISTS doctor_patient_access (
    doctor_id       TEXT NOT NULL,
    patient_id      TEXT NOT NULL,
    access_level    TEXT NOT NULL DEFAULT 'read_write'
                    CHECK (access_level IN ('read_only', 'read_write')),
    created_at      TEXT NOT NULL,
    PRIMARY KEY (doctor_id, patient_id),
    FOREIGN KEY (doctor_id)
        REFERENCES users(id)
        ON DELETE CASCADE,
    FOREIGN KEY (patient_id)
        REFERENCES patients(id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_access_patient
    ON doctor_patient_access(patient_id);

CREATE TABLE IF NOT EXISTS attachments (
    id              TEXT PRIMARY KEY,
    case_id         TEXT NOT NULL,
    uploaded_by     TEXT,
    original_name   TEXT NOT NULL,
    storage_path    TEXT NOT NULL,
    mime_type       TEXT,
    sha256          TEXT,
    analyzed_at     TEXT,
    created_at      TEXT NOT NULL,
    FOREIGN KEY (case_id)
        REFERENCES cases(id)
        ON DELETE CASCADE,
    FOREIGN KEY (uploaded_by)
        REFERENCES users(id)
        ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_attachments_case
    ON attachments(case_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_attachments_case_storage_path
    ON attachments(case_id, storage_path);

CREATE TABLE IF NOT EXISTS findings (
    id                  TEXT PRIMARY KEY,
    case_id             TEXT NOT NULL,
    source_attachment_id TEXT,
    created_by          TEXT,
    finding_type        TEXT NOT NULL,
    anatomy             TEXT,
    diameter_mm         REAL CHECK (diameter_mm IS NULL OR diameter_mm >= 0),
    observed_at         TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'confirmed'
                        CHECK (status IN ('draft', 'confirmed', 'superseded')),
    payload_json        TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    FOREIGN KEY (case_id)
        REFERENCES cases(id)
        ON DELETE CASCADE,
    FOREIGN KEY (source_attachment_id)
        REFERENCES attachments(id)
        ON DELETE SET NULL,
    FOREIGN KEY (created_by)
        REFERENCES users(id)
        ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_findings_case
    ON findings(case_id);

CREATE INDEX IF NOT EXISTS idx_findings_observed_at
    ON findings(observed_at);

CREATE TABLE IF NOT EXISTS reports (
    id              TEXT PRIMARY KEY,
    case_id         TEXT NOT NULL,
    created_by      TEXT,
    version         INTEGER NOT NULL CHECK (version >= 1),
    status          TEXT NOT NULL DEFAULT 'draft'
                    CHECK (status IN ('draft', 'final', 'superseded')),
    content         TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    finalized_at    TEXT,
    FOREIGN KEY (case_id)
        REFERENCES cases(id)
        ON DELETE CASCADE,
    FOREIGN KEY (created_by)
        REFERENCES users(id)
        ON DELETE SET NULL,
    UNIQUE (case_id, version)
);

CREATE INDEX IF NOT EXISTS idx_reports_case
    ON reports(case_id);

CREATE TABLE IF NOT EXISTS case_change_audit (
    id              TEXT PRIMARY KEY,
    actor_user_id   TEXT,
    target_type     TEXT NOT NULL,
    target_id       TEXT NOT NULL,
    action          TEXT NOT NULL,
    before_json     TEXT,
    after_json      TEXT,
    occurred_at     TEXT NOT NULL,
    FOREIGN KEY (actor_user_id)
        REFERENCES users(id)
        ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_case_change_target
    ON case_change_audit(target_type, target_id);

CREATE INDEX IF NOT EXISTS idx_case_change_actor
    ON case_change_audit(actor_user_id);
