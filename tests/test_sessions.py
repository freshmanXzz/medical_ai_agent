from types import SimpleNamespace

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.sqlite import SqliteSaver

from martin.agent.sessions import SessionManager


class FakeCheckpointer:
    def __init__(self, items):
        self.items = items

    def list(self, config):
        return iter(self.items)


def checkpoint(thread_id, timestamp, messages, case_context=None):
    return SimpleNamespace(
        config={"configurable": {"thread_id": thread_id}},
        checkpoint={
            "ts": timestamp,
            "channel_values": {"messages": messages, "case_context": case_context or {}},
        },
    )


def test_list_sessions_uses_latest_checkpoint_and_first_user_message():
    items = [
        checkpoint(
            "session-a",
            "2026-07-13T10:00:00Z",
            [HumanMessage(content="分析这张 CT"), AIMessage(content="检测到 3 个结节")],
        ),
        checkpoint(
            "session-a",
            "2026-07-13T11:00:00Z",
            [
                HumanMessage(content="分析这张 CT"),
                AIMessage(content="检测到 3 个结节"),
                HumanMessage(content="生成详细报告"),
                AIMessage(content="这是详细报告"),
            ],
        ),
        checkpoint(
            "session-b",
            "2026-07-14T08:00:00Z",
            [HumanMessage(content="查询 Lung-RADS")],
        ),
    ]

    summaries = SessionManager(FakeCheckpointer(items)).list_sessions()

    assert [item.thread_id for item in summaries] == ["session-b", "session-a"]
    assert summaries[1].title == "分析这张 CT"


def test_get_messages_filters_case_context_and_tool_messages():
    items = [
        checkpoint(
            "session-a",
            "2026-07-13T11:00:00Z",
            [
                HumanMessage(content="【当前病例上下文】\n患者：65 岁"),
                HumanMessage(content="分析这张 CT"),
                ToolMessage(content="检测结果", tool_call_id="call-1"),
                AIMessage(content="检测到 3 个结节"),
            ],
        )
    ]

    messages = SessionManager(FakeCheckpointer(items)).get_messages("session-a")

    assert [(item.role, item.content) for item in messages] == [
        ("User", "分析这张 CT"),
        ("Martin", "检测到 3 个结节"),
    ]


def test_list_sessions_uses_ct_filename_when_detection_has_no_chat_messages():
    items = [
        checkpoint(
            "image-only-session",
            "2026-07-14T12:00:00Z",
            [],
            {"image_info": {"filename": "case.nii.gz"}, "nodules": [{"index": 1}]},
        )
    ]

    summaries = SessionManager(FakeCheckpointer(items)).list_sessions()

    assert summaries[0].thread_id == "image-only-session"
    assert summaries[0].title == "case.nii.gz"
    assert SessionManager(FakeCheckpointer(items)).get_case_context("image-only-session")["nodules"][0]["index"] == 1


def test_sqlite_checkpoint_survives_reopen(tmp_path):
    database = str(tmp_path / "sessions.sqlite")
    config = {
        "configurable": {
            "thread_id": "persistent-session",
            "checkpoint_ns": "",
        }
    }

    with SqliteSaver.from_conn_string(database) as saver:
        saver.put(
            config,
            {
                "v": 1,
                "id": "checkpoint-1",
                "ts": "2026-07-14T09:00:00Z",
                "channel_values": {
                    "messages": [
                        HumanMessage(content="持久化测试"),
                        AIMessage(content="已保存"),
                    ]
                },
                "channel_versions": {"__start__": 1},
                "versions_seen": {"__input__": {}},
            },
            {"source": "input", "step": 0, "writes": {}},
            {"messages": 1},
        )

    with SqliteSaver.from_conn_string(database) as saver:
        messages = SessionManager(saver).get_messages("persistent-session")

    assert [item.content for item in messages] == ["持久化测试", "已保存"]
