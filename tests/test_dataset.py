"""Tests for instance image-name derivation (patchpilot.dataset)."""

from __future__ import annotations

from patchpilot.dataset import instance_image_name


def test_image_name_replaces_double_underscore():
    assert (
        instance_image_name("django__django-11099")
        == "swebench/sweb.eval.x86_64.django_1776_django-11099:latest"
    )


def test_image_name_lowercases():
    assert instance_image_name("PyCQA__flake8-1").startswith(
        "swebench/sweb.eval.x86_64.pycqa_1776_flake8-1"
    )
