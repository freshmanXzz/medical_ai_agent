"""Rich-based terminal presentation for the interactive Agent CLI."""

from __future__ import annotations

import re
from typing import Any, Iterable, Optional

from rich import box
from rich.console import Console, Group
from rich.markdown import Markdown
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text


class AgentCLI:
    """Render the interactive consultation without leaking Markdown syntax."""

    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console(highlight=False, emoji=False)

    def welcome(self, session_id: str) -> None:
        intro = Group(
            Text("您好，我是 Martin 医学影像智能体。", style="bold bright_green"),
            Text(
                "我会像门诊医生一样了解情况，并协助分析肺部 CT、检索医学知识和生成报告。"
            ),
            Text("直接输入中文或英文开始问诊；输入 /help 查看系统命令。", style="dim"),
            Text(f"当前会话: {session_id}", style="dim"),
        )
        self.console.print()
        self.console.print(
            Panel(
                intro,
                title="Martin Medical AI Agent",
                border_style="bright_black",
                padding=(1, 2),
            )
        )
        self.console.print()

    def prompt(self) -> str:
        return self.console.input("[bold bright_blue]患者 >[/] ").strip()

    def ask_session_number(self) -> str:
        return self.console.input("[bold yellow]会话编号 >[/] ").strip()

    def assistant(self, content: str, is_report: bool = False) -> None:
        renderable: Any = Markdown(self._normalize_markdown(content))
        if is_report or self._looks_like_report(content):
            renderable = Panel(
                renderable,
                title="病例报告",
                border_style="bright_black",
                padding=(1, 2),
            )
        self._message("Martin >", renderable, "bold bright_green")

    def user_message(self, content: str) -> None:
        self._message("患者 >", Text(content), "bold bright_blue")

    def system(self, message: str) -> None:
        self.console.print(Text.assemble(("系统 > ", "bold yellow"), message))

    def error(self, message: str) -> None:
        self.console.print(Text.assemble(("错误 > ", "bold red"), message))

    def help(self) -> None:
        table = Table(
            title="系统命令",
            box=box.SIMPLE,
            border_style="bright_black",
            header_style="bold",
            show_edge=False,
        )
        table.add_column("命令", style="bright_cyan", no_wrap=True)
        table.add_column("作用")
        for command, description in (
            ("/list", "列出历史会话"),
            ("/open <编号>", "查看历史会话"),
            ("/switch <编号>", "切换并继续历史会话"),
            ("/new", "创建新会话"),
            ("/back", "返回当前会话"),
            ("/help", "查看命令帮助"),
            ("/exit", "退出程序"),
        ):
            table.add_row(command, description)
        self.console.print(table)

    def session_list(self, summaries: Iterable[Any], current_id: str) -> None:
        table = Table(
            title="历史会话",
            box=box.SIMPLE_HEAD,
            border_style="bright_black",
            header_style="bold",
            expand=True,
        )
        table.add_column("#", style="bright_cyan", width=4)
        table.add_column("标题", ratio=3)
        table.add_column("更新时间", style="dim", width=20)
        table.add_column("会话 ID", style="dim", width=12)
        for index, summary in enumerate(summaries, 1):
            timestamp = summary.updated_at.replace("T", " ")[:19]
            marker = "当前" if summary.thread_id == current_id else ""
            table.add_row(
                str(index),
                summary.title,
                timestamp,
                f"{summary.thread_id} {marker}".strip(),
            )
        self.console.print(table)

    def history_start(self, title: str) -> None:
        self.console.print(Rule(Text(f"历史会话 / {title}"), style="bright_black"))

    def history_end(self) -> None:
        self.console.print(Rule("历史记录结束", style="bright_black"))

    def history_message(self, role: str, content: str) -> None:
        if role == "Martin":
            self.assistant(content)
        else:
            self.user_message(content)

    def _message(self, label: str, renderable: Any, style: str) -> None:
        layout = Table.grid(padding=(0, 1), expand=True)
        layout.add_column(width=10, no_wrap=True)
        layout.add_column(ratio=1, overflow="fold")
        layout.add_row(Text(label, style=style), renderable)
        self.console.print(layout)
        self.console.print()

    @staticmethod
    def _looks_like_report(content: str) -> bool:
        report_markers = ("病例报告", "诊断报告", "影像学报告", "病例摘要")
        return len(content) > 300 and any(marker in content for marker in report_markers)

    @staticmethod
    def _normalize_markdown(content: str) -> str:
        return re.sub(r"(\*\*[^*\n]+\*\*)(?=[^\s\W])", r"\1 ", content)
