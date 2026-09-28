"""Opaque server-side doctor sessions backed by app.sqlite."""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from martin.db import transaction
from martin.repositories.auth_sessions import AuthSessionRepository
from martin.repositories.users import UserRepository

from .passwords import verify_password


SESSION_HOURS = 12


@dataclass(frozen=True)
class DoctorIdentity:
    id: str
    username: str
    display_name: str


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class SessionService:
    def __init__(self, db_path: str | Path | None = None):
        self.db_path = db_path

    def login(self, username: str, password: str) -> tuple[str, DoctorIdentity] | None:
        with transaction(self.db_path) as connection:
            user = UserRepository(connection).get_by_username(username)
            if not user or not user["is_active"]:
                return None
            if not verify_password(user["password_hash"], password):
                return None
            token = secrets.token_urlsafe(32)
            expires_at = (datetime.now(timezone.utc) + timedelta(hours=SESSION_HOURS)).isoformat()
            AuthSessionRepository(connection).create(
                user["id"], _token_hash(token), expires_at
            )
            return token, DoctorIdentity(user["id"], user["username"], user["display_name"])

    def authenticate(self, token: str | None) -> DoctorIdentity | None:
        if not token:
            return None
        with transaction(self.db_path) as connection:
            session = AuthSessionRepository(connection).get_by_token_hash(_token_hash(token))
            if not session or session["revoked_at"]:
                return None
            if datetime.fromisoformat(session["expires_at"]) <= datetime.now(timezone.utc):
                return None
            user = UserRepository(connection).get_by_id(session["user_id"])
            if not user or not user["is_active"]:
                return None
            return DoctorIdentity(user["id"], user["username"], user["display_name"])

    def logout(self, token: str | None) -> bool:
        if not token:
            return False
        with transaction(self.db_path) as connection:
            sessions = AuthSessionRepository(connection)
            session = sessions.get_by_token_hash(_token_hash(token))
            return bool(session and sessions.revoke(session["id"]))
