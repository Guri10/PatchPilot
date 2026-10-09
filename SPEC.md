# PatchPilot — Spec (source of truth)

_Reconciled 2026-09-10 from `CONTEXT.md`, `research.md`, the ADRs in `docs/adr/`, and a grilling
session. Where this file and older notes disagree, **this file wins.** `CONTEXT.md` (domain glossary)
and the ADRs (rationale for individual decisions) are kept consistent with it._

## Goal
A Python **bug-fixing agent**: given a real repo + an issue, it locates the bug, edits the code, and
produces a patch. **Goal is portfolio** (learning rides along); the artifacts are a strong **resolved
rate** plus the **issue-guided vs test-guided ablation** writeup, demoed as a real GitHub PR.

## Benchmark & scoring
- **SWE-bench Lite** (300 real bug-fix tasks, 11 Python repos). Resolved rate = headline metric,
  reported from the **issue-guided** arm.
- **Scoring in-sandbox with the official `swebench` harness — see ADR-0005.** After the loop we apply
  the instance's `test_patch` + judgment tests on top of the agent's patch and run them **inside the
  same Modal instance image the agent worked in**, parsing the result with the `swebench` library's own
  log-parser. Grading runs in the official image → zero env drift (the concern behind the old
  "never scored locally" rule; that concern doesn't apply when the grader runs in that image).
- **Cloud sb-cli is not the grader right now.** Its key-generation endpoint has been down since
  2026-08-24 (`swe-bench/sb-cli#38`, unfixed as of 2026-09-11), so no key can be obtained. The
  `predictions.jsonl` we produce is exactly what sb-cli consumes, so cloud submission stays a one-line
  swap-in for when the outage clears. Do NOT use Modal's paid `--modal` scoring flag — that double-pays.

## Two eval arms — see ADR-0001
- **Issue-guided** (headline): agent sees only the issue text + repo; must infer, localize, fix. The
  judgment tests are kept strictly out of its context.
- **Test-guided** (diagnostic oracle upper bound): judgment tests revealed to the agent, gated behind
  an explicit flag. Never reported as the headline number.

## Architecture (reconciled)
| Piece | Decision | ADR |
|---|---|---|
| Agent loop | Hand-rolled loop over Anthropic's raw `messages.create` (no framework/SDK). Flat ReAct: send → read `tool_use` → dispatch → append `tool_result` → repeat. **Reproduce-first** as soft discipline (log which path each instance took). | 0003 |
| Code access | **Agentic on-demand search** (model calls grep/read to decide what to look at). No static retrieval, no whole-repo dumps. | 0003 |
| Action space | **Bash-only to bootstrap** (one exec tool) to reach a working loop fastest, then **graduate to the structured toolset**: `read_file` (line ranges), `grep` (`file:line`), `edit_file` (search/replace), `run_tests` (truncated output). | 0004 |
| Agent environment | Tools execute inside the **official SWE-bench instance image**, hosted on a **Modal Sandbox** (managed — not hand-rolled — so it fits "no bespoke sandboxing"). Same image sb-cli grades on → zero env drift. Mac only orchestrates. | 0002 |
| Models | **Haiku** for building/debugging the scaffold; **Sonnet** for iteration + the headline scoring runs. Opus not used. Behind one swappable interface. | — |
| Patch → score | After the loop, take the sandbox's `git diff`, **strip the agent's own reproduction test** (submit source changes only), assemble `predictions.jsonl`, then **grade in-sandbox** — apply the instance `test_patch` + judgment tests in the same image and parse with the `swebench` harness. `predictions.jsonl` stays the artifact cloud sb-cli would consume. | 0004, 0005 |
| Observability | Full per-instance **trajectory log** (every thought / command / output) on by default. | 0003 |
| Orchestration | One Modal sandbox per instance → loop → extract diff → tear down. **Bounded parallelism** (start sequential on the dev subset). **Resumable** by `instance_id`. **Cost-tracked** with a global hard-cap kill-switch. | 0004 |
| Demo | Open a fix PR (or post a patch) on a real GitHub repo via the **GitHub MCP**. | — |

## Kinds of tests (from CONTEXT.md — kept)
- **Judgment tests**: `FAIL_TO_PASS` + `PASS_TO_PASS` baked into the instance; applied by the harness to
  score; never edited by the agent; hidden from it in the issue-guided arm.
- **Reproduction test**: agent-authored, to confirm it reproduced the bug and later that the fix closes
  it. Stripped from the submitted patch.
- **Regression tests**: the repo's existing suite (or a subset), run to avoid `PASS_TO_PASS` breakage.

## Stop conditions
Finalize when the reproduction test passes **and** the regression subset passes. Otherwise stop at a
hard max-iterations (~40 steps) or a per-instance cost cap.

## Workflow
Validate the full pipeline on **1–2 instances** → iterate on a **~20–30 case dev subset** →
**full 300-instance run** only at milestones (cost-estimate each full run first).

## Budget & guardrails
- **$40 / month, hard total cap $150.** Model tokens dominate spend; Modal compute is small/metered
  (scale-to-zero, ~$30 free credit likely covers the build phase).
- Per-instance **step cap (~40)**, per-instance **cost ceiling** (tokens **and** Modal compute),
  and a **global run budget that halts the whole eval** if the cap is hit. All config values.
- Prompt-cache the repo/context to control token cost.
- Model pricing ref (per 1M in/out): Haiku 4.5 $1/$5 · Sonnet 5 $2/$10.

## External pieces to set up
- SWE-bench Lite dataset (HuggingFace, free).
- `swebench` library (in-sandbox grading; ADR-0005). No account needed.
- sb-cli account/key — **not required** while grading in-sandbox; currently unobtainable anyway
  (`swe-bench/sb-cli#38`). Only needed if/when we swap back to cloud submission.
- Modal account (agent sandboxes; $30 free credit).
- Anthropic API key (Haiku + Sonnet).
- GitHub MCP (already available in this environment) for the PR demo.

## Explicitly out of scope (from research.md — kept)
Non-Python code · bug *detection* as a standalone product · **hand-rolled** execution sandboxing
(managed Modal sandbox is fine) · test-generation / style / security / coverage review.

## Not yet decided (next session — when we build)
- Repo scaffold layout and module boundaries.
- Exact agent system prompt.
- Trajectory log format.
- Config schema for the guardrails.
- Modal sandbox lifecycle details (image pull/caching, parallelism level).

## Changed vs. today's opening ask
Session opened aiming at SWE-bench **Verified**; reconciled to **Lite** to match the existing project.
Swap is a one-line dataset change if you revisit it.
