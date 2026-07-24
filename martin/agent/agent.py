"""Agent 编排模块

完整迁移至 langchain 1.x：create_agent + SqliteSaver 会话记忆。
底层走 DeepSeek 原生 Function Calling，通过 Prompt 强制 reasoning 字段。

日志分离：
- 系统日志 → log/YYYY-MM-DD.log（通过标准的 logging 模块）
- 思维日志 → log/agent_thinking/YYYY-MM-DD.log（Agent 推理过程、工具调用参数、完整 reasoning）
- 审计日志 → audit/{session_id}.jsonl（结构化 reasoning 审计溯源）
"""
import logging
import os
from datetime import datetime
from typing import Annotated, Any, Dict, List, Optional, Tuple, TypedDict

from langchain_core.agents import AgentAction
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.message import add_messages
from langgraph.managed import IsLastStep, RemainingSteps

# 使用 langgraph.prebuilt.create_react_agent 而非 langchain.agents.create_agent，
# 因为前者支持 prompt Callable（动态注入 CaseContext），后者仅有静态 system_prompt。
# 弃用警告预计在 LangGraph V2.0 才移除，当前 V1.x 可安全使用。
from langgraph.prebuilt import create_react_agent as create_langchain_agent

from martin.agent import (
    analyze_image,
    download_from_oss,
    generate_report,
    retrieve_knowledge,
    update_case_context,
    upload_to_oss,
)
from martin.agent.prompt import SYSTEM_PROMPT
from martin.agent.case_context import CaseContext
from martin.agent.tools import reset_case_context, set_case_context
from martin.llm.chat_model import get_chat_model
from martin.agent.sessions import (
    SessionManager,
    get_default_checkpointer,
)

logger = logging.getLogger(__name__)


def _get_thinking_logger() -> logging.Logger:
    """创建或获取 Agent 思维日志记录器。

    日志写入 log/agent_thinking/YYYY-MM-DD.log，同时输出到控制台。
    与控制台 print() 不同，该日志器记录完整的 reasoning 和参数（不截断）。
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

    仅输出到 log/agent_thinking/YYYY-MM-DD.log（完整内容，含时间戳）。
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
        self._current_reasoning = (
            tool_args.pop("reasoning", "") if isinstance(tool_args, dict) else ""
        )
        self._current_tool_args = self._extract_args(tool_args)

        # --- 思维日志文件（完整内容） ---
        self._thinking_logger.info(
            "[%s] 调用工具: %s", "Agent", tool_name
        )
        self._thinking_logger.info(
            "[%s] 工具参数: %s", "Agent", self._current_tool_args
        )
        if self._current_reasoning:
            self._thinking_logger.info(
                "[%s] 推理过程 (完整 CoT): %s", "Agent", self._current_reasoning
            )
        else:
            self._thinking_logger.info(
                "[%s] 警告: reasoning 字段缺失", "Agent"
            )

    def on_tool_end(self, output, **kwargs) -> None:
        """工具执行完毕后打印 Observation 日志。"""
        # langgraph 传递的是 ToolMessage 对象
        content = output.content if hasattr(output, "content") else str(output)

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


class MartinState(TypedDict):
    """Martin Agent 的 State Schema，扩展 LangGraph 默认 State。"""

    messages: Annotated[list[BaseMessage], add_messages]
    is_last_step: IsLastStep
    remaining_steps: RemainingSteps
    case_context: dict  # CaseContext.to_dict() 的序列化结果


def _build_prompt(state: MartinState) -> list:
    """从 state 中提取 case_context，动态生成完整消息列表。

    LangGraph 的 create_react_agent 在 prompt 为 Callable 且返回 list 时，
    会用返回值完全替换 LLM 的输入消息列表。因此必须包含 state["messages"]，
    否则对话历史和用户输入会丢失。
    """
    messages = state.get("messages", [])
    ctx_dict = state.get("case_context") or {}

    system_messages = []
    if ctx_dict:
        try:
            ctx = CaseContext.from_dict(ctx_dict)
            context_str = ctx.to_context_string(max_nodules=5)
            if context_str:
                system_messages = [
                    SystemMessage(content=SYSTEM_PROMPT),
                    SystemMessage(
                        content=(
                            f"【当前病例上下文】\n{context_str}\n\n"
                            "请基于以上病例信息理解后续问题。"
                        )
                    ),
                ]
        except Exception:
            pass

    if not system_messages:
        system_messages = [SystemMessage(content=SYSTEM_PROMPT)]

    return system_messages + list(messages)


# ─── Agent 执行器 ───────────────────────────────────────────

class AgentExecutor:
    """基于 langchain 1.x 的 Agent 执行器。

    使用 create_agent + LangGraph Checkpointer 构建，
    自动保持多轮对话记忆，底层走 DeepSeek 原生 Function Calling。
    支持在同一会话（thread_id）的多个实例间共享病例上下文。
    """

    def __init__(
        self,
        tools: List[BaseTool],
        verbose: bool = True,
        thread_id: Optional[str] = None,
        checkpointer: Optional[BaseCheckpointSaver] = None,
    ):
        self.tools = tools
        self.verbose = verbose
        self.handle_parsing_errors = True
        self.thread_id = thread_id or "default"
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
            prompt=_build_prompt,
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
        messages = [("human", user_input)]

        # langgraph 的 thread_id 配置
        config = {"configurable": {"thread_id": self.thread_id}}

        # 回调（仅 verbose=True 时附加）
        if self.verbose:
            config["callbacks"] = [AgentLoggingHandler()]

        # 设置当前会话的病例上下文，供工具调用时使用
        token = set_case_context(self.case_context)
        try:
            result = self._agent.invoke(
                {
                    "messages": messages,
                    "case_context": self.case_context.to_dict(),
                },
                config=config,
            )
        except Exception as e:
            logger.error("Agent 执行失败: %s", e, exc_info=True)
            return {
                "output": f"错误: Agent 执行失败: {e}",
                "intermediate_steps": [],
            }
        finally:
            reset_case_context(token)

        # 从返回的 state 中读取最新的 case_context
        if isinstance(result, dict) and "case_context" in result:
            latest_ctx = result.get("case_context")
            if latest_ctx:
                self.case_context = CaseContext.from_dict(latest_ctx)

        all_messages = result.get("messages", [])
        parsed_result = self._parse_result(all_messages)

        # 根据工具执行结果同步病例上下文
        self._sync_case_context_from_steps(
            parsed_result.get("intermediate_steps", [])
        )

        self.save_case_context()

        return parsed_result

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
            # 不影响已生成的回答，但记录错误，避免“界面显示已更新、重启后丢失”
            # 这类难以追踪的数据不一致问题。
            logger.error("写回病例上下文 checkpoint 失败: %s", exc, exc_info=True)

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
                is_error = "错误:" in output_str or "未初始化" in output_str

                if tool_name == "retrieve_knowledge" and not is_error:
                    self.case_context.set_knowledge_summary(output_str[:2000])
                elif tool_name == "generate_report" and not is_error:
                    self.case_context.add_clinical_note("已生成病例报告。")
        except Exception as e:
            logger.warning("从 Agent 结果同步病例上下文失败: %s", e)

    def _parse_result(self, messages: List) -> Dict[str, Any]:
        """从完整消息列表中解析 output 和 intermediate_steps。"""
        intermediate_steps: List[Tuple[AgentAction, str]] = []
        final_output = ""

        for msg in messages:
            if isinstance(msg, AIMessage) and msg.tool_calls:
                for tc in msg.tool_calls:
                    tool_name = tc.get("name", "")
                    tool_args = tc.get("args", {})

                    action = AgentAction(
                        tool=tool_name,
                        tool_input=tool_args,
                        log="",
                    )
                    intermediate_steps.append((action, ""))

            elif isinstance(msg, ToolMessage):
                if intermediate_steps and intermediate_steps[-1][1] == "":
                    action, _ = intermediate_steps[-1]
                    intermediate_steps[-1] = (action, msg.content)

            elif isinstance(msg, AIMessage) and not msg.tool_calls:
                final_output = msg.content or ""

        if self.verbose and final_output:
            self._thinking_logger.info("[Agent] 最终输出:")
            self._thinking_logger.info(final_output)

        return {
            "output": final_output,
            "intermediate_steps": intermediate_steps,
        }


# ─── 工厂函数 ───────────────────────────────────────────────

def create_agent(
    tools: Optional[List[BaseTool]] = None,
    verbose: bool = True,
    thread_id: Optional[str] = None,
    checkpointer: Optional[BaseCheckpointSaver] = None,
) -> AgentExecutor:
    """创建 Agent 执行器。

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
    return AgentExecutor(
        tools=tools,
        verbose=verbose,
        thread_id=thread_id,
        checkpointer=checkpointer,
    )
