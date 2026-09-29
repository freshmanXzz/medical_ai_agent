"""Entity V0 acceptance with real LangGraph SQLite checkpoints."""

from typing import TypedDict

import pytest
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from martin.agent.sessions import CheckpointDeletionError
from martin.db import connect
from martin.services.thread_service import ThreadService


class _GraphState(TypedDict):
    value: int


def _save_checkpoint(saver, thread_id):
    graph = StateGraph(_GraphState)
    graph.add_node("increment", lambda state: {"value": state["value"] + 1})
    graph.add_edge(START, "increment")
    graph.add_edge("increment", END)
    runnable = graph.compile(checkpointer=saver)
    config = {"configurable": {"thread_id": thread_id}}
    assert runnable.invoke({"value": 0}, config)["value"] == 1
    assert saver.get_tuple(config) is not None
    return config


def test_thread_delete_removes_business_row_and_real_checkpoint(seeded_db_path, tmp_path):
    saver_path = tmp_path / "sessions.sqlite"
    with SqliteSaver.from_conn_string(str(saver_path)) as saver:
        service = ThreadService(seeded_db_path, saver)
        thread_id = service.create_thread("D001", "C001")
        config = _save_checkpoint(saver, thread_id)
        service.delete_thread("D001", thread_id)
        assert saver.get_tuple(config) is None
    with connect(seeded_db_path) as connection:
        assert connection.execute(
            "SELECT 1 FROM threads WHERE id = ?", (thread_id,)
        ).fetchone() is None
        assert connection.execute(
            "SELECT 1 FROM cases WHERE id = 'C001'"
        ).fetchone() is not None
        assert connection.execute(
            """SELECT action FROM case_change_audit
               WHERE target_type = 'thread' AND target_id = ?""",
            (thread_id,),
        ).fetchone()[0] == "deleted"


def test_checkpoint_failure_keeps_business_thread(seeded_db_path):
    class FailingSaver:
        def delete_thread(self, _thread_id):
            raise OSError("synthetic saver failure")

    service = ThreadService(seeded_db_path, FailingSaver())
    thread_id = service.create_thread("D001", "C001")
    with pytest.raises(CheckpointDeletionError, match="failed"):
        service.delete_thread("D001", thread_id)
    with connect(seeded_db_path) as connection:
        assert connection.execute(
            "SELECT 1 FROM threads WHERE id = ?", (thread_id,)
        ).fetchone() is not None


def test_unconfirmed_checkpoint_deletion_keeps_business_thread(seeded_db_path):
    class NoOpSaver:
        def delete_thread(self, _thread_id):
            pass

        def get_tuple(self, _config):
            return object()

    service = ThreadService(seeded_db_path, NoOpSaver())
    thread_id = service.create_thread("D001", "C001")
    with pytest.raises(CheckpointDeletionError, match="still exists"):
        service.delete_thread("D001", thread_id)
    with connect(seeded_db_path) as connection:
        assert connection.execute(
            "SELECT 1 FROM threads WHERE id = ?", (thread_id,)
        ).fetchone() is not None


def test_entity_coordinates_and_longitudinal_facts(seeded_db_path):
    with connect(seeded_db_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        users = connection.execute("SELECT id FROM users ORDER BY id").fetchall()
        cases = connection.execute(
            "SELECT id, patient_id FROM cases ORDER BY id"
        ).fetchall()
        access = connection.execute(
            "SELECT doctor_id, patient_id FROM doctor_patient_access ORDER BY doctor_id"
        ).fetchall()
        facts = connection.execute(
            """SELECT findings.id, findings.diameter_mm FROM findings
               JOIN cases ON cases.id = findings.case_id
               WHERE cases.patient_id = 'P001' ORDER BY findings.observed_at"""
        ).fetchall()
    assert "memories" not in tables
    assert [row[0] for row in users] == ["D001", "D002"]
    assert [tuple(row) for row in cases] == [
        ("C001", "P001"),
        ("C002", "P001"),
        ("C003", "P002"),
    ]
    assert [tuple(row) for row in access] == [("D001", "P001"), ("D002", "P002")]
    assert [tuple(row) for row in facts] == [("F001", 6.0), ("F002", 8.0)]
