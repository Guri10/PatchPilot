"""Shared test doubles for the LLM client and the sandbox."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from patchpilot.sandbox import ExecResult


@dataclass
class Block:
    """A content block that quacks like an Anthropic SDK block."""

    type: str
    text: str | None = None
    id: str | None = None
    name: str | None = None
    input: dict[str, Any] | None = None


def text_block(text: str) -> Block:
    return Block(type="text", text=text)


def tool_use_block(tool_id: str, name: str, tool_input: dict[str, Any]) -> Block:
    return Block(type="tool_use", id=tool_id, name=name, input=tool_input)


@dataclass
class Response:
    content: list[Block]
    stop_reason: str = "end_turn"


class FakeClient:
    """Replays a scripted list of responses; the last one repeats if exhausted."""

    def __init__(self, responses: list[Response]) -> None:
        self._responses = responses
        self._i = 0
        self.calls: list[str] = []  # JSON of {system, messages} per call

    def create(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_tokens: int = 4096,
    ) -> Response:
        self.calls.append(json.dumps({"system": system, "messages": messages}))
        if self._i < len(self._responses):
            resp = self._responses[self._i]
            self._i += 1
            return resp
        return self._responses[-1]


@dataclass
class FakeSandbox:
    """Records commands, returns canned exec results and a fixed diff."""

    diff: str = ""
    exec_result: ExecResult = field(
        default_factory=lambda: ExecResult(0, "ok", "")
    )
    commands: list[str] = field(default_factory=list)
    torn_down: bool = False

    def exec(self, command: str, *, timeout: int = 300) -> ExecResult:
        self.commands.append(command)
        return self.exec_result

    def git_diff(self) -> str:
        return self.diff

    def teardown(self) -> None:
        self.torn_down = True
