"""Tests for the .env loader (patchpilot.env)."""

from __future__ import annotations

from patchpilot.env import find_dotenv, load_dotenv, parse_env


def test_parse_basic_pairs():
    assert parse_env("A=1\nB=two") == {"A": "1", "B": "two"}


def test_parse_skips_comments_and_blanks():
    assert parse_env("# comment\n\nA=1\n   \n# x\nB=2") == {"A": "1", "B": "2"}


def test_parse_strips_export_prefix():
    assert parse_env("export KEY=value") == {"KEY": "value"}


def test_parse_strips_surrounding_quotes():
    assert parse_env("A='v1'\nB=\"v2\"") == {"A": "v1", "B": "v2"}


def test_parse_keeps_equals_in_value():
    assert parse_env("URL=a=b=c") == {"URL": "a=b=c"}


def test_parse_skips_lines_without_key():
    assert parse_env("=novalue\nnoequals\nA=1") == {"A": "1"}


def test_load_dotenv_missing_file_is_noop(tmp_path):
    target: dict[str, str] = {}
    assert load_dotenv(tmp_path / "nope.env", environ=target) == {}
    assert target == {}


def test_load_dotenv_fills_env(tmp_path):
    f = tmp_path / ".env"
    f.write_text("ANTHROPIC_API_KEY=sk-test\nPATCHPILOT_STEP_CAP=7\n")
    target: dict[str, str] = {}
    applied = load_dotenv(f, environ=target)
    assert applied == {"ANTHROPIC_API_KEY": "sk-test", "PATCHPILOT_STEP_CAP": "7"}
    assert target["ANTHROPIC_API_KEY"] == "sk-test"


def test_load_dotenv_does_not_override_real_env(tmp_path):
    f = tmp_path / ".env"
    f.write_text("ANTHROPIC_API_KEY=from-file")
    target = {"ANTHROPIC_API_KEY": "from-shell"}
    applied = load_dotenv(f, environ=target)
    assert applied == {}  # nothing applied
    assert target["ANTHROPIC_API_KEY"] == "from-shell"


def test_load_dotenv_override_true(tmp_path):
    f = tmp_path / ".env"
    f.write_text("ANTHROPIC_API_KEY=from-file")
    target = {"ANTHROPIC_API_KEY": "from-shell"}
    load_dotenv(f, environ=target, override=True)
    assert target["ANTHROPIC_API_KEY"] == "from-file"


def test_find_dotenv_walks_up_to_repo_root(tmp_path):
    # Simulate a repo root holding .env with a worktree nested below it.
    (tmp_path / ".env").write_text("ANTHROPIC_API_KEY=root")
    worktree = tmp_path / ".claude" / "worktrees" / "feature"
    worktree.mkdir(parents=True)
    found = find_dotenv(start=worktree, stop=tmp_path)
    assert found == (tmp_path / ".env").resolve()


def test_find_dotenv_prefers_nearest(tmp_path):
    (tmp_path / ".env").write_text("X=root")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / ".env").write_text("X=sub")
    assert find_dotenv(start=sub, stop=tmp_path) == (sub / ".env").resolve()


def test_find_dotenv_returns_none_when_absent(tmp_path):
    sub = tmp_path / "a" / "b"
    sub.mkdir(parents=True)
    assert find_dotenv(start=sub, stop=tmp_path) is None
