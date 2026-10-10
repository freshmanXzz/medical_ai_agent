"""Repeatable synthetic P1 projection comparison against the saved V2.1 source.

No network, credentials, live database or image data is used. Counts here are
conservative UTF-8 estimates; real provider usage belongs to live acceptance.
"""

import argparse
import dataclasses
import hashlib
import json
import os
import statistics
import sys
import time
import types
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
RUN = REPO / "tmp/v22-p1-projections"

from martin.llm.context_budget import (
    BudgetItem,
    ContextBudgetExceeded,
    begin_budget_scope,
    conservative_count,
    count_payload,
    finish_budget_scope,
    select_context,
)
from martin.memory.budget_policy import BudgetPolicy
from martin.memory.context import MemorySnapshot
from martin.memory.router import MemoryContext, RetrievalPlan


def baseline_class():
    folder = REPO / "validation_scripts/baselines/memory_v21"
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    source = (folder / "router.py").read_bytes()
    if (
        hashlib.sha256(source).hexdigest()
        != manifest["files"]["martin/memory/router.py"]
    ):
        raise ValueError("V2.1 baseline fixture hash changed")
    module = types.ModuleType("martin.memory._v21_baseline_projection")
    module.__package__ = "martin.memory"
    sys.modules[module.__name__] = module
    exec(compile(source, "<saved-v21-router>", "exec"), module.__dict__)
    return module.MemoryContext, manifest["head"]


def dataset():
    current = {
        "finding_id": "F002",
        "diameter_mm": 8.0,
        "observed_at": "2026-09-01T00:00:00+00:00",
        "status": "confirmed",
    }
    old = {
        "finding_id": "F001",
        "diameter_mm": 6.0,
        "observed_at": "2024-06-01T00:00:00+00:00",
        "status": "confirmed",
    }
    records = [
        {
            "memory_id": f"M{i:02}",
            "memory_type": "historical_discussion",
            "text": f"第{i}次医生讨论：等待原始影像复核；这是讨论理由，不是确认诊断。",
            "doctor_id": "D001",
            "patient_id": "P001",
            "case_id": "C002",
            "observed_at": f"2026-06-{i+1:02}T00:00:00+00:00",
            "status": "active",
            "authority": "doctor_context",
            "source_id": f"T{i:02}",
            "provenance": {
                "kind": "api_submission",
                "submission_id": f"S{i:02}",
                "actor_role": "doctor",
                "actor_id": "D001",
            },
        }
        for i in range(12)
    ]
    conflict = {
        "source_finding_id": "F002",
        "source_memory_id": "C09",
        "field": "diameter_mm",
        "business_value": 8.0,
        "proposed_value": 9.0,
        "status": "conflict",
        "authority": "unverified_claim",
    }
    snapshot = MemorySnapshot(
        "C002",
        "P001",
        current_findings=[current],
        historical_observations=[old],
        typed_records=records,
        patient_facts={"sex": "male", "age_at_encounter_years": 55},
    )
    summary = {
        "available": True,
        "requested": True,
        "kind": "rolling_summary",
        "source_memory_ids": [r["memory_id"] for r in records],
        "sources": [
            {
                "memory_id": r["memory_id"],
                "observed_at": r["observed_at"],
                "status": r["status"],
                "authority": r["authority"],
            }
            for r in records
        ],
        "text": "\n".join(
            f"[{r['memory_id']};{r['observed_at']}] 医生讨论：{r['text']}"
            for r in records
        ),
    }
    contexts = []
    for task, query in (
        ("qa", "请列出当前已确认大小"),
        ("report", "生成报告，仅使用确认事实"),
        ("followup", "比较2024和2026观察，并解释历史讨论原因"),
    ):
        plan = RetrievalPlan.for_query(query)
        temporal = {
            "events": (
                [dict(old, current=False), dict(current, current=True)]
                if plan.temporal
                else []
            ),
            "changes": [],
            "warnings": ["lesion_identity_unconfirmed"] if plan.temporal else [],
        }
        contexts.append(
            (
                task,
                query,
                MemoryContext(
                    snapshot,
                    plan,
                    records,
                    temporal,
                    {"records": [], "available": True},
                    {
                        "exact": "available",
                        "semantic": "not_requested",
                        "temporal": "available",
                    },
                    [conflict],
                    detailed_summary=summary if plan.temporal or plan.semantic else {},
                ),
            )
        )
    return contexts, records


def measure(renderer):
    timings, prompt = [], ""
    for _ in range(5):
        started = time.perf_counter()
        prompt = renderer()
        timings.append((time.perf_counter() - started) * 1000)
    return prompt, {"median_ms": statistics.median(timings), "max_ms": max(timings)}


def main(output_dir=None):
    run = output_dir or RUN
    run.mkdir(parents=True, exist_ok=True)
    os.environ["MARTIN_MEMORY_DB_PATH"] = str(run / "policy-only.sqlite")
    old_class, head = baseline_class()
    policy = BudgetPolicy()
    results = {
        "baseline_head": head,
        "baseline_source": "saved_worktree_router_sha256_verified",
        "count_method": "utf8_bytes_upper_bound",
        "samples": [],
        "stage_samples": [],
    }
    contexts, records = dataset()
    old_fields = {f.name for f in dataclasses.fields(old_class)}
    for task, query, context in contexts:
        old_context = old_class(
            **{
                f.name: getattr(context, f.name)
                for f in dataclasses.fields(context)
                if f.name in old_fields
            }
        )
        before, before_latency = measure(lambda: old_context.to_prompt(query))
        after, after_latency = measure(lambda: context.to_prompt(query))
        payload = lambda p: {
            "messages": [
                {"role": "system", "content": p},
                {"role": "user", "content": query},
            ]
        }
        required = [
            '"finding_id": "F002"',
            '"diameter_mm": 8.0',
            '"business_value": 8.0',
            '"proposed_value": 9.0',
        ]
        if task == "followup":
            required += [
                '"finding_id": "F001"',
                '"diameter_mm": 6.0',
                "2024-06-01",
                "lesion_identity_unconfirmed",
            ]
        # New serialization is compact: comparison ignores whitespace only.
        normalized = lambda value: value.replace(" ", "")
        retained = lambda p: sum(normalized(item) in normalized(p) for item in required)
        source_coverage = lambda p: sum(r["memory_id"] in p for r in records)
        before_count, after_count = count_payload(payload(before)), count_payload(
            payload(after)
        )
        row = {
            "task": task,
            "required_atoms": len(required),
            "before": {
                "input_estimate": before_count,
                "retained_atoms": retained(before),
                "discussion_sources": source_coverage(before),
                "render_latency": before_latency,
            },
            "after": {
                "input_estimate": after_count,
                "retained_atoms": retained(after),
                "discussion_sources": source_coverage(after),
                "render_latency": after_latency,
            },
            "input_change_ratio": (after_count - before_count) / before_count,
            "effective_atoms_per_1000_estimate": 1000 * retained(after) / after_count,
            "model_calls": 0,
            "degraded": "未完成完整分析" in after,
        }
        results["samples"].append(row)
    raw_size = conservative_count(records)
    text_size = conservative_count("\n".join(r["text"] for r in records))
    results["extractive_summary"] = {
        "raw_record_estimate": raw_size,
        "literal_text_estimate": text_size,
        "envelope_reduction_ratio": 1 - text_size / raw_size,
        "note": "Envelope reduction only; literals retained. Summary source pointers consume additional space.",
    }
    for batches in (4, 1):
        stage_policy = dataclasses.replace(policy, max_stage_batches=batches)
        items = [
            BudgetItem(
                f"F{i}",
                "memory",
                {
                    "finding_id": f"F{i}",
                    "diameter_mm": i + 1.25,
                    "observed_at": "2026-01-01",
                    "provenance": {"redundant": "x" * 900},
                },
                True,
                (f"F{i}",),
                "2026-01-01",
                {
                    "finding_id": f"F{i}",
                    "diameter_mm": i + 1.25,
                    "observed_at": "2026-01-01",
                },
            )
            for i in range(4)
        ]
        token = begin_budget_scope("followup", policy=stage_policy)
        row = {"batch_limit": batches, "required_sources": 4}
        try:
            selected = select_context(items, available=1400, task="followup")
            row.update(
                complete=len(selected.selected_ids) == 4,
                degraded=False,
                retained_sources=len(selected.selected_ids),
            )
        except ContextBudgetExceeded as exc:
            row.update(
                complete=False,
                degraded=True,
                retained_sources=len(exc.processed),
                omitted_sources=len(exc.omitted),
                reason=exc.reason,
            )
        finally:
            row["trace"] = finish_budget_scope(token)
        results["stage_samples"].append(row)
    results["p1_status"] = "REVIEW"
    (run / "comparison.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "evidence": str(run / "comparison.json"),
                "samples": results["samples"],
                "summary": results["extractive_summary"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path)
    main(parser.parse_args().output_dir)
