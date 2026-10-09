"""End-to-end spine for one SWE-bench Lite instance (issue-guided arm).

    python -m patchpilot.run --instance-id pallets__flask-4045

Steps: load the instance -> boot a Modal sandbox on its official image -> run the
bash-only ReAct loop over the issue text -> extract the git diff, strip the
agent's reproduction test -> write predictions.jsonl -> grade in-sandbox and
print resolved / not resolved.

--gold skips the agent and grades the gold patch instead, to validate the grader
on its own (it should always resolve).
"""

from __future__ import annotations

import argparse
import json
import sys

from patchpilot.agent import run_loop
from patchpilot.config import RunConfig
from patchpilot.dataset import load_instance, test_spec_for
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

    if gold:
        print("[patchpilot] --gold: grading the gold patch (grader self-check)")
        model_patch = instance["patch"]
    else:
        with InstanceSandbox(spec.image) as sandbox:
            print("[patchpilot] sandbox up; running agent loop...")
            result = run_loop(
                config, sandbox, instance["problem_statement"], trajectory
            )
            print(f"[patchpilot] loop stopped: {result.stop_reason} after {result.steps} steps")
            raw_diff = extract_diff(sandbox)
        model_patch = strip_test_changes(raw_diff)

    prediction = build_prediction(config.instance_id, config.model, model_patch)
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
    parser.add_argument("--model", default=None, help="Anthropic model id")
    parser.add_argument("--max-steps", type=int, default=None, help="Loop step cap")
    parser.add_argument(
        "--gold", action="store_true", help="Grade the gold patch (grader self-check)"
    )
    args = parser.parse_args(argv)

    config = RunConfig.from_env(
        instance_id=args.instance_id, model=args.model, max_steps=args.max_steps
    )
    resolved = run(config, gold=args.gold)
    return 0 if resolved else 1


if __name__ == "__main__":
    sys.exit(main())
