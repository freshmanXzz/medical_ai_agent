"""Plan T13/T14: real SQLite retrieval under synthetic embedding collisions.

The embedding intentionally ranks unrelated near duplicates together. This
checks bounded injection and trace coverage, not BGE relevance quality.
"""

import re
from dataclasses import replace

from langchain_core.embeddings import Embeddings

from martin.llm.context_budget import (
    begin_budget_scope,
    conservative_count,
    finish_budget_scope,
    select_context,
)
from martin.memory.budget_policy import BudgetPolicy
from martin.memory.models import MemoryCandidate
from martin.memory.router import MemoryRetrievalRouter
from martin.memory.scope import authorize_scope
from martin.memory.semantic import SemanticRetriever
from martin.memory.service import MemoryService
from martin.memory.vector_index import MemoryVectorIndex
from martin.memory.writer import MemoryWriter
from martin.services.thread_service import ThreadService


class CollisionEmbeddings(Embeddings):
    def embed_documents(self, texts):
        return [[1.0, 0.0] for _ in texts]

    def embed_query(self, text):
        return [1.0, 0.0]


def test_t13_near_duplicate_retrieval_flood_keeps_facts_and_explains_omissions(
    entity_db,
    tmp_path,
):
    service = MemoryService(entity_db)
    thread = ThreadService(entity_db).create_thread("D001", "C002")
    scope = authorize_scope("D001", thread, entity_db)
    index = MemoryVectorIndex(
        tmp_path / "flood-vectors.sqlite",
        embeddings=CollisionEmbeddings(),
        dims=2,
    )
    try:
        writer = MemoryWriter(service, index)
        # These are distinct historical occurrences, deliberately similar words.
        # Clinical deduplication must retain them even with colliding embeddings.
        for batch in range(3):
            writer.write(
                scope,
                [
                    MemoryCandidate(
                        "historical_discussion",
                        f"unrelated filing workflow repeated discussion {number:02d}",
                        logical_key=f"noise-{number:02d}",
                        observed_at="2026-06-01",
                    )
                    for number in range(batch * 20, (batch + 1) * 20)
                ],
                source_type="thread",
                source_id=thread,
                provenance={
                    "kind": "api_submission",
                    "actor_id": "D001",
                    "actor_role": "doctor",
                    "submission_id": f"batch-{batch}",
                    "thread_id": thread,
                },
            )
        assert len(service.list_records(scope)) == 60
        semantic = SemanticRetriever(service, index)
        retrieved = semantic.retrieve(scope, "why target lesion measurement", limit=20)
        assert retrieved["available"]
        assert len(retrieved["records"]) == 20
        assert len({row["memory_id"] for row in retrieved["records"]}) == 20

        context = MemoryRetrievalRouter(service, semantic=semantic).retrieve(
            "D001",
            thread,
            "为什么当前测量是8mm",
            limit=20,
        )
        items = context.budget_items("qa")
        optional = next(
            item
            for item in items
            if item.reference.startswith("SEMANTIC HISTORICAL DISCUSSIONS:")
        )
        # Simulate the same retrieval hit arriving twice; it must be traceable.
        token = begin_budget_scope("qa", policy=BudgetPolicy())
        try:
            selected = select_context([*items, optional], available=2500, task="qa")
        finally:
            trace = finish_budget_scope(token)
        assert conservative_count(selected.text) <= 2500
        assert "CURRENT CASE FACTS:F002" in selected.selected_ids
        assert re.search(r'"diameter_mm"\s*:\s*8\.0', selected.text)
        assert re.search(r'"observed_at"\s*:\s*"2026-09-01', selected.text)
        assert len(selected.selected_ids) == len(set(selected.selected_ids))
        assert any(row["reason"] == "duplicate" for row in trace["items"])
        assert any(row["reason"] == "budget_exceeded" for row in trace["items"])
        allocated = {
            row["item_id"] for row in trace["items"] if row["stage"] == "allocation"
        }
        assert allocated == {item.reference for item in items}
        assert selected.omitted_ids
        # Budget pruning must not destroy raw sources or current business facts.
        assert len(service.list_records(scope)) == 60
        assert (
            service.snapshot_for_thread("D001", thread).current_findings[0][
                "diameter_mm"
            ]
            == 8.0
        )
    finally:
        index.close()


def test_t14_three_task_profiles_share_limit_but_prioritize_different_pools():
    from martin.llm.context_budget import BudgetItem

    quotas = {
        "qa": {"rag": 90, "memory": 0, "summary": 0, "history": 10},
        "report": {"rag": 0, "memory": 90, "summary": 0, "history": 10},
        "followup": {"rag": 0, "memory": 90, "summary": 0, "history": 10},
        "default": {"rag": 25, "memory": 25, "summary": 20, "history": 30},
    }
    policy = replace(BudgetPolicy(), category_quotas=quotas)
    items = [
        BudgetItem("history-reason", "memory", "m" * 400),
        BudgetItem("guideline", "rag", "r" * 400),
    ]
    selected = {
        task: select_context(items, available=600, task=task, policy=policy)
        for task in ("qa", "report", "followup")
    }
    assert selected["qa"].selected_ids == ["guideline"]
    assert selected["report"].selected_ids == ["history-reason"]
    assert selected["followup"].selected_ids == ["history-reason"]
    assert all(conservative_count(row.text) <= 600 for row in selected.values())
