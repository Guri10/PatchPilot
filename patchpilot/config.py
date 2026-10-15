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

# Evaluation arm (ADR-0001). "issue-guided" is the headline, default arm: the
# agent never sees the judgment tests. "test-guided" is the flag-gated oracle
# that reveals them — it can only be selected explicitly, never by accident.
ARM = "issue-guided"
TEST_GUIDED_ARM = "test-guided"
VALID_ARMS = (ARM, TEST_GUIDED_ARM)


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

    def __post_init__(self) -> None:
        if self.arm not in VALID_ARMS:
            raise ValueError(
                f"unknown arm {self.arm!r}; expected one of {VALID_ARMS}"
            )

    @property
    def test_guided(self) -> bool:
        """True only in the flag-gated oracle arm that reveals the judgment tests."""
        return self.arm == TEST_GUIDED_ARM

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
        test_guided: bool | None = None,
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
        # The oracle arm must be switched on deliberately. A CLI --test-guided
        # flag wins; otherwise PATCHPILOT_ARM; otherwise the issue-guided default.
        arm = _resolve_arm(test_guided)
        return cls(
            anthropic_api_key=key,
            instance_id=instance_id or DEFAULT_INSTANCE_ID,
            model=resolve_model(chosen_model)[0],
            max_steps=max_steps if max_steps is not None else 40,
            arm=arm,
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


def _resolve_arm(test_guided: bool | None) -> str:
    """Pick the arm from the CLI flag, else PATCHPILOT_ARM, else the default.

    An explicit ``test_guided`` (the CLI flag) always wins so the environment
    can never silently override what the operator typed. ``PATCHPILOT_ARM``
    accepts a full arm name and is validated against the known arms.
    """
    if test_guided is not None:
        return TEST_GUIDED_ARM if test_guided else ARM
    raw = os.environ.get("PATCHPILOT_ARM")
    if raw is None or raw.strip() == "":
        return ARM
    arm = raw.strip()
    if arm not in VALID_ARMS:
        raise ValueError(f"PATCHPILOT_ARM={arm!r} is not one of {VALID_ARMS}")
    return arm


def _env_float(name: str, default: float) -> float:
    """Read a float env var, falling back to ``default`` if unset or malformed."""
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default
