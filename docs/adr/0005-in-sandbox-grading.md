# Grade in-sandbox with the official harness, not the cloud sb-cli service

Scoring runs the official SWE-bench grading **inside the Modal sandbox** (the instance's own
image), not via the hosted cloud sb-cli service. After the loop we apply the instance's
`test_patch` (the judgment tests) on top of the agent's source-only patch, run its
`FAIL_TO_PASS` + `PASS_TO_PASS` tests, and parse the log with the `swebench` library's own
spec-builder and log-parser. Resolved = all `FAIL_TO_PASS` pass and all `PASS_TO_PASS` still pass.

**Revises SPEC.md's "Scoring via free cloud sb-cli … Never scored locally."** The prohibition on
"scored locally" was aimed at env drift — grading in a *different* environment than the loop ran in.
In-sandbox grading runs in the *same official image* the agent worked in, so that concern does not
apply here. See "Why".

## Why

The cloud sb-cli key-generation endpoint has been returning HTTP 500 since 2026-08-24
(`swe-bench/sb-cli#38`), with a second confirmed report and no maintainer fix or workaround as of
2026-09-11. A new API key cannot be obtained, so the hosted grading path is unavailable — the whole
pipeline would otherwise be blocked on an external outage outside our control.

The instance image already installs the repo and its dependencies (ADR-0002), and grading only needs
to add the judgment tests and run them. The `swebench` package generates the exact eval script
(environment activation → apply `test_patch` → run the named tests) and parses the result log, so we
reuse the official grading logic rather than hand-rolling it. Running that script via the sandbox's
`exec` layer means "passes at judgment" runs in the identical environment as "passes in the loop" —
the same zero-drift guarantee ADR-0002 secures, now covering scoring as well.

## Consequences

- No sb-cli account or API key is required to score a run.
- `predictions.jsonl` is still assembled exactly as before (source-only patch, reproduction test
  stripped; ADR-0004). It is the artifact the cloud service consumes, so nothing about the patch
  contract changes.
- The judgment tests (`test_patch`) are fetched from the SWE-bench Lite dataset row at grading time
  and applied only *after* the loop ends — the agent's context in the issue-guided arm never sees
  them, preserving ADR-0001.
- Grading depends on the `swebench` library's spec/log-parser API; pin its version so a log-format
  change upstream can't silently misgrade.
- The cloud sb-cli path stays a one-line swap-in: when `#38` is fixed, submitting the same
  `predictions.jsonl` via `sb-cli submit` is a drop-in alternative to the in-sandbox grader.
- Rejected: **wait for the outage to clear** — open ~2.5 weeks with no maintainer activity; open-ended.
- Rejected: **grade in a fresh local Docker container** — the arm64 + disk limits from ADR-0002 that
  ruled out local `docker run` for the loop apply equally to grading.
