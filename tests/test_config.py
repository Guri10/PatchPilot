"""Offline unit tests for RunConfig."""

from pathlib import Path

import pytest

from patchpilot import config as cfg
from patchpilot.config import RunConfig


def test_defaults():
    c = RunConfig(anthropic_api_key="k")
    assert c.instance_id == cfg.DEFAULT_INSTANCE_ID
    assert c.model == cfg.HAIKU
    assert c.max_steps == 40
    assert c.arm == "issue-guided"
    assert c.instance_budget_usd == cfg.DEFAULT_INSTANCE_BUDGET_USD
    assert c.global_budget_usd == cfg.DEFAULT_GLOBAL_BUDGET_USD


def test_run_dir_is_per_instance():
    c = RunConfig(anthropic_api_key="k", instance_id="repo__x-1")
    assert c.run_dir == Path("runs") / "repo__x-1"


def test_from_env_requires_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(cfg, "load_dotenv", lambda *a, **k: None)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        RunConfig.from_env()


def test_from_env_overrides(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret")
    monkeypatch.setattr(cfg, "load_dotenv", lambda *a, **k: None)
    c = RunConfig.from_env(instance_id="repo__y-2", max_steps=5)
    assert c.anthropic_api_key == "secret"
    assert c.instance_id == "repo__y-2"
    assert c.max_steps == 5


def test_model_swap_by_friendly_name(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret")
    monkeypatch.setattr(cfg, "load_dotenv", lambda *a, **k: None)
    # Switching to Sonnet is a single config value — no code edit.
    c = RunConfig.from_env(model="sonnet")
    assert c.model == cfg.SONNET
    assert c.model_spec.input_per_mtok == 2.0


def test_model_defaults_from_env_var(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret")
    monkeypatch.setenv("PATCHPILOT_MODEL", "sonnet")
    monkeypatch.setattr(cfg, "load_dotenv", lambda *a, **k: None)
    assert RunConfig.from_env().model == cfg.SONNET


def test_budget_knobs_from_env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret")
    monkeypatch.setenv("PATCHPILOT_INSTANCE_BUDGET", "2.5")
    monkeypatch.setenv("PATCHPILOT_GLOBAL_BUDGET", "40")
    monkeypatch.setattr(cfg, "load_dotenv", lambda *a, **k: None)
    c = RunConfig.from_env()
    assert c.instance_budget_usd == 2.5
    assert c.global_budget_usd == 40.0


def test_malformed_budget_env_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret")
    monkeypatch.setenv("PATCHPILOT_INSTANCE_BUDGET", "not-a-number")
    monkeypatch.setattr(cfg, "load_dotenv", lambda *a, **k: None)
    assert RunConfig.from_env().instance_budget_usd == cfg.DEFAULT_INSTANCE_BUDGET_USD
