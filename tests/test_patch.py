"""Offline unit tests for the patch splitting / test-stripping logic."""

from patchpilot.patch import (
    _is_test_path,
    build_prediction,
    split_diff_by_file,
    strip_test_changes,
)

SRC_SECTION = """diff --git a/src/pkg/core.py b/src/pkg/core.py
index 1111111..2222222 100644
--- a/src/pkg/core.py
+++ b/src/pkg/core.py
@@ -10,3 +10,3 @@ def f(x):
-    return x + 1
+    return x - 1
"""

TEST_SECTION = """diff --git a/tests/test_core.py b/tests/test_core.py
new file mode 100644
index 0000000..3333333
--- /dev/null
+++ b/tests/test_core.py
@@ -0,0 +1,3 @@
+def test_repro():
+    from src.pkg.core import f
+    assert f(1) == 0
"""


def test_is_test_path():
    assert _is_test_path("tests/test_core.py")
    assert _is_test_path("pkg/tests/helpers.py")
    assert _is_test_path("pkg/foo_test.py")
    assert _is_test_path("conftest.py")
    assert not _is_test_path("src/pkg/core.py")
    # A source file named 'testutils' living outside a tests dir is not a test.
    assert not _is_test_path("src/pkg/testutils.py")


def test_is_test_path_singular_test_dirs_are_source():
    # Singular 'test' / 'testing' dirs are commonly source packages and must
    # NOT be stripped (regression guard for the over-stripping bug).
    assert not _is_test_path("django/test/client.py")
    assert not _is_test_path("numpy/testing/_private/utils.py")
    # But the plural 'tests' dir still counts as tests.
    assert _is_test_path("django/tests/foo.py")


def test_split_diff_by_file():
    sections = split_diff_by_file(SRC_SECTION + TEST_SECTION)
    paths = [p for p, _ in sections]
    assert paths == ["src/pkg/core.py", "tests/test_core.py"]


def test_strip_test_changes_drops_only_tests():
    stripped = strip_test_changes(SRC_SECTION + TEST_SECTION)
    assert "src/pkg/core.py" in stripped
    assert "tests/test_core.py" not in stripped
    assert "return x - 1" in stripped


def test_strip_test_changes_keeps_pure_source():
    stripped = strip_test_changes(SRC_SECTION)
    assert stripped.strip() == SRC_SECTION.strip()


def test_strip_all_when_only_test():
    assert strip_test_changes(TEST_SECTION).strip() == ""


def test_build_prediction_schema():
    pred = build_prediction("repo__x-1", "claude-haiku", "PATCH")
    assert pred == {
        "instance_id": "repo__x-1",
        "model_name_or_path": "claude-haiku",
        "model_patch": "PATCH",
    }
