"""Load a single SWE-bench Lite instance and derive its official image name.

Only the fields the spine needs are surfaced. The judgment tests
(`FAIL_TO_PASS` / `PASS_TO_PASS`) are deliberately *not* exposed to the agent
in the issue-guided arm — they live on the instance for scoring context only and
are never placed in the model's context (see CONTEXT.md, ADR-0001).
"""

from __future__ import annotations

from dataclasses import dataclass

# Path the SWE-bench instance images check the repo out to.
TESTBED_PATH = "/testbed"


@dataclass(frozen=True)
class Instance:
    """One SWE-bench Lite task."""

    instance_id: str
    repo: str
    base_commit: str
    problem_statement: str  # the issue text the agent is allowed to see


def instance_image_name(instance_id: str) -> str:
    """Return the official SWE-bench x86_64 image for an instance.

    SWE-bench derives the image tag from the instance id, lowercased, with the
    ``__`` separator replaced by ``_1776_`` (Docker tags disallow the bare
    double underscore convention SWE-bench uses in ids). Example:
    ``django__django-11099`` -> ``swebench/sweb.eval.x86_64.django_1776_django-11099:latest``.
    """
    tag = instance_id.lower().replace("__", "_1776_")
    return f"swebench/sweb.eval.x86_64.{tag}:latest"


def load_instance(instance_id: str, *, dataset: str, split: str) -> Instance:
    """Load one instance from the SWE-bench Lite dataset on HuggingFace.

    Imports ``datasets`` lazily so the package (and its tests) load without it.
    """
    from datasets import load_dataset  # type: ignore[import-untyped]

    # The HuggingFace dataset id for the sb-cli name ``swe-bench_lite``.
    hf_name = "princeton-nlp/SWE-bench_Lite" if dataset == "swe-bench_lite" else dataset
    rows = load_dataset(hf_name, split=split)
    for row in rows:
        if row["instance_id"] == instance_id:
            return _instance_from_row(row)
    raise KeyError(f"instance_id {instance_id!r} not found in {hf_name} [{split}]")


def _instance_from_row(row: dict) -> Instance:
    return Instance(
        instance_id=row["instance_id"],
        repo=row["repo"],
        base_commit=row["base_commit"],
        problem_statement=row["problem_statement"],
    )
