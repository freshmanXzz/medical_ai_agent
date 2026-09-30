"""V1.1-1 live report checks using synthetic, isolated SQLite databases.

Run with the configured project Python from the repository root. Credentials
come from environment variables, or the local Conda state used by other live
scripts. Port 8001 must be free; the harness starts/stops its own API service.
Pass criteria: authorized current Finding -> actual report-model prompt -> real
LLM report (anatomy/date/8mm, no historical6mm), for three REST report types and
the Agent tool path. A successful fallback alone does not count as live PASS.
Evidence contains synthetic facts, public prompts/answers, never credentials or
reasoning. It lives outside Git under ../validation/finding-report-live-*/.
"""

import json
import logging
import os
from pathlib import Path
import re
import sys
import threading
import time
from datetime import datetime, timezone
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
WORKSPACE = REPO.parent
sys.path.insert(0, str(REPO))


def main():
    names = ("DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "DEEPSEEK_MODEL")
    if not all(os.environ.get(name) for name in names):
        state = WORKSPACE / "conda/envs/medical_ai_agent/conda-meta/state"
        settings = json.loads(state.read_text(encoding="utf-8"))["env_vars"]
        for name in names:
            os.environ[name] = settings[name]
    run = WORKSPACE / "validation" / (
        "finding-report-live-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    )
    run.mkdir(parents=True)
    os.environ.update({
        "MARTIN_APP_DB_PATH": str(run / "app.sqlite"),
        "MARTIN_MEMORY_DB_PATH": str(run / "memory.sqlite"),
        "LANGCHAIN_TRACING_V2": "false",
        "LANGSMITH_TRACING": "false",
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
    })
    thinking = logging.getLogger("agent_thinking")
    thinking.addHandler(logging.NullHandler())
    thinking.disabled = True
    thinking.propagate = False
    logging.basicConfig(level=logging.ERROR)

    import httpx
    import uvicorn
    from langchain_core.callbacks import BaseCallbackHandler
    from martin.agent.audit import AuditLogger
    from martin.agent.sessions import (
        close_default_checkpointer, get_default_checkpointer,
    )
    from martin.llm.chat_model import clear_chat_model_cache, get_chat_model
    from martin.memory.store import close_default_store
    from martin.services.report_input_service import ReportInputService
    from scripts.seed_entity_v0 import seed_entity_v0

    evidence = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "model": os.environ["DEEPSEEK_MODEL"],
        "scope": "Current C002 Finding without CT; isolated REST and Agent",
        "retrievals": [], "model_calls": [], "responses": [], "checks": {},
    }
    phase = "setup"

    def clean(value):
        if isinstance(value, dict):
            return {
                key: clean(item) for key, item in value.items()
                if key not in {"reasoning", "reasoning_content", "api_key", "token"}
            }
        if isinstance(value, (list, tuple)):
            return [clean(item) for item in value]
        return value

    def flush():
        (run / "evidence.json").write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    class EvidenceCallback(BaseCallbackHandler):
        def on_chat_model_start(self, serialized, messages, *, run_id, **kwargs):
            evidence["model_calls"].append({
                "run_id": str(run_id), "phase": phase,
                "prompts": [
                    {"role": message.type, "content": message.content}
                    for batch in messages for message in batch
                    if message.type in {"system", "human"}
                ],
            })
            flush()

        def on_llm_end(self, response, *, run_id, **kwargs):
            call = next(
                item for item in evidence["model_calls"]
                if item["run_id"] == str(run_id)
            )
            call["answers"] = [
                {"answer": generation.message.content,
                 "tool_calls": clean(generation.message.tool_calls),
                 "finish_reason": generation.message.response_metadata.get(
                     "finish_reason"
                 )}
                for batch in response.generations for generation in batch
            ]
            flush()

        def on_llm_error(self, error, *, run_id, **kwargs):
            evidence.setdefault("llm_errors", []).append({
                "phase": phase, "type": type(error).__name__,
            })
            flush()

    real_build = ReportInputService.build
    real_audit_init = AuditLogger.__init__
    real_audit_call = AuditLogger.log_tool_call

    def recorded_build(self, doctor_id, thread_id):
        result = real_build(self, doctor_id, thread_id)
        evidence["retrievals"].append({"phase": phase, "input": result})
        flush()
        return result

    def audit_init(self, session_id=None, audit_dir=None):
        real_audit_init(self, session_id, str(run / "audit"))

    def audit_call(self, tool_name, args, output_summary, **kwargs):
        return real_audit_call(
            self, tool_name, clean(args), output_summary, **kwargs
        )

    def verify(response, field):
        body = response.json()
        answer = body.get(field, "")
        evidence["responses"].append({
            "phase": phase, "status": response.status_code, "body": clean(body),
        })
        retrieval = next((
            item["input"] for item in evidence["retrievals"]
            if item["phase"] == phase
        ), None)
        report_calls = [
            item for item in evidence["model_calls"] if item["phase"] == phase
            and any(
                message["role"] == "human" and "【报告要求】" in message["content"]
                for message in item["prompts"]
            )
        ]
        prompts = "\n".join(
            message["content"] for call in report_calls
            for message in call["prompts"] if message["role"] == "human"
        )
        checks = {
            "http_success": response.status_code == 200,
            "current_finding_only": bool(retrieval)
            and [n["finding_id"] for n in retrieval["nodules"]] == ["F002"],
            "current_values_in_report_prompt": all(
                value in prompts for value in ("RUL", "2026-09-01", "8.00")
            ) and "2026-06-01" not in prompts,
            "real_report_llm_answer": any(
                answer.get("answer") for call in report_calls
                for answer in call.get("answers", [])
            ),
            "answer_current_diameter": bool(
                re.search(r"8(?:\.0+)?\s*(?:mm|毫米)", answer, re.I)
            ),
            "answer_anatomy": "RUL" in answer or "右上叶" in answer
            or "右肺上叶" in answer,
            "answer_observation_date": "2026-09-01" in answer
            or "2026年9月1日" in answer or "2026年09月01日" in answer,
            "no_historical_measurement": not re.search(
                r"6(?:\.0+)?\s*(?:mm|毫米)", answer, re.I
            ),
        }
        evidence["checks"][phase] = {
            "checks": checks,
            "status": "PASS" if all(checks.values()) else "FAIL",
            "semantic_review_required": "No invented CT, confidence or morphology",
        }
        flush()
        print(phase + ": " + evidence["checks"][phase]["status"], flush=True)

    seed_entity_v0(
        run / "app.sqlite", doctor_a_password="SyntheticLiveDoctorA!2026",
        doctor_b_password="SyntheticLiveDoctorB!2026",
    )
    get_default_checkpointer(str(run / "sessions.sqlite"))
    clear_chat_model_cache()
    get_chat_model(callbacks=[EvidenceCallback()], max_retries=0)
    from api.main import app

    server = uvicorn.Server(uvicorn.Config(
        app, host="127.0.0.1", port=8001, log_level="error", access_log=False,
    ))
    with patch.object(ReportInputService, "build", recorded_build), \
            patch.object(AuditLogger, "__init__", audit_init), \
            patch.object(AuditLogger, "log_tool_call", audit_call):
        worker = threading.Thread(target=server.run, daemon=True)
        worker.start()
        try:
            for _ in range(100):
                if server.started or not worker.is_alive():
                    break
                time.sleep(0.1)
            if not server.started:
                raise RuntimeError("Acceptance service did not start")
            with httpx.Client(
                base_url="http://127.0.0.1:8001", timeout=240, trust_env=False
            ) as client:
                client.post("/api/auth/login", json={
                    "username": "doctor_a", "password": "SyntheticLiveDoctorA!2026",
                }).raise_for_status()
                thread = client.post("/api/threads", json={"case_id": "C002"})
                thread.raise_for_status()
                thread_id = thread.json()["thread_id"]
                for report_type in ("brief", "detailed", "research"):
                    phase = "REST_" + report_type
                    response = client.post("/api/report/generate", json={
                        "session_id": thread_id, "report_type": report_type,
                        "detection_result": {"nodules": [{"diameter": 99}]},
                    })
                    verify(response, "report")
                phase = "Agent_report"
                response = client.post("/api/agent/chat", json={
                    "session_id": thread_id,
                    "user_message": "生成当前病例的详细报告，不要加入历史对比。",
                })
                verify(response, "output")
        except Exception as exc:
            evidence["harness_error"] = {"type": type(exc).__name__}
            raise
        finally:
            server.should_exit = True
            worker.join(timeout=15)
            evidence["acceptance_service_stopped"] = not worker.is_alive()
            close_default_checkpointer()
            close_default_store()
            evidence["finished_at"] = datetime.now(timezone.utc).isoformat()
            flush()
            print("Evidence: " + str(run / "evidence.json"), flush=True)
    if any(item["status"] != "PASS" for item in evidence["checks"].values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
