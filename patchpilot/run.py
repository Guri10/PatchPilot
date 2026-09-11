"""Orchestrate one instance end to end (ADR-0004).

create sandbox -> run loop -> extract diff -> strip reproduction test -> write
predictions.jsonl -> tear down -> (optionally) submit to sb-cli.

``run_with`` is the testable core (inject a client and sandbox); ``run_instance``
builds the real Anthropic client and Modal sandbox and calls it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .agent import LoopResult, run_loop
from .config import RunConfig
from .dataset import Instance, load_instance
from .llm import AnthropicClient, LLMClient
from .patch import build_prediction, partition_test_files, write_predictions_jsonl
from .sandbox import ModalSandbox, Sandbox
from .submit import load_report, parse_resolved, submit
from .trajectory import TrajectoryLog

PREDICTIONS_FILENAME = "predictions.jsonl"
TRAJECTORY_FILENAME = "trajectory.jsonl"


@dataclass
class RunSummary:
    """What one run produced."""

    instance_id: str
    stop_reason: str
    steps: int
    predictions_path: Path
    patch_is_empty: bool
    resolved: bool | None = None  # set only when scored via sb-cli


def run_with(
    *,
    client: LLMClient,
    sandbox: Sandbox,
    instance: Instance,
    config: RunConfig,
) -> RunSummary:
    """Run the loop against a given client/sandbox and assemble the prediction.

    The sandbox is *not* torn down here — the caller owns its lifecycle.
    """
    run_dir = config.run_dir
    trajectory_path = run_dir / TRAJECTORY_FILENAME
    predictions_path = run_dir / PREDICTIONS_FILENAME

    with TrajectoryLog.open(trajectory_path) as trajectory:
        trajectory.run_started(
            instance_id=instance.instance_id,
            model=config.model,
            arm=config.arm,
            step_cap=config.step_cap,
        )
        result: LoopResult = run_loop(
            client=client,
            sandbox=sandbox,
            instance=instance,
            step_cap=config.step_cap,
            trajectory=trajectory,
            arm=config.arm,
        )

        # Post-loop patch extraction, logged in the same trajectory.
        raw_diff = sandbox.git_diff()
        source_patch, stripped_files = partition_test_files(raw_diff)
        prediction = build_prediction(
            instance.instance_id, config.model, source_patch
        )
        write_predictions_jsonl([prediction], predictions_path)
        patch_is_empty = not source_patch.strip()
        trajectory.patch_assembled(
            stripped_files=stripped_files,
            patch_empty=patch_is_empty,
            predictions_path=str(predictions_path),
        )

    return RunSummary(
        instance_id=instance.instance_id,
        stop_reason=result.stop_reason,
        steps=result.steps,
        predictions_path=predictions_path,
        patch_is_empty=patch_is_empty,
    )


def run_instance(config: RunConfig, *, submit_score: bool = False) -> RunSummary:
    """Full real run: load the instance, spin up Modal, loop, assemble, score."""
    instance = load_instance(
        config.instance_id, dataset=config.dataset, split=config.split
    )
    client = AnthropicClient(config.anthropic_api_key, config.model)

    sandbox = ModalSandbox.create(
        config.instance_id, image_override=config.image_override
    )
    try:
        summary = run_with(
            client=client, sandbox=sandbox, instance=instance, config=config
        )
    finally:
        sandbox.teardown()

    if submit_score:
        summary.resolved = _score(config, summary.predictions_path)
    return summary


def _score(config: RunConfig, predictions_path: Path) -> bool | None:
    """Submit to sb-cli and read the verdict from the report it writes.

    ``sb-cli submit`` waits for evaluation and writes a JSON report into the
    output dir; we point that at the run dir and read the report back.
    """
    run_id = f"patchpilot-{config.instance_id}"
    report_dir = predictions_path.parent
    proc = submit(
        predictions_path=predictions_path,
        run_id=run_id,
        dataset=config.dataset,
        split=config.split,
        output_dir=report_dir,
    )
    print(proc.stdout)
    if proc.stderr:
        print(proc.stderr)
    # sb-cli names the report itself; predictions is .jsonl, so *.json is the
    # report. Take the newest in case of reruns.
    reports = sorted(report_dir.glob("*.json"), key=lambda p: p.stat().st_mtime)
    if reports:
        return parse_resolved(load_report(reports[-1]), config.instance_id)
    print(
        f"no report json in {report_dir}; fetch it with "
        f"`sb-cli get-report {config.dataset} {config.split} --run_id {run_id}`"
    )
    return None
