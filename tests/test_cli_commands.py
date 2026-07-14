"""CLI slash command parsing tests."""

from martin.__main__ import _parse_agent_command


def test_natural_language_is_not_consumed_as_command():
    assert _parse_agent_command("list") == (None, "")
    assert _parse_agent_command("请帮我 open 这份报告") == (None, "")
    assert _parse_agent_command("What is a lung nodule?") == (None, "")


def test_slash_command_and_argument_are_parsed():
    assert _parse_agent_command("/list") == ("list", "")
    assert _parse_agent_command("/open  2") == ("open", "2")
    assert _parse_agent_command("/SWITCH 3") == ("switch", "3")


def test_unknown_slash_input_stays_a_local_command():
    assert _parse_agent_command("/unknown something") == ("unknown", "something")
