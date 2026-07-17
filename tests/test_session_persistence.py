"""测试会话持久化相关功能：SqliteSaver 持久化、SessionManager 列表与消息查询、多会话独立性。"""

import json
import os
import tempfile
import uuid

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from martin.agent.sessions import CONTEXT_MESSAGE_PREFIX, SessionManager

try:
    from langgraph.checkpoint.sqlite import SqliteSaver

    SQLITE_AVAILABLE = True
except ImportError:
    SQLITE_AVAILABLE = False

pytestmark = pytest.mark.skipif(not SQLITE_AVAILABLE, reason="langgraph-checkpoint-sqlite 不可用")


def _make_config(thread_id: str) -> dict:
    """构造 SqliteSaver.put 所需的 config 字典。"""
    return {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}


def _make_checkpoint(messages: list, ts: str = "2026-07-14T10:00:00Z") -> dict:
    """构造 SqliteSaver.put 所需的 checkpoint 字典。"""
    return {
        "v": 1,
        "id": str(uuid.uuid4()),
        "ts": ts,
        "channel_values": {"messages": list(messages)},
        "channel_versions": {"__start__": 1},
        "versions_seen": {"__input__": {}},
    }


_META = {"source": "input", "step": 0, "writes": {}}
_VERSIONS = {"messages": 1}


@pytest.fixture
def temp_db():
    """创建临时 SQLite 数据库文件路径，测试结束后自动清理。"""
    fd, path = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd)
    yield path
    try:
        os.unlink(path)
    except OSError:
        pass


class TestSqliteCheckpointerPersistence:
    """测试 SqliteSaver 的 checkpoint 创建与恢复。"""

    def test_checkpoint_roundtrip(self, temp_db):
        """写入 checkpoint 后能立即读取，关闭后重新打开数据仍在。"""
        messages = [
            HumanMessage(content="分析这张 CT"),
            AIMessage(content="检测到 3 个结节"),
        ]
        config = _make_config("session-roundtrip")

        with SqliteSaver.from_conn_string(temp_db) as saver:
            saver.put(config, _make_checkpoint(messages), _META, _VERSIONS)

        # 重新打开验证数据持久化
        with SqliteSaver.from_conn_string(temp_db) as saver:
            mgr = SessionManager(saver)
            result = mgr.get_messages("session-roundtrip")

        assert len(result) == 2
        assert result[0].role == "User"
        assert result[0].content == "分析这张 CT"
        assert result[1].role == "Martin"
        assert result[1].content == "检测到 3 个结节"

    def test_empty_database_returns_no_messages(self, temp_db):
        """空数据库查询不存在的 thread_id 应返回空列表。"""
        with SqliteSaver.from_conn_string(temp_db) as saver:
            mgr = SessionManager(saver)
            result = mgr.get_messages("nonexistent")

        assert result == []


class TestSessionManagerListSessions:
    """测试 SessionManager.list_sessions 方法。"""

    def test_lists_multiple_sessions(self, temp_db):
        """两个不同 thread_id 的 checkpoint 应在列表中各出现一次。"""
        with SqliteSaver.from_conn_string(temp_db) as saver:
            saver.put(
                _make_config("session-a"),
                _make_checkpoint(
                    [HumanMessage(content="查询 Lung-RADS")],
                    ts="2026-07-14T09:00:00Z",
                ),
                _META,
                _VERSIONS,
            )
            saver.put(
                _make_config("session-b"),
                _make_checkpoint(
                    [HumanMessage(content="生成详细报告")],
                    ts="2026-07-14T10:00:00Z",
                ),
                _META,
                _VERSIONS,
            )
            mgr = SessionManager(saver)
            summaries = mgr.list_sessions()

        assert len(summaries) == 2
        thread_ids = {s.thread_id for s in summaries}
        assert thread_ids == {"session-a", "session-b"}

    def test_sorted_by_updated_at_descending(self, temp_db):
        """列表应按 updated_at 降序排列（最新会话在前）。"""
        with SqliteSaver.from_conn_string(temp_db) as saver:
            saver.put(
                _make_config("older"),
                _make_checkpoint(
                    [HumanMessage(content="旧会话")],
                    ts="2026-06-01T08:00:00Z",
                ),
                _META,
                _VERSIONS,
            )
            saver.put(
                _make_config("newer"),
                _make_checkpoint(
                    [HumanMessage(content="新会话")],
                    ts="2026-07-14T12:00:00Z",
                ),
                _META,
                _VERSIONS,
            )
            mgr = SessionManager(saver)
            summaries = mgr.list_sessions()

        assert [s.thread_id for s in summaries] == ["newer", "older"]

    def test_same_thread_multiple_checkpoints_returns_latest(self, temp_db):
        """同一 thread_id 有多个 checkpoint 时只返回时间戳最新的一个。"""
        with SqliteSaver.from_conn_string(temp_db) as saver:
            saver.put(
                _make_config("same-session"),
                _make_checkpoint(
                    [HumanMessage(content="第一轮问题")],
                    ts="2026-07-14T08:00:00Z",
                ),
                _META,
                _VERSIONS,
            )
            saver.put(
                _make_config("same-session"),
                _make_checkpoint(
                    [
                        HumanMessage(content="第一轮问题"),
                        AIMessage(content="第一轮回答"),
                        HumanMessage(content="第二轮问题"),
                        AIMessage(content="第二轮回答"),
                    ],
                    ts="2026-07-14T09:00:00Z",
                ),
                _META,
                _VERSIONS,
            )
            mgr = SessionManager(saver)
            summaries = mgr.list_sessions()

        assert len(summaries) == 1
        assert summaries[0].thread_id == "same-session"
        assert summaries[0].created_at == "2026-07-14T08:00:00Z"
        # 应使用最新 checkpoint 的时间戳
        assert summaries[0].updated_at == "2026-07-14T09:00:00Z"

    def test_restores_case_context_from_checkpoint(self, temp_db):
        """结构化病例上下文应随 checkpoint 恢复。"""
        context = {
            "patient_info": {"age": 62, "gender": "男"},
            "image_info": {"image_name": "case.nii.gz"},
            "nodules": [{"index": 1, "diameter": 8.2}],
        }
        content = f"{CONTEXT_MESSAGE_PREFIX}{json.dumps(context, ensure_ascii=False)}\n\n病例摘要"

        with SqliteSaver.from_conn_string(temp_db) as saver:
            saver.put(
                _make_config("context-session"),
                _make_checkpoint([HumanMessage(content=content)]),
                _META,
                _VERSIONS,
            )
            restored = SessionManager(saver).get_case_context("context-session")

        assert restored == context

    def test_title_from_first_user_message(self, temp_db):
        """会话标题应取自第一条 User 消息。"""
        with SqliteSaver.from_conn_string(temp_db) as saver:
            saver.put(
                _make_config("title-test"),
                _make_checkpoint(
                    [HumanMessage(content="分析这张肺部 CT 图像中的结节位置和大小")],
                    ts="2026-07-14T10:00:00Z",
                ),
                _META,
                _VERSIONS,
            )
            mgr = SessionManager(saver)
            summaries = mgr.list_sessions()

        assert summaries[0].title == "分析这张肺部 CT 图像中的结节位置和大小"

    def test_long_title_truncated(self, temp_db):
        """超过 48 字符的标题应截断并加省略号。"""
        long_msg = "请帮我详细分析这张胸部 CT 图像中的所有异常发现，包括结节钙化纤维化等各类病变的详细描述信息"
        with SqliteSaver.from_conn_string(temp_db) as saver:
            saver.put(
                _make_config("long-title"),
                _make_checkpoint(
                    [HumanMessage(content=long_msg)],
                    ts="2026-07-14T10:00:00Z",
                ),
                _META,
                _VERSIONS,
            )
            mgr = SessionManager(saver)
            summaries = mgr.list_sessions()

        assert len(summaries[0].title) <= 51  # 48 + "..."
        # 中文长消息: 长度 ≤48 不截断，>48 才加 "..."
        if len(long_msg) > 48:
            assert summaries[0].title.endswith("...")
        else:
            assert not summaries[0].title.endswith("...")


class TestSessionManagerGetMessages:
    """测试 SessionManager.get_messages 方法。"""

    def test_returns_correct_roles_and_content(self, temp_db):
        """HumanMessage → User 角色，AIMessage（无 tool_calls） → Martin 角色。"""
        with SqliteSaver.from_conn_string(temp_db) as saver:
            saver.put(
                _make_config("msg-test"),
                _make_checkpoint([
                    HumanMessage(content="请分析我的 CT 结果"),
                    AIMessage(content="根据分析，您的 CT 显示右肺上叶有一个 5mm 结节。"),
                ]),
                _META,
                _VERSIONS,
            )
            mgr = SessionManager(saver)
            messages = mgr.get_messages("msg-test")

        assert len(messages) == 2
        assert messages[0].role == "User"
        assert messages[0].content == "请分析我的 CT 结果"
        assert messages[1].role == "Martin"
        assert messages[1].content == "根据分析，您的 CT 显示右肺上叶有一个 5mm 结节。"

    def test_filters_case_context_messages(self, temp_db):
        """包含"病例上下文"且含换行的 HumanMessage 应被过滤。"""
        with SqliteSaver.from_conn_string(temp_db) as saver:
            saver.put(
                _make_config("ctx-filter"),
                _make_checkpoint([
                    HumanMessage(content="【当前病例上下文】\n患者：65 岁男性"),
                    HumanMessage(content="分析结节大小"),
                    AIMessage(content="结节大小约 8mm"),
                ]),
                _META,
                _VERSIONS,
            )
            mgr = SessionManager(saver)
            messages = mgr.get_messages("ctx-filter")

        assert len(messages) == 2
        assert messages[0].content == "分析结节大小"
        assert messages[1].content == "结节大小约 8mm"

    def test_filters_tool_messages(self, temp_db):
        """ToolMessage 不应出现在显示消息中。"""
        from langchain_core.messages import ToolMessage

        with SqliteSaver.from_conn_string(temp_db) as saver:
            saver.put(
                _make_config("tool-filter"),
                _make_checkpoint([
                    HumanMessage(content="检索 Lung-RADS 标准"),
                    ToolMessage(content="Lung-RADS 检索结果...", tool_call_id="call-1"),
                    AIMessage(content="根据 Lung-RADS 标准，该结节属于 3 类。"),
                ]),
                _META,
                _VERSIONS,
            )
            mgr = SessionManager(saver)
            messages = mgr.get_messages("tool-filter")

        assert len(messages) == 2
        assert messages[0].role == "User"
        assert messages[1].role == "Martin"

    def test_messages_with_tool_calls_excluded(self, temp_db):
        """带 tool_calls 属性的 AIMessage 应被排除，只保留最终文本回复。"""
        with SqliteSaver.from_conn_string(temp_db) as saver:
            saver.put(
                _make_config("toolcall-filter"),
                _make_checkpoint([
                    HumanMessage(content="分析图像"),
                    AIMessage(content="", tool_calls=[{"name": "analyze_image", "args": {}, "id": "call_1"}]),
                    AIMessage(content="图像分析完成，发现 2 个结节。"),
                ]),
                _META,
                _VERSIONS,
            )
            mgr = SessionManager(saver)
            messages = mgr.get_messages("toolcall-filter")

        # 只应有 User 消息和最终 AIMessage（无 tool_calls 的那条）
        assert len(messages) == 2
        assert messages[1].content == "图像分析完成，发现 2 个结节。"

    def test_nonexistent_thread_returns_empty(self, temp_db):
        """查询不存在的 thread_id 返回空列表。"""
        with SqliteSaver.from_conn_string(temp_db) as saver:
            mgr = SessionManager(saver)
            messages = mgr.get_messages("ghost-session")

        assert messages == []


class TestMultiSessionIndependence:
    """测试多会话数据隔离。"""

    def test_different_threads_isolated(self, temp_db):
        """不同 thread_id 的会话消息完全独立，不会互相干扰。"""
        with SqliteSaver.from_conn_string(temp_db) as saver:
            # 会话 1：多轮对话
            saver.put(
                _make_config("session-1"),
                _make_checkpoint([
                    HumanMessage(content="会话1第一轮问题"),
                    AIMessage(content="会话1第一轮回答"),
                    HumanMessage(content="会话1第二轮问题"),
                    AIMessage(content="会话1第二轮回答"),
                ]),
                _META,
                _VERSIONS,
            )
            # 会话 2：单轮对话
            saver.put(
                _make_config("session-2"),
                _make_checkpoint([
                    HumanMessage(content="会话2唯一问题"),
                    AIMessage(content="会话2唯一回答"),
                ]),
                _META,
                _VERSIONS,
            )

        with SqliteSaver.from_conn_string(temp_db) as saver:
            mgr = SessionManager(saver)

            msgs1 = mgr.get_messages("session-1")
            msgs2 = mgr.get_messages("session-2")

            # 会话 1 应有 4 条消息
            assert len(msgs1) == 4
            assert msgs1[0].content == "会话1第一轮问题"
            assert msgs1[3].content == "会话1第二轮回答"

            # 会话 2 应有 2 条消息
            assert len(msgs2) == 2
            assert msgs2[0].content == "会话2唯一问题"
            assert msgs2[1].content == "会话2唯一回答"

            # list_sessions 返回两个独立会话
            summaries = mgr.list_sessions()
            assert len(summaries) == 2

    def test_new_session_does_not_affect_existing(self, temp_db):
        """创建新会话不会影响已有会话的数据。"""
        with SqliteSaver.from_conn_string(temp_db) as saver:
            saver.put(
                _make_config("existing"),
                _make_checkpoint(
                    [HumanMessage(content="已有会话的消息")],
                    ts="2026-07-14T09:00:00Z",
                ),
                _META,
                _VERSIONS,
            )

        # 第二次打开，添加新会话
        with SqliteSaver.from_conn_string(temp_db) as saver:
            saver.put(
                _make_config("new-session"),
                _make_checkpoint(
                    [HumanMessage(content="新会话的消息")],
                    ts="2026-07-14T10:00:00Z",
                ),
                _META,
                _VERSIONS,
            )

        # 验证两个会话数据均完整
        with SqliteSaver.from_conn_string(temp_db) as saver:
            mgr = SessionManager(saver)
            assert mgr.get_messages("existing")[0].content == "已有会话的消息"
            assert mgr.get_messages("new-session")[0].content == "新会话的消息"
            assert len(mgr.list_sessions()) == 2
