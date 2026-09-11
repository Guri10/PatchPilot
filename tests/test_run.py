"""Integration test for the orchestration core (patchpilot.run.run_with)."""

from __future__ import annotations

import json

from patchpilot.config import RunConfig
from patchpilot.dataset import Instance
from patchpilot.run import run_with
from tests.fakes import FakeClient, FakeSandbox, Response, text_block, tool_use_block

INSTANCE = Instance(
    instance_id="acme__widgets-1",
    repo="acme/widgets",
    base_commit="deadbeef",
    problem_statement="add is broken",
)

# Diff the sandbox reports: one source fix + one agent reproduction test.
SANDBOX_DIFF = """diff --git a/src/calc.py b/src/calc.py
index 1..2 100644
--- a/src/calc.py
+++ b/src/calc.py
@@ -1 +1 @@
-    return a - b
+    return a + b
diff --git a/tests/test_repro.py b/tests/test_repro.py
new file mode 100644
index 0..3
--- /dev/null
+++ b/tests/test_repro.py
@@ -0,0 +1 @@
+def test_repro(): assert add(1, 2) == 3
"""


def _config(tmp_path):
    return RunConfig(
        instance_id=INSTANCE.instance_id,
        anthropic_api_key="k",
        runs_dir=tmp_path / "runs",
    )


def test_run_with_writes_predictions_and_strips_repro(tmp_path):
    client = FakeClient(
        [
            Response(
                content=[tool_use_block("t1", "bash", {"command": "edit"})],
                stop_reason="tool_use",
            ),
            Response(content=[text_block("done")], stop_reason="end_turn"),
        ]
    )
    sandbox = FakeSandbox(diff=SANDBOX_DIFF)
    config = _config(tmp_path)

    summary = run_with(
        client=client, sandbox=sandbox, instance=INSTANCE, config=config
    )

    assert summary.stop_reason == "agent_finished"
    assert not summary.patch_is_empty

    record = json.loads(summary.predictions_path.read_text().strip())
    assert record["instance_id"] == INSTANCE.instance_id
    # Source fix kept, reproduction test stripped.
    assert "src/calc.py" in record["model_patch"]
    assert "test_repro.py" not in record["model_patch"]

    # Trajectory was written next to the prediction, and covers the post-loop
    # patch step (diff strip + predictions), not just the loop.
    traj_lines = (config.run_dir / "trajectory.jsonl").read_text().splitlines()
    patch_events = [json.loads(x) for x in traj_lines if '"type": "patch"' in x]
    assert len(patch_events) == 1
    assert patch_events[0]["stripped_files"] == ["tests/test_repro.py"]
    assert patch_events[0]["patch_empty"] is False


def test_run_with_flags_empty_patch(tmp_path):
    client = FakeClient([Response(content=[text_block("nothing to do")])])
    sandbox = FakeSandbox(diff="")
    summary = run_with(
        client=client, sandbox=sandbox, instance=INSTANCE, config=_config(tmp_path)
    )
    assert summary.patch_is_empty
