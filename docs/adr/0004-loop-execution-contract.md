# Loop execution contract: tools, stop conditions, patch, orchestration

How the loop actually runs, per instance and across the batch.

## Tools

**Bootstrap phase:** start with a single `bash` tool (a shell command run via the Modal-sandbox
`exec`) to reach a working end-to-end loop fastest. Once the loop is proven, **graduate** to the
structured tools below — each a thin wrapper over that same `exec`. The structured set is the target
because it solves problems bash-only hits: huge test output blowing context, and flaky edits.

- `read_file` — supports line ranges.
- `grep` — returns `file:line` matches.
- `edit_file` — **search/replace**: find an exact snippet, swap it. Token-cheap and robust; whole-file rewrites and line-range patches rejected.
- `run_tests` — takes test node-ids/paths, returns **truncated** output (head+tail). Test output can be huge and would otherwise blow context. In the issue-guided arm the test patch is absent from the container, so there is nothing to leak.

## Stop conditions

Finalize when the reproduction test passes *and* the regression subset passes. Otherwise stop at a hard max-iterations or a cost cap.

## Submitted patch

Strip the agent's own reproduction test from the final `git diff` and submit **source changes only**. The harness supplies its own judgment tests; a stray agent-authored test file risks breaking `PASS_TO_PASS`. This is why the reported patch will not contain the test the agent used to verify itself — deliberate, not an omission.

## Orchestration

One **Modal sandbox** per instance: create it from the instance image → loop → extract diff → tear down. **Bounded parallelism** (e.g. 4–8 workers; start sequential on the dev subset while debugging). **Resumable** by `instance_id` persisted to disk — reruns skip solved instances. **Cost-tracked** per instance (model tokens **and** Modal compute) with a global hard-cap kill-switch, given the $40/mo budget and $150 ceiling.
