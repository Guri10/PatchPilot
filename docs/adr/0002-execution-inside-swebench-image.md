# Agent tools execute inside the SWE-bench instance image

The agent's tools (`read_file`, `grep`, `edit_file`, `run_tests`) execute against the repo *inside the SWE-bench instance's own Docker image* — the same container the harness builds for evaluation. Tools are a `docker exec` layer into that container. The prediction is the container's `git diff` after the loop.

## Why

The agent runs tests mid-loop (see ADR-0001), so it needs the repo with dependencies installed somewhere. The instance image already solves per-repo environment setup. Reusing it means "passes in the loop" and "passes at judgment" run in the identical environment — zero env drift — and avoids building bespoke sandboxing, which the project scope explicitly rules out. Patch extraction becomes a clean `git diff`.

## Consequences

- Tool implementations are thin wrappers over `docker exec`; a later decision.
- The loop's per-instance lifecycle (start container, run, extract diff, tear down) must be managed, and orchestration across 300 instances must account for container spin-up cost and parallelism — a later decision.
- Rejected: a host-side checkout with self-installed dependencies — full control but re-solves environment setup SWE-bench already solved, and risks loop-env ≠ eval-env drift.
