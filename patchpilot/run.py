"""End-to-end spine for one SWE-bench Lite instance.

    python -m patchpilot.run --instance-id pallets__flask-4045

Steps: load the instance -> boot a Modal sandbox on its official image -> run the
ReAct loop over the issue text -> extract the git diff, strip the agent's
reproduction test -> write predictions.jsonl -> grade in-sandbox and print
resolved / not resolved.

Defaults to the issue-guided (headline) arm. --test-guided switches to the
flag-gated oracle arm (ADR-0001), which reveals the judgment tests to the agent;
such runs are loudly labelled and their predictions tagged so the number is
never mistaken for the headline resolved rate.

--gold skips the agent and grades the gold patch instead, to validate the grader
on its own (it should always resolve).
"""

from __future__ import annotations

import argparse
import json
import sys

from patchpilot.agent import run_loop
from patchpilot.budget import BudgetExceeded, BudgetTracker
from patchpilot.config import RunConfig
from patchpilot.dataset import judgment_tests_guidance, load_instance, test_spec_for
from patchpilot.grade import grade
from patchpilot.patch import build_prediction, strip_test_changes, write_predictions
from patchpilot.sandbox import InstanceSandbox
from patchpilot.trajectory import TrajectoryLog


def extract_diff(sandbox: InstanceSandbox) -> str:
    """Capture the agent's edits to tracked files as a unified diff.

    ``git diff HEAD`` (not ``git add -A``) so untracked artifacts the agent may
    leave behind — a stray ``reproduce.py``, ``.pytest_cache/`` — never enter
    the "source-only" prediction. This matches the shape of SWE-bench gold
    patches (edits to existing files); a fix that adds a brand-new source file
    would not be captured, which is rare in Lite and acceptable for the spine.
    ``strip_test_changes`` still runs as defense-in-depth for edited test files.
    """
    _, diff = sandbox.exec("git diff HEAD")
    return diff


def run(config: RunConfig, gold: bool = False) -> bool:
    instance = load_instance(
        config.instance_id, config.dataset_name, config.dataset_split
    )
    spec = test_spec_for(instance)
    run_dir = config.run_dir
    run_dir.mkdir(parents=True, exist_ok=True)
    trajectory = TrajectoryLog(run_dir / "trajectory.jsonl")

    print(f"[patchpilot] instance={config.instance_id} model={config.model}")
    print(f"[patchpilot] image={spec.image}")
    # In gold mode no agent runs, so the arm is irrelevant — don't label the
    # grader self-check as an oracle result.
    oracle = config.test_guided and not gold
    trajectory.log("arm", arm=config.arm if not gold else "gold")
    if oracle:
        # The oracle arm reveals the judgment tests to the agent. Shout about it
        # so a resolved rate from this run is never mistaken for the headline.
        print("*" * 50)
        print("  ARM: TEST-GUIDED (oracle) — judgment tests revealed to agent.")
        print("  Diagnostic upper bound. NOT the headline resolved rate.")
        print("*" * 50)

    if gold:
        print("[patchpilot] --gold: grading the gold patch (grader self-check)")
        model_patch = instance["patch"]
    else:
        budget = BudgetTracker(
            instance_cap_usd=config.instance_budget_usd,
            global_cap_usd=config.global_budget_usd,
        )
        budget.start_instance()
        print(
            f"[patchpilot] budget: instance cap ${config.instance_budget_usd:.2f}, "
            f"global cap ${config.global_budget_usd:.2f}"
        )
        # Oracle guidance is built only in the test-guided arm; otherwise None so
        # the judgment tests never reach the agent in the default arm.
        guidance = judgment_tests_guidance(instance) if config.test_guided else None
        with InstanceSandbox(spec.image) as sandbox:
            print("[patchpilot] sandbox up; running agent loop...")
            result = run_loop(
                config,
                sandbox,
                instance["problem_statement"],
                trajectory,
                budget,
                judgment_guidance=guidance,
            )
            print(f"[patchpilot] loop stopped: {result.stop_reason} after {result.steps} steps")
            raw_diff = extract_diff(sandbox)
            # Bill Modal compute for this sandbox's lifetime before teardown.
            budget.add_compute(sandbox.elapsed_seconds, config.modal_rate_usd_per_sec)
        budget.raise_if_global_exceeded()
        print(f"[patchpilot] spend: ${budget.total_cost:.4f} (tokens + compute)")
        model_patch = strip_test_changes(raw_diff)

    # Tag the oracle arm's predictions in the field any leaderboard-style
    # aggregation groups by, so a test-guided number can never be silently
    # pooled into the headline issue-guided resolved rate.
    model_label = f"{config.model}__test-guided" if oracle else config.model
    prediction = build_prediction(config.instance_id, model_label, model_patch)
    pred_path = write_predictions(run_dir / "predictions.jsonl", prediction)
    print(f"[patchpilot] wrote {pred_path} (patch: {len(model_patch)} chars)")

    print("[patchpilot] grading in-sandbox (official swebench harness)...")
    grade_result = grade(spec, prediction, run_dir / "eval.log")
    trajectory.score(grade_result["resolved"], grade_result["report"])

    resolved = grade_result["resolved"]
    if not grade_result["patch_applied"] and model_patch.strip():
        print("[patchpilot] WARNING: model patch failed to apply cleanly")
    print("\n" + "=" * 50)
    print(f"  {config.instance_id}: {'RESOLVED' if resolved else 'NOT RESOLVED'}")
    print("=" * 50)
    print(f"  tests_status: {json.dumps(grade_result['report'].get('tests_status', {}))[:400]}")
    print(f"  artifacts in: {run_dir}")
    return resolved


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PatchPilot one-instance spine")
    parser.add_argument("--instance-id", default=None, help="SWE-bench Lite instance id")
    parser.add_argument(
        "--model", default=None, help="Model: 'haiku', 'sonnet', or a raw Anthropic id"
    )
    parser.add_argument("--max-steps", type=int, default=None, help="Loop step cap")
    parser.add_argument(
        "--gold", action="store_true", help="Grade the gold patch (grader self-check)"
    )
    parser.add_argument(
        "--test-guided",
        action="store_true",
        help="ORACLE arm: reveal the judgment tests to the agent. Diagnostic "
        "upper bound only — never the headline resolved rate (ADR-0001).",
    )
    args = parser.parse_args(argv)

    config = RunConfig.from_env(
        instance_id=args.instance_id,
        model=args.model,
        max_steps=args.max_steps,
        test_guided=args.test_guided or None,
    )
    try:
        resolved = run(config, gold=args.gold)
    except BudgetExceeded as exc:
        # The global kill-switch fired: halt the whole run, non-zero exit.
        print(f"\n[patchpilot] HALTED — {exc}", file=sys.stderr)
        return 2
    return 0 if resolved else 1


if __name__ == "__main__":
    sys.exit(main())
