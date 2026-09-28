"""User persistence; no request identity or authorization decisions here."""

from .base import Repository, new_id, now_utc


class UserRepository(Repository):
    def create(
        self,
        username: str,
        display_name: str,
        password_hash: str,
        *,
        user_id: str | None = None,
    ) -> str:
        user_id = user_id or new_id()
        now = now_utc()
        self.connection.execute(
            """INSERT INTO users
               (id, username, display_name, role, password_hash, created_at, updated_at)
               VALUES (?, ?, ?, 'doctor', ?, ?, ?)""",
            (user_id, username, display_name, password_hash, now, now),
        )
        return user_id

    def get_by_id(self, user_id: str):
        return self.connection.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()

    def get_by_username(self, username: str):
        return self.connection.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()

    def deactivate(self, user_id: str) -> bool:
        cursor = self.connection.execute(
            "UPDATE users SET is_active = 0, updated_at = ? WHERE id = ?",
            (now_utc(), user_id),
        )
        return cursor.rowcount == 1
