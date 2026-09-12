"""Turn the sandbox's working-tree changes into a submittable prediction.

Two responsibilities (ADR-0004):

1. Split a unified ``git diff`` into per-file sections and drop the ones that
   touch test files. In the issue-guided arm the judgment tests are never in
   the container, so any test-file change in the diff is the agent's own
   reproduction test — we submit source changes only.
2. Assemble the ``predictions.jsonl`` record the grader (and, later, cloud
   sb-cli) consumes.

The diff parsing is deliberately dependency-free and unit-tested offline.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

# A file section in a `git diff` starts with this marker.
_FILE_HEADER = re.compile(r"^diff --git a/(?P<a>.+?) b/(?P<b>.+)$")


def _is_test_path(path: str) -> bool:
    """Heuristic: does this path look like a test file (not source)?

    Matches the common Python conventions SWE-bench repos use: a ``tests``
    directory anywhere in the path, or a ``test_*`` / ``*_test.py`` filename,
    or ``conftest.py``.

    Only the *plural* ``tests`` directory counts. Singular ``test`` and
    ``testing`` are commonly source packages (e.g. ``django/test/``,
    ``numpy/testing/``); treating them as test dirs would silently drop
    legitimate source fixes.
    """
    parts = path.split("/")
    name = parts[-1]
    if any(p == "tests" for p in parts[:-1]):
        return True
    if name == "conftest.py":
        return True
    if name.startswith("test_") and name.endswith(".py"):
        return True
    if name.endswith("_test.py"):
        return True
    return False


def split_diff_by_file(diff: str) -> list[tuple[str, str]]:
    """Split a unified diff into ``(target_path, section_text)`` pairs."""
    sections: list[tuple[str, str]] = []
    current_path: str | None = None
    current_lines: list[str] = []

    def flush() -> None:
        if current_path is not None and current_lines:
            sections.append((current_path, "".join(current_lines)))

    for line in diff.splitlines(keepends=True):
        header = _FILE_HEADER.match(line.rstrip("\n"))
        if header:
            flush()
            current_path = header.group("b")
            current_lines = [line]
        elif current_path is not None:
            current_lines.append(line)
    flush()
    return sections


def strip_test_changes(diff: str) -> str:
    """Return the diff with all test-file sections removed."""
    kept = [text for path, text in split_diff_by_file(diff) if not _is_test_path(path)]
    result = "".join(kept)
    # Preserve a trailing newline if the original had content.
    if result and not result.endswith("\n"):
        result += "\n"
    return result


def build_prediction(instance_id: str, model_name: str, model_patch: str) -> dict:
    """Assemble one prediction record in the schema sb-cli / the harness expect."""
    return {
        "instance_id": instance_id,
        "model_name_or_path": model_name,
        "model_patch": model_patch,
    }


def write_predictions(path: Path, prediction: dict) -> Path:
    """Write a single-line ``predictions.jsonl`` and return its path."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(prediction) + "\n", encoding="utf-8")
    return path
