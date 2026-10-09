"""The agent's action space — the structured toolset (ADR-0004, issue #2).

Four tools, each a thin wrapper over the Modal-sandbox ``exec`` / ``write_file``:

- ``read_file`` — read a file (optionally a line range) with absolute line numbers.
- ``grep`` — recursive search returning ``file:line`` matches.
- ``edit_file`` — a **search/replace** edit: find an exact snippet and swap it.
  Whole-file rewrites and line-range patches are deliberately not offered.
- ``run_tests`` — run pytest node-ids/paths; output is truncated head+tail so a
  big suite can't blow the context window.

``read_file`` and ``edit_file`` do their line math / replacement on the host over
``cat`` + ``write_file`` so the logic is pure and unit-testable; ``grep`` and
``run_tests`` run in the sandbox. All replace the bootstrap ``bash`` tool.
"""

from __future__ import annotations

import posixpath
import shlex

from patchpilot.sandbox import InstanceSandbox

MAX_OUTPUT_CHARS = 8000
TESTBED = "/testbed"


def truncate(output: str, limit: int = MAX_OUTPUT_CHARS) -> str:
    """Keep the head and tail of long output; elide the middle."""
    if len(output) <= limit:
        return output
    half = limit // 2
    head, tail = output[:half], output[-half:]
    elided = len(output) - 2 * half
    return f"{head}\n...[{elided} chars truncated]...\n{tail}"


# --- Pure logic (unit-tested offline) ---------------------------------------


def apply_edit(content: str, old_string: str, new_string: str) -> tuple[str | None, str]:
    """Replace one exact occurrence of ``old_string`` with ``new_string``.

    Returns ``(new_content, message)`` on success, or ``(None, message)`` when the
    edit cannot be applied safely: empty or absent snippet, a snippet that matches
    more than once (ambiguous — the agent must add surrounding context), or an
    edit that changes nothing. Refusing a non-unique match is what makes the tool
    robust where a blind ``sed`` would silently edit the wrong line.
    """
    if old_string == new_string:
        return None, "old_string and new_string are identical; nothing to change."
    if not old_string:
        return None, "old_string is empty; provide the exact snippet to replace."
    count = content.count(old_string)
    if count == 0:
        return None, "old_string not found in file; it must match the source exactly."
    if count > 1:
        return (
            None,
            f"old_string is not unique: found {count} occurrences. "
            "Add surrounding lines so it matches exactly once.",
        )
    return content.replace(old_string, new_string, 1), "replaced 1 occurrence."


def render_file(
    content: str, path: str, start: int | None, end: int | None
) -> str:
    """Render ``content`` (optionally a 1-based inclusive line range) with numbers.

    Line numbers are absolute (a slice starting at line 40 is numbered from 40) so
    the agent can quote a `file:line` back to ``edit_file`` or ``grep``. Out-of-range
    requests are reported rather than silently returning nothing.
    """
    lines = content.splitlines()
    total = len(lines)
    s = 1 if start is None else start
    e = total if end is None else end
    s = max(1, s)
    e = min(total, e)
    if total == 0:
        return f"# {path} (0 lines — empty file)"
    if s > total:
        return (
            f"# {path} ({total} lines total)\n"
            f"[requested start line {start} is beyond end of file]"
        )
    if s > e:
        return (
            f"# {path} ({total} lines total)\n"
            f"[empty range: start line {start} is after end line {end}]"
        )
    header = f"# {path} (lines {s}-{e} of {total})"
    width = len(str(e))
    body = "\n".join(f"{i:>{width}}\t{lines[i - 1]}" for i in range(s, e + 1))
    return f"{header}\n{body}"


# --- Tool schemas (sent to the model) ---------------------------------------

READ_FILE_TOOL = {
    "name": "read_file",
    "description": (
        "Read a file from the repository at /testbed, with absolute line numbers. "
        "Optionally pass start_line/end_line (1-based, inclusive) to read just a "
        "range — prefer a range for large files."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path, relative to /testbed or absolute."},
            "start_line": {"type": "integer", "description": "First line to read (1-based). Optional."},
            "end_line": {"type": "integer", "description": "Last line to read (inclusive). Optional."},
        },
        "required": ["path"],
    },
}

GREP_TOOL = {
    "name": "grep",
    "description": (
        "Search the repository recursively for a pattern and return file:line "
        "matches. Use this to locate code before reading it."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Text or basic regular expression to search for."},
            "path": {
                "type": "string",
                "description": "File or directory to search, relative to /testbed. Defaults to the whole repo.",
            },
        },
        "required": ["pattern"],
    },
}

EDIT_FILE_TOOL = {
    "name": "edit_file",
    "description": (
        "Edit a file by replacing an exact snippet. old_string must appear exactly "
        "once in the file (include enough surrounding lines to make it unique); it "
        "is replaced with new_string. Whole-file rewrites are not supported — make "
        "targeted edits."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path, relative to /testbed or absolute."},
            "old_string": {"type": "string", "description": "Exact snippet to find (must be unique in the file)."},
            "new_string": {"type": "string", "description": "Replacement snippet."},
        },
        "required": ["path", "old_string", "new_string"],
    },
}

RUN_TESTS_TOOL = {
    "name": "run_tests",
    "description": (
        "Run tests with pytest inside the repo and return truncated output. Pass "
        "node-ids or paths (e.g. 'tests/test_x.py::test_y') to run a focused subset "
        "— output is truncated, so narrow targets give you the most signal."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "target": {
                "type": "string",
                "description": "pytest node-ids or paths, space-separated. Optional; omit to run the whole suite.",
            }
        },
    },
}

STRUCTURED_TOOLS = [READ_FILE_TOOL, GREP_TOOL, EDIT_FILE_TOOL, RUN_TESTS_TOOL]


# --- Sandbox-facing handlers -------------------------------------------------


def _abs(path: str) -> str:
    """Resolve a repo-relative path against /testbed; leave absolute paths alone."""
    return path if path.startswith("/") else posixpath.join(TESTBED, path)


def _cat(sandbox: InstanceSandbox, path: str) -> tuple[int, str]:
    """Read a file's contents from the sandbox; return (exit_code, text)."""
    return sandbox.exec(f"cat -- {shlex.quote(_abs(path))}")


def _read_file(sandbox: InstanceSandbox, inp: dict) -> tuple[bool, str]:
    path = inp["path"]
    code, content = _cat(sandbox, path)
    if code != 0:
        return True, f"could not read {path}: {truncate(content)}"
    rendered = render_file(content, path, inp.get("start_line"), inp.get("end_line"))
    return False, truncate(rendered)


def _grep(sandbox: InstanceSandbox, inp: dict) -> tuple[bool, str]:
    pattern = inp["pattern"]
    path = inp.get("path") or "."
    cmd = (
        f"grep -rnI --exclude-dir=.git -e {shlex.quote(pattern)} -- {shlex.quote(path)}"
    )
    code, out = sandbox.exec(cmd)
    # grep's exit codes: 0 = matched, 1 = no match (not an error), >=2 = a real
    # error (bad path or regex). Keep the three distinct so the agent isn't told
    # "no matches" when its pattern or path was actually wrong.
    if code == 0:
        return False, truncate(out)
    if code == 1:
        return False, "no matches."
    return True, f"grep error: {truncate(out) or '(no detail)'}"


def _edit_file(sandbox: InstanceSandbox, inp: dict) -> tuple[bool, str]:
    path = inp["path"]
    target = _abs(path)
    code, content = _cat(sandbox, path)
    if code != 0:
        return True, f"could not read {path} to edit: {truncate(content)}"
    new_content, msg = apply_edit(content, inp["old_string"], inp["new_string"])
    if new_content is None:
        return True, f"edit of {path} failed: {msg}"
    sandbox.write_file(target, new_content)
    return False, f"edited {path}: {msg}"


def _run_tests(sandbox: InstanceSandbox, inp: dict) -> tuple[bool, str]:
    target = (inp.get("target") or "").strip()
    # Quote each node-id/path separately so a space or shell metacharacter in a
    # model-supplied target can't break out of the pytest invocation. An empty
    # target runs the whole suite (truncation keeps that safe).
    quoted = " ".join(shlex.quote(t) for t in target.split())
    cmd = f"python -m pytest -q -p no:cacheprovider {quoted}".rstrip()
    code, out = sandbox.exec(cmd)
    # A nonzero exit means tests failed, which is information for the agent, not a
    # tool error — pass it through with the exit code so pass/fail is unambiguous.
    return False, truncate(f"(pytest exit {code})\n{out}")


_HANDLERS = {
    "read_file": _read_file,
    "grep": _grep,
    "edit_file": _edit_file,
    "run_tests": _run_tests,
}


def dispatch(sandbox: InstanceSandbox, name: str, inp: dict) -> tuple[bool, str]:
    """Run the named structured tool; return ``(is_error, text)``.

    An unknown tool name is reported back to the model as a tool error rather than
    crashing the loop, so a malformed tool call can be recovered from.
    """
    handler = _HANDLERS.get(name)
    if handler is None:
        return True, f"unknown tool: {name!r}"
    return handler(sandbox, inp)
