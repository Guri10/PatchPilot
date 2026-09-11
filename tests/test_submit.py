"""Tests for sb-cli command building and report parsing (patchpilot.submit)."""

from __future__ import annotations

from patchpilot.submit import build_submit_command, parse_resolved


def test_build_submit_command():
    cmd = build_submit_command(
        predictions_path="runs/x/predictions.jsonl",
        run_id="patchpilot-x",
        dataset="swe-bench_lite",
        split="test",
    )
    assert cmd[:4] == ["sb-cli", "submit", "swe-bench_lite", "test"]
    assert "--predictions_path" in cmd
    assert "runs/x/predictions.jsonl" in cmd
    assert "patchpilot-x" in cmd


def test_parse_resolved_id_list_form():
    report = {"resolved": ["a", "b"], "unresolved": ["c"]}
    assert parse_resolved(report, "a") is True
    assert parse_resolved(report, "c") is False
    assert parse_resolved(report, "z") is None


def test_parse_resolved_mapping_form():
    report = {"a": {"resolved": True}, "b": {"resolved": False}}
    assert parse_resolved(report, "a") is True
    assert parse_resolved(report, "b") is False
    assert parse_resolved(report, "z") is None
