"""Offline tests for the flag-gated test-guided (oracle) arm (issue #4).

These pin the three acceptance criteria:
  - flag off (default) behaves exactly like issue-guided — tests stay hidden;
  - flag on places the judgment tests in the agent's prompt;
  - a test-guided run is clearly labelled so its number can't be mistaken for
    the headline.
No network, Modal, or dataset download is touched.
"""

import json

import pytest

from patchpilot import config as cfg
from patchpilot.agent import build_user_prompt
from patchpilot.config import RunConfig
from patchpilot.dataset import judgment_tests_guidance

PROBLEM = "Flask app.run() ignores the PORT env var."

# A minimal instance row shaped like a SWE-bench Lite row, with the test fields
# in both forms the loader can hand back (list here; JSON-string case below).
INSTANCE = {
    "problem_statement": PROBLEM,
    "FAIL_TO_PASS": ["tests/test_cli.py::test_port_env"],
    "PASS_TO_PASS": ["tests/test_cli.py::test_host_default"],
    "test_patch": "diff --git a/tests/test_cli.py b/tests/test_cli.py\n+assert port == 8000\n",
}


# --- arm resolution (config) ------------------------------------------------


def test_default_arm_is_issue_guided_and_not_test_guided():
    c = RunConfig(anthropic_api_key="k")
    assert c.arm == "issue-guided"
    assert c.test_guided is False


def test_explicit_test_guided_arm():
    c = RunConfig(anthropic_api_key="k", arm="test-guided")
    assert c.test_guided is True


def test_unknown_arm_rejected():
    with pytest.raises(ValueError, match="unknown arm"):
        RunConfig(anthropic_api_key="k", arm="oracle")


def test_from_env_defaults_to_issue_guided(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret")
    monkeypatch.delenv("PATCHPILOT_ARM", raising=False)
    monkeypatch.setattr(cfg, "load_dotenv", lambda *a, **k: None)
    assert RunConfig.from_env().arm == "issue-guided"


def test_from_env_flag_turns_on_oracle(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret")
    monkeypatch.setattr(cfg, "load_dotenv", lambda *a, **k: None)
    assert RunConfig.from_env(test_guided=True).test_guided is True


def test_from_env_reads_arm_env_var(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret")
    monkeypatch.setenv("PATCHPILOT_ARM", "test-guided")
    monkeypatch.setattr(cfg, "load_dotenv", lambda *a, **k: None)
    assert RunConfig.from_env().test_guided is True


def test_cli_flag_wins_over_env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret")
    monkeypatch.setenv("PATCHPILOT_ARM", "test-guided")
    monkeypatch.setattr(cfg, "load_dotenv", lambda *a, **k: None)
    # An operator who passes --test-guided is honoured; the env can't force it
    # on or off against the explicit flag.
    assert RunConfig.from_env(test_guided=False).arm == "issue-guided"


def test_malformed_arm_env_rejected(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret")
    monkeypatch.setenv("PATCHPILOT_ARM", "bogus")
    monkeypatch.setattr(cfg, "load_dotenv", lambda *a, **k: None)
    with pytest.raises(ValueError, match="PATCHPILOT_ARM"):
        RunConfig.from_env()


# --- prompt construction ----------------------------------------------------


def test_prompt_without_guidance_hides_tests():
    prompt = build_user_prompt(PROBLEM)
    # The default-arm prompt is byte-identical to passing guidance=None, and
    # contains no judgment-test material at all.
    assert prompt == build_user_prompt(PROBLEM, None)
    assert "judgment_tests" not in prompt
    assert "test_patch" not in prompt


def test_prompt_with_guidance_includes_tests():
    guidance = judgment_tests_guidance(INSTANCE)
    prompt = build_user_prompt(PROBLEM, guidance)
    assert PROBLEM in prompt
    assert "tests/test_cli.py::test_port_env" in prompt
    assert "assert port == 8000" in prompt


# --- judgment guidance rendering --------------------------------------------


def test_guidance_lists_fail_and_pass_tests_and_patch():
    text = judgment_tests_guidance(INSTANCE)
    assert "tests/test_cli.py::test_port_env" in text
    assert "tests/test_cli.py::test_host_default" in text
    assert "assert port == 8000" in text


def test_guidance_accepts_json_string_fields():
    # Some dataset revisions hand the test lists back JSON-encoded.
    row = dict(INSTANCE)
    row["FAIL_TO_PASS"] = json.dumps(INSTANCE["FAIL_TO_PASS"])
    row["PASS_TO_PASS"] = json.dumps(INSTANCE["PASS_TO_PASS"])
    text = judgment_tests_guidance(row)
    assert "tests/test_cli.py::test_port_env" in text
    assert "tests/test_cli.py::test_host_default" in text


def test_guidance_accepts_python_repr_and_bare_string_fields():
    # A Python-repr list (single quotes) is not valid JSON; a bare node-id is
    # neither. Both must be handled without crashing the oracle run.
    row = dict(INSTANCE)
    row["FAIL_TO_PASS"] = "['tests/test_cli.py::test_port_env']"  # Python repr
    row["PASS_TO_PASS"] = "tests/test_cli.py::test_host_default"  # bare id
    text = judgment_tests_guidance(row)
    assert "tests/test_cli.py::test_port_env" in text
    assert "tests/test_cli.py::test_host_default" in text
