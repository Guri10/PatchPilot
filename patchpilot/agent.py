"""The hand-rolled ReAct loop (ADR-0003, ADR-0004).

Flat loop over the Messages API: send -> read ``tool_use`` -> dispatch to the
bash tool -> append ``tool_result`` -> repeat, until the agent ends its turn
without calling a tool, or the step cap is hit.

In the issue-guided arm the only task context the agent ever sees is the issue
text; the judgment tests are never placed in ``messages``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .config import ARM_TEST_GUIDED
from .dataset import Instance
from .llm import DEFAULT_MAX_TOKENS, LLMClient
from .sandbox import Sandbox
from .tools import BASH_TOOL_NAME, BASH_TOOL_SCHEMA, run_bash_tool
from .trajectory import TrajectoryLog

STOP_AGENT_FINISHED = "agent_finished"
STOP_STEP_CAP = "step_cap"

SYSTEM_PROMPT = """You are PatchPilot, an autonomous software engineer fixing a \
bug in a Python repository.

You are given a bug report (the issue text). The repository is checked out in \
your working directory and its dependencies are already installed. You interact \
with it only through the `bash` tool.

Work like this:
- Explore the code with grep/cat/ls to localise the bug.
- Where you can, write a small reproduction test from the issue and run it to \
confirm the bug, then fix the source, then confirm the reproduction passes. If \
you cannot build a reproduction, fix directly and say so.
- Run the repository's own relevant tests to check you did not break anything.
- Edit source files in place (e.g. with `python - <<'PY'` scripts, `sed`, or a \
heredoc). Change the source, not the tests, to fix the bug.

When you are confident the bug is fixed, stop and end your turn without calling \
the tool. Do not ask the user questions; you are fully autonomous."""


@dataclass
class LoopResult:
    """Outcome of one agent run."""

    stop_reason: str
    steps: int


def build_user_prompt(instance: Instance) -> str:
    """The initial user message: the issue text only."""
    return (
        f"Repository: {instance.repo}\n\n"
        f"Fix the bug described in the following issue.\n\n"
        f"--- ISSUE ---\n{instance.problem_statement}\n--- END ISSUE ---"
    )


def _get(block: Any, key: str) -> Any:
    """Read a field from a content block that may be a dict or an SDK object."""
    if isinstance(block, dict):
        return block.get(key)
    return getattr(block, key, None)


def _normalize_block(block: Any) -> dict[str, Any] | None:
    """Convert an assistant content block to a plain dict for the transcript."""
    btype = _get(block, "type")
    if btype == "text":
        return {"type": "text", "text": _get(block, "text") or ""}
    if btype == "tool_use":
        return {
            "type": "tool_use",
            "id": _get(block, "id"),
            "name": _get(block, "name"),
            "input": _get(block, "input") or {},
        }
    return None


def run_loop(
    *,
    client: LLMClient,
    sandbox: Sandbox,
    instance: Instance,
    step_cap: int,
    trajectory: TrajectoryLog,
    arm: str,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> LoopResult:
    """Run the ReAct loop for one instance until it finishes or hits the cap."""
    system = SYSTEM_PROMPT
    if arm == ARM_TEST_GUIDED:
        # The test-guided arm would inject judgment tests here, gated by the
        # explicit flag. The issue-guided spine deliberately never does.
        raise NotImplementedError(
            "test-guided arm is out of scope for the issue-guided spine (issue #1)"
        )

    messages: list[dict[str, Any]] = [
        {"role": "user", "content": build_user_prompt(instance)}
    ]
    tools = [BASH_TOOL_SCHEMA]

    for step in range(1, step_cap + 1):
        response = client.create(
            system=system,
            messages=messages,
            tools=tools,
            max_tokens=max_tokens,
        )

        assistant_blocks: list[dict[str, Any]] = []
        tool_uses: list[dict[str, Any]] = []
        for block in response.content:
            norm = _normalize_block(block)
            if norm is None:
                continue
            assistant_blocks.append(norm)
            if norm["type"] == "text" and norm["text"].strip():
                trajectory.assistant_text(step, norm["text"])
            elif norm["type"] == "tool_use":
                tool_uses.append(norm)

        messages.append({"role": "assistant", "content": assistant_blocks})

        if not tool_uses:
            trajectory.stopped(step, STOP_AGENT_FINISHED)
            return LoopResult(STOP_AGENT_FINISHED, step)

        tool_results: list[dict[str, Any]] = []
        for call in tool_uses:
            trajectory.tool_use(step, call["name"], call["input"])
            if call["name"] == BASH_TOOL_NAME:
                output = run_bash_tool(call["input"], sandbox)
            else:
                output = f"error: unknown tool {call['name']!r}"
            trajectory.tool_result(step, output)
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": call["id"],
                    "content": output,
                }
            )
        messages.append({"role": "user", "content": tool_results})

    trajectory.stopped(step_cap, STOP_STEP_CAP)
    return LoopResult(STOP_STEP_CAP, step_cap)
