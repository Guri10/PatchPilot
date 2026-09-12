"""Offline unit tests for output truncation."""

from patchpilot.tools import MAX_OUTPUT_CHARS, truncate


def test_short_output_unchanged():
    assert truncate("hello") == "hello"


def test_long_output_truncated_with_marker():
    big = "x" * (MAX_OUTPUT_CHARS + 500)
    out = truncate(big)
    assert len(out) < len(big)
    assert "truncated" in out
    # Head and tail are preserved.
    assert out.startswith("x")
    assert out.endswith("x")


def test_truncate_respects_custom_limit():
    out = truncate("abcdefghij", limit=4)
    assert "truncated" in out
    assert out.startswith("ab")
    assert out.endswith("ij")
