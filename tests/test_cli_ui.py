"""Terminal UI rendering tests."""

from io import StringIO

from rich.console import Console

from martin.agent.cli_ui import AgentCLI


def _test_ui():
    output = StringIO()
    console = Console(
        file=output,
        width=100,
        color_system=None,
        force_terminal=False,
    )
    return AgentCLI(console), output


def test_assistant_renders_markdown_instead_of_printing_markers():
    ui, output = _test_ui()

    ui.assistant("请提供 **年龄和性别**。")

    rendered = output.getvalue()
    assert "Martin >" in rendered
    assert "年龄和性别" in rendered
    assert "**" not in rendered


def test_assistant_normalizes_bold_text_followed_by_chinese_content():
    ui, output = _test_ui()

    ui.assistant("- **患者信息：**62 岁男性")

    rendered = output.getvalue()
    assert "患者信息" in rendered
    assert "62 岁男性" in rendered
    assert "**" not in rendered


def test_report_is_rendered_in_a_named_panel():
    ui, output = _test_ui()

    ui.assistant("# 肺部 CT 病例报告\n\n未发现紧急征象。", is_report=True)

    rendered = output.getvalue()
    assert "病例报告" in rendered
    assert "肺部 CT 病例报告" in rendered


def test_welcome_identifies_agent_and_session():
    ui, output = _test_ui()

    ui.welcome("session-001")

    rendered = output.getvalue()
    assert "Martin 医学影像智能体" in rendered
    assert "session-001" in rendered
