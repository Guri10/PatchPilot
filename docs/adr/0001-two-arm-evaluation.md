# Two-arm evaluation: issue-guided headline, test-guided as a labeled oracle

PatchPilot's self-verification target is not a single choice — it is the experiment. We run two arms and the gap between them is the writeup's finding.

- **Issue-guided (headline).** The agent never sees the judgment tests. It self-verifies via a reproduction test it writes and a regression subset, following a reproduce-first discipline (preferred, not required). This is the realistic, leaderboard-legit resolved rate we report.
- **Test-guided (diagnostic).** The judgment tests are revealed to the agent, gated behind an explicit flag. Resolved rate here is higher but partly inflated — the agent can satisfy the exact assertions without truly fixing the bug. Reported only as a labeled oracle upper bound, never as the headline.

In both arms the harness's judgment tests are what score resolved / not resolved; the agent never edits them.

## Why

Revealing the judgment tests collapses localization, specification, and the fix into "make these assertions pass," and lets a patch score resolved without fixing the bug. SWE-bench's leaderboard rules forbid using the test patch as input for exactly this reason. Choosing one arm globally would either throw away the honest number or throw away the ablation; running both keeps the honest number and gets the ablation for free.

## Consequences

- The test patch must be kept strictly out of the agent's context in the issue-guided arm; the test-guided path is behind an explicit flag so leakage cannot happen by accident.
- The loop must log which path each instance took (reproduce-first vs. fix-directly) as data for the writeup.
