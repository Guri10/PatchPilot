"""Tests for the trajectory log (patchpilot.trajectory)."""

from __future__ import annotations

import json

from patchpilot.trajectory import TrajectoryLog


def _read(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_trajectory_writes_header_and_events(tmp_path):
    path = tmp_path / "sub" / "trajectory.jsonl"
    with TrajectoryLog.open(path) as log:
        log.run_started(
            instance_id="inst-1", model="m", arm="issue-guided", step_cap=40
        )
        log.assistant_text(1, "thinking")
        log.tool_use(1, "bash", {"command": "ls"})
        log.tool_result(1, "file.py")
        log.stopped(1, "agent_finished")

    events = _read(path)
    assert events[0]["type"] == "run"
    assert events[0]["instance_id"] == "inst-1"
    assert [e["type"] for e in events[1:]] == [
        "assistant_text",
        "tool_use",
        "tool_result",
        "stop",
    ]
    assert all("ts" in e for e in events)
    assert events[2]["input"] == {"command": "ls"}
