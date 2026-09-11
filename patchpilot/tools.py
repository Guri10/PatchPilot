"""The single ``bash`` tool for the bootstrap phase (ADR-0004).

One exec tool is all the agent gets: it runs shell commands inside the Modal
sandbox and gets back combined output. Output is truncated head+tail so a noisy
command (a full test run, a big file) can't blow the context window.
"""

from __future__ import annotations

from typing import Any

from .sandbox import Sandbox

BASH_TOOL_NAME = "bash"

# Keep the most useful signal (start and end) when a command floods output.
DEFAULT_MAX_OUTPUT_CHARS = 8000

BASH_TOOL_SCHEMA: dict[str, Any] = {
    "name": BASH_TOOL_NAME,
    "description": (
        "Run a bash command inside the repository checkout and return its "
        "combined stdout and stderr. The working directory is the repo root. "
        "Use this to explore the code (grep, cat, ls), edit files, and run "
        "tests. Long output is truncated in the middle."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The bash command to execute.",
            }
        },
        "required": ["command"],
    },
}


def truncate_output(text: str, max_chars: int = DEFAULT_MAX_OUTPUT_CHARS) -> str:
    """Truncate ``text`` in the middle, keeping the head and tail.

    Returns ``text`` unchanged when it already fits. Otherwise keeps the first
    and last halves of the budget with a marker naming how many chars were cut.
    """
    if max_chars < 1:
        raise ValueError("max_chars must be at least 1")
    if len(text) <= max_chars:
        return text
    cut = len(text) - max_chars
    head_len = max_chars // 2
    tail_len = max_chars - head_len
    head = text[:head_len]
    tail = text[len(text) - tail_len :]
    return f"{head}\n... [{cut} characters truncated] ...\n{tail}"


def run_bash_tool(
    tool_input: dict[str, Any],
    sandbox: Sandbox,
    *,
    max_chars: int = DEFAULT_MAX_OUTPUT_CHARS,
) -> str:
    """Execute a ``bash`` tool call and return the text for the tool_result."""
    command = tool_input.get("command")
    if not isinstance(command, str) or not command.strip():
        return "error: 'command' must be a non-empty string"
    result = sandbox.exec(command)
    body = truncate_output(result.output, max_chars)
    if result.exit_code != 0:
        return f"[exit code {result.exit_code}]\n{body}"
    return body
