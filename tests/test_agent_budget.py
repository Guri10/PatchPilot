"""Loop-level tests for the cost guardrails and prompt caching (issue #3).

These drive :func:`run_loop` with a fake Anthropic client and a fake sandbox so
no network or Modal is touched. They pin the behaviour the acceptance criteria
name: a per-instance overspend stops the one instance cleanly, a global
overspend raises the kill-switch, and the prompt-cache breakpoint rides the
latest turn.
"""

from types import SimpleNamespace

import pytest

from patchpilot import agent
from patchpilot.budget import BudgetExceeded, BudgetTracker
from patchpilot.config import RunConfig
from patchpilot.trajectory import TrajectoryLog


def _usage(output_tokens=0, input_tokens=0, cache_read=0, cache_write=0):
    return SimpleNamespace(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_input_tokens=cache_read,
        cache_creation_input_tokens=cache_write,
    )


def _tool_use_turn(output_tokens):
    """A response that calls read_file once (stop_reason tool_use)."""
    block = SimpleNamespace(type="tool_use", id="t1", name="read_file", input={"path": "x"})
    return SimpleNamespace(content=[block], stop_reason="tool_use", usage=_usage(output_tokens))


def _end_turn():
    block = SimpleNamespace(type="text", text="done")
    return SimpleNamespace(content=[block], stop_reason="end_turn", usage=_usage(10))


class _FakeMessages:
    def __init__(self, responses, calls):
        self._responses = list(responses)
        self._calls = calls

    def create(self, **kwargs):
        # Snapshot whether the latest turn carries a cache breakpoint right now.
        msgs = kwargs["messages"]
        last = msgs[-1]["content"] if msgs else None
        has_bp = (
            isinstance(last, list)
            and last
            and isinstance(last[-1], dict)
            and "cache_control" in last[-1]
        )
        self._calls.append({"system_cached": "cache_control" in kwargs["system"][0], "last_turn_cached": has_bp})
        return self._responses.pop(0)


class _FakeClient:
    def __init__(self, responses, calls):
        self.messages = _FakeMessages(responses, calls)


class _RaisingSandbox:
    elapsed_seconds = 0.0

    def exec(self, *a, **k):
        raise RuntimeError("no sandbox in this test")


class _ComputeSandbox:
    """A sandbox whose clock alone can blow the per-instance ceiling."""

    elapsed_seconds = 10_000.0

    def exec(self, *a, **k):
        raise RuntimeError("no sandbox in this test")


@pytest.fixture
def patched(monkeypatch):
    calls: list[dict] = []
    responses: list = []

    def install(resp):
        responses.extend(resp)
        monkeypatch.setattr(
            agent.anthropic, "Anthropic", lambda **kw: _FakeClient(responses, calls)
        )
        return calls

    return install


def _config():
    return RunConfig(anthropic_api_key="k", model="haiku", max_steps=10)


def test_instance_budget_stops_this_instance_cleanly(patched, tmp_path):
    # One pricey turn ($5 output) blows a $1 instance cap; global ($100) is safe.
    patched([_tool_use_turn(output_tokens=1_000_000)])
    budget = BudgetTracker(instance_cap_usd=1.0, global_cap_usd=100.0)
    traj = TrajectoryLog(tmp_path / "t.jsonl")
    result = agent.run_loop(_config(), _RaisingSandbox(), "bug", traj, budget)
    assert result.stop_reason == "stopped:instance_budget"
    assert budget.instance_exceeded()
    assert "stopped:instance_budget" in (tmp_path / "t.jsonl").read_text()


def test_global_budget_fires_kill_switch(patched, tmp_path):
    patched([_tool_use_turn(output_tokens=1_000_000)])  # $5 > $2 global cap
    budget = BudgetTracker(instance_cap_usd=100.0, global_cap_usd=2.0)
    traj = TrajectoryLog(tmp_path / "t.jsonl")
    with pytest.raises(BudgetExceeded):
        agent.run_loop(_config(), _RaisingSandbox(), "bug", traj, budget)
    assert "stopped:global_budget" in (tmp_path / "t.jsonl").read_text()


def test_cache_breakpoint_rides_the_tool_result_turn(patched, tmp_path):
    # Turn 1 calls a tool (cheap); turn 2 ends. By turn 2 the tool-result turn
    # should carry the rolling cache breakpoint.
    calls = patched([_tool_use_turn(output_tokens=1), _end_turn()])
    budget = BudgetTracker(instance_cap_usd=100.0, global_cap_usd=100.0)
    traj = TrajectoryLog(tmp_path / "t.jsonl")
    result = agent.run_loop(_config(), _RaisingSandbox(), "bug", traj, budget)
    assert result.stop_reason == "completed"
    assert all(c["system_cached"] for c in calls)
    # First call's only turn is the plain-string user prompt (no block to mark);
    # second call sends the tool-result turn, which must be marked.
    assert calls[0]["last_turn_cached"] is False
    assert calls[1]["last_turn_cached"] is True


def test_modal_compute_alone_trips_the_instance_ceiling(patched, tmp_path):
    # Tokens are trivial here; the sandbox clock (10_000s x $0.0001 = $1.00) is
    # what blows the $1 instance cap — proving the ceiling covers compute too.
    patched([_tool_use_turn(output_tokens=1)])
    budget = BudgetTracker(instance_cap_usd=1.0, global_cap_usd=100.0)
    traj = TrajectoryLog(tmp_path / "t.jsonl")
    result = agent.run_loop(_config(), _ComputeSandbox(), "bug", traj, budget)
    assert result.stop_reason == "stopped:instance_budget"


def test_runs_without_a_budget(patched, tmp_path):
    # Budget is optional: the loop still completes when none is passed.
    patched([_end_turn()])
    traj = TrajectoryLog(tmp_path / "t.jsonl")
    result = agent.run_loop(_config(), _RaisingSandbox(), "bug", traj)
    assert result.stop_reason == "completed"
