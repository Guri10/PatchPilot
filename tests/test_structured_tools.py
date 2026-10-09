"""Offline unit tests for the structured toolset's pure logic (issue #2).

The sandbox-facing wrappers (grep / run_tests / the exec+write_file plumbing of
read_file / edit_file) are exercised live; here we pin the two pieces of pure
logic that must be exactly right: the search/replace edit and the line-range
rendering with absolute line numbers.
"""

import pytest

from patchpilot.tools import apply_edit, render_file

FOUR_LINES = "alpha\nbravo\ncharlie\ndelta\n"


class TestApplyEdit:
    def test_unique_match_is_replaced(self):
        new, msg = apply_edit("a\nbravo\nc\n", "bravo", "BRAVO")
        assert new == "a\nBRAVO\nc\n"
        assert new is not None

    def test_multiline_snippet_replaced(self):
        content = "def f():\n    return 1\n\ndef g():\n    return 2\n"
        new, _ = apply_edit(content, "    return 1", "    return 10")
        assert new == "def f():\n    return 10\n\ndef g():\n    return 2\n"

    def test_not_found_is_rejected(self):
        new, msg = apply_edit("alpha\nbravo\n", "zulu", "x")
        assert new is None
        assert "not found" in msg.lower()

    def test_multiple_matches_rejected_with_count(self):
        new, msg = apply_edit("x\nx\nx\n", "x", "y")
        assert new is None
        # The message must tell the agent how many it found so it can
        # disambiguate with more surrounding context.
        assert "3" in msg

    def test_identical_old_and_new_rejected(self):
        new, msg = apply_edit("alpha\n", "alpha", "alpha")
        assert new is None
        assert "identical" in msg.lower()


class TestRenderFile:
    def test_absolute_line_numbers_for_a_range(self):
        out = render_file(FOUR_LINES, "f.py", 2, 3)
        # Lines 2 and 3 only, numbered with their real positions.
        assert "bravo" in out and "charlie" in out
        assert "alpha" not in out and "delta" not in out
        assert "2" in out and "3" in out

    def test_whole_file_when_range_omitted(self):
        out = render_file(FOUR_LINES, "f.py", None, None)
        for word in ("alpha", "bravo", "charlie", "delta"):
            assert word in out

    def test_header_names_the_path(self):
        out = render_file(FOUR_LINES, "src/pkg/core.py", 1, 1)
        assert "src/pkg/core.py" in out

    def test_start_beyond_eof_is_reported(self):
        out = render_file(FOUR_LINES, "f.py", 99, 100)
        assert "99" in out
        # No file content lines leak through.
        assert "alpha" not in out

    def test_end_clamped_to_last_line(self):
        out = render_file(FOUR_LINES, "f.py", 3, 999)
        assert "charlie" in out and "delta" in out
        assert "alpha" not in out

    def test_start_only_reads_to_end(self):
        out = render_file(FOUR_LINES, "f.py", 3, None)
        assert "charlie" in out and "delta" in out
        assert "alpha" not in out and "bravo" not in out

    def test_inverted_range_is_reported(self):
        out = render_file(FOUR_LINES, "f.py", 3, 2)
        assert "empty range" in out.lower()
        # No content lines leak through.
        for word in ("alpha", "bravo", "charlie", "delta"):
            assert word not in out
