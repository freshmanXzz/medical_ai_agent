"""会话检查点访问和历史会话展示工具。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver


@dataclass(frozen=True)
class SessionSummary:
    thread_id: str
    title: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class ConversationMessage:
    role: str
    content: str


def _message_content(message: Any) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            item.get("text", "") if isinstance(item, dict) else str(item)
            for item in content
        )
    return str(content)


def _is_context_message(content: str) -> bool:
    """过滤 invoke 前注入的病例摘要，不把它显示成用户消息。"""
    return "病例上下文" in content and "\n" in content


def _display_messages(messages: Iterable[Any]) -> List[ConversationMessage]:
    displayed: List[ConversationMessage] = []
    for message in messages:
        content = _message_content(message).strip()
        if not content or isinstance(message, (HumanMessage, AIMessage)) is False:
            continue
        if isinstance(message, HumanMessage):
            if _is_context_message(content):
                continue
            displayed.append(ConversationMessage("User", content))
        elif isinstance(message, AIMessage) and not getattr(message, "tool_calls", None):
            displayed.append(ConversationMessage("Martin", content))
    return displayed


def _title_from_messages(messages: Iterable[Any]) -> str:
    for message in _display_messages(messages):
        if message.role == "User":
            title = " ".join(message.content.split())
            return title[:48] + ("..." if len(title) > 48 else "")
    return "未命名会话"


def _checkpoint_messages(item: Any) -> List[Any]:
    checkpoint = getattr(item, "checkpoint", {}) or {}
    channel_values = checkpoint.get("channel_values", {})
    return channel_values.get("messages", []) or []


def _checkpoint_time(item: Any) -> str:
    checkpoint = getattr(item, "checkpoint", {}) or {}
    return checkpoint.get("ts", "") or ""


class SessionManager:
    """基于 LangGraph checkpointer 的会话列表和消息查询。"""

    def __init__(self, checkpointer: BaseCheckpointSaver):
        self.checkpointer = checkpointer

    def _latest_checkpoints(self) -> Dict[str, Any]:
        latest: Dict[str, Any] = {}
        for item in self.checkpointer.list(None):
            config = getattr(item, "config", {}) or {}
            thread_id = config.get("configurable", {}).get("thread_id")
            if not thread_id:
                continue
            previous = latest.get(thread_id)
            if previous is None or _checkpoint_time(item) >= _checkpoint_time(previous):
                latest[thread_id] = item
        return latest

    def list_sessions(self) -> List[SessionSummary]:
        summaries = []
        for thread_id, item in self._latest_checkpoints().items():
            timestamp = _checkpoint_time(item)
            summaries.append(
                SessionSummary(
                    thread_id=thread_id,
                    title=_title_from_messages(_checkpoint_messages(item)),
                    created_at=timestamp,
                    updated_at=timestamp,
                )
            )
        return sorted(summaries, key=lambda item: item.updated_at, reverse=True)

    def get_messages(self, thread_id: str) -> List[ConversationMessage]:
        item = self._latest_checkpoints().get(thread_id)
        if item is None:
            return []
        return _display_messages(_checkpoint_messages(item))


class CheckpointerManager:
    """持有进程级 checkpointer，保证 Agent 实例共享同一存储。"""

    def __init__(self, checkpointer: BaseCheckpointSaver, context: Any = None):
        self.checkpointer = checkpointer
        self._context = context

    def close(self) -> None:
        if self._context is not None:
            self._context.__exit__(None, None, None)
            self._context = None


_default_manager: Optional[CheckpointerManager] = None


def create_memory_checkpointer() -> CheckpointerManager:
    return CheckpointerManager(MemorySaver())


def get_default_checkpointer(db_path: Optional[str] = None) -> BaseCheckpointSaver:
    global _default_manager
    if _default_manager is None:
        from langgraph.checkpoint.sqlite import SqliteSaver

        if db_path is None:
            project_root = Path(__file__).resolve().parents[2]
            db_path = str(project_root / "data" / "sessions.sqlite")
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        context = SqliteSaver.from_conn_string(db_path)
        _default_manager = CheckpointerManager(context.__enter__(), context)
    return _default_manager.checkpointer


def close_default_checkpointer() -> None:
    global _default_manager
    if _default_manager is not None:
        _default_manager.close()
        _default_manager = None

