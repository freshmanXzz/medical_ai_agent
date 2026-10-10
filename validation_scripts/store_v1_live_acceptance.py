"""Three synthetic live scenarios through the unchanged HTTP API and real LLM.

Evidence instrumentation records data, actual model inputs and public answers.
Only the isolated acceptance Store read is fault-injected for scenario C.
No credentials, reasoning fields, provider hidden reasoning or patient data are logged.
"""

import dataclasses
import json
import logging
import os
import re
import socket
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO.parent
sys.path.insert(0, str(REPO))
from dotenv import load_dotenv

load_dotenv(REPO / ".env", override=False)
missing = [name for name in ("DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "DEEPSEEK_MODEL")
           if not os.environ.get(name)]
if missing:
    raise SystemExit("Missing LLM configuration: " + ", ".join(missing))
OUTPUT_ROOT = Path(os.environ.get("MARTIN_ACCEPTANCE_OUTPUT_DIR", ROOT / "validation"))
RUN = OUTPUT_ROOT / ("store-v1-live-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f"))
RUN.mkdir(parents=True)
PORT = int(os.environ.get("MARTIN_ACCEPTANCE_PORT", "0"))
os.environ.update({
    "MARTIN_APP_DB_PATH": str(RUN / "app.sqlite"),
    "MARTIN_MEMORY_DB_PATH": str(RUN / "memory.sqlite"),
    "MARTIN_MEMORY_VECTOR_DB_PATH": str(RUN / "memory_vectors.sqlite"),
    "CHROMA_PERSIST_DIR": str(RUN / "knowledge"),
    "CHROMA_COLLECTION": "synthetic_acceptance_knowledge",
    "MARTIN_LOCAL_OBJECT_STORAGE_DIR": str(RUN / "objects"),
    "MARTIN_LOCAL_OBJECT_STORAGE_FALLBACK": "false",
    "LANGCHAIN_TRACING_V2": "false", "LANGSMITH_TRACING": "false",
    "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
})
# Disable legacy reasoning logger; do not alter prompts or execution behavior.
thinking = logging.getLogger("agent_thinking")
thinking.addHandler(logging.NullHandler())
thinking.disabled = True
thinking.propagate = False
logging.basicConfig(level=logging.ERROR)
# Evidence records safe exception types; production loggers may include provider
# details in raw exception text, which this synthetic harness does not retain.
logging.disable(logging.CRITICAL)

import httpx
import uvicorn
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.store.sqlite import SqliteStore

from martin.agent.audit import AuditLogger
from martin.agent.sessions import close_default_checkpointer, get_default_checkpointer
from martin.llm.chat_model import clear_chat_model_cache, get_chat_model
from martin.memory.service import MemoryService
from martin.memory.store import close_default_store, get_default_store
from scripts.seed_entity_v0 import seed_entity_v0

phase = "setup"
fault = False
evidence = {
    "started_at": datetime.now(timezone.utc).isoformat(),
    "model": os.environ["DEEPSEEK_MODEL"],
    "python": sys.version.split()[0],
    "scope": "Three synthetic scenarios, actual REST API, actual LLM, isolated SQLite files",
    "store_reads": [], "snapshots": [], "model_calls": [], "http": [], "checks": {},
}


def clean(value):
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()
                if k not in {"reasoning", "reasoning_content", "api_key", "password", "token"}}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    return value


def flush():
    (RUN / "evidence.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")


class EvidenceCallback(BaseCallbackHandler):
    def on_chat_model_start(self, serialized, messages, *, run_id, **kwargs):
        evidence["model_calls"].append({
            "run_id": str(run_id), "phase": phase,
            "system_prompts": [m.content for batch in messages for m in batch if isinstance(m, SystemMessage)],
            "human_messages": [m.content for batch in messages for m in batch if isinstance(m, HumanMessage)],
        })
        flush()

    def on_llm_end(self, response, *, run_id, **kwargs):
        entry = next(x for x in evidence["model_calls"] if x["run_id"] == str(run_id))
        entry["responses"] = []
        for batch in response.generations:
            for generation in batch:
                m = generation.message
                entry["responses"].append({
                    "answer": m.content, "tool_calls": clean(m.tool_calls),
                    "model": m.response_metadata.get("model_name"),
                })
        flush()

    def on_llm_error(self, error, *, run_id, **kwargs):
        evidence.setdefault("llm_errors", []).append({"phase": phase, "type": type(error).__name__})
        flush()


real_search = SqliteStore.search
real_get = SqliteStore.get
real_snapshot = MemoryService.snapshot_for_thread
real_audit_init = AuditLogger.__init__
real_audit_call = AuditLogger.log_tool_call
real_audit_error = AuditLogger.log_agent_error


def recorded_search(self, namespace_prefix, *args, **kwargs):
    entry = {"phase": phase, "operation": "search", "namespace": list(namespace_prefix),
             "query": kwargs.get("query")}
    if fault:
        entry["error"] = "OSError: synthetic Store read failure"
        evidence["store_reads"].append(entry)
        flush()
        raise OSError("synthetic Store read failure")
    result = real_search(self, namespace_prefix, *args, **kwargs)
    entry["items"] = [{"key": item.key, "value": item.value, "score": item.score} for item in result]
    evidence["store_reads"].append(entry)
    return result


def recorded_get(self, namespace, key, *args, **kwargs):
    if fault:
        raise OSError("synthetic Store read failure")
    result = real_get(self, namespace, key, *args, **kwargs)
    evidence["store_reads"].append({"phase": phase, "operation": "get", "namespace": list(namespace),
                                    "key": key, "value": result.value if result else None})
    return result


def recorded_snapshot(self, doctor_id, thread_id, *args, **kwargs):
    result = real_snapshot(self, doctor_id, thread_id, *args, **kwargs)
    evidence["snapshots"].append({"phase": phase, "thread_id": thread_id,
                                  "snapshot": dataclasses.asdict(result),
                                  "candidate_projection_not_proof_of_injection": result.to_prompt()})
    flush()
    return result


def audit_init(self, session_id=None, audit_dir=None):
    real_audit_init(self, session_id, str(RUN / "audit"))


def audit_call(self, tool_name, args, output_summary, user_input="", final_output=""):
    return real_audit_call(self, tool_name, clean(args), output_summary, user_input, final_output)


def audit_error(self, error_msg):
    return real_audit_error(self, "Synthetic acceptance agent error; see structured evidence.")


def excluded_image_tool(*args, **kwargs):
    evidence.setdefault("excluded_image_tool_attempts", []).append({"phase": phase})
    flush()
    raise RuntimeError("No image operations are permitted in synthetic memory acceptance")


def record_response(label, response):
    body = clean(response.json())
    evidence["http"].append({"phase": phase, "label": label, "status": response.status_code, "body": body})
    flush()
    return body


def new_thread(client, case_id):
    response = client.post("/api/threads", json={"case_id": case_id})
    response.raise_for_status()
    return response.json()["thread_id"]


def chat(client, thread_id, message, label):
    response = client.post("/api/agent/chat", json={"session_id": thread_id, "user_message": message})
    return response, record_response(label, response)


def actual_prompts(label):
    return [p for c in evidence["model_calls"] if c["phase"] == label for p in c["system_prompts"]]


def section(prompt, title, next_title):
    if title not in prompt:
        return ""
    return prompt.split(title, 1)[1].split(next_title, 1)[0]


def run_longitudinal(client):
    global phase
    phase = "B_new_thread"
    third = new_thread(client, "C002")
    rb, bb = chat(client, third, "和上次相比，结节大小有什么变化？", "longitudinal_comparison")
    text = bb.get("output", "")
    p = next((p for p in actual_prompts(phase) if "[CURRENT CASE FACTS]" in p), "")
    current = section(p, "[CURRENT CASE FACTS]", "[DOCTOR PREFERENCES]")
    history = section(p, "[PATIENT HISTORICAL MEMORY]", "[CASE MEMORY]")
    b_checks = {
        "store_returned_historical_6mm": any(x["phase"] == phase and x["namespace"] == ["patient", "P001", "memory"]
            and any(i["value"].get("finding_id") == "F001" and i["value"].get("diameter_mm") == 6 for i in x.get("items", [])) for x in evidence["store_reads"]),
        "current_prompt_only_F002_8mm": '"F002"' in current and '"diameter_mm": 8.0' in current and '"F001"' not in current,
        "history_prompt_only_F001_6mm": '"F001"' in history and '"diameter_mm": 6.0' in history and '"F002"' not in history,
        "http_success": rb.status_code == 200,
        "mentions_6mm": bool(re.search(r"6(?:\.0)?\s*(?:mm|毫米)", text, re.I)),
        "mentions_8mm": bool(re.search(r"8(?:\.0)?\s*(?:mm|毫米)", text, re.I)),
        "mentions_difference_2mm": bool(re.search(r"(?:增加|增大|增粗|增|差值|相差|差|[+＋])\s*(?:为|了|约)?\s*2(?:\.0+)?\s*(?:mm|毫米)", text, re.I)),
    }
    evidence["checks"]["Longitudinal Memory"] = {"checks": b_checks,
        "status": "REVIEW" if all(b_checks.values()) else "FAIL", "semantic_review_required": "6mm historical; 8mm current; observation difference 2mm, preserve unconfirmed lesion identity", "thread": third}
    flush()
    print("Longitudinal Memory: " + evidence["checks"]["Longitudinal Memory"]["status"], flush=True)


def run_scenarios(client):
    global phase, fault
    login = client.post("/api/auth/login", json={"username": "doctor_a", "password": "SyntheticLiveDoctorA!2026"})
    login.raise_for_status()

    phase = "A_thread_A"
    first = new_thread(client, "C002")
    r1, b1 = chat(client, first, "以后报告请结论前置、200字以内、重点毛刺征。", "set_preference")
    preference = get_default_store().get(("doctor", "D001", "preferences"), "report_style")
    phase = "A_thread_B"
    second = new_thread(client, "C002")
    r2, b2 = chat(client, second, "生成报告", "new_thread_report")
    answer = b2.get("output", "")
    pref = preference.value if preference else {}
    a_checks = {
        "different_threads": first != second,
        "preference_saved_by_real_agent": r1.status_code == 200 and pref.get("conclusion_first") is True
            and pref.get("max_words") == 200 and "毛刺征" in pref.get("focus", []),
        "retrieved_in_new_thread": any(x["phase"] == phase and x["namespace"] == ["doctor", "D001", "preferences"]
            and any(i["key"] == "report_style" and i["value"] == pref for i in x.get("items", [])) for x in evidence["store_reads"]),
        "in_actual_model_prompt": any('"max_words": 200' in p and '"毛刺征"' in p and '"conclusion_first": true' in p for p in actual_prompts(phase)),
        "http_success": r2.status_code == 200,
        "conclusion_first": bool(re.match(r"^[\s#*]*结论[：:]", answer)),
        "at_most_200_chars": bool(answer) and len(answer) <= 200,
        "spiculation_addressed": "毛刺征" in answer,
    }
    evidence["checks"]["Doctor Preference"] = {"checks": a_checks, "answer_chars": len(answer),
        "status": "PASS" if all(a_checks.values()) else "FAIL", "thread_A": first, "thread_B": second}
    flush()
    print("Doctor Preference: " + evidence["checks"]["Doctor Preference"]["status"], flush=True)

    run_longitudinal(client)

    phase = "C_store_failure"
    fourth = new_thread(client, "C002")
    fault = True
    try:
        rc, bc = chat(client, fourth, "和上次相比有没有变化", "store_read_failure")
    finally:
        fault = False
    calls = [c for c in evidence["model_calls"] if c["phase"] == phase]
    c_checks = {
        "store_read_failure_observed": any(x["phase"] == phase and x.get("error") for x in evidence["store_reads"]),
        "degraded_snapshot_created": any(x["phase"] == phase and not x["snapshot"]["available"] for x in evidence["snapshots"]),
        "unavailable_in_actual_model_prompt": any("历史记忆不可用" in p for p in actual_prompts(phase)),
        "real_model_invoked": bool(calls),
        "final_llm_answer_present": rc.status_code == 200 and bool(bc.get("output")),
    }
    evidence["checks"]["Store Failure Degradation"] = {"checks": c_checks,
        "status": "REVIEW" if all(c_checks.values()) else "FAIL", "thread": fourth,
        "failure_layer": "Context injection / API pre-model guard" if not calls else "requires answer review"}
    flush()
    print("Store Failure Degradation: " + evidence["checks"]["Store Failure Degradation"]["status"], flush=True)


def main():
    global PORT
    seed_entity_v0(RUN / "app.sqlite", doctor_a_password="SyntheticLiveDoctorA!2026", doctor_b_password="SyntheticLiveDoctorB!2026")
    manifest = {
        "source": "scripts.seed_entity_v0: deterministic synthetic_fixture",
        "patients": ["P001/Patient Alpha", "P002/Patient Beta"],
        "findings": {"F001": {"case": "C001", "diameter_mm": 6},
                     "F002": {"case": "C002", "diameter_mm": 8}},
        "isolated_paths": {"business": str(RUN / "app.sqlite"),
                           "memory": str(RUN / "memory.sqlite"),
                           "checkpoint": str(RUN / "sessions.sqlite"),
                           "derived_memory_vectors": str(RUN / "memory_vectors.sqlite"),
                           "empty_knowledge": str(RUN / "knowledge"),
                           "objects": str(RUN / "objects")},
        "image_tools": "blocked by acceptance guard; no CT or object access",
        "external_model_payload": "application prompts and synthetic test facts only",
        "credentials": "existing environment or repository .env; never recorded",
    }
    (RUN / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    evidence["isolation_manifest"] = "manifest.json"
    get_default_checkpointer(str(RUN / "sessions.sqlite"))
    # Populate observations through the real authorized service; no preference is seeded.
    MemoryService().sync_finding("D001", "F001")
    MemoryService().sync_finding("D001", "F002")
    clear_chat_model_cache()
    get_chat_model(callbacks=[EvidenceCallback()], max_retries=0)
    from api.main import app
    from martin.agent import analyze_image, download_from_oss, upload_to_oss
    listener = socket.socket()
    listener.bind(("127.0.0.1", PORT))
    PORT = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="error", access_log=False))
    with patch.object(SqliteStore, "search", recorded_search), patch.object(SqliteStore, "get", recorded_get), \
         patch.object(MemoryService, "snapshot_for_thread", recorded_snapshot), \
         patch.object(AuditLogger, "__init__", audit_init), \
         patch.object(AuditLogger, "log_tool_call", audit_call), \
         patch.object(AuditLogger, "log_agent_error", audit_error), \
         patch.object(analyze_image, "func", excluded_image_tool), \
         patch.object(download_from_oss, "func", excluded_image_tool), \
         patch.object(upload_to_oss, "func", excluded_image_tool):
        worker = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
        worker.start()
        try:
            with httpx.Client(base_url=f"http://127.0.0.1:{PORT}", timeout=240, trust_env=False) as client:
                for _ in range(100):
                    if server.started:
                        break
                    time.sleep(0.1)
                if not server.started:
                    raise RuntimeError("Acceptance API did not start")
                evidence["acceptance_service_health"] = client.get("/api/health").json()
                # 8000 上的常驻服务只是观测项；未运行时记录并继续，不影响三场景判定。
                try:
                    with httpx.Client(timeout=5, trust_env=False) as normal:
                        evidence["restarted_service_health"] = normal.get("http://127.0.0.1:8000/api/health").json()
                except Exception as exc:
                    evidence["restarted_service_health"] = {"not_running": type(exc).__name__}
                run_scenarios(client)
        except Exception as exc:
            evidence["harness_error"] = {"type": type(exc).__name__}
            return 1
        finally:
            server.should_exit = True
            worker.join(timeout=15)
            listener.close()
            close_default_checkpointer()
            close_default_store()
            vector_module = sys.modules.get("martin.memory.vector_index")
            if vector_module is not None:
                vector_module.close_default_vector_index()
            evidence["acceptance_service_stopped"] = not worker.is_alive()
            evidence["finished_at"] = datetime.now(timezone.utc).isoformat()
            flush()
            print("Evidence: " + str(RUN / "evidence.json"), flush=True)
    return int(any(result["status"] == "FAIL" for result in evidence["checks"].values()))


if __name__ == "__main__":
    raise SystemExit(main())
