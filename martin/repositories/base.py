"""Shared repository connection and ID helpers."""

import sqlite3
import uuid
from datetime import datetime, timezone


def new_id() -> str:
    return str(uuid.uuid4())


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


class Repository:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection
