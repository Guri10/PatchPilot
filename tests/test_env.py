"""Tests for the .env loader (patchpilot.env)."""

from __future__ import annotations

from patchpilot.env import load_dotenv, parse_env


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
