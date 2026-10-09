"""PatchPilot — a Python bug-fixing agent scored on SWE-bench Lite.

Issue-guided arm: the agent sees only the issue text + repo, works inside the
official SWE-bench instance image on a Modal sandbox, and is graded in-sandbox
with the official ``swebench`` harness (see docs/adr/0005-in-sandbox-grading.md).
"""

__all__ = ["__version__"]

__version__ = "0.1.0"
