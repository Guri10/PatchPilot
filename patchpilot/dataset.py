"""Load one SWE-bench Lite instance and its grading spec.

Uses swebench's own loader so each row is the "baked" format that carries
``image`` / ``eval_script`` / ``log_parser`` — the fields ``make_test_spec``
needs. The ``problem_statement`` is the only task text the agent sees in the
issue-guided arm; ``test_patch`` / ``FAIL_TO_PASS`` / ``PASS_TO_PASS`` are used
only at grading time and never enter the agent's context — except in the
flag-gated test-guided arm, where :func:`judgment_tests_guidance` hands them to
the agent on purpose (ADR-0001).
"""

from __future__ import annotations

import ast
import json

from swebench.harness.utils import load_swebench_dataset, make_test_spec
from swebench.types import TestSpec


def load_instance(instance_id: str, dataset_name: str, split: str) -> dict:
    """Return the single dataset row for ``instance_id``.

    Raises a clear error listing nothing sensitive if the id is not in the split.
    """
    rows = load_swebench_dataset(dataset_name, split, [instance_id])
    if not rows:
        raise KeyError(
            f"instance_id {instance_id!r} not found in {dataset_name} split {split!r}"
        )
    return rows[0]


def test_spec_for(instance: dict) -> TestSpec:
    """Build the official grading spec (image, eval script, log parser)."""
    return make_test_spec(instance)


def _as_node_ids(value) -> list[str]:
    """Normalise a FAIL_TO_PASS / PASS_TO_PASS field to a list of test node-ids.

    The loader may hand these back as a real list, a JSON-encoded string, or a
    Python-repr string depending on the dataset revision, so accept all three.
    A bare node-id that parses as neither is treated as a single-element list
    rather than crashing the oracle run.
    """
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        parsed = None
        for loader in (json.loads, ast.literal_eval):
            try:
                parsed = loader(text)
                break
            except (ValueError, SyntaxError):
                continue
        value = parsed if isinstance(parsed, (list, tuple)) else [text]
    return [str(node_id) for node_id in value]


def judgment_tests_guidance(instance: dict) -> str:
    """Render the instance's judgment tests as a guidance block for the agent.

    This is the ONLY place the hidden tests are shaped for the agent's context,
    and it must run only in the flag-gated test-guided arm (ADR-0001). It reveals
    both the scoring test node-ids (``FAIL_TO_PASS`` + ``PASS_TO_PASS``) and the
    ``test_patch`` that defines their assertions — the full oracle.
    """
    fail_to_pass = _as_node_ids(instance.get("FAIL_TO_PASS"))
    pass_to_pass = _as_node_ids(instance.get("PASS_TO_PASS"))
    test_patch = instance.get("test_patch") or ""

    lines = [
        "The exact tests that will score this task are given below. The tests "
        "that must newly pass after your fix:",
        "",
        *(f"  - {node_id}" for node_id in fail_to_pass),
        "",
        "The tests that must keep passing (do not break them):",
        "",
        *(f"  - {node_id}" for node_id in pass_to_pass),
        "",
        "These tests are applied by the harness after your patch; you cannot "
        "edit them. The diff that introduces them is:",
        "",
        "<test_patch>",
        test_patch,
        "</test_patch>",
    ]
    return "\n".join(lines)
