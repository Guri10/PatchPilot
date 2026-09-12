"""In-sandbox grading with the official swebench harness (ADR-0005).

Instead of submitting to the cloud sb-cli service, we reproduce exactly what the
harness does, in a *fresh* sandbox from the same instance image:

    clean checkout at base_commit  (the image ships this)
    -> apply the model patch (source-only)
    -> run the instance's official eval_script (resets test files, applies the
       judgment test_patch, runs FAIL_TO_PASS + PASS_TO_PASS)
    -> parse the log with swebench's own get_eval_report.

A fresh sandbox (not the agent's working one) guarantees grading starts from the
same clean state the harness assumes, uncontaminated by the agent's edits or its
reproduction test. The image is cached on Modal after the loop's first pull.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from swebench.harness.grading import get_eval_report
from swebench.types import TestSpec

from patchpilot.sandbox import InstanceSandbox

MODEL_PATCH_PATH = "/tmp/model_patch.diff"
EVAL_SCRIPT_PATH = "/eval.sh"


def _apply_model_patch(sandbox: InstanceSandbox, model_patch: str) -> tuple[bool, str]:
    """Apply the source-only patch to /testbed.

    Try a plain ``git apply``, then a ``--3way`` merge. Both stay faithful to
    the patch's real context; we deliberately do NOT fall back to a fuzzy
    ``patch --fuzz`` apply, which can silently land hunks at the wrong lines and
    still report success. If neither applies, we report ``False`` honestly so
    the caller can flag it rather than grading mis-patched code.
    """
    sandbox.write_file(MODEL_PATCH_PATH, model_patch)
    code, out = sandbox.exec(f"git apply -v {MODEL_PATCH_PATH}")
    if code == 0:
        return True, out
    code2, out2 = sandbox.exec(f"git apply --3way -v {MODEL_PATCH_PATH}")
    return code2 == 0, out + "\n--- git apply --3way fallback ---\n" + out2


def grade(
    spec: TestSpec,
    prediction: dict,
    log_path: Path,
    image_timeout: int = 1800,
) -> dict[str, Any]:
    """Run the official eval in a fresh sandbox and return a grading summary.

    Returns a dict with ``resolved`` (bool), ``patch_applied`` (bool), and the
    swebench per-instance ``report``.
    """
    model_patch = prediction.get("model_patch") or ""
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    patch_applied = False
    apply_output = ""
    with InstanceSandbox(spec.image, timeout=image_timeout) as sandbox:
        if model_patch.strip():
            patch_applied, apply_output = _apply_model_patch(sandbox, model_patch)
        sandbox.write_file(EVAL_SCRIPT_PATH, spec.eval_script)
        _, eval_log = sandbox.exec(f"chmod +x {EVAL_SCRIPT_PATH} && bash {EVAL_SCRIPT_PATH}")

    # Persist the full eval log for get_eval_report and for the audit trail.
    full_log = (
        "===== MODEL PATCH APPLY =====\n"
        f"{apply_output}\n"
        "===== EVAL SCRIPT OUTPUT =====\n"
        f"{eval_log}"
    )
    log_path.write_text(full_log, encoding="utf-8")

    report_map = get_eval_report(
        test_spec=spec,
        prediction=prediction,
        test_log_path=str(log_path),
        include_tests_status=True,
    )
    instance_report = report_map.get(spec.instance_id, {})
    return {
        "resolved": bool(instance_report.get("resolved", False)),
        "patch_applied": patch_applied,
        "report": instance_report,
    }
