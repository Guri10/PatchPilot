"""PatchPilot: a Python bug-fixing agent scored on SWE-bench Lite.

This package is the end-to-end spine for the issue-guided arm (see SPEC.md):
load one SWE-bench Lite instance, run a hand-rolled ReAct loop with a single
bash tool inside the official SWE-bench image on a Modal sandbox, extract the
diff (stripping the agent's reproduction test), and submit to sb-cli.
"""

__version__ = "0.1.0"
