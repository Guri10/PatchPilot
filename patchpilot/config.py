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

from patchpilot.budget import ModelSpec, resolve_model

# Haiku for the build/debug phase per SPEC ("Models" row); Sonnet is a later swap.
# The ids live in the budget model registry (one source of truth, with pricing);
# these aliases keep the historical import path working.
HAIKU = resolve_model("haiku")[0]
SONNET = resolve_model("sonnet")[0]

# Default per-instance cost ceiling and global run budget (USD), both from SPEC
# ("Budget & guardrails": $150 hard total cap). Modal compute is billed per
# sandbox-second; the default rate is a small, overridable estimate since model
# tokens dominate spend.
DEFAULT_INSTANCE_BUDGET_USD = 1.0
DEFAULT_GLOBAL_BUDGET_USD = 150.0
DEFAULT_MODAL_RATE_USD_PER_SEC = 0.0001

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
    instance_budget_usd: float = DEFAULT_INSTANCE_BUDGET_USD
    global_budget_usd: float = DEFAULT_GLOBAL_BUDGET_USD
    modal_rate_usd_per_sec: float = DEFAULT_MODAL_RATE_USD_PER_SEC
    dataset_name: str = DATASET_NAME
    dataset_split: str = DATASET_SPLIT
    arm: str = ARM
    runs_dir: Path = field(default_factory=lambda: Path("runs"))

    @property
    def run_dir(self) -> Path:
        """Per-instance output directory (trajectory log, predictions.jsonl)."""
        return self.runs_dir / self.instance_id

    @property
    def model_spec(self) -> ModelSpec:
        """Pricing/spec for :attr:`model` (resolves friendly names and raw ids)."""
        return resolve_model(self.model)[1]

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
        # Model swap is a single config change: a friendly name ("haiku"/"sonnet")
        # from the CLI or PATCHPILOT_MODEL, resolved to its API id here — no call
        # site hard-codes an id.
        chosen_model = model or os.environ.get("PATCHPILOT_MODEL") or "haiku"
        return cls(
            anthropic_api_key=key,
            instance_id=instance_id or DEFAULT_INSTANCE_ID,
            model=resolve_model(chosen_model)[0],
            max_steps=max_steps if max_steps is not None else 40,
            instance_budget_usd=_env_float(
                "PATCHPILOT_INSTANCE_BUDGET", DEFAULT_INSTANCE_BUDGET_USD
            ),
            global_budget_usd=_env_float(
                "PATCHPILOT_GLOBAL_BUDGET", DEFAULT_GLOBAL_BUDGET_USD
            ),
            modal_rate_usd_per_sec=_env_float(
                "PATCHPILOT_MODAL_RATE", DEFAULT_MODAL_RATE_USD_PER_SEC
            ),
        )


def _env_float(name: str, default: float) -> float:
    """Read a float env var, falling back to ``default`` if unset or malformed."""
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default
