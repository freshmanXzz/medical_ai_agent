"""Real REST/WS + LLM + BGE acceptance of scoped three-way memory.

Uses the synthetic-only Store harness. No real patient, knowledge document or
image is loaded. Semantic answer review is separate from structural checks.
"""

import json
import re
import sqlite3
from unittest.mock import patch

import store_v1_live_acceptance as h
from websockets.sync.client import connect


DECISION_FRAGMENT = "选择继续观察，因为当时形态资料不完整，需要先补齐资料并等待复查"
SAVE_REQUEST = (
    "请长期保存我明确提供的上次临床决策：我们" + DECISION_FRAGMENT
    + "。这里只记录决策背景，不修改结节的业务事实。"
)
COMBINED_QUERY = "这个患者为什么上次选择观察，现在又有什么变化？"
h.evidence["version"] = "Exact + Temporal + Semantic live acceptance"
h.evidence["scope"] = (
    "Synthetic explicit decision writer -> new thread scoped exact, temporal, "
    "semantic retrieval -> actual model prompt/answer; REST, WS, authorization "
    "and isolated semantic-index failure."
)


def all_dicts(value):
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from all_dicts(item)
    elif isinstance(value, list):
        for item in value:
            yield from all_dicts(item)


def check(name, checks, *, review=False, **details):
    result = {
        "checks": checks,
        "status": ("REVIEW" if review else "PASS")
        if all(checks.values()) else "FAIL",
        **details,
    }
    h.evidence["checks"][name] = result
    h.flush()
    print(name + ": " + result["status"], flush=True)


def phase_contexts():
    return [item["context"] for item in h.evidence.get("retrieval_contexts", [])
            if item["phase"] == h.phase]


def has_decision(value):
    return any(
        item.get("memory_type") == "clinical_decision"
        and "形态资料不完整" in item.get("text", "")
        and item.get("source_type") and item.get("source_id")
        for item in all_dicts(value)
    )


def has_delta(value):
    return any(
        item.get("from_mm") == 6 and item.get("to_mm") == 8
        and item.get("delta_mm") == 2
        for item in all_dicts(value)
    )


def answer_measurements(answer):
    return {
        "Historical 6mm": bool(re.search(r"6(?:\.0+)?\s*(?:mm|毫米)", answer, re.I)),
        "Current 8mm": bool(re.search(r"8(?:\.0+)?\s*(?:mm|毫米)", answer, re.I)),
        "Difference 2mm": bool(re.search(r"2(?:\.0+)?\s*(?:mm|毫米)", answer, re.I)),
    }


def websocket_chat(client, thread_id, message):
    cookie = "; ".join(f"{key}={value}" for key, value in client.cookies.items())
    with connect(
        f"ws://127.0.0.1:{h.PORT}/api/ws/agent/{thread_id}",
        additional_headers={"Cookie": cookie}, open_timeout=20, proxy=None,
    ) as ws:
        ws.recv(timeout=20)
        ws.send(json.dumps({"message": message}, ensure_ascii=False))
        events = []
        while True:
            event = json.loads(ws.recv(timeout=240))
            events.append(event)
            if event["type"] in ("final", "error"):
                break
    h.evidence["http"].append({
        "phase": h.phase, "label": "websocket", "status": 101,
        "body": {"output": event["content"] if event["type"] == "final" else "",
                 "events": h.clean(events)},
    })
    h.flush()
    return event


def run(client):
    from martin.memory.vector_index import MemoryVectorIndex

    login = client.post("/api/auth/login", json={
        "username": "doctor_a", "password": "SyntheticLiveDoctorA!2026",
    })
    login.raise_for_status()

    h.phase = "Writer_explicit_decision"
    previous_thread = h.new_thread(client, "C001")
    response, body = h.chat(client, previous_thread, SAVE_REQUEST, "explicit_decision")
    records_response = client.get(f"/api/memory/threads/{previous_thread}/records")
    records_body = h.record_response("saved_records", records_response)
    with sqlite3.connect(h.RUN / "app.sqlite") as connection:
        findings = connection.execute(
            "SELECT id, case_id, diameter_mm, status FROM findings ORDER BY id"
        ).fetchall()
    checks = {
        "HTTP success": response.status_code == 200,
        "Real Agent used writer tool": any(
            item.get("tool_name") == "save_long_term_memory"
            for item in body.get("tool_calls", [])
        ),
        "Authorized records readable": records_response.status_code == 200,
        "Typed decision with provenance": bool(has_decision(records_body)),
        "Selected literal human fragments": all(
            item["text"].strip() in SAVE_REQUEST
            for item in records_body.get("records", [])
        ),
        "Business findings unchanged": findings == [
            ("F001", "C001", 6.0, "confirmed"),
            ("F002", "C002", 8.0, "confirmed"),
        ],
    }
    check("Explicit Memory Writer", checks, thread=previous_thread)

    # A direct authenticated preference is an Exact lookup control, not an LLM
    # preference-write claim; the latter was proved by the separate V1.1 run.
    preference_response = client.post("/api/memory/preferences/report-style", json={
        "conclusion_first": True, "max_words": 200, "focus": ["毛刺征"],
    })
    preference_response.raise_for_status()

    h.phase = "Combined_REST"
    current_thread = h.new_thread(client, "C002")
    retrieval_response = client.post(
        f"/api/memory/threads/{current_thread}/retrieve",
        json={"query": COMBINED_QUERY},
    )
    retrieval = h.record_response("scoped_retrieval", retrieval_response)
    response, body = h.chat(client, current_thread, COMBINED_QUERY, "combined_memory")
    answer = body.get("output", "")
    prompts = h.actual_prompts(h.phase)
    contexts = phase_contexts()
    checks = {
        "HTTP retrieval success": retrieval_response.status_code == 200,
        "Temporal intent selected": retrieval.get("plan", {}).get("temporal") is True,
        "Semantic intent selected": retrieval.get("plan", {}).get("semantic") is True,
        "Temporal structured delta": has_delta(retrieval),
        "Semantic decision retrieved": bool(has_decision(retrieval)),
        "Native vector produced a similarity score": any(
            item.get("retrieval_method") == "semantic"
            and type(item.get("score")) in (int, float)
            for item in all_dicts(retrieval)
        ),
        "Current thread differs from writer": current_thread != previous_thread,
        "HTTP chat success": response.status_code == 200,
        "Actual model received decision": any("形态资料不完整" in p for p in prompts),
        "Chat router produced structured delta": has_delta(contexts),
        "Actual model received temporal sources": any(
            "[TEMPORAL CHANGES]" in p and '"delta_mm": 2' in p for p in prompts
        ),
        "Exact preferences still available": any(
            '"max_words": 200' in p for p in prompts
        ),
        "Lesion identity uncertainty in model prompt": any(
            "lesion_identity_unconfirmed" in p for p in prompts
        ),
        "Public answer uses decision background": (
            "形态资料" in answer and "观察" in answer
        ),
        **answer_measurements(answer),
    }
    check("Combined REST Retrieval", checks, review=True, thread=current_thread)

    h.phase = "Combined_WS"
    ws_thread = h.new_thread(client, "C002")
    final = websocket_chat(client, ws_thread, COMBINED_QUERY)
    ws_answer = final.get("content", "")
    check("Combined WebSocket Retrieval", {
        "Final event": final["type"] == "final",
        "Real model invoked": bool(h.actual_prompts(h.phase)),
        "Actual model received decision": any(
            "形态资料不完整" in p for p in h.actual_prompts(h.phase)
        ),
        "Structured temporal delta": has_delta(phase_contexts()),
        "Public answer uses decision background": (
            "形态资料" in ws_answer and "观察" in ws_answer
        ),
        **answer_measurements(ws_answer),
    }, review=True, thread=ws_thread)

    h.phase = "Older_current_case"
    older_thread = h.new_thread(client, "C001")
    older_query = (
        "只总结当前病例，并列出比当前病例更早的既往观察；"
        "不要把较晚病例当成历史。"
    )
    older_response = client.post(
        f"/api/memory/threads/{older_thread}/retrieve",
        json={"query": older_query},
    )
    older_context = h.record_response("older_case_retrieval", older_response)
    response, body = h.chat(client, older_thread, older_query, "older_case_summary")
    older_answer = body.get("output", "")
    check("Older Current Case Chronology", {
        "Retrieval succeeds": older_response.status_code == 200,
        "No newer F002 in memory context": not any(
            item.get("finding_id") == "F002"
            or item.get("source_finding_id") == "F002"
            for item in all_dicts(older_context)
        ),
        "No delta against a later case": not bool(
            older_context.get("temporal", {}).get("changes")
        ),
        "Actual model history excludes newer case": all(
            '"F002"' not in h.section(
                p, "[PATIENT HISTORICAL MEMORY]", "[CASE MEMORY]"
            )
            for p in h.actual_prompts(h.phase)
        ),
        "Real LLM answer present": response.status_code == 200 and bool(older_answer),
        "Current 6mm retained": bool(
            re.search(r"6(?:\.0+)?\s*(?:mm|毫米)", older_answer, re.I)
        ),
        "No newer 8mm called prior": not bool(
            re.search(r"8(?:\.0+)?\s*(?:mm|毫米)", older_answer, re.I)
        ),
    }, review=True, thread=older_thread)

    h.phase = "Isolation_doctor_B"
    with h.httpx.Client(base_url=client.base_url, timeout=30, trust_env=False) as other:
        other.post("/api/auth/login", json={
            "username": "doctor_b", "password": "SyntheticLiveDoctorB!2026",
        }).raise_for_status()
        denied = other.post(
            f"/api/memory/threads/{current_thread}/retrieve",
            json={"query": COMBINED_QUERY},
        )
        denied_body = h.record_response("unauthorized_retrieval", denied)
    check("Unauthorized Retrieval Isolation", {
        "Rejected before retrieval": denied.status_code in (403, 404),
        "No Alpha private decision returned": not has_decision(denied_body),
        "No Store read after failed authorization": not any(
            item["phase"] == h.phase for item in h.evidence["store_reads"]
        ),
    })

    h.phase = "Semantic_index_failure"
    failure_thread = h.new_thread(client, "C002")

    def failed_search(*args, **kwargs):
        h.evidence.setdefault("semantic_index_faults", []).append({"phase": h.phase})
        raise OSError("synthetic acceptance semantic index read failure")

    with patch.object(MemoryVectorIndex, "search", failed_search):
        retrieval_response = client.post(
            f"/api/memory/threads/{failure_thread}/retrieve",
            json={"query": COMBINED_QUERY},
        )
        degraded = h.record_response("degraded_scoped_retrieval", retrieval_response)
        response, body = h.chat(
            client, failure_thread, COMBINED_QUERY, "semantic_failure"
        )
    answer = body.get("output", "")
    prompts = h.actual_prompts(h.phase)
    check("Independent Semantic Failure", {
        "Index fault actually injected": bool(h.evidence.get("semantic_index_faults")),
        "Retrieval remains successful": retrieval_response.status_code == 200,
        "Exact status remains available": (
            degraded.get("retrieval_status", {}).get("exact") == "available"
        ),
        "Temporal status remains available": (
            degraded.get("retrieval_status", {}).get("temporal") == "available"
        ),
        "Temporal structured delta survives": has_delta(degraded),
        "Semantic unavailable metadata": (
            "semantic_index_unavailable" in json.dumps(degraded)
        ),
        "No unavailable decision returned": not has_decision(degraded),
        "Exact preferences survive in prompt": any(
            '"max_words": 200' in p for p in prompts
        ),
        "Semantic failure in actual model prompt": any(
            "semantic_index_unavailable" in p for p in prompts
        ),
        "Real LLM answer continues": response.status_code == 200 and bool(answer),
        "Does not invent inaccessible decision": "形态资料不完整" not in answer,
        **answer_measurements(answer),
    }, review=True, thread=failure_thread)


h.run_scenarios = run
if __name__ == "__main__":
    from martin.memory.router import MemoryRetrievalRouter

    real_retrieve = MemoryRetrievalRouter.retrieve

    def recorded_retrieve(self, *args, **kwargs):
        result = real_retrieve(self, *args, **kwargs)
        h.evidence.setdefault("retrieval_contexts", []).append({
            "phase": h.phase, "context": result.to_dict(),
        })
        h.flush()
        return result

    with patch.object(MemoryRetrievalRouter, "retrieve", recorded_retrieve):
        raise SystemExit(h.main())
