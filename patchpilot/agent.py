"""Hand-rolled ReAct loop over Anthropic's raw messages.create (ADR-0003).

Flat loop: send -> read tool_use -> dispatch a structured tool -> append
tool_result -> repeat. No agent framework. The agent sees only the issue text
(issue-guided arm); the judgment tests are never placed in its context.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import anthropic

from patchpilot.tools import STRUCTURED_TOOLS, dispatch
from patchpilot.sandbox import InstanceSandbox
from patchpilot.trajectory import TrajectoryLog

MAX_TOKENS = 4096

SYSTEM_PROMPT = """You are PatchPilot, an autonomous software-engineering agent.

You are given a bug report for a Python project. The project's full source is \
checked out at /testbed and its dependencies are already installed. You work \
through a small set of tools:

- `grep` — find where something is defined or used (returns file:line).
- `read_file` — read a file or a line range, with line numbers.
- `edit_file` — replace an exact, unique snippet in a file with a new one.
- `run_tests` — run pytest on specific node-ids/paths and see the (truncated) result.

Your job: locate the bug described in the report, edit the source to fix it, and \
verify the fix. Work like a careful engineer:

1. Explore first — use `grep` and `read_file` to understand the relevant code before editing.
2. Reproduce where practical — run the nearby existing tests with `run_tests` to see \
the failure first, so you can confirm your fix later. If you truly cannot reproduce \
it, fix directly and say so.
3. Fix the source — make the smallest `edit_file` change that addresses the root \
cause. `old_string` must match the file exactly and be unique; include surrounding \
lines if you need to disambiguate.
4. Verify — re-run the relevant tests with `run_tests` to confirm the fix and that \
you did not break nearby behavior.

Rules:
- Change only source code needed for the fix. Do not edit the project's own test \
suite to make it pass.
- When you are confident the bug is fixed, stop and reply WITHOUT calling a tool, \
summarizing what you changed and how you verified it."""


def build_user_prompt(problem_statement: str) -> str:
    return (
        "Here is the bug report for the project checked out at /testbed:\n\n"
        "<issue>\n"
        f"{problem_statement}\n"
        "</issue>\n\n"
        "Investigate and fix the bug. Begin by exploring the repository."
    )


@dataclass
class LoopResult:
    stop_reason: str  # "completed" | "step_cap" | "error" | "stopped:<reason>"
    steps: int


def run_loop(
    config,
    sandbox: InstanceSandbox,
    problem_statement: str,
    trajectory: TrajectoryLog,
) -> LoopResult:
    client = anthropic.Anthropic(api_key=config.anthropic_api_key)
    system = [{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}]
    messages: list[dict] = [
        {"role": "user", "content": build_user_prompt(problem_statement)}
    ]

    steps = 0
    while steps < config.max_steps:
        try:
            response = client.messages.create(
                model=config.model,
                max_tokens=MAX_TOKENS,
                system=system,
                tools=STRUCTURED_TOOLS,
                messages=messages,
            )
        except anthropic.APIError as exc:
            # A transient API error (rate limit, 5xx, network) should end the
            # instance cleanly with a terminal trajectory event, not crash the
            # whole run with no log of why.
            trajectory.stop(f"error: {type(exc).__name__}", steps)
            return LoopResult("error", steps)
        messages.append({"role": "assistant", "content": response.content})

        tool_uses = []
        for block in response.content:
            if block.type == "text" and block.text.strip():
                trajectory.thought(block.text)
            elif block.type == "tool_use":
                tool_uses.append(block)

        if response.stop_reason == "end_turn":
            trajectory.stop("completed", steps)
            return LoopResult("completed", steps)
        if response.stop_reason != "tool_use":
            # max_tokens (truncated mid-turn), pause_turn, refusal, etc. — the
            # turn did not finish normally and any tool_use block may be partial,
            # so stop rather than mislabel it "completed".
            trajectory.stop(f"stopped:{response.stop_reason}", steps)
            return LoopResult(f"stopped:{response.stop_reason}", steps)

        tool_results = []
        for tu in tool_uses:
            inp = tu.input if isinstance(tu.input, dict) else {}
            steps += 1
            trajectory.command(steps, f"{tu.name} {json.dumps(inp, ensure_ascii=False)}")
            is_error, text = dispatch(sandbox, tu.name, inp)
            trajectory.output(steps, 1 if is_error else 0, text)
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": text or "(no output)",
                    "is_error": is_error,
                }
            )
            if steps >= config.max_steps:
                break
        messages.append({"role": "user", "content": tool_results})

    trajectory.stop("step_cap", steps)
    return LoopResult("step_cap", steps)
