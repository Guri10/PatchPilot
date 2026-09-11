# Agent tools execute inside the SWE-bench image, hosted on a Modal sandbox

The agent's tools execute against the repo *inside the SWE-bench instance's own image* — the same
environment sb-cli grades on — but that image runs on a **Modal Sandbox**, not a local Docker daemon.
Tools are an `exec` layer into the Modal sandbox. The prediction is the sandbox's `git diff` after the
loop (with the agent's reproduction test stripped; see ADR-0004).

During the bash-only bootstrap phase (ADR-0004) the single tool is a shell command run via that same
sandbox `exec`; the later structured tools (`read_file`, `grep`, `edit_file`, `run_tests`) are thin
wrappers over it.

## Why

The agent runs tests mid-loop (see ADR-0001), so it needs the repo with dependencies installed
somewhere. The instance image already solves per-repo environment setup, and reusing it means "passes
in the loop" and "passes at judgment" run in the identical environment — zero env drift.

Local Docker was the obvious host but is not viable here: the dev machine is arm64 with limited disk,
so the x86 official images would run under slow emulation and not fit. Modal runs the same images
natively in the cloud with scale-to-zero billing, removing the disk and architecture limits **without
building bespoke sandboxing** — Modal is a managed sandbox, which the project scope allows (only
hand-rolled sandboxing is out of scope).

## Consequences

- Tool implementations are thin wrappers over Modal-sandbox `exec`; a later decision.
- The per-instance lifecycle (create sandbox from the instance image, run the loop, extract the diff,
  tear down) must be managed, and orchestration across 300 instances must account for sandbox
  spin-up cost and parallelism — a later decision (see ADR-0004).
- Compute is now metered (small; ~$30 Modal free credit likely covers the build phase) and must be
  counted in the cost guardrails alongside model tokens.
- Rejected: **local `docker run` per instance** — blocked by arm64 emulation + disk limits.
- Rejected: **a host-side checkout with self-installed dependencies** — full control but re-solves
  environment setup SWE-bench already solved, and risks loop-env ≠ eval-env drift.
