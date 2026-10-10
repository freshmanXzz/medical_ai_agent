"""Agent 编排模块

基于 LangChain create_agent 构建 Agent，底层由 LangGraph 执行 ReAct 图、
状态管理和会话持久化。动态病例 Prompt 通过 LangChain middleware 注入；
底层走 DeepSeek 原生 Function Calling，通过 Prompt 强制 reasoning 字段。

日志分离：
- 系统日志 → log/YYYY-MM-DD.log（通过标准的 logging 模块）
- 执行日志 → log/agent_thinking/YYYY-MM-DD.log（工具名称和结果状态）
- 审计日志 → audit/{session_id}.jsonl（最小结构化执行记录）
"""

import logging
import os
import re
from contextvars import ContextVar
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from langchain.agents import AgentState
from langchain.agents import create_agent as create_langchain_agent
from langchain.agents.middleware import ModelRequest, dynamic_prompt
from langchain_core.agents import AgentAction
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver

from martin.agent import (
    analyze_image,
    download_from_oss,
    generate_report,
    retrieve_knowledge,
    save_report_preference,
    update_case_context,
    upload_to_oss,
)
from martin.agent.case_context import CaseContext
from martin.agent.errors import CasePersistenceError
from martin.agent.prompt import SYSTEM_PROMPT
from martin.agent.report_scope import reset_report_scope, set_report_scope
from martin.agent.sessions import (
    SessionManager,
    get_default_checkpointer,
)
from martin.agent.tools import get_case_context, reset_case_context, set_case_context
from martin.llm.chat_model import get_chat_model
from martin.memory.actor import reset_actor_id, set_actor_id
from martin.memory.interaction import (
    MemoryInteraction,
    reset_interaction,
    set_interaction,
)
from martin.memory.output_preferences import (
    PREFERENCE_WRITE_FAILURE_MESSAGE,
    OutputPreferences,
    PreferenceValidationError,
    enforce_preferences,
)
from martin.memory.tools import (
    inspect_long_term_memory,
    retract_long_term_memory,
    save_long_term_memory,
)

logger = logging.getLogger(__name__)
_memory_prompt_var: ContextVar[str] = ContextVar("memory_prompt", default="")


def _get_thinking_logger() -> logging.Logger:
    """创建或获取 Agent 思维日志记录器。

    日志写入 log/agent_thinking/YYYY-MM-DD.log，同时输出到控制台。
    沿用历史目录名，仅记录最小执行状态，不保存原始参数或思考文本。
    """
    log_name = "agent_thinking"
    thinking_logger = logging.getLogger(log_name)
    if thinking_logger.handlers:
        return thinking_logger

    thinking_logger.setLevel(logging.INFO)
    thinking_logger.propagate = False

    # 日志目录：项目根目录下的 log/agent_thinking/
    current_dir = os.path.dirname(os.path.abspath(__file__))  # martin/agent/
    project_root = os.path.dirname(os.path.dirname(current_dir))  # 项目根
    log_dir = os.path.join(project_root, "log", "agent_thinking")
    os.makedirs(log_dir, exist_ok=True)

    log_file = os.path.join(log_dir, f"{datetime.now():%Y-%m-%d}.log")

    # 文件处理器（完整内容 + 时间戳）
    file_handler = logging.FileHandler(log_file, encoding="utf-8", mode="a")
    file_handler.setLevel(logging.INFO)
    file_fmt = logging.Formatter(
        "%(asctime)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_fmt)
    thinking_logger.addHandler(file_handler)

    logger.info("Agent 思维日志文件: %s", log_file)
    return thinking_logger


# ─── 日志回调 ───────────────────────────────────────────────

class AgentLoggingHandler(BaseCallbackHandler):
    """LangChain 回调处理器，记录 Agent 中间步骤日志。

    仅输出工具名与状态到 log/agent_thinking/YYYY-MM-DD.log。
    """

    def __init__(self):
        super().__init__()
        self._current_tool_name = ""
        self._current_tool_args: Dict = {}
        self._current_reasoning = ""
        self._thinking_logger = _get_thinking_logger()

    def on_chat_model_start(self, serialized, messages, **kwargs) -> None:
        self._current_tool_name = ""
        self._current_tool_args = {}
        self._current_reasoning = ""

    @staticmethod
    def _parse_tool_input(input_str: Any) -> Dict:
        """将工具输入解析为字典。

        langgraph 将参数序列化为 Python repr 格式（单引号），
        json.loads 无法解析，需用 ast.literal_eval。
        """
        import ast
        import json

        if isinstance(input_str, dict):
            return dict(input_str)
        if isinstance(input_str, str):
            try:
                return json.loads(input_str)
            except json.JSONDecodeError:
                pass
            try:
                return ast.literal_eval(input_str)
            except (ValueError, SyntaxError):
                pass
            return {"raw": input_str[:200]}
        return {"raw": str(input_str)[:200]}

    def on_tool_start(self, serialized, input_str, **kwargs) -> None:
        """工具即将执行时打印 Thought/Action 日志。"""
        tool_name = serialized.get("name", "unknown")
        self._current_tool_name = tool_name

        tool_args = self._parse_tool_input(input_str)
        self._current_reasoning = ""
        self._current_tool_args = {}

        # --- 思维日志文件（完整内容） ---
        self._thinking_logger.info(
            "[%s] 调用工具: %s", "Agent", tool_name
        )

    def on_tool_end(self, output, **kwargs) -> None:
        """工具执行完毕后打印 Observation 日志。"""
        # langgraph 传递的是 ToolMessage 对象
        content = output.content if hasattr(output, "content") else str(output)
        content = (
            "tool_failed" if str(content).startswith("错误:") else "tool_completed"
        )

        # --- 思维日志文件（完整） ---
        self._thinking_logger.info(
            "[%s] 观察结果: %s", "Agent", content
        )
        self._thinking_logger.info("")

    @staticmethod
    def _extract_args(raw: Any) -> Dict:
        """安全提取工具参数字典（去除 reasoning）。"""
        if isinstance(raw, dict):
            return {k: v for k, v in raw.items() if k != "reasoning"}
        return {"input": str(raw)[:200]}


# ─── State Schema 与 Prompt 构造 ─────────────────────────────


class MartinState(AgentState):
    """Martin 的 LangChain Agent State，底层由 LangGraph 持久化。"""

    case_context: dict  # CaseContext.to_dict() 的序列化结果


def _build_system_prompt(state: MartinState) -> str:
    """从 State 中提取病例上下文，构建当前轮的系统提示词。"""
    ctx_dict = state.get("case_context") or {}

    if ctx_dict:
        try:
            ctx = CaseContext.from_dict(ctx_dict)
            context_str = ctx.to_context_string(max_nodules=5)
            if context_str:
                return (
                    f"{SYSTEM_PROMPT}\n\n"
                    f"【当前病例上下文】\n{context_str}\n\n"
                    "请基于以上病例信息理解后续问题。"
                )
        except Exception:
            pass

    return SYSTEM_PROMPT


@dynamic_prompt
def _case_context_prompt(request: ModelRequest) -> str:
    """运行期间以工具使用的同一个对象构建 Prompt，完成后统一保存快照。"""
    prompt = _build_system_prompt({"case_context": get_case_context().to_dict()})
    memory_prompt = _memory_prompt_var.get()
    # Tool execution may have superseded or withdrawn the snapshot from turn start.
    # Context variables in parallel tool workers cannot update their parent, so
    # inspect the completed tool messages when constructing the next model input.
    messages = request.state.get("messages", [])
    start = next(
        (
            i + 1
            for i in range(len(messages) - 1, -1, -1)
            if isinstance(messages[i], HumanMessage)
        ),
        0,
    )
    mutations = {
        "save_long_term_memory",
        "save_report_preference",
        "retract_long_term_memory",
    }
    call_ids = {
        call["id"]
        for message in messages[start:]
        if isinstance(message, AIMessage)
        for call in message.tool_calls
        if call["name"] in mutations
    }
    if any(
        isinstance(message, ToolMessage)
        and message.tool_call_id in call_ids
        and not str(message.content).startswith("错误:")
        for message in messages[start:]
    ):
        from martin.agent.report_scope import current_report_scope
        from martin.memory.interaction import current_interaction
        from martin.memory.router import MemoryRetrievalRouter

        actor, interaction = current_report_scope(), current_interaction()
        if actor is not None and interaction is not None:
            context = MemoryRetrievalRouter().retrieve(
                actor.doctor_id, actor.thread_id, interaction.user_text
            )
            memory_prompt = context.to_prompt(interaction.user_text)
    return f"{prompt}\n\n{memory_prompt}" if memory_prompt else prompt


# ─── Agent 执行器 ───────────────────────────────────────────

class AgentExecutor:
    """基于 LangChain Agent API 的 Agent 执行器。

    使用 LangChain create_agent、MartinState 与 dynamic_prompt middleware 构建；
    LangGraph 在底层自动管理 ReAct 工具路由、State 与 Checkpointer。
    支持在同一会话（thread_id）的多个实例间共享病例上下文。
    """

    def __init__(
        self,
        tools: List[BaseTool],
        verbose: bool = True,
        thread_id: Optional[str] = None,
        checkpointer: Optional[BaseCheckpointSaver] = None,
        doctor_id: Optional[str] = None,
    ):
        self.tools = tools
        self.verbose = verbose
        self.handle_parsing_errors = True
        self.thread_id = thread_id or "default"
        self.doctor_id = doctor_id
        self.memory_prompt = ""
        self.report_preferences = {}
        self._thinking_logger = _get_thinking_logger()

        # 会话记忆：同一 thread_id 的多次 invoke 自动保持历史
        memory = checkpointer or get_default_checkpointer()

        # 从 Checkpointer 的 state 恢复 CaseContext，若无则新建
        saved_context = SessionManager(memory).get_case_context(self.thread_id)
        if saved_context:
            self.case_context = CaseContext.from_dict(saved_context)
        else:
            self.case_context = CaseContext()

        llm = get_chat_model()

        self._agent = create_langchain_agent(
            model=llm,
            tools=tools,
            state_schema=MartinState,
            middleware=[_case_context_prompt],
            checkpointer=memory,
        )

        logger.info(
            "Agent 创建成功，工具数量: %d, thread_id: %s",
            len(tools),
            self.thread_id,
        )

    def invoke(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """执行一次 Agent 推理（自动保持会话记忆）。

        Args:
            inputs: 输入字典，必须含 "input" 字段。
                    "chat_history" 字段不需传入，由 LangGraph Checkpointer 自动管理。

        Returns:
            含 "output" 和 "intermediate_steps" 的字典。
        """
        user_input = inputs.get("input", "")
        human_input = inputs.get("human_input", user_input)
        if not isinstance(user_input, str) or not isinstance(human_input, str):
            return {"output": "错误: 对话输入必须为文本。", "intermediate_steps": []}
        interaction_id = str(uuid4())
        messages = [HumanMessage(content=user_input, id=interaction_id)]

        # langgraph 的 thread_id 配置
        config = {"configurable": {"thread_id": self.thread_id}}

        # 回调（仅 verbose=True 时附加）
        if self.verbose:
            config["callbacks"] = [AgentLoggingHandler()]

        # 设置当前会话的病例上下文，供工具调用时使用
        token = set_case_context(self.case_context)
        memory_token = _memory_prompt_var.set(getattr(self, "memory_prompt", ""))
        actor_token = set_actor_id(getattr(self, "doctor_id", None))
        report_token = set_report_scope(getattr(self, "doctor_id", None), self.thread_id)
        interaction_token = set_interaction(MemoryInteraction(
            interaction_id, human_input,
        ))
        try:
            result = self._agent.invoke(
                {
                    "messages": messages,
                    "case_context": self.case_context.to_dict(),
                },
                config=config,
            )
        except Exception as e:
            logger.error("Agent 执行失败: %s", type(e).__name__)
            return {
                "output": f"错误: Agent 执行失败: {e}",
                "intermediate_steps": [],
            }
        finally:
            reset_interaction(interaction_token)
            reset_report_scope(report_token)
            reset_actor_id(actor_token)
            _memory_prompt_var.reset(memory_token)
            reset_case_context(token)

        # 工具修改的是当前运行对象；Graph 中的输入快照不能反向覆盖它。
        # 所有工具结束后，由 save_case_context 统一写入持久化快照。

        all_messages = result.get("messages", [])
        parsed_result = self._parse_result(all_messages)
        initial_output = parsed_result["output"]
        preferences = OutputPreferences.from_dict(
            getattr(self, "report_preferences", {})
        ).for_task(user_input)
        steps = parsed_result.get("intermediate_steps", [])
        durable_write_failed = any(
            action.tool == "save_long_term_memory" and str(output).startswith("错误:")
            for action, output in steps
        )
        retraction_failed = any(
            action.tool == "retract_long_term_memory"
            and str(output).startswith("错误:")
            for action, output in steps
        )
        write_failed = False
        for action, output in steps:
            if action.tool == "save_report_preference":
                preferences = OutputPreferences.from_dict(
                    action.tool_input
                ).for_task(user_input)
                if str(output).startswith("错误:"):
                    write_failed = True
            if action.tool == "retract_long_term_memory" and not str(output).startswith(
                "错误:"
            ):
                from martin.memory.service import MemoryService

                try:
                    current = MemoryService().get_doctor_preferences(self.doctor_id)
                    preferences = OutputPreferences.from_dict(
                        current.get("report_style", {})
                    ).for_task(user_input)
                except Exception:
                    # A completed withdrawal must not re-enable cached formatting rules.
                    preferences = OutputPreferences()
        report_requested = any(action.tool == "generate_report" for action, _ in steps)
        report_requested = report_requested or bool(re.search(
            r"(?:生成|出|写|整理|提供).{0,6}报告", user_input
        ))
        if durable_write_failed:
            parsed_result["memory_write_failed"] = True
            failure = "长期记忆保存失败，本次内容未确认写入；后续会话可能无法恢复。"
            parsed_result["output"] = (
                parsed_result["output"] + "\n" + failure if report_requested else failure
            )
        if write_failed:
            parsed_result["memory_write_failed"] = True
        if write_failed and not report_requested:
            # Never let a model's optimistic acknowledgement override failed I/O.
            parsed_result["output"] = PREFERENCE_WRITE_FAILURE_MESSAGE
            if preferences.focus_spiculation:
                parsed_result["output"] += "毛刺征只按已有资料描述。"

        if retraction_failed:
            parsed_result["memory_write_failed"] = True
            parsed_result["output"] = (
                "长期记忆撤回失败，原记忆可能仍生效；请重试，不能视为已取消。"
            )

        if report_requested and not retraction_failed:
            try:
                parsed_result["output"], parsed_result["preference_validation"] = (
                    enforce_preferences(
                        parsed_result["output"], preferences,
                        lambda messages: get_chat_model().invoke(messages),
                        persistence_failed=write_failed,
                        memory_persistence_failed=durable_write_failed,
                        focus_context=self._focus_context(),
                    )
                )
            except PreferenceValidationError:
                # A failed repair must not leave an unapproved final in history.
                self._replace_final_answer(
                    all_messages, "报告格式校验未通过，暂未提供正式报告，请重试。"
                )
                self.save_case_context()
                raise
        if parsed_result["output"] != initial_output:
            self._replace_final_answer(all_messages, parsed_result["output"])

        # 根据工具执行结果同步病例上下文
        self._sync_case_context_from_steps(
            parsed_result.get("intermediate_steps", [])
        )

        self.save_case_context()

        return parsed_result

    def _replace_final_answer(self, messages: list, answer: str) -> None:
        """Persist the exact public answer using the original message identity."""
        start = next((
            i + 1 for i in range(len(messages) - 1, -1, -1)
            if isinstance(messages[i], HumanMessage)
        ), 0)
        last_answer = next((
            msg for msg in reversed(messages[start:])
            if isinstance(msg, AIMessage) and not msg.tool_calls
        ), None)
        try:
            self._agent.update_state(
                {"configurable": {"thread_id": self.thread_id}},
                {"messages": [AIMessage(
                    content=answer, id=last_answer.id if last_answer else None,
                )]},
            )
        except Exception as exc:
            raise CasePersistenceError("病例保存失败，请重试。") from exc

    def _focus_context(self) -> str:
        """Only literal current-case descriptions, never historical observations."""
        lines = [
            note.strip() for note in self.case_context.clinical_notes
            if isinstance(note, str) and "毛刺" in note
        ]
        for nodule in self.case_context.nodules[:5]:
            for key, value in nodule.items():
                if "毛刺" in str(value) or key in ("spiculation", "毛刺", "毛刺征"):
                    lines.append(f"{key}：{value}")
        return "\n".join(lines)[:500]

    def save_case_context(self) -> None:
        """将当前病例上下文写入该会话的最新 LangGraph checkpoint。

        除了常规 ``invoke``，影像 API 也会直接调用检测工具。两条路径都必须
        使用同一入口写回 state，避免进程内显示已更新、重启后却丢失病例数据。
        """
        config = {"configurable": {"thread_id": self.thread_id}}
        try:
            self._agent.update_state(
                config,
                {"case_context": self.case_context.to_dict()},
            )
        except Exception as exc:
            logger.error("写回病例上下文 checkpoint 失败: %s", type(exc).__name__)
            raise CasePersistenceError("病例保存失败，请重试。") from exc

    def _sync_case_context_from_steps(
        self, intermediate_steps: List[Tuple[AgentAction, str]]
    ) -> None:
        """根据 Agent 中间步骤同步病例上下文。

        Args:
            intermediate_steps: AgentAction 与工具输出的元组列表。
        """
        try:
            for action, output in intermediate_steps:
                tool_name = getattr(action, "tool", "")
                output_str = str(output)
                is_error = any(
                    marker in output_str
                    for marker in ("错误:", "未初始化", "报告生成失败")
                )

                if tool_name == "retrieve_knowledge" and not is_error:
                    self.case_context.set_knowledge_summary(output_str[:2000])
                elif tool_name == "generate_report" and not is_error:
                    self.case_context.add_clinical_note("已生成病例报告。")
        except Exception as e:
            logger.warning("从 Agent 结果同步病例上下文失败: %s", type(e).__name__)

    def _parse_result(self, messages: List) -> Dict[str, Any]:
        """只解析最后一条用户消息之后的调用，按 tool_call_id 配对。"""
        intermediate_steps: List[Tuple[AgentAction, str]] = []
        final_output = ""
        start = next(
            (i + 1 for i in range(len(messages) - 1, -1, -1)
             if isinstance(messages[i], HumanMessage)),
            0,
        )
        current_messages = messages[start:]
        outputs = {
            msg.tool_call_id: msg.content
            for msg in current_messages if isinstance(msg, ToolMessage)
        }
        seen = set()

        for msg in current_messages:
            if isinstance(msg, AIMessage) and msg.tool_calls:
                for tc in msg.tool_calls:
                    call_id = tc.get("id")
                    if not call_id or call_id in seen:
                        continue
                    seen.add(call_id)
                    tool_name = tc.get("name", "")
                    tool_args = tc.get("args", {})

                    action = AgentAction(
                        tool=tool_name,
                        tool_input=tool_args,
                        log="",
                    )
                    intermediate_steps.append((action, outputs.get(call_id, "")))

            elif isinstance(msg, AIMessage) and not msg.tool_calls:
                final_output = msg.content or ""

        if self.verbose and final_output:
            self._thinking_logger.info(
                "[Agent] 公开答复已生成，字符数: %d", len(final_output)
            )

        return {
            "output": final_output,
            "intermediate_steps": intermediate_steps,
        }


# ─── Martin Agent 工厂函数 ────────────────────────────────────

def create_agent(
    tools: Optional[List[BaseTool]] = None,
    verbose: bool = True,
    thread_id: Optional[str] = None,
    checkpointer: Optional[BaseCheckpointSaver] = None,
    doctor_id: Optional[str] = None,
) -> AgentExecutor:
    """创建基于 LangChain Agent API 的 Martin Agent 执行器。

    Args:
        tools: 工具列表，默认为六个核心工具：
               analyze_image / retrieve_knowledge / generate_report /
               update_case_context / upload_to_oss / download_from_oss。
        verbose: 是否打印详细日志。
        thread_id: 会话 ID，同一 thread_id 的多次调用共享记忆。
        checkpointer: 可选的检查点保存器，默认 None 时使用 SqliteSaver。

    Returns:
        AgentExecutor 实例。
    """
    if tools is None:
        tools = [
            analyze_image,
            retrieve_knowledge,
            generate_report,
            update_case_context,
            upload_to_oss,
            download_from_oss,
        ]
        if doctor_id is not None:
            tools.append(save_report_preference)
            tools.append(save_long_term_memory)
            tools.append(inspect_long_term_memory)
            tools.append(retract_long_term_memory)
    return AgentExecutor(
        tools=tools,
        verbose=verbose,
        thread_id=thread_id,
        checkpointer=checkpointer,
        doctor_id=doctor_id,
    )
