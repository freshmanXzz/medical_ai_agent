"""Agent 对话 API 路由

封装已有 AgentExecutor，提供 REST 和 WebSocket 两种交互方式。
不重新实现 Agent 逻辑，仅做 API 封装。
"""
import json
import logging
import asyncio

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from langchain_core.agents import AgentAction

from api.models import (
    AttachmentInfo,
    ChatRequest,
    ChatResponse,
    ToolCallInfo,
    WsStatusMessage,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Agent 对话"])

# 医学影像文件扩展名
_MEDICAL_IMAGE_EXTENSIONS = (".nii", ".nii.gz", ".dcm")


def _is_medical_image(filename: str) -> bool:
    """判断文件是否为医学影像格式"""
    filename_lower = filename.lower()
    return any(filename_lower.endswith(ext) for ext in _MEDICAL_IMAGE_EXTENSIONS)


def _process_attachment(agent, attachment: AttachmentInfo) -> str:
    """处理附件，注入 CaseContext 并返回引导消息

    Args:
        agent: AgentExecutor 实例
        attachment: 附件信息

    Returns:
        引导 Agent 的消息前缀
    """
    if attachment.medical_image or _is_medical_image(attachment.filename):
        # 注入影像信息到 CaseContext
        agent.case_context.image_info = {
            "modality": "CT",
            "image_path": attachment.object_key,
            "filename": attachment.filename,
        }
        return (
            f"已上传医学影像文件: {attachment.filename}（OSS路径: {attachment.object_key}）。"
            f"请调用 analyze_image 工具进行影像分析。"
        )
    else:
        return f"已上传文件: {attachment.filename}（OSS路径: {attachment.object_key}）。"


@router.post("/agent/chat", response_model=ChatResponse)
def agent_chat(request: ChatRequest):
    """Agent 对话接口，调用现有 AgentExecutor 进行推理。"""
    from martin.agent.agent import create_agent
    from martin.agent.sessions import get_default_checkpointer

    try:
        checkpointer = get_default_checkpointer()
        agent = create_agent(
            thread_id=request.session_id,
            checkpointer=checkpointer,
            verbose=False,
        )
    except ValueError as exc:
        logger.warning("Agent 尚未完成配置: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Agent 尚未完成配置，请检查 DEEPSEEK_API_KEY。",
        ) from exc

    if request.case_context:
        from martin.agent.agent import AgentExecutor
        from martin.agent.case_context import CaseContext

        restored_context = CaseContext.from_dict(request.case_context)
        AgentExecutor._context_cache[request.session_id] = restored_context
        agent.case_context = restored_context

    # 处理附件：注入影像信息并生成引导消息
    user_message = request.user_message
    if request.attachment is not None:
        guidance = _process_attachment(agent, request.attachment)
        stripped = user_message.strip()
        # 若用户消息为占位符（空白或单字符如 "."），直接使用引导消息
        if not stripped or stripped == ".":
            user_message = guidance
        else:
            user_message = f"{guidance}{user_message}"

    result = agent.invoke({"input": user_message})
    if str(result.get("output", "")).startswith("错误: Agent 执行失败"):
        raise HTTPException(status_code=502, detail="Agent 执行失败，请稍后重试。")

    # 解析 intermediate_steps 为 tool_calls
    tool_calls = []
    for action, output in result.get("intermediate_steps", []):
        if isinstance(action, AgentAction):
            tool_args = dict(action.tool_input) if isinstance(action.tool_input, dict) else {"input": str(action.tool_input)}
            tool_args.pop("reasoning", None)
            tool_calls.append(ToolCallInfo(
                tool_name=action.tool,
                tool_args=tool_args,
                output=str(output)[:500],
            ))

    # 获取当前病例上下文
    case_context = {}
    try:
        case_context = agent.case_context.to_dict()
    except Exception:
        pass

    return ChatResponse(
        output=result.get("output", ""),
        session_id=request.session_id,
        tool_calls=tool_calls,
        case_context=case_context,
    )


@router.websocket("/ws/agent/{session_id}")
async def agent_websocket(websocket: WebSocket, session_id: str):
    """WebSocket 端点，实时推送 Agent 工作状态。

    不展示 LLM 思维链，只推送可读的工作状态节点：
    - status: 开始/结束状态
    - tool_call: 工具调用名称
    - observation: 工具输出摘要
    - final: 最终回答
    - error: 错误信息
    """
    await websocket.accept()

    try:
        await websocket.send_json(WsStatusMessage(
            type="status",
            content="会话已连接",
        ).model_dump())

        while True:
            data = await websocket.receive_text()

            try:
                message = json.loads(data)
                user_input = message.get("message", "")
                attachment_data = message.get("attachment")

                # 消息与附件均为空时提示错误
                if not user_input and not attachment_data:
                    await websocket.send_json(WsStatusMessage(
                        type="error",
                        content="消息为空",
                    ).model_dump())
                    continue

                # 推送开始状态
                await websocket.send_json(WsStatusMessage(
                    type="status",
                    content="开始分析...",
                ).model_dump())

                from martin.agent.agent import create_agent
                from martin.agent.sessions import get_default_checkpointer

                checkpointer = get_default_checkpointer()
                agent = create_agent(
                    thread_id=session_id,
                    checkpointer=checkpointer,
                    verbose=False,
                )

                # 处理附件：注入影像信息并生成引导消息
                if attachment_data:
                    try:
                        attachment = AttachmentInfo(**attachment_data)
                    except Exception as exc:
                        await websocket.send_json(WsStatusMessage(
                            type="error",
                            content=f"附件信息无效: {exc}",
                        ).model_dump())
                        continue
                    guidance = _process_attachment(agent, attachment)
                    stripped = user_input.strip()
                    # 若用户消息为占位符（空白或单字符如 "."），直接使用引导消息
                    if not stripped or stripped == ".":
                        final_input = guidance
                    else:
                        final_input = f"{guidance}{user_input}"
                else:
                    final_input = user_input

                result = await asyncio.to_thread(agent.invoke, {"input": final_input})

                # 推送工具调用状态
                for action, output in result.get("intermediate_steps", []):
                    if isinstance(action, AgentAction):
                        # 推送工具调用
                        await websocket.send_json(WsStatusMessage(
                            type="tool_call",
                            content=f"调用 {action.tool}",
                            tool_name=action.tool,
                        ).model_dump())

                        # 推送观察结果摘要
                        output_str = str(output)[:200]
                        await websocket.send_json(WsStatusMessage(
                            type="observation",
                            content=output_str,
                            tool_name=action.tool,
                        ).model_dump())

                # 推送最终回答
                final_output = result.get("output", "")
                await websocket.send_json(WsStatusMessage(
                    type="final",
                    content=final_output,
                ).model_dump())

                # 推送病例上下文更新
                try:
                    ctx = agent.case_context.to_dict()
                    await websocket.send_json(WsStatusMessage(
                        type="status",
                        content=json.dumps({"case_context": ctx}, ensure_ascii=False),
                    ).model_dump())
                except Exception:
                    pass

            except json.JSONDecodeError:
                await websocket.send_json(WsStatusMessage(
                    type="error",
                    content="无效的消息格式",
                ).model_dump())
            except Exception as e:
                logger.error("Agent WebSocket 处理失败: %s", e, exc_info=True)
                await websocket.send_json(WsStatusMessage(
                    type="error",
                    content="Agent 执行失败，请稍后重试。",
                ).model_dump())

    except WebSocketDisconnect:
        logger.info("WebSocket 连接断开: session_id=%s", session_id)
    except Exception as e:
        logger.error("WebSocket 异常: %s", e, exc_info=True)
