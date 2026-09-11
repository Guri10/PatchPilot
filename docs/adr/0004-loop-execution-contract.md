# Loop execution contract: tools, stop conditions, patch, orchestration

How the loop actually runs, per instance and across the batch.

## Tools

- `read_file` — supports line ranges.
- `grep` — returns `file:line` matches.
- `edit_file` — **search/replace**: find an exact snippet, swap it. Token-cheap and robust; whole-file rewrites and line-range patches rejected.
- `run_tests` — takes test node-ids/paths, returns **truncated** output (head+tail). Test output can be huge and would otherwise blow context. In the issue-guided arm the test patch is absent from the container, so there is nothing to leak.

## Stop conditions

Finalize when the reproduction test passes *and* the regression subset passes. Otherwise stop at a hard max-iterations or a cost cap.

## Submitted patch

Strip the agent's own reproduction test from the final `git diff` and submit **source changes only**. The harness supplies its own judgment tests; a stray agent-authored test file risks breaking `PASS_TO_PASS`. This is why the reported patch will not contain the test the agent used to verify itself — deliberate, not an omission.

## Orchestration

One container per instance: `docker run` the image → loop → extract diff → tear down. **Bounded parallelism** (e.g. 4–8 workers; start sequential on the dev subset while debugging). **Resumable** by `instance_id` persisted to disk — reruns skip solved instances. **Cost-tracked** per instance with a global hard-cap kill-switch, given the $150 ceiling.
