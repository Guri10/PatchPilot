"""Tests for the ReAct loop (patchpilot.agent)."""

from __future__ import annotations

import json

import pytest

from patchpilot.agent import (
    STOP_AGENT_FINISHED,
    STOP_STEP_CAP,
    build_user_prompt,
    run_loop,
)
from patchpilot.dataset import Instance
from patchpilot.trajectory import TrajectoryLog
from tests.fakes import FakeClient, FakeSandbox, Response, text_block, tool_use_block

INSTANCE = Instance(
    instance_id="inst-1",
    repo="acme/widgets",
    base_commit="deadbeef",
    problem_statement="add(1, 2) returns -1; addition is broken.",
)


def _trajectory(tmp_path):
    return TrajectoryLog.open(tmp_path / "trajectory.jsonl")


def _events(tmp_path):
    text = (tmp_path / "trajectory.jsonl").read_text()
    return [json.loads(line) for line in text.splitlines()]


def test_loop_dispatches_tool_then_finishes(tmp_path):
    client = FakeClient(
        [
            Response(
                content=[
                    text_block("Let me look."),
                    tool_use_block("t1", "bash", {"command": "grep -r add ."}),
                ],
                stop_reason="tool_use",
            ),
            Response(content=[text_block("Fixed it.")], stop_reason="end_turn"),
        ]
    )
    sandbox = FakeSandbox()
    with _trajectory(tmp_path) as traj:
        result = run_loop(
            client=client,
            sandbox=sandbox,
            instance=INSTANCE,
            step_cap=40,
            trajectory=traj,
            arm="issue-guided",
        )

    assert result.stop_reason == STOP_AGENT_FINISHED
    assert result.steps == 2
    assert sandbox.commands == ["grep -r add ."]
    types = [e["type"] for e in _events(tmp_path)]
    assert "tool_use" in types and "tool_result" in types and "stop" in types


def test_loop_halts_at_step_cap(tmp_path):
    # Always asks for another tool call -> never finishes on its own.
    forever = Response(
        content=[tool_use_block("t", "bash", {"command": "ls"})],
        stop_reason="tool_use",
    )
    client = FakeClient([forever])
    with _trajectory(tmp_path) as traj:
        result = run_loop(
            client=client,
            sandbox=FakeSandbox(),
            instance=INSTANCE,
            step_cap=3,
            trajectory=traj,
            arm="issue-guided",
        )
    assert result.stop_reason == STOP_STEP_CAP
    assert result.steps == 3


def test_issue_guided_context_never_contains_judgment_tests(tmp_path):
    # The loop must only ever surface the issue text, never a judgment test.
    judgment_sentinel = "def test_FAIL_TO_PASS"
    client = FakeClient([Response(content=[text_block("done")], stop_reason="end_turn")])
    with _trajectory(tmp_path) as traj:
        run_loop(
            client=client,
            sandbox=FakeSandbox(),
            instance=INSTANCE,
            step_cap=40,
            trajectory=traj,
            arm="issue-guided",
        )
    all_context = "".join(client.calls)
    assert INSTANCE.problem_statement in all_context
    assert judgment_sentinel not in all_context
    assert "FAIL_TO_PASS" not in all_context
    assert "PASS_TO_PASS" not in all_context


def test_test_guided_arm_is_gated_off(tmp_path):
    with _trajectory(tmp_path) as traj:
        with pytest.raises(NotImplementedError):
            run_loop(
                client=FakeClient([Response(content=[])]),
                sandbox=FakeSandbox(),
                instance=INSTANCE,
                step_cap=1,
                trajectory=traj,
                arm="test-guided",
            )


def test_build_user_prompt_contains_only_issue_text():
    prompt = build_user_prompt(INSTANCE)
    assert INSTANCE.problem_statement in prompt
    assert INSTANCE.repo in prompt
