"""Opaque session token hash persistence; raw tokens never enter this table."""

from .base import Repository, new_id, now_utc


class AuthSessionRepository(Repository):
    def create(
        self,
        user_id: str,
        token_hash: str,
        expires_at: str,
        *,
        session_id: str | None = None,
    ) -> str:
        session_id = session_id or new_id()
        self.connection.execute(
            """INSERT INTO auth_sessions
               (id, user_id, token_hash, created_at, expires_at)
               VALUES (?, ?, ?, ?, ?)""",
            (session_id, user_id, token_hash, now_utc(), expires_at),
        )
        return session_id

    def get_by_id(self, session_id: str):
        return self.connection.execute(
            "SELECT * FROM auth_sessions WHERE id = ?", (session_id,)
        ).fetchone()

    def get_by_token_hash(self, token_hash: str):
        return self.connection.execute(
            "SELECT * FROM auth_sessions WHERE token_hash = ?", (token_hash,)
        ).fetchone()

    def revoke(self, session_id: str) -> bool:
        cursor = self.connection.execute(
            """UPDATE auth_sessions SET revoked_at = ?
               WHERE id = ? AND revoked_at IS NULL""",
            (now_utc(), session_id),
        )
        return cursor.rowcount == 1
