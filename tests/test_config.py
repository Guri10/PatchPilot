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
