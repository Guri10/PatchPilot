"""Minimal ``.env`` loader (no third-party dependency).

Lets each project keep its own ``ANTHROPIC_API_KEY`` (and other config) in a
gitignored ``.env`` file instead of a global shell export. Kept dependency-free
so ``patchpilot`` still imports and tests still run without anything installed.

Convention (matching python-dotenv's default): a real environment variable
always wins — ``.env`` only fills in what is not already set. A missing file is
a silent no-op.
"""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_ENV_FILE = ".env"


def parse_env(text: str) -> dict[str, str]:
    """Parse ``.env`` text into a dict.

    Supports ``KEY=value``, a leading ``export``, ``#`` comment lines, blank
    lines, and surrounding single/double quotes on the value. Lines without an
    ``=`` or with an empty key are skipped.
    """
    result: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        key, sep, value = line.partition("=")
        key = key.strip()
        if not sep or not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        result[key] = value
    return result


def load_dotenv(
    path: str | os.PathLike[str] = DEFAULT_ENV_FILE,
    *,
    environ: dict[str, str] | None = None,
    override: bool = False,
) -> dict[str, str]:
    """Load ``path`` into the environment and return the keys applied.

    By default existing variables are preserved (``override=False``). Missing
    file → returns ``{}`` and changes nothing. Pass ``environ`` to target a dict
    other than ``os.environ`` (used in tests).
    """
    target = environ if environ is not None else os.environ
    p = Path(path)
    if not p.is_file():
        return {}
    parsed = parse_env(p.read_text(encoding="utf-8"))
    applied: dict[str, str] = {}
    for key, value in parsed.items():
        if override or key not in target:
            target[key] = value
            applied[key] = value
    return applied
