"""Run configuration for a single-instance PatchPilot run.

Values come from explicit arguments first, then environment variables, then
defaults. The guardrails here (step cap) are the ones issue #1 needs; the wider
cost caps from SPEC.md are left as later config once the spine runs.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# The two evaluation arms (see CONTEXT.md / ADR-0001).
ARM_ISSUE_GUIDED = "issue-guided"
ARM_TEST_GUIDED = "test-guided"

# Model aliases. Sonnet is the default for real runs; Haiku is for cheap
# scaffold debugging (SPEC.md "Models").
MODEL_SONNET = "claude-sonnet-5"
MODEL_HAIKU = "claude-haiku-4-5-20251001"

# SWE-bench Lite identifiers used by both the dataset loader and sb-cli.
DATASET_SWEBENCH_LITE = "swe-bench_lite"
DEFAULT_SPLIT = "test"

DEFAULT_STEP_CAP = 40


class ConfigError(ValueError):
    """Raised when required configuration is missing or invalid."""


@dataclass
class RunConfig:
    """Everything one instance run needs to execute."""

    instance_id: str
    anthropic_api_key: str
    model: str = MODEL_SONNET
    arm: str = ARM_ISSUE_GUIDED
    step_cap: int = DEFAULT_STEP_CAP
    dataset: str = DATASET_SWEBENCH_LITE
    split: str = DEFAULT_SPLIT
    # Where trajectory logs and predictions.jsonl land, one dir per instance.
    runs_dir: Path = field(default_factory=lambda: Path("runs"))
    # Override the SWE-bench image if the derived name is ever wrong.
    image_override: str | None = None

    def __post_init__(self) -> None:
        if not self.instance_id:
            raise ConfigError("instance_id is required")
        if not self.anthropic_api_key:
            raise ConfigError(
                "Anthropic API key is required (set ANTHROPIC_API_KEY)"
            )
        if self.arm not in (ARM_ISSUE_GUIDED, ARM_TEST_GUIDED):
            raise ConfigError(f"unknown arm: {self.arm!r}")
        if self.step_cap < 1:
            raise ConfigError("step_cap must be at least 1")
        self.runs_dir = Path(self.runs_dir)

    @property
    def run_dir(self) -> Path:
        """The per-instance output directory (created lazily by callers)."""
        return self.runs_dir / self.instance_id

    @classmethod
    def from_env(
        cls,
        instance_id: str,
        *,
        model: str | None = None,
        step_cap: int | None = None,
        runs_dir: str | os.PathLike[str] | None = None,
        image_override: str | None = None,
        env: dict[str, str] | None = None,
    ) -> "RunConfig":
        """Build a config, filling unset fields from the environment.

        Explicit arguments win over env vars, which win over defaults. The
        ``arm`` stays issue-guided here — test-guided is constructed explicitly
        (it is gated off in this spine), never reachable from the environment.
        """
        environ = env if env is not None else dict(os.environ)
        step = step_cap
        if step is None and environ.get("PATCHPILOT_STEP_CAP"):
            step = int(environ["PATCHPILOT_STEP_CAP"])
        return cls(
            instance_id=instance_id,
            anthropic_api_key=environ.get("ANTHROPIC_API_KEY", ""),
            model=model or environ.get("PATCHPILOT_MODEL") or MODEL_SONNET,
            step_cap=step if step is not None else DEFAULT_STEP_CAP,
            runs_dir=Path(runs_dir or environ.get("PATCHPILOT_RUNS_DIR") or "runs"),
            image_override=image_override,
        )
