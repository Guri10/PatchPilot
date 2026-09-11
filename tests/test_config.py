"""Tests for RunConfig (patchpilot.config)."""

from __future__ import annotations

import pytest

from patchpilot.config import (
    ARM_ISSUE_GUIDED,
    DEFAULT_STEP_CAP,
    MODEL_SONNET,
    ConfigError,
    RunConfig,
)


def test_defaults():
    cfg = RunConfig(instance_id="inst-1", anthropic_api_key="key")
    assert cfg.model == MODEL_SONNET
    assert cfg.arm == ARM_ISSUE_GUIDED
    assert cfg.step_cap == DEFAULT_STEP_CAP
    assert cfg.run_dir.name == "inst-1"


def test_requires_instance_id():
    with pytest.raises(ConfigError):
        RunConfig(instance_id="", anthropic_api_key="key")


def test_requires_api_key():
    with pytest.raises(ConfigError):
        RunConfig(instance_id="inst-1", anthropic_api_key="")


def test_rejects_bad_arm():
    with pytest.raises(ConfigError):
        RunConfig(instance_id="i", anthropic_api_key="k", arm="oracle")


def test_rejects_zero_step_cap():
    with pytest.raises(ConfigError):
        RunConfig(instance_id="i", anthropic_api_key="k", step_cap=0)


def test_from_env_reads_key_and_overrides():
    env = {
        "ANTHROPIC_API_KEY": "envkey",
        "PATCHPILOT_STEP_CAP": "12",
        "PATCHPILOT_MODEL": "envmodel",
    }
    cfg = RunConfig.from_env("inst-1", env=env)
    assert cfg.anthropic_api_key == "envkey"
    assert cfg.step_cap == 12
    assert cfg.model == "envmodel"


def test_explicit_args_beat_env():
    env = {"ANTHROPIC_API_KEY": "envkey", "PATCHPILOT_STEP_CAP": "12"}
    cfg = RunConfig.from_env("inst-1", step_cap=5, env=env)
    assert cfg.step_cap == 5
