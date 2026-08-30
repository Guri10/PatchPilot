# PatchPilot — Project Scope

## What it is (one line)
A Python **bug-fixing agent**: given a real repo + an issue, it locates the bug, edits the code, and produces a patch — measured by **resolved rate on SWE-bench Lite** via the official harness.

## In scope (v1)
- **Agent**: manual agent loop (you write it), tools = `read_file`, `grep/structural search`, `edit_file`, `run_tests`
- **Execution**: delegated to the SWE-bench Docker harness — no bespoke sandboxing
- **Eval**: SWE-bench Lite; resolved rate as the metric; ~20–30 case dev subset, full 300 for milestones; Sonnet 5 for iteration, Opus 5 for headline
- **Detection**: folded into the loop, surfaced as a byproduct — not a separate product
- **Demo**: opens a fix PR (or posts a patch) on a real GitHub repo via the GitHub MCP
- **The writeup**: issue-vs-test-guided ablation — the portfolio centerpiece

## Explicitly out of scope
- Non-Python code
- Bug *detection* as a standalone product/mode
- Building your own execution/environment sandboxing
- Test-generation, style/security/coverage review

## Settled decisions
Goal (learn + portfolio) · 1 project not 2 · Python-only · GitHub PRs via MCP · manual loop · SWE-bench Lite + harness · resolved-rate scoring · fixer-with-detection-folded-in · timeline relaxed.

## Reference
- SWE-bench Lite — 300 real-world GitHub bug-fix tasks from 11 Python repos; each instance = repo snapshot at a commit + issue text + gold patch + curated tests. Official containerized harness builds the env, applies a patch, runs the tests, reports pass/fail.
- Model pricing (per 1M tokens): Haiku 4.5 \$1/\$5 · Sonnet 5 \$2/\$10 · Opus 5 \$5/\$25.
- Est. cost: ~\$50 budget, hard cap \$150 (prompt-cache the repo snapshot; Sonnet for iteration, Opus for final).
