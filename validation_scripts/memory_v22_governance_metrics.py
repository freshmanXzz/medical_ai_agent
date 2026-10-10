"""Synthetic P1 Writer/SummaryService measurement with explicit denominators.

Runs on a new isolated SQLite directory, with no model/embedding calls. The
append-only baseline is the same submitted occurrences without growth control;
it is not a replay of the V2.1 Agent. Token estimates are UTF-8 upper bounds.
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from langgraph.store.sqlite import SqliteStore

from martin.db import transaction
from martin.llm.context_budget import _render as render_budget_items
from martin.llm.context_budget import conservative_count
from martin.memory.context import MemorySnapshot
from martin.memory.models import MemoryCandidate
from martin.memory.router import MemoryContext, RetrievalPlan
from martin.memory.scope import authorize_scope
from martin.memory.service import MemoryService
from martin.memory.summaries import SummaryService, _reference, _render, summaries_ns
from martin.memory.writer import MemoryWriter
from martin.services.thread_service import ThreadService
from scripts.seed_entity_v0 import seed_entity_v0


def provenance(scope, marker):
    return {
        "kind": "api_submission",
        "actor_id": scope.doctor_id,
        "actor_role": "doctor",
        "submission_id": marker,
        "thread_id": scope.thread_id,
    }


def write(writer, scope, candidate, marker):
    return writer.write(
        scope,
        [candidate],
        source_type="thread",
        source_id=scope.thread_id,
        provenance=provenance(scope, marker),
    )


def business_findings(db):
    with transaction(db) as connection:
        return [
            dict(row)
            for row in connection.execute("SELECT * FROM findings ORDER BY id")
        ]


def dedup_samples():
    low = lambda text, **kwargs: MemoryCandidate(
        "workflow_preference", text, "style", **kwargs
    )
    clinical = lambda text, **kwargs: MemoryCandidate(
        "clinical_decision", text, "decision", **kwargs
    )
    return [
        (
            "exact_preference",
            "equivalent",
            low("以后报告先给结论"),
            low("以后报告先给结论"),
        ),
        (
            "report_synonym",
            "equivalent",
            low("以后报告先给结论"),
            low("今后报告结论前置"),
        ),
        (
            "analysis_synonym",
            "equivalent",
            low("分析先列数据限制"),
            low("影像分析先说明资料限制"),
        ),
        (
            "condition_refinement",
            "distinct",
            low("普通报告控制在200字以内"),
            low("复杂病例可以详细写"),
        ),
        ("negation", "distinct", low("以后报告先给结论"), low("以后报告不要先给结论")),
        (
            "added_information",
            "distinct",
            low("以后报告先给结论"),
            low("以后报告先给结论并写出所有依据"),
        ),
        (
            "distinct_reason",
            "high_risk_distinct",
            clinical("观察，等待病理"),
            clinical("观察，等待影像复核"),
        ),
        (
            "distinct_time",
            "high_risk_distinct",
            clinical("右上叶观察", observed_at="2024-06-01"),
            clinical("右上叶观察", observed_at="2026-06-01"),
        ),
        (
            "distinct_lesion",
            "high_risk_distinct",
            clinical(
                "右上叶观察",
                data={"lesion_id": "synthetic-L1"},
                observed_at="2026-06-01",
            ),
            clinical(
                "右上叶观察",
                data={"lesion_id": "synthetic-L2"},
                observed_at="2026-06-01",
            ),
        ),
        (
            "unspecified_occurrences",
            "high_risk_distinct",
            clinical("右上叶观察"),
            clinical("右上叶观察"),
        ),
    ]


def measure_dedup(run, db, scope):
    rows = []
    for index, (name, group, first, second) in enumerate(dedup_samples()):
        with SqliteStore.from_conn_string(str(run / f"dedup-{index}.sqlite")) as store:
            store.setup()
            service = MemoryService(db, store)
            writer = MemoryWriter(service, SimpleNamespace(sync=lambda *a, **k: None))
            original = write(writer, scope, first, "first").records[0]
            result = write(writer, scope, second, "second")
            active = service.list_records(scope)
            merged = result.deduplicated == 1
            expected_merge = group == "equivalent"
            sources = {
                json.dumps(row["provenance"], sort_keys=True) for row in active
            } | {
                json.dumps(reference["provenance"], sort_keys=True)
                for row in active
                for reference in row.get("reinforced_sources", [])
            }
            rows.append(
                {
                    "sample": name,
                    "group": group,
                    "submitted_occurrences": 2,
                    "append_only_records": 2,
                    "active_records": len(active),
                    "eliminated_records": 2 - len(active),
                    "merged": merged,
                    "expected_merge": expected_merge,
                    "correct": merged == expected_merge,
                    "distinct_source_occurrences": len(sources),
                    "original_preserved": service.get_record(
                        scope, original["memory_id"]
                    )
                    is not None,
                }
            )
    eligible = [row for row in rows if row["expected_merge"]]
    distinct = [row for row in rows if not row["expected_merge"]]
    near = [row for row in eligible if row["sample"] != "exact_preference"]
    false_merges_by_risk = {}
    for label, group in (
        ("lower_risk", "distinct"),
        ("high_risk", "high_risk_distinct"),
    ):
        group_rows = [row for row in rows if row["group"] == group]
        false_merges_by_risk[label] = {
            "numerator": sum(row["merged"] for row in group_rows),
            "denominator": len(group_rows),
        }
    return {
        "baseline": "same_occurrences_append_only_not_v21_engine_replay",
        "samples": rows,
        "submitted_occurrences": sum(row["submitted_occurrences"] for row in rows),
        "eliminated_equivalent_records": sum(
            row["eliminated_records"] for row in eligible
        ),
        "equivalent_merge_success": {
            "numerator": sum(row["merged"] for row in eligible),
            "denominator": len(eligible),
        },
        "supported_near_equivalence_recall": {
            "numerator": sum(row["merged"] for row in near),
            "denominator": len(near),
        },
        "false_merge_on_distinct_pairs": {
            "numerator": sum(row["merged"] for row in distinct),
            "denominator": len(distinct),
        },
        "false_merge_on_distinct_pairs_by_risk": false_merges_by_risk,
        "new_information_retention": {
            "numerator": sum(row["active_records"] == 2 for row in distinct),
            "denominator": len(distinct),
        },
        "source_occurrence_coverage": {
            "numerator": sum(row["distinct_source_occurrences"] for row in rows),
            "denominator": sum(row["submitted_occurrences"] for row in rows),
        },
    }


def measure_summary(run, db, scope):
    with SqliteStore.from_conn_string(str(run / "summary.sqlite")) as store:
        store.setup()
        service = MemoryService(db, store)
        writer = MemoryWriter(service, SimpleNamespace(sync=lambda *a, **k: None))
        for index, (kind, text, diameter, date) in enumerate(
            (
                (
                    "historical_discussion",
                    "医生讨论既往6mm，尚未确认同一病灶",
                    6.0,
                    "2024-06-01",
                ),
                (
                    "clinical_decision",
                    "医生讨论当前8mm，等待原始影像复核",
                    8.0,
                    "2026-06-01",
                ),
                (
                    "historical_discussion",
                    "医生保留等待病理理由，未确认诊断",
                    8.0,
                    "2026-06-02",
                ),
                (
                    "clinical_decision",
                    "医生保留观察理由，非确认业务事实",
                    8.0,
                    "2026-06-03",
                ),
            )
        ):
            write(
                writer,
                scope,
                MemoryCandidate(
                    kind,
                    text,
                    f"source-{index}",
                    data={"discussed_diameter_mm": diameter},
                    observed_at=date,
                ),
                f"source-{index}",
            )
        # A claim and assistant inference must not be converted into summary facts.
        assistant_rejected = False
        try:
            writer.write(
                scope,
                [MemoryCandidate("historical_discussion", "assistant推测确认诊断")],
                source_type="thread",
                source_id=scope.thread_id,
                provenance=dict(provenance(scope, "assistant"), actor_role="assistant"),
            )
        except ValueError:
            assistant_rejected = True
        claim = write(
            writer,
            scope,
            MemoryCandidate(
                "clinical_claim",
                "医生口述9mm待核实",
                "claim",
                data={
                    "target_finding_id": "F002",
                    "field": "diameter_mm",
                    "proposed_value": 9.0,
                },
            ),
            "claim",
        ).records[0]
        summaries = SummaryService(service)
        eligible = summaries.eligible_sources(scope)
        full = summaries.rebuild(
            scope, token_budget=20000, token_counter=conservative_count
        )
        stored = store.get(summaries_ns(scope), full["summary_id"]).value
        expected_references = [_reference(row) for row in eligible]
        expected_text = "\n".join(_render(row) for row in eligible)
        drift = sum(
            segment["text"] != _render(row)
            for segment, row in zip(stored["segments"], eligible)
        )
        attribution = sum(
            source != expected
            for source, expected in zip(full["sources"], expected_references)
        )
        raw_tokens = conservative_count(eligible)
        full_tokens = conservative_count(full)
        context = MemoryContext(
            MemorySnapshot(scope.case_id, scope.patient_id),
            RetrievalPlan(semantic=True),
            eligible,
            {},
            {"available": True, "records": eligible},
            {},
            detailed_summary=full,
        )
        budget_items = context.budget_items("qa")
        raw_items = [
            item
            for item in budget_items
            if item.reference.startswith("SEMANTIC HISTORICAL DISCUSSIONS:")
        ]
        summary_items = [
            item
            for item in budget_items
            if item.reference == "ON DEMAND LONG TERM SUMMARY"
        ]
        raw_prompt_tokens = conservative_count(render_budget_items(raw_items))
        summary_prompt_tokens = conservative_count(render_budget_items(summary_items))
        result = {
            "count_method": "utf8_bytes_upper_bound_not_billing_tokens",
            "eligible_raw_records": len(eligible),
            "source_coverage": {
                "numerator": len(full["source_memory_ids"]),
                "denominator": len(eligible),
            },
            "literal_and_structured_segment_drift": {
                "numerator": drift,
                "denominator": len(eligible),
            },
            "source_misattribution": {
                "numerator": attribution,
                "denominator": len(expected_references),
            },
            "all_expected_rendered_text_retained": full["text"] == expected_text,
            "raw_record_estimate": raw_tokens,
            "actual_rendered_summary_text_estimate": conservative_count(full["text"]),
            "actual_stored_summary_envelope_estimate": conservative_count(stored),
            "actual_materialized_summary_envelope_estimate": full_tokens,
            "materialized_vs_raw_reduction_ratio": 1 - full_tokens / raw_tokens,
            "actual_raw_discussion_prompt_items_estimate": raw_prompt_tokens,
            "actual_prompt_summary_item_estimate": summary_prompt_tokens,
            "prompt_item_reduction_ratio": 1
            - summary_prompt_tokens / raw_prompt_tokens,
            "claim_excluded": claim["memory_id"] not in full["source_memory_ids"],
            "assistant_evidence_rejected": assistant_rejected,
            "authority": full["authority"],
            "model_calls": 0,
            "summary_validated": summaries.validate_materialized(scope, full),
        }
        limited = summaries.rebuild(
            scope,
            token_budget=conservative_count(_render(eligible[0])) + 10,
            token_counter=conservative_count,
        )
        result["limited_coverage"] = {
            "included": len(limited["source_memory_ids"]),
            "eligible": len(eligible),
            "explicit_omissions": limited["omitted"],
            "coverage_accounts_for_all_sources": set(limited["source_memory_ids"])
            | set(limited["omitted_source_memory_ids"])
            == {row["memory_id"] for row in eligible},
        }
        service.retract_record(
            scope,
            full["source_memory_ids"][0],
            provenance=provenance(scope, "withdraw"),
        )
        result["withdrawn_cached_summary_rejected"] = (
            not summaries.validate_materialized(scope, full)
        )
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    run = args.output_dir or REPO / "tmp" / (
        "v22-governance-metrics-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    )
    # Never reuse a directory, so repeated runs cannot mutate pre-existing data.
    run.mkdir(parents=True, exist_ok=False)
    db = run / "app.sqlite"
    os.environ["MARTIN_APP_DB_PATH"] = str(db)
    os.environ["MARTIN_MEMORY_DB_PATH"] = str(run / "unused-default-memory.sqlite")
    seed_entity_v0(
        db,
        doctor_a_password="SyntheticMetricsA!2026",
        doctor_b_password="SyntheticMetricsB!2026",
    )
    scope = authorize_scope("D001", ThreadService(db).create_thread("D001", "C002"), db)
    before = business_findings(db)
    result = {
        "scope": "synthetic_governance_microbenchmark_no_network_no_real_patients",
        "deduplication": measure_dedup(run, db, scope),
        "summary": measure_summary(run, db, scope),
        "business_findings_unchanged": business_findings(db) == before,
        "limitations": [
            "Ten hand-labelled pairs test supported equivalence vocabulary; no population error rate is inferred.",
            "Four eligible summary sources test deterministic rendering, not model clinical quality.",
            "Stored/materialized envelopes and actual prompt projection are measured separately; full envelopes may exceed raw-record size.",
            "No provider tokens, BGE relevance, model latency, live job cost or V2.1 engine replay is measured.",
        ],
    }
    path = run / "metrics.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"evidence": str(path), **result}, ensure_ascii=False))
    checks = [
        row["correct"]
        and row["original_preserved"]
        and row["distinct_source_occurrences"] == 2
        for row in result["deduplication"]["samples"]
    ]
    checks += [
        result["business_findings_unchanged"],
        result["summary"]["summary_validated"],
        result["summary"]["claim_excluded"],
        result["summary"]["assistant_evidence_rejected"],
        result["summary"]["all_expected_rendered_text_retained"],
        result["summary"]["withdrawn_cached_summary_rejected"],
        result["summary"]["limited_coverage"]["coverage_accounts_for_all_sources"],
    ]
    return 0 if all(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
