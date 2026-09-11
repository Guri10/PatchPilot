# Agent loop: raw Messages API with agentic search

The agent is a hand-rolled loop over Anthropic's raw `messages.create`: send messages, read `tool_use` blocks, dispatch to our own tools, append `tool_result`, repeat until a stop condition. No Agent SDK, no framework (LangGraph etc.), and no Tool Runner — Tool Runner is held in reserve only if the loop plumbing becomes a drag.

Code reaches context via **agentic on-demand search**: the model decides what to look at on demand — via bash `grep`/`cat` in the bootstrap phase, then via the `grep`/`read_file` tools once they graduate (ADR-0004). No static retrieval (BM25/embeddings) subsystem and no whole-repo dumps.

## Why

Tools must execute inside the SWE-bench container (ADR-0002), which forces us to replace any framework's built-in host-side tools anyway — erasing most of a framework's value while keeping its abstraction. The loop is really an ablation harness: per-step control over prompt-cache breakpoints (central to the $40/mo budget, cap $150), trajectory logging, custom stop conditions, and issue-guided vs test-guided gating all live in the loop body, which frameworks and Tool Runner own or hide. Agentic search matches the toolset, ties token cost to what is actually touched, and is what modern SWE agents do; static retrieval is a separate dated subsystem and whole-repo blows the budget. "You write it" is also the project's learning and portfolio goal.

## Consequences

- We hand-roll context management if trajectories grow long; agentic search + prompt caching + a bounded iteration budget is expected to keep it small, with simple trimming as the fallback.
- Debugging stays within our own ~200-line loop rather than a framework's internals.
