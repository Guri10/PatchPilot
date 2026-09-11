# PatchPilot — Project Scope

> Decisions of record live in **`SPEC.md`** (source of truth) and `docs/adr/`. This file is the
> scope & rationale narrative, kept consistent with them.

## What it is (one line)
A Python **bug-fixing agent**: given a real repo + an issue, it locates the bug, edits the code, and
produces a patch — measured by **resolved rate on SWE-bench Lite** via the official harness.

## In scope (v1)
- **Agent**: hand-rolled agent loop (you write it). **Bash-only to bootstrap**, then graduate to the
  structured tools `read_file`, `grep`/structural search, `edit_file`, `run_tests` (see ADR-0004).
- **Execution**: tools run inside the **official SWE-bench instance image on a Modal Sandbox** — a
  *managed* sandbox, not hand-rolled (see ADR-0002). Chosen over local Docker because the dev machine
  is arm64 with limited disk.
- **Scoring**: delegated to the **free cloud sb-cli** (SWE-bench's hosted, Modal-backed official
  harness). Same image the agent iterates on → zero env drift.
- **Eval**: SWE-bench Lite; resolved rate as the metric; ~20–30 case dev subset, full 300 for
  milestones; **Haiku** for scaffold build/debug, **Sonnet** for iteration + headline.
- **Detection**: folded into the loop, surfaced as a byproduct — not a separate product.
- **Demo**: opens a fix PR (or posts a patch) on a real GitHub repo via the GitHub MCP.
- **The writeup**: issue-vs-test-guided ablation — the portfolio centerpiece.

## Explicitly out of scope
- Non-Python code
- Bug *detection* as a standalone product/mode
- **Hand-rolled** execution/environment sandboxing (a managed Modal sandbox is fine)
- Test-generation, style/security/coverage review

## Settled decisions
Goal (learn + portfolio) · 1 project not 2 · Python-only · GitHub PRs via MCP · hand-rolled loop ·
bash-only bootstrap → structured tools · SWE-bench Lite · Modal-sandbox execution · sb-cli scoring ·
resolved-rate scoring · Haiku(dev)/Sonnet(headline) · fixer-with-detection-folded-in · timeline relaxed.

## Reference
- SWE-bench Lite — 300 real-world GitHub bug-fix tasks from 11 Python repos; each instance = repo
  snapshot at a commit + issue text + gold patch + curated tests. Official containerized harness builds
  the env, applies a patch, runs the tests, reports pass/fail. Scored remotely for free via sb-cli.
- Model pricing (per 1M tokens): Haiku 4.5 \$1/\$5 · Sonnet 5 \$2/\$10.
- Budget: **\$40/month, hard cap \$150** (prompt-cache the repo snapshot; Haiku to build, Sonnet for
  iteration + headline). Modal compute is small/metered with ~\$30 free credit.
