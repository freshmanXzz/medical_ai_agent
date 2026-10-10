"""Versioned system budget policy, isolated from authored clinical memory.

Parameters start as measured development safeguards, not provider token pricing.
Clinical data permissions are never granted by policy administration.
"""

from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from urllib.parse import urlparse

from langgraph.store.base import PutOp

from martin.services.access_service import AccessDeniedError

from .lifecycle import atomic_batch, write_lock
from .scope import revalidate_scope
from .store import get_default_store

POLICY_NS = ("system", "memory_budget")
VERSION_NS = ("system", "memory_budget_versions")
CONTEXT_MIN = 8192
CONTEXT_HARD_MAX = 65536
OUTPUT_MIN = 512
OUTPUT_MAX = 8192
MAX_STAGE_BATCHES = 8
PARAMETER_BOUNDS = {
    "context_window": (CONTEXT_MIN, CONTEXT_HARD_MAX),
    "reserved_output": (OUTPUT_MIN, OUTPUT_MAX),
    "safety_margin": (256, 8192),
    "minimal_background_tokens": (64, 2048),
    "summary_tokens": (128, 8192),
    "summary_trigger_count": (2, 200),
    "summary_trigger_tokens": (512, CONTEXT_HARD_MAX),
    "max_stage_batches": (1, MAX_STAGE_BATCHES),
    "max_stage_tokens": (CONTEXT_MIN, CONTEXT_HARD_MAX * MAX_STAGE_BATCHES),
    "max_stage_seconds": (1, 120),
    "version": (0, 2**31 - 1),
}

# Verified against Ark Coding Plan's official model table on 2026-10-09.
# This is a model capacity, distinct from the application's smaller hard cap.
MODEL_CONTEXT_WINDOWS = {
    "deepseek-v4.1-flash": 1024000,
    "deepseek-v4-flash": 1024000,
    "deepseek-v4-pro": 1024000,
}
MODEL_WINDOW_SOURCE = (
    "https://docs.volcengine.com/docs/ark/coding-plan-personal-ai-zcode?lang=zh"
)


def resolve_model_context(model: str, base_url: str | None = None) -> int | None:
    if base_url is not None:
        parsed = urlparse(str(base_url))
        if parsed.scheme != "https" or parsed.hostname != "ark.cn-beijing.volces.com":
            return None
    return MODEL_CONTEXT_WINDOWS.get(model)


def _quotas():
    return {
        "qa": {"rag": 40, "memory": 20, "summary": 10, "history": 30},
        "report": {"rag": 35, "memory": 25, "summary": 15, "history": 25},
        "followup": {"rag": 15, "memory": 40, "summary": 30, "history": 15},
        "default": {"rag": 25, "memory": 25, "summary": 20, "history": 30},
    }


@dataclass(frozen=True)
class BudgetPolicy:
    context_window: int = CONTEXT_HARD_MAX
    reserved_output: int = 4096
    safety_margin: int = 2048
    category_quotas: dict = field(default_factory=_quotas)
    minimal_background_tokens: int = 512
    summary_tokens: int = 2400
    summary_trigger_count: int = 12
    summary_trigger_tokens: int = 12000
    max_stage_batches: int = 4
    max_stage_tokens: int = 131072
    max_stage_seconds: int = 30
    version: int = 0

    @property
    def input_token_limit(self) -> int:
        return self.context_window - self.reserved_output - self.safety_margin

    @property
    def policy_version(self) -> int:
        return self.version

    def to_dict(self) -> dict:
        return deepcopy(asdict(self))

    @classmethod
    def from_dict(cls, data: dict, *, version: int | None = None):
        if not isinstance(data, dict) or set(data) - set(cls.__dataclass_fields__):
            raise ValueError("Unsupported budget policy fields")
        policy = cls(**deepcopy(data))
        for key, (minimum, maximum) in PARAMETER_BOUNDS.items():
            value = getattr(policy, key)
            if type(value) is not int or not minimum <= value <= maximum:
                raise ValueError(f"Invalid budget policy {key}")
        if policy.input_token_limit < 2048:
            raise ValueError("Output and safety reserves leave insufficient input")
        if (
            policy.summary_tokens + policy.minimal_background_tokens
            > policy.input_token_limit
        ):
            raise ValueError("Summary budgets exceed usable input")
        if not isinstance(policy.category_quotas, dict) or set(
            policy.category_quotas
        ) != set(_quotas()):
            raise ValueError("All supported task quota profiles are required")
        for quotas in policy.category_quotas.values():
            if not isinstance(quotas, dict) or set(quotas) != {
                "rag",
                "memory",
                "summary",
                "history",
            }:
                raise ValueError("Unsupported quota categories")
            if any(
                type(value) is not int or not 0 <= value <= 100
                for value in quotas.values()
            ):
                raise ValueError("Quota weights must be bounded integers")
            if sum(quotas.values()) != 100:
                raise ValueError("Task quota weights must total 100")
        if version is not None:
            values = policy.to_dict()
            values["version"] = version
            return cls.from_dict(values)
        return policy


class PolicyVersionConflict(ValueError):
    pass


class PolicyService:
    def __init__(self, db_path=None, store=None):
        self.db_path = db_path
        self.store = store

    def _store(self):
        return self.store if self.store is not None else get_default_store()

    def current_info(self) -> dict:
        source = "safe_default"
        policy = BudgetPolicy()
        try:
            row = self._store().get(POLICY_NS, "current")
            if row is not None:
                value = row.value
                if not isinstance(value, dict) or value.get("schema_version") != 1:
                    raise ValueError("Unsupported policy storage version")
                policy = BudgetPolicy.from_dict(
                    value["policy"], version=value["version"]
                )
                source = "persisted"
        except Exception:
            # Corrupt or unavailable config cannot disable the safety envelope.
            source = "safe_default"
        return {
            "policy": policy.to_dict(),
            "version": policy.version,
            "source": source,
            "limits": {
                "context_min": CONTEXT_MIN,
                "context_max": CONTEXT_HARD_MAX,
                "output_min": OUTPUT_MIN,
                "output_max": OUTPUT_MAX,
                "max_stage_batches": MAX_STAGE_BATCHES,
                "parameter_bounds": {
                    key: list(value)
                    for key, value in PARAMETER_BOUNDS.items()
                    if key != "version"
                },
            },
        }

    def current(self) -> BudgetPolicy:
        info = self.current_info()
        return BudgetPolicy.from_dict(info["policy"])

    def _require_admin(self, actor_id):
        if not self.can_manage(actor_id):
            raise AccessDeniedError("Budget administrator capability required")

    def can_manage(self, actor_id):
        try:
            from martin.auth.capabilities import is_budget_admin

            return is_budget_admin(actor_id, db_path=self.db_path)
        except Exception:
            return False

    def versions(self, actor_id) -> list[dict]:
        self._require_admin(actor_id)
        result, offset = [], 0
        while True:
            page = self._store().search(VERSION_NS, limit=100, offset=offset)
            result.extend(item.value for item in page if isinstance(item.value, dict))
            if len(page) < 100:
                self._require_admin(actor_id)
                return sorted(result, key=lambda value: value["version"], reverse=True)
            offset += len(page)

    def save(self, actor_id, data, *, expected_version, reason="", reverted_from=None):
        self._require_admin(actor_id)
        if type(expected_version) is not int or expected_version < 0:
            raise ValueError("Invalid expected policy version")
        if not isinstance(reason, str) or len(reason) > 500:
            raise ValueError("Budget change reason must be a bounded string")
        # Clients may echo the previous version but cannot assign a new one.
        policy = BudgetPolicy.from_dict(data)
        with write_lock:
            store = self._store()
            row = store.get(POLICY_NS, "current")
            if row:
                if (
                    not isinstance(row.value, dict)
                    or row.value.get("schema_version") != 1
                ):
                    raise ValueError(
                        "Invalid stored policy; maintenance repair is required"
                    )
                stored = BudgetPolicy.from_dict(
                    row.value["policy"], version=row.value["version"]
                )
                actual_version = stored.version
            else:
                actual_version = 0
            if actual_version != expected_version:
                raise PolicyVersionConflict(
                    "Budget policy changed; reload before saving"
                )
            previous = row.value["policy"] if row else BudgetPolicy().to_dict()
            policy = BudgetPolicy.from_dict(
                policy.to_dict(), version=actual_version + 1
            )
            record = {
                "schema_version": 1,
                "version": policy.version,
                "policy": policy.to_dict(),
                "before": previous,
                "actor_id": actor_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "reason": reason,
                "reverted_from": reverted_from,
            }
            # Recheck authorization immediately before committing the version.
            self._require_admin(actor_id)
            atomic_batch(
                store,
                [
                    PutOp(namespace=POLICY_NS, key="current", value=record),
                    PutOp(namespace=VERSION_NS, key=str(policy.version), value=record),
                ],
            )
        return self.current_info()

    def rollback(self, actor_id, target_version, *, expected_version, reason=""):
        self._require_admin(actor_id)
        if type(target_version) is not int or target_version < 0:
            raise ValueError("Invalid rollback target")
        if target_version == 0:
            data = BudgetPolicy().to_dict()
        else:
            item = self._store().get(VERSION_NS, str(target_version))
            if item is None:
                raise ValueError("Budget policy version not found")
            data = item.value["policy"]
        return self.save(
            actor_id,
            data,
            expected_version=expected_version,
            reason=reason,
            reverted_from=target_version,
        )

    @staticmethod
    def _trace_ns(scope):
        return ("doctor", scope.doctor_id, "thread", scope.thread_id, "budget_trace")

    def record_trace(self, scope, trace: dict) -> None:
        revalidate_scope(scope, db_path=self.db_path)
        if not isinstance(trace, dict):
            raise ValueError("Budget trace must be an object")
        # Only metrics/references from the budget code enter this namespace.
        # Reject text-bearing keys at any nesting level; trace isn't a PHI log.
        pending = [trace]
        while pending:
            value = pending.pop()
            if isinstance(value, dict):
                if set(value) & {
                    "text",
                    "content",
                    "messages",
                    "prompt",
                    "answer",
                    "reasoning",
                    "query",
                    "user_input",
                }:
                    raise ValueError("Budget trace cannot store clinical text")
                pending.extend(value.values())
            elif isinstance(value, list):
                pending.extend(value)
        with write_lock:
            revalidate_scope(scope, db_path=self.db_path)
            self._store().put(self._trace_ns(scope), "latest", deepcopy(trace))

    def latest_trace(self, scope) -> dict | None:
        revalidate_scope(scope, db_path=self.db_path)
        with write_lock:
            item = self._store().get(self._trace_ns(scope), "latest")
            revalidate_scope(scope, db_path=self.db_path)
            return (
                deepcopy(item.value) if item and isinstance(item.value, dict) else None
            )
