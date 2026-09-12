# PatchPilot

A Python bug-fixing agent scored on **SWE-bench Lite**. Given a real repo and an
issue, it locates the bug, edits the code, and produces a patch — measured by
resolved rate. See `SPEC.md` for the full design and `docs/adr/` for decisions.

This is the **issue-guided** arm (headline metric): the agent sees only the issue
text plus the repo. Judgment tests are kept out of its context.

## How it works (one instance, end to end)

1. Load one Lite instance from `SWE-bench/SWE-bench_Lite`.
2. Boot a **Modal sandbox** on the instance's **official SWE-bench image** — same
   image the harness grades on, so there is zero environment drift (ADR-0002).
3. Run a hand-rolled **ReAct loop** over Anthropic's raw `messages.create` with a
   single `bash` tool (ADR-0003, ADR-0004). A trajectory log is written per run.
4. Take the sandbox's `git diff`, **strip the agent's reproduction test**, and
   assemble `predictions.jsonl` (source changes only).
5. **Grade in-sandbox** with the official `swebench` harness — apply the judgment
   tests in the same image and parse the result. No cloud sb-cli key needed
   (ADR-0005; cloud sb-cli is down — `swe-bench/sb-cli#38`).

## Setup

```bash
python3.10 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Configure credentials:

- **Anthropic** — put `ANTHROPIC_API_KEY=...` in `.env`.
- **Modal** — `modal token new` (stores `~/.modal.toml`); ships ~$30 free credit.

## Run

```bash
# Full end-to-end on the default instance (pallets__flask-4045):
.venv/bin/python -m patchpilot.run

# A different instance / model / step cap:
.venv/bin/python -m patchpilot.run --instance-id psf__requests-2317 --max-steps 40

# Grader self-check: grade the gold patch (should always RESOLVE):
.venv/bin/python -m patchpilot.run --gold
```

Artifacts land in `runs/<instance_id>/`: `trajectory.jsonl`, `predictions.jsonl`,
`eval.log`.

## Tests

```bash
.venv/bin/python -m pytest tests/ -q
```

The offline suite covers the pure-Python seams (patch splitting / test-stripping,
output truncation, config). The Modal + Anthropic paths are validated by the
`--gold` grader self-check and a full run.
