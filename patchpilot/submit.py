"""Submit predictions to the free cloud sb-cli and read back the score.

Scoring is always delegated to sb-cli (SWE-bench's hosted, Modal-backed official
harness) — never scored locally, and never with Modal's paid ``--modal`` flag
(SPEC.md). This module shells out to the ``sb-cli`` binary; the command it builds
and the report it parses are the testable parts.

The report schema below is sb-cli's per-run results JSON (a ``resolved`` /
``unresolved`` id split). If a future sb-cli version changes it, only
:func:`parse_resolved` needs updating.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any


def build_submit_command(
    *,
    predictions_path: str | Path,
    run_id: str,
    dataset: str,
    split: str,
    output_dir: str | Path | None = None,
) -> list[str]:
    """Build the ``sb-cli submit`` argv.

    ``sb-cli submit`` waits for evaluation and writes a report into
    ``output_dir`` (its own default is ``sb-cli-reports/``); pass ``output_dir``
    to land it somewhere we control. The API key is read from ``SWEBENCH_API_KEY``
    in the environment, so it is not passed on the command line.
    """
    cmd = [
        "sb-cli",
        "submit",
        dataset,
        split,
        "--predictions_path",
        str(predictions_path),
        "--run_id",
        run_id,
    ]
    if output_dir is not None:
        cmd += ["--output_dir", str(output_dir)]
    return cmd


def submit(
    *,
    predictions_path: str | Path,
    run_id: str,
    dataset: str,
    split: str,
    output_dir: str | Path | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run ``sb-cli submit`` and return the completed process.

    Does not raise on a non-zero exit; the caller inspects the result and the
    trajectory/console output. Inherits the environment (so ``SWEBENCH_API_KEY``,
    including one loaded from ``.env``, reaches sb-cli).
    """
    cmd = build_submit_command(
        predictions_path=predictions_path,
        run_id=run_id,
        dataset=dataset,
        split=split,
        output_dir=output_dir,
    )
    return subprocess.run(cmd, capture_output=True, text=True)


def parse_resolved(report: dict[str, Any], instance_id: str) -> bool | None:
    """Return whether ``instance_id`` resolved, or ``None`` if not in the report.

    Accepts either id-list form (``{"resolved": [...], "unresolved": [...]}``) or
    a per-instance mapping (``{"<id>": {"resolved": true}}``).
    """
    resolved = report.get("resolved")
    if isinstance(resolved, list):
        if instance_id in resolved:
            return True
        unresolved = report.get("unresolved")
        if isinstance(unresolved, list) and instance_id in unresolved:
            return False
        return None
    entry = report.get(instance_id)
    if isinstance(entry, dict) and "resolved" in entry:
        return bool(entry["resolved"])
    return None


def load_report(path: str | Path) -> dict[str, Any]:
    """Load an sb-cli results JSON report from disk."""
    return json.loads(Path(path).read_text(encoding="utf-8"))
