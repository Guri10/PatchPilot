"""The agent's action space — bash only, for the bootstrap phase (ADR-0004).

A single ``bash`` tool executed via the Modal sandbox ``exec``. Output is
truncated head+tail so a runaway command (e.g. a full test run) can't blow the
context window; the structured toolset is a later graduation.
"""

from __future__ import annotations

from patchpilot.sandbox import InstanceSandbox

MAX_OUTPUT_CHARS = 8000

BASH_TOOL = {
    "name": "bash",
    "description": (
        "Run a bash command inside the repository checkout at /testbed and return "
        "its combined stdout/stderr. Use this to explore the code (grep, cat, ls), "
        "edit files, and run tests. State does NOT persist between calls except for "
        "changes written to the filesystem — each call is a fresh shell."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The bash command to run.",
            }
        },
        "required": ["command"],
    },
}


def truncate(output: str, limit: int = MAX_OUTPUT_CHARS) -> str:
    """Keep the head and tail of long output; elide the middle."""
    if len(output) <= limit:
        return output
    half = limit // 2
    head, tail = output[:half], output[-half:]
    elided = len(output) - 2 * half
    return f"{head}\n...[{elided} chars truncated]...\n{tail}"


def run_bash(sandbox: InstanceSandbox, command: str) -> tuple[int, str]:
    """Execute a bash command; return (exit_code, truncated_output)."""
    code, output = sandbox.exec(command)
    return code, truncate(output)
