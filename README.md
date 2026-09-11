# PatchPilot

A Python bug-fixing agent scored on SWE-bench Lite via the official cloud
harness. See `SPEC.md` for the full design and `docs/adr/` for the decisions.

This is the **end-to-end spine** for the issue-guided arm (issue #1): point it at
one SWE-bench Lite `instance_id` and get a scored result — load the instance,
run a hand-rolled ReAct loop with a single `bash` tool inside the official
SWE-bench image on a Modal sandbox, extract the diff (stripping the agent's own
reproduction test), and submit to sb-cli.

## Layout

```
patchpilot/
  config.py       RunConfig: env + defaults (step cap, model, arm)
  dataset.py      load one SWE-bench Lite instance; derive its image name
  sandbox.py      Modal sandbox lifecycle (create / exec / git_diff / teardown)
  llm.py          thin Anthropic messages.create wrapper (behind an interface)
  tools.py        the single bash tool (schema, dispatch, output truncation)
  agent.py        the ReAct loop
  patch.py        strip the reproduction test; assemble predictions.jsonl
  submit.py       sb-cli submission + report parsing
  trajectory.py   per-instance JSONL trajectory log
  run.py          orchestrate one instance end to end
  __main__.py     CLI
tests/            unit + integration tests (run offline with fakes)
```

## Install

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Run

Prerequisites (see SPEC.md → "External pieces to set up"):

- `ANTHROPIC_API_KEY` — see "Configuration" below.
- A Modal account, authenticated (`modal token new`).
- For `--submit`: an sb-cli key. Generate with `sb-cli gen-api-key <email>`,
  then set `SWEBENCH_API_KEY` (in your `.env` works — it reaches sb-cli).

```bash
python -m patchpilot --instance-id django__django-11099 --submit
```

### Configuration

Config comes from (in precedence order) CLI flags → environment variables →
a per-project `.env` file → defaults. Recognised variables: `ANTHROPIC_API_KEY`
(required), `PATCHPILOT_MODEL`, `PATCHPILOT_STEP_CAP`, `PATCHPILOT_RUNS_DIR`.

For a project-local key, copy the template and fill it in:

```bash
cp .env.example .env      # .env is gitignored — never commit real keys
```

The CLI finds `.env` by searching **up** from the current directory (override
with `--env-file`). Put one `.env` at the repo root and every git worktree under
it (`.claude/worktrees/<name>/`) picks it up automatically — no need to copy it
into each worktree. A real exported environment variable always wins over `.env`,
so a global `export ANTHROPIC_API_KEY=...` still works and takes precedence.

Outputs land in `runs/<instance_id>/`:

- `trajectory.jsonl` — every thought / command / output (one JSON event per line).
- `predictions.jsonl` — the submitted patch (source changes only).

Useful flags: `--model`, `--step-cap` (default 40), `--runs-dir`, `--image`
(override the derived SWE-bench image).

## Test & typecheck

```bash
pytest        # runs offline; no API keys or network needed
mypy
```

## Notes / assumptions to verify against live services

- **Image name** (`dataset.instance_image_name`): `swebench/sweb.eval.x86_64.<id>`
  with `__` → `_1776_`, lowercased. Override with `--image` if a registry tag
  differs.
- **sb-cli report shape** (`submit.parse_resolved`): assumed a `resolved`/
  `unresolved` id split (or a per-id mapping). The submit command and auth are
  verified against sb-cli 0.1.x (`submit` waits and writes a report into
  `--output_dir`, which we point at the run dir); the report's exact JSON keys
  are confirmed on the first live run — adjust that one function if they differ.
- The **test-guided arm is intentionally gated off** in this spine (raises in
  `agent.run_loop`); it is a later, flag-gated addition.
