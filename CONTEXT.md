# PatchPilot

A Python bug-fixing agent: given a real repo and an issue, it locates the bug, edits the code, and produces a patch — measured by resolved rate on SWE-bench Lite via the official harness.

## Language

### Evaluation arms

**Issue-guided**:
The agent sees only the issue text (plus the repo) and must infer, localize, and fix the bug. The realistic, leaderboard-legit setting and PatchPilot's **headline** number.
_Avoid_: issue-only, blind mode

**Test-guided**:
A diagnostic arm where the judgment tests are revealed to the agent as guidance. An oracle upper bound, never reported as the headline resolved rate. Gated behind an explicit flag so it can't happen by accident.
_Avoid_: oracle mode (as a synonym reported without the caveat), test-visible

### Kinds of tests

**Judgment tests**:
The `FAIL_TO_PASS` + `PASS_TO_PASS` tests baked into a SWE-bench instance's test patch. Applied by the harness after the agent's patch to score resolved / not resolved. Fixed, always score, never edited by the agent, and hidden from the agent in the issue-guided arm.
_Avoid_: gold tests, hidden tests, ground-truth tests

**Reproduction test**:
A test the agent writes itself from the issue text to confirm it has reproduced the bug and, later, that its fix closes it. Agent-authored — never the judgment tests.
_Avoid_: repro, failing test

**Regression tests**:
The repo's pre-existing suite (or a relevant subset) the agent runs to confirm it did not break unrelated behavior. The agent's own insurance against `PASS_TO_PASS` failures.
_Avoid_: existing tests, the test suite

### Workflow

**Reproduce-first**:
The preferred loop discipline in the issue-guided arm: write a failing reproduction test, then fix, then confirm it passes. Encouraged but not hard-required — the agent may fix directly when it cannot build a reproduction, and logs which path it took.
_Avoid_: TDD, test-first

**Resolved rate**:
The fraction of instances where, after applying the agent's patch, all judgment tests pass. PatchPilot's headline metric, reported from the issue-guided arm.
_Avoid_: pass rate, success rate, accuracy
