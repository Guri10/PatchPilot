"""Load one SWE-bench Lite instance and its grading spec.

Uses swebench's own loader so each row is the "baked" format that carries
``image`` / ``eval_script`` / ``log_parser`` — the fields ``make_test_spec``
needs. The ``problem_statement`` is the only task text the agent sees in the
issue-guided arm; ``test_patch`` / ``FAIL_TO_PASS`` / ``PASS_TO_PASS`` are used
only at grading time and never enter the agent's context.
"""

from __future__ import annotations

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
