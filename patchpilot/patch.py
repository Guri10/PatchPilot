"""Turn the sandbox's ``git diff`` into a submittable prediction.

Two jobs (ADR-0004):

1. Strip the agent's own reproduction test so the submitted patch is source
   changes only — a stray agent-authored test risks breaking ``PASS_TO_PASS``,
   and the harness supplies its own judgment tests anyway.
2. Assemble ``predictions.jsonl`` in the shape sb-cli expects.

The diff is split on ``diff --git`` file boundaries; any section whose target
path looks like a test file is dropped.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

_DIFF_HEADER = "diff --git "


@dataclass(frozen=True)
class DiffSection:
    """One file's worth of a unified diff."""

    path: str  # the target ("b/") path, repo-relative
    text: str  # the full section text, including its trailing newline(s)


def is_test_path(path: str) -> bool:
    """True if ``path`` looks like a test file (reproduction/judgment/regression).

    Matches pytest-style layouts: a ``tests`` directory anywhere in the path, a
    ``test_*.py`` or ``*_test.py`` basename, or ``conftest.py``. The directory
    rule is the plural ``tests`` only — the singular ``test`` is a real source
    package in some repos (e.g. Django's ``django/test/``), so matching it would
    silently strip legitimate source changes from the submitted patch.
    """
    parts = path.split("/")
    if "tests" in parts[:-1]:
        return True
    name = parts[-1]
    if name == "conftest.py":
        return True
    if name.endswith(".py") and (name.startswith("test_") or name.endswith("_test.py")):
        return True
    return False


def _section_path(header_line: str) -> str:
    """Extract the target path from a ``diff --git a/X b/Y`` header line."""
    rest = header_line[len(_DIFF_HEADER) :].strip()
    # The b/ side is authoritative (it survives renames/adds).
    marker = " b/"
    idx = rest.find(marker)
    if idx != -1:
        return rest[idx + len(marker) :].strip()
    # Fallback: take the last whitespace-separated token, drop a leading b/.
    token = rest.split()[-1]
    return token[2:] if token.startswith("b/") else token


def split_diff_by_file(diff: str) -> list[DiffSection]:
    """Split a unified diff into one :class:`DiffSection` per file.

    Concatenating the sections' ``text`` reproduces the input exactly.
    """
    if not diff:
        return []
    lines = diff.splitlines(keepends=True)
    sections: list[DiffSection] = []
    current: list[str] | None = None
    current_path = ""
    for line in lines:
        if line.startswith(_DIFF_HEADER):
            if current is not None:
                sections.append(DiffSection(current_path, "".join(current)))
            current = [line]
            current_path = _section_path(line)
        elif current is not None:
            current.append(line)
        # Lines before the first header (rare) are ignored.
    if current is not None:
        sections.append(DiffSection(current_path, "".join(current)))
    return sections


def partition_test_files(diff: str) -> tuple[str, list[str]]:
    """Split ``diff`` into (source-only diff, list of stripped test paths)."""
    kept: list[str] = []
    stripped: list[str] = []
    for section in split_diff_by_file(diff):
        if is_test_path(section.path):
            stripped.append(section.path)
        else:
            kept.append(section.text)
    return "".join(kept), stripped


def strip_test_files(diff: str) -> str:
    """Return ``diff`` with every test-file section removed."""
    return partition_test_files(diff)[0]


def build_prediction(instance_id: str, model_name: str, model_patch: str) -> dict[str, Any]:
    """Build one sb-cli prediction record."""
    return {
        "instance_id": instance_id,
        "model_name_or_path": model_name,
        "model_patch": model_patch,
    }


def write_predictions_jsonl(records: Iterable[dict[str, Any]], path: str | Path) -> Path:
    """Write prediction records to a JSONL file, one per line."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return p
