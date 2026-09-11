"""Tests for the bash tool (patchpilot.tools)."""

from __future__ import annotations

from patchpilot.sandbox import ExecResult
from patchpilot.tools import (
    BASH_TOOL_SCHEMA,
    run_bash_tool,
    truncate_output,
)


class FakeSandbox:
    def __init__(self, result: ExecResult) -> None:
        self.result = result
        self.commands: list[str] = []

    def exec(self, command: str, *, timeout: int = 300) -> ExecResult:
        self.commands.append(command)
        return self.result

    def git_diff(self) -> str:  # pragma: no cover - not used here
        return ""

    def teardown(self) -> None:  # pragma: no cover
        pass


def test_truncate_output_short_passthrough():
    assert truncate_output("hello", 100) == "hello"


def test_truncate_output_keeps_head_and_tail():
    text = "A" * 50 + "B" * 50
    out = truncate_output(text, 20)
    assert out.startswith("A")
    assert out.endswith("B")
    assert "truncated" in out
    assert len(out) < len(text)


def test_run_bash_tool_returns_output():
    sb = FakeSandbox(ExecResult(exit_code=0, stdout="ok", stderr=""))
    assert run_bash_tool({"command": "ls"}, sb) == "ok"
    assert sb.commands == ["ls"]


def test_run_bash_tool_marks_nonzero_exit():
    sb = FakeSandbox(ExecResult(exit_code=2, stdout="", stderr="boom"))
    out = run_bash_tool({"command": "false"}, sb)
    assert "exit code 2" in out
    assert "boom" in out


def test_run_bash_tool_rejects_missing_command():
    sb = FakeSandbox(ExecResult(exit_code=0, stdout="", stderr=""))
    assert "error" in run_bash_tool({}, sb)
    assert sb.commands == []


def test_schema_declares_command_input():
    assert BASH_TOOL_SCHEMA["input_schema"]["required"] == ["command"]
