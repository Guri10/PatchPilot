"""Tests for diff surgery and predictions assembly (patchpilot.patch)."""

from __future__ import annotations

import json

from patchpilot.patch import (
    build_prediction,
    is_test_path,
    split_diff_by_file,
    strip_test_files,
    write_predictions_jsonl,
)

SRC_SECTION = """diff --git a/src/pkg/calc.py b/src/pkg/calc.py
index 1111111..2222222 100644
--- a/src/pkg/calc.py
+++ b/src/pkg/calc.py
@@ -1,3 +1,3 @@
 def add(a, b):
-    return a - b
+    return a + b
"""

REPRO_SECTION = """diff --git a/tests/test_repro.py b/tests/test_repro.py
new file mode 100644
index 0000000..3333333
--- /dev/null
+++ b/tests/test_repro.py
@@ -0,0 +1,3 @@
+def test_repro():
+    from src.pkg.calc import add
+    assert add(1, 2) == 3
"""


def test_is_test_path_recognises_test_files():
    assert is_test_path("tests/test_repro.py")
    assert is_test_path("pkg/foo_test.py")
    assert is_test_path("a/b/tests/thing.py")
    assert is_test_path("conftest.py")


def test_is_test_path_rejects_source_files():
    assert not is_test_path("src/pkg/calc.py")
    assert not is_test_path("pkg/latest.py")  # 'test' only as a substring
    assert not is_test_path("README.md")


def test_is_test_path_keeps_singular_test_source_package():
    # Django ships real source under django/test/ — must NOT be stripped.
    assert not is_test_path("django/test/utils.py")
    assert not is_test_path("django/test/client.py")
    # ...but a test-named file inside it is still a test.
    assert is_test_path("django/test/test_utils.py")


def test_split_diff_by_file_separates_sections():
    sections = split_diff_by_file(SRC_SECTION + REPRO_SECTION)
    assert len(sections) == 2
    assert sections[0].path == "src/pkg/calc.py"
    assert sections[1].path == "tests/test_repro.py"
    # Round-trips exactly.
    assert sections[0].text + sections[1].text == SRC_SECTION + REPRO_SECTION


def test_strip_test_files_drops_repro_keeps_source():
    stripped = strip_test_files(SRC_SECTION + REPRO_SECTION)
    assert "src/pkg/calc.py" in stripped
    assert "test_repro.py" not in stripped
    assert stripped == SRC_SECTION


def test_strip_test_files_on_source_only_is_noop():
    assert strip_test_files(SRC_SECTION) == SRC_SECTION


def test_strip_test_files_empty_diff():
    assert strip_test_files("") == ""


def test_build_prediction_shape():
    pred = build_prediction("django__django-11099", "claude-sonnet-5", SRC_SECTION)
    assert pred == {
        "instance_id": "django__django-11099",
        "model_name_or_path": "claude-sonnet-5",
        "model_patch": SRC_SECTION,
    }


def test_write_predictions_jsonl(tmp_path):
    pred = build_prediction("inst-1", "m", SRC_SECTION)
    out = tmp_path / "predictions.jsonl"
    write_predictions_jsonl([pred], out)
    lines = out.read_text().strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0]) == pred
