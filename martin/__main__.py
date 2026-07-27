"""
Martin - Medical AI Agent 入口文件

运行方式：
python -m martin [命令] [参数]

命令列表：
- detect: 检测肺部结节
- case: 生成病例报告
- analyze: 分析检测结果
- report: 生成医学报告
- convert: 转换图像格式
- web: 启动 Web API 与已构建前端
"""
import argparse
import sys

_interactive_console = bool(getattr(sys.stdout, "isatty", lambda: False)())

if sys.platform == "win32" and _interactive_console:
    try:
        import ctypes

        ctypes.windll.kernel32.SetConsoleOutputCP(65001)
        ctypes.windll.kernel32.SetConsoleCP(65001)
    except (AttributeError, OSError):
        pass

if hasattr(sys.stdout, "reconfigure"):
    if _interactive_console:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    else:
        sys.stdout.reconfigure(errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    if _interactive_console:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    else:
        sys.stderr.reconfigure(errors="replace")

def main():
    parser = argparse.ArgumentParser(
        prog="Martin",
        description="Medical AI Agent - 肺部结节检测系统",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
    subparsers = parser.add_subparsers(dest="command", help="可用命令")
    
    # detect 命令
    detect_parser = subparsers.add_parser("detect", help="检测肺部结节")
    detect_parser.add_argument("-i", "--input", required=True, help="输入图像文件路径")
    detect_parser.add_argument("-o", "--output", default="results/detection_results.json", 
                              help="输出结果文件路径")
    detect_parser.add_argument("--device", default=None, help="运行设备 (cuda/cpu)")
    
    # case 命令
    case_parser = subparsers.add_parser("case", help="生成病例报告")
    case_parser.add_argument("-i", "--input", required=True, help="检测结果JSON文件")
    case_parser.add_argument("-o", "--output", default="results/case_report.md", 
                              help="输出报告文件路径")
    case_parser.add_argument("--type", default="detailed", choices=["brief", "detailed", "research"],
                              help="报告类型: brief(简洁版)/detailed(详细版)/research(科研版)")
    case_parser.add_argument("--lang", default="zh", choices=["zh", "en"],
                              help="语言: zh(中文)/en(英文)")
    case_parser.add_argument("--llm", action="store_true", help="使用LLM生成智能报告")
    case_parser.add_argument("--rag", action="store_true", help="使用RAG增强（基于知识库生成）")
    case_parser.add_argument("--api-key", help="DeepSeek API密钥")
    
    # analyze 命令
    analyze_parser = subparsers.add_parser("analyze", help="分析检测结果")
    analyze_parser.add_argument("-i", "--input", required=True, help="检测结果JSON文件")
    analyze_parser.add_argument("--api-key", help="DeepSeek API密钥")
    
    # report 命令
    report_parser = subparsers.add_parser("report", help="生成医学报告")
    report_parser.add_argument("-i", "--input", required=True, help="检测结果JSON文件")
    report_parser.add_argument("-o", "--output", default="results/report.txt", 
                              help="输出报告文件路径")
    report_parser.add_argument("--api-key", help="DeepSeek API密钥")
    
    # convert 命令
    convert_parser = subparsers.add_parser("convert", help="转换图像格式")
    convert_parser.add_argument("-i", "--input", required=True, help="输入文件路径")
    convert_parser.add_argument("-o", "--output", required=True, help="输出文件路径")
    
    # info 命令
    info_parser = subparsers.add_parser("info", help="查看图像信息")
    info_parser.add_argument("-i", "--input", required=True, help="输入图像文件路径")
    
    # agent 命令（多轮对话）
    agent_parser = subparsers.add_parser("agent", help="启动多轮对话 Agent")
    agent_parser.add_argument("--image", help="首次运行的 CT 图像路径")
    agent_parser.add_argument("--report-type", default="detailed",
                              choices=["brief", "detailed", "research"],
                              help="报告类型")
    agent_parser.add_argument("--language", default="zh", choices=["zh", "en"],
                               help="报告语言")

    # web 命令（FastAPI + 已构建的 Vue 前端）
    web_parser = subparsers.add_parser("web", help="启动 Web 服务")
    web_parser.add_argument("--host", default="127.0.0.1", help="监听地址")
    web_parser.add_argument("--port", type=int, default=8000, help="监听端口")
    web_parser.add_argument("--reload", action="store_true", help="启用后端热重载")
    
    args = parser.parse_args()
    
    if args.command is None:
        parser.print_help()
        sys.exit(1)
    
    # 执行命令
    if args.command == "detect":
        run_detect(args)
    elif args.command == "case":
        run_case(args)
    elif args.command == "analyze":
        run_analyze(args)
    elif args.command == "report":
        run_report(args)
    elif args.command == "convert":
        run_convert(args)
    elif args.command == "info":
        run_info(args)
    elif args.command == "agent":
        handle_agent_v2(args)
    elif args.command == "web":
        run_web(args)


def run_web(args):
    """启动 FastAPI；若 frontend/dist 存在则同时提供 Vue 页面。"""
    try:
        import uvicorn
    except ImportError as exc:
        raise RuntimeError("缺少 Web 依赖，请先执行 pip install -r requirements.txt") from exc

    uvicorn.run(
        "api.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )

def run_detect(args):
    """执行结节检测"""
    from martin.vision.nodule_detector import NoduleDetector
    
    print(f"正在检测: {args.input}")
    
    detector = NoduleDetector()
    result = detector.detect(args.input)
    
    # 保存结果到按日期分类的目录
    saved_path = detector.save_result(result, args.output)
    
    print(f"检测完成！结果已保存到: {saved_path}")
    print(f"检测到 {result['total_nodules']} 个结节")
    
    for nodule in result['nodules']:
        print(f"  结节 {nodule['index']}: 置信度 {nodule['score']:.2%}, "
              f"直径 {nodule['diameter']:.2f}mm")

def run_analyze(args):
    """分析检测结果"""
    import json
    
    with open(args.input, 'r', encoding='utf-8') as f:
        report_data = json.load(f)
    
    from martin.llm import DeepSeekClient
    
    client = DeepSeekClient(api_key=args.api_key)
    analysis = client.analyze_report(report_data)
    
    print("\n=== 分析结果 ===")
    print(analysis)
    print("=" * 50)

def run_report(args):
    """生成医学报告"""
    import json
    
    with open(args.input, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    from martin.llm import DeepSeekClient
    
    client = DeepSeekClient(api_key=args.api_key)
    report = client.generate_report(data.get('nodules', []))
    
    with open(args.output, 'w', encoding='utf-8') as f:
        f.write(report)
    
    print(f"报告已生成并保存到: {args.output}")

def run_convert(args):
    """转换图像格式"""
    from martin.vision import ImageProcessor
    
    if args.input.endswith('.mhd') and (args.output.endswith('.nii.gz') or args.output.endswith('.nii')):
        ImageProcessor.metaimage_to_nifti(args.input, args.output)
        print(f"转换完成！已保存到: {args.output}")
    else:
        print("不支持的转换格式")

def run_case(args):
    """生成病例报告"""
    import json
    import os

    with open(args.input, 'r', encoding='utf-8') as f:
        detection_result = json.load(f)

    from martin.llm.chain import generate_report

    print(f"生成病例报告，类型: {args.type}...")
    report = generate_report(detection_result, report_type=args.type)

    # 保存报告
    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"病例报告已生成并保存到: {args.output}")
    print("\n=== 报告预览 ===")
    print(report[:1000] + "..." if len(report) > 1000 else report)

def run_info(args):
    """查看图像信息"""
    from martin.vision import ImageProcessor
    
    info = ImageProcessor.get_image_info(args.input)
    
    print("=== 图像信息 ===")
    print(f"尺寸: {info['dim_size']}")
    print(f"像素间距: {info['spacing']} mm")
    print(f"总像素数: {info['voxel_count']:,}")
    print(f"数据范围: [{info['data_range'][0]}, {info['data_range'][1]}]")

def handle_agent_legacy(args):
    """处理 agent 命令，支持多轮对话。"""
    from martin.agent.agent import create_agent
    from martin.agent.audit import AuditLogger

    # 创建审计日志（session_id 同时作为 langgraph thread_id）
    audit_logger = AuditLogger()
    print(f"审计日志会话 ID: {audit_logger.session_id}")
    print(f"审计日志保存到: {audit_logger.log_file}")
    print()

    # 创建 Agent（与审计日志共享 session_id，实现多轮记忆持久化）
    print("正在初始化 AI Agent...")
    agent_executor = create_agent(
        verbose=True,
        thread_id=audit_logger.session_id,
    )

    # 首次输入
    first_input = None
    if args.image:
        first_input = (
            f"分析CT图像: {args.image}，"
            f"生成{args.report_type}类型报告（{args.language}）"
        )

    print("=" * 60)
    print("多轮对话模式已启动（输入 exit/退出 结束会话）")
    print("=" * 60)
    print()

    user_input = first_input
    while True:
        if user_input is None:
            user_input = input(">>> ").strip()
            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit", "退出"):
                print("结束会话，审计日志已保存。")
                break

        try:
            # 执行旧版 Agent（LangGraph Checkpointer 自动管理对话历史）
            result = agent_executor.invoke({"input": user_input})
            output = result.get("output", "")

            # 审计日志：提取 intermediate_steps
            intermediate_steps = result.get("intermediate_steps", [])
            for action, action_output in intermediate_steps:
                audit_logger.log_tool_call(
                    tool_name=action.tool,
                    args=action.tool_input,
                    output_summary=str(action_output)[:500],
                )

            # 打印最终输出
            if output:
                print()
                print(output)
                print()

            # 保存报告到 results/
            if args.image and output:
                _save_agent_report(output, args)

        except Exception as e:
            error_msg = f"错误: Agent 执行失败: {e}"
            print(error_msg)
            audit_logger.log_agent_error(str(e))

        # 首轮结束后，后续输入靠 input()
        user_input = None


def _parse_agent_command(user_input: str):
    """Parse slash-prefixed local commands without consuming natural language."""
    if not user_input.startswith("/"):
        return None, ""
    command_text = user_input[1:].strip()
    command, _, argument = command_text.partition(" ")
    return command.lower(), argument.strip()


def _print_agent_help(ui=None) -> None:
    """Print interactive Agent commands."""
    if ui is not None:
        ui.help()
        return
    print("可用命令:")
    print("  /list              列出历史会话")
    print("  /open <编号>       查看历史会话")
    print("  /switch <编号>     切换并继续历史会话")
    print("  /new               创建新会话")
    print("  /back              返回当前会话")
    print("  /help              查看命令帮助")
    print("  /exit              退出程序")


def handle_agent_v2(args):
    """Run the interactive agent with persistent session navigation."""
    from martin.utils.logger import AppLogger
    from martin.utils.runtime_output import capture_runtime_output

    AppLogger.disable_console_output()
    with capture_runtime_output():
        from martin.agent.agent import create_agent
        from martin.agent.audit import AuditLogger
        from martin.agent.cli_ui import AgentCLI
        from martin.agent.sessions import (
            SessionManager,
            close_default_checkpointer,
            get_default_checkpointer,
        )

    with capture_runtime_output():
        checkpointer = get_default_checkpointer()
    session_manager = SessionManager(checkpointer)
    ui = AgentCLI()

    def start_session(session_id=None):
        audit_logger = AuditLogger(session_id=session_id)
        with capture_runtime_output():
            executor = create_agent(
                verbose=True,
                thread_id=audit_logger.session_id,
                checkpointer=checkpointer,
            )
        return audit_logger, executor

    audit_logger, agent_executor = start_session()
    ui.welcome(audit_logger.session_id)

    first_input = None
    if args.image:
        first_input = (
            f"Analyze CT image: {args.image}; "
            f"generate a {args.report_type} report in {args.language}."
        )

    user_input = first_input
    try:
        while True:
            if user_input is None:
                try:
                    user_input = ui.prompt()
                except (EOFError, KeyboardInterrupt):
                    ui.system("会话已结束，历史记录已保存。")
                    break
                if not user_input:
                    user_input = None
                    continue
                command, argument = _parse_agent_command(user_input)

                if command in ("exit", "quit", "\u9000\u51fa"):
                    ui.system("会话已结束，历史记录已保存。")
                    break
                if command in ("help", "?"):
                    _print_agent_help(ui)
                    user_input = None
                    continue
                if command in ("list", "sessions", "\u5386\u53f2"):
                    summaries = session_manager.list_sessions()
                    if not summaries:
                        ui.system("暂无历史会话。")
                    else:
                        ui.session_list(summaries, audit_logger.session_id)
                    user_input = None
                    continue
                if command == "open":
                    summaries = session_manager.list_sessions()
                    selection = argument or ui.ask_session_number()
                    try:
                        selected = summaries[int(selection) - 1]
                    except (ValueError, IndexError):
                        ui.error("无效的会话编号。")
                        user_input = None
                        continue
                    ui.history_start(selected.title)
                    messages = session_manager.get_messages(selected.thread_id)
                    if not messages:
                        ui.system("这个会话没有可显示的消息。")
                    else:
                        for message in messages:
                            ui.history_message(message.role, message.content)
                    ui.history_end()
                    user_input = None
                    continue
                if command == "switch":
                    summaries = session_manager.list_sessions()
                    selection = argument or ui.ask_session_number()
                    try:
                        selected = summaries[int(selection) - 1]
                    except (ValueError, IndexError):
                        ui.error("无效的会话编号。")
                        user_input = None
                        continue
                    audit_logger, agent_executor = start_session(selected.thread_id)
                    ui.system(f"已切换到会话: {selected.title} ({selected.thread_id})")
                    user_input = None
                    continue
                if command == "new":
                    audit_logger, agent_executor = start_session()
                    ui.system(f"已创建新会话: {audit_logger.session_id}")
                    user_input = None
                    continue
                if command == "back":
                    ui.system("已返回当前会话。")
                    user_input = None
                    continue
                if command is not None:
                    shown_command = command or user_input
                    ui.error(f"不支持的系统命令: /{shown_command}")
                    ui.system("输入 /help 查看可用命令；不带 / 的内容会作为自然语言交给 Agent。")
                    user_input = None
                    continue

            try:
                with capture_runtime_output():
                    result = agent_executor.invoke({"input": user_input})
                output = result.get("output", "")
                intermediate_steps = result.get("intermediate_steps", [])
                for action, action_output in intermediate_steps:
                    audit_logger.log_tool_call(
                        tool_name=action.tool,
                        args=action.tool_input,
                        output_summary=str(action_output)[:500],
                    )
                if output:
                    generated_report = any(
                        action.tool == "generate_report"
                        for action, _ in intermediate_steps
                    )
                    ui.assistant(output, is_report=generated_report)
                if args.image and output:
                    report_path = _save_agent_report(output, args, announce=False)
                    ui.system(f"报告已保存到: {report_path}")
            except Exception as exc:
                error_msg = f"Agent execution failed: {exc}"
                ui.error(error_msg)
                audit_logger.log_agent_error(str(exc))
            user_input = None
    finally:
        close_default_checkpointer()


def _save_agent_report(report: str, args, announce: bool = True) -> str:
    """保存 Agent 生成的报告到 results/ 目录。"""
    import os
    from datetime import datetime

    results_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "results",
    )
    os.makedirs(results_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"agent_report_{timestamp}.md"
    filepath = os.path.join(results_dir, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(report)

    if announce:
        print(f"报告已保存到: {filepath}")
    return filepath


if __name__ == "__main__":
    main()
