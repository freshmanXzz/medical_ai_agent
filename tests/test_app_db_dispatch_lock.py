"""Business mutations share the single-process memory dispatch boundary."""

import threading

import pytest

from martin.db.app_db import connect, transaction
from martin.memory.lifecycle import write_lock


def test_business_commit_waits_for_dispatch_and_releases_lock(tmp_path):
    path = tmp_path / "isolated.sqlite"
    with connect(path) as connection:
        connection.execute("CREATE TABLE facts (value INTEGER)")
    attempting = threading.Event()
    completed = threading.Event()
    failures = []

    def mutate():
        attempting.set()
        try:
            with transaction(path) as connection:
                connection.execute("INSERT INTO facts VALUES (9)")
        except BaseException as exc:
            failures.append(exc)
        finally:
            completed.set()

    with write_lock:
        # A fresh dispatch validator can read while holding the same RLock.
        with transaction(path) as connection:
            assert connection.execute("SELECT COUNT(*) FROM facts").fetchone()[0] == 0
        worker = threading.Thread(target=mutate)
        worker.start()
        assert attempting.wait(2)
        assert not completed.wait(0.1)
    assert completed.wait(2)
    worker.join(2)
    assert not failures
    with transaction(path) as connection:
        assert connection.execute("SELECT value FROM facts").fetchone()[0] == 9


def test_failed_transaction_rolls_back_and_unlocks(tmp_path):
    path = tmp_path / "isolated.sqlite"
    with transaction(path) as connection:
        connection.execute("CREATE TABLE facts (value INTEGER)")
    with pytest.raises(RuntimeError):
        with transaction(path) as connection:
            connection.execute("INSERT INTO facts VALUES (9)")
            raise RuntimeError("synthetic failure")
    with transaction(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM facts").fetchone()[0] == 0
