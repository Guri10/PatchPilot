"""Hand-rolled ReAct loop over Anthropic's raw messages.create (ADR-0003).

Flat loop: send -> read tool_use -> dispatch bash -> append tool_result -> repeat.
No agent framework. The agent sees only the issue text (issue-guided arm); the
judgment tests are never placed in its context.
"""

from __future__ import annotations

from dataclasses import dataclass

import anthropic

from patchpilot.tools import BASH_TOOL, run_bash
from patchpilot.sandbox import InstanceSandbox
from patchpilot.trajectory import TrajectoryLog

MAX_TOKENS = 4096

SYSTEM_PROMPT = """You are PatchPilot, an autonomous software-engineering agent.

You are given a bug report for a Python project. The project's full source is \
checked out at /testbed and its dependencies are already installed. You have a \
single tool, `bash`, that runs commands inside that checkout.

Your job: locate the bug described in the report, edit the source to fix it, and \
verify the fix. Work like a careful engineer:

1. Explore first — use grep/find/cat to understand the relevant code before editing.
2. Reproduce the bug — where practical, write a small script or test that fails \
because of the bug, so you can confirm your fix later. If you truly cannot build a \
reproduction, fix directly and say so.
3. Fix the source — make the smallest change that addresses the root cause.
4. Verify — re-run your reproduction and any nearby existing tests to check you did \
not break related behavior.

Rules:
- Change only source code needed for the fix. Do not edit the project's own test \
suite to make it pass.
- Edit files in place (e.g. with `python - <<EOF`, `sed`, or writing files); changes \
on disk are what get graded.
- When you are confident the bug is fixed, stop and reply WITHOUT calling the tool, \
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
                tools=[BASH_TOOL],
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
            command = tu.input.get("command", "")
            steps += 1
            trajectory.command(steps, command)
            code, output = run_bash(sandbox, command)
            trajectory.output(steps, code, output)
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": f"(exit {code})\n{output}" if output else f"(exit {code}, no output)",
                }
            )
            if steps >= config.max_steps:
                break
        messages.append({"role": "user", "content": tool_results})

    trajectory.stop("step_cap", steps)
    return LoopResult("step_cap", steps)
