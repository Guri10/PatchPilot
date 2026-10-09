"""Run configuration for a single-instance PatchPilot run.

All guardrail knobs (model, step cap, arm) live here so the rest of the code
reads them from one place. Values come from ``.env`` + sensible defaults; the
CLI (``run.py``) can override the instance id and model.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Haiku for the build/debug phase per SPEC ("Models" row); Sonnet is a later swap.
HAIKU = "claude-haiku-4-5-20251001"
SONNET = "claude-sonnet-5"

# The one instance the spine targets by default: a small Flask bug (fast image
# pull, ~52 tests). Verified present in SWE-bench Lite. Overridable on the CLI.
DEFAULT_INSTANCE_ID = "pallets__flask-4045"

# The "baked" Lite dataset: rows carry image / eval_script / log_parser, which
# swebench's make_test_spec needs (the older princeton-nlp/ rows do not).
DATASET_NAME = "SWE-bench/SWE-bench_Lite"
DATASET_SPLIT = "test"

# Arm is fixed to issue-guided for the spine; test-guided is a later, flag-gated
# arm (ADR-0001) and deliberately not reachable here.
ARM = "issue-guided"


@dataclass
class RunConfig:
    """Everything one run needs. Built via :meth:`from_env`."""

    anthropic_api_key: str
    instance_id: str = DEFAULT_INSTANCE_ID
    model: str = HAIKU
    max_steps: int = 40
    dataset_name: str = DATASET_NAME
    dataset_split: str = DATASET_SPLIT
    arm: str = ARM
    runs_dir: Path = field(default_factory=lambda: Path("runs"))

    @property
    def run_dir(self) -> Path:
        """Per-instance output directory (trajectory log, predictions.jsonl)."""
        return self.runs_dir / self.instance_id

    @classmethod
    def from_env(
        cls,
        instance_id: str | None = None,
        model: str | None = None,
        max_steps: int | None = None,
    ) -> "RunConfig":
        load_dotenv()
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Add it to .env or the environment."
            )
        return cls(
            anthropic_api_key=key,
            instance_id=instance_id or DEFAULT_INSTANCE_ID,
            model=model or HAIKU,
            max_steps=max_steps if max_steps is not None else 40,
        )
