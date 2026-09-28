"""Minimal structured audit persistence for entity changes."""

from .base import Repository, new_id, now_utc


class AuditRepository(Repository):
    def append(
        self,
        target_type: str,
        target_id: str,
        action: str,
        *,
        actor_user_id: str | None = None,
        before_json: str | None = None,
        after_json: str | None = None,
        audit_id: str | None = None,
    ) -> str:
        audit_id = audit_id or new_id()
        self.connection.execute(
            """INSERT INTO case_change_audit
               (id, actor_user_id, target_type, target_id, action,
                before_json, after_json, occurred_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                audit_id,
                actor_user_id,
                target_type,
                target_id,
                action,
                before_json,
                after_json,
                now_utc(),
            ),
        )
        return audit_id

    def list_for_target(self, target_type: str, target_id: str):
        return self.connection.execute(
            """SELECT * FROM case_change_audit
               WHERE target_type = ? AND target_id = ? ORDER BY occurred_at, id""",
            (target_type, target_id),
        ).fetchall()
