"""Cost guardrails: model registry, token pricing, and the run budget (issue #3).

Three concerns live here, all pure so they can be unit-tested offline:

- **Model-swap** — :data:`MODELS` maps a friendly name (``"haiku"`` / ``"sonnet"``)
  to its API id and per-million-token prices. Switching models is picking a name;
  no call site hard-codes an id. :func:`resolve_model` also accepts a raw id so a
  new model can be used before it is listed here.
- **Cost** — :func:`token_cost` prices one API call's :class:`TokenUsage`,
  including the two prompt-cache token classes (cheaper reads, slightly dearer
  writes) so caching actually shows up as savings.
- **Budget** — :class:`BudgetTracker` accumulates spend and answers two questions:
  has *this instance* overspent (stop it cleanly), and has the *whole run*
  overspent (kill-switch — halt everything). It carries both model-token and
  Modal-compute cost, per SPEC ("tokens **and** Modal compute").

Prices are per 1M tokens (SPEC "Budget & guardrails"): Haiku 4.5 $1/$5,
Sonnet 5 $2/$10. Prompt-cache writes cost 1.25x base input and reads 0.1x, the
standard Anthropic multipliers.
"""

from __future__ import annotations

from dataclasses import dataclass

# Cache-token price multipliers relative to a model's base input price.
_CACHE_WRITE_MULT = 1.25
_CACHE_READ_MULT = 0.10


@dataclass(frozen=True)
class ModelSpec:
    """A model's API id and its per-million-token prices (USD)."""

    model_id: str
    input_per_mtok: float
    output_per_mtok: float

    @property
    def cache_write_per_mtok(self) -> float:
        return self.input_per_mtok * _CACHE_WRITE_MULT

    @property
    def cache_read_per_mtok(self) -> float:
        return self.input_per_mtok * _CACHE_READ_MULT


# Friendly name -> spec. Haiku builds/debugs the scaffold; Sonnet runs iteration
# and the headline scoring runs (SPEC "Models"). Opus is deliberately absent.
MODELS: dict[str, ModelSpec] = {
    "haiku": ModelSpec("claude-haiku-4-5-20251001", input_per_mtok=1.0, output_per_mtok=5.0),
    "sonnet": ModelSpec("claude-sonnet-5", input_per_mtok=2.0, output_per_mtok=10.0),
}


def resolve_model(name: str) -> tuple[str, ModelSpec]:
    """Resolve a friendly name or raw model id to ``(model_id, ModelSpec)``.

    A friendly name (case-insensitive) looks up :data:`MODELS`. Anything else is
    treated as a raw API id the caller wants to use directly; it is priced with
    the most expensive known model so an unlisted model can never make a run look
    cheaper than it is and slip past the budget caps.
    """
    spec = MODELS.get(name.lower())
    if spec is not None:
        return spec.model_id, spec
    dearest = max(MODELS.values(), key=lambda m: m.input_per_mtok)
    return name, ModelSpec(name, dearest.input_per_mtok, dearest.output_per_mtok)


@dataclass
class TokenUsage:
    """Token counts from one ``messages.create`` call.

    Field names are the budget's own vocabulary; :func:`from_response` maps the
    Anthropic SDK's ``usage`` object (whose cache fields may be absent on older
    responses) onto them.
    """

    input_tokens: int = 0
    output_tokens: int = 0
    cache_write_tokens: int = 0
    cache_read_tokens: int = 0

    @classmethod
    def from_response(cls, usage) -> "TokenUsage":
        """Build from an SDK ``response.usage``; missing fields count as zero."""
        return cls(
            input_tokens=getattr(usage, "input_tokens", 0) or 0,
            output_tokens=getattr(usage, "output_tokens", 0) or 0,
            cache_write_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
            cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
        )


def token_cost(spec: ModelSpec, usage: TokenUsage) -> float:
    """USD cost of one call's token usage under ``spec``'s prices."""
    return (
        usage.input_tokens * spec.input_per_mtok
        + usage.output_tokens * spec.output_per_mtok
        + usage.cache_write_tokens * spec.cache_write_per_mtok
        + usage.cache_read_tokens * spec.cache_read_per_mtok
    ) / 1_000_000


class BudgetExceeded(Exception):
    """Raised when the global run budget is hit — the kill-switch fired."""


class BudgetTracker:
    """Accumulates run spend and answers the two guardrail questions.

    One tracker lives for a whole run. :meth:`start_instance` zeroes the
    per-instance counter at each new instance while the global total keeps
    climbing, so the two caps are independent: an instance can be halted for
    overspending without ending the run, and the run can be halted no matter how
    the spend was spread across instances.
    """

    def __init__(self, instance_cap_usd: float, global_cap_usd: float):
        self.instance_cap_usd = instance_cap_usd
        self.global_cap_usd = global_cap_usd
        self._instance_cost = 0.0
        self._total_cost = 0.0
        # Sandbox-seconds already billed for the current instance, so compute can
        # be billed "through" a running total without double-charging.
        self._compute_seconds_billed = 0.0

    @property
    def instance_cost(self) -> float:
        return self._instance_cost

    @property
    def total_cost(self) -> float:
        return self._total_cost

    def _add(self, cost: float) -> float:
        self._instance_cost += cost
        self._total_cost += cost
        return cost

    def add_usage(self, spec: ModelSpec, usage: TokenUsage) -> float:
        """Price one API call and add it to both counters; return its cost."""
        return self._add(token_cost(spec, usage))

    def add_compute(self, total_seconds: float, rate_usd_per_sec: float) -> float:
        """Bill Modal compute *through* ``total_seconds`` of sandbox wall-clock.

        Takes the running elapsed time (not a delta) and charges only the part not
        yet billed, so it can be called every turn to keep the per-instance ceiling
        aware of compute — per SPEC, the ceiling covers tokens **and** Modal
        compute — and once more at teardown to catch the final seconds, without
        double-charging. Returns the cost added this call.
        """
        delta = total_seconds - self._compute_seconds_billed
        if delta <= 0:
            return 0.0
        self._compute_seconds_billed = total_seconds
        return self._add(delta * rate_usd_per_sec)

    def start_instance(self) -> None:
        """Begin a new instance: reset the per-instance counters only.

        The global total keeps climbing; the per-instance cost and the
        compute-billed watermark zero out because the next instance gets a fresh
        sandbox whose elapsed time restarts at zero.
        """
        self._instance_cost = 0.0
        self._compute_seconds_billed = 0.0

    def instance_exceeded(self) -> bool:
        return self._instance_cost >= self.instance_cap_usd

    def global_exceeded(self) -> bool:
        return self._total_cost >= self.global_cap_usd

    def raise_if_global_exceeded(self) -> None:
        """Fire the kill-switch if the whole-run budget is spent."""
        if self.global_exceeded():
            raise BudgetExceeded(
                f"global run budget exhausted: ${self._total_cost:.2f} "
                f">= ${self.global_cap_usd:.2f} cap"
            )


def set_cache_breakpoint(messages: list[dict]) -> None:
    """Keep exactly one rolling prompt-cache breakpoint at the end of ``messages``.

    Anthropic caches the message prefix up to a ``cache_control`` marker. The
    repo/context the agent reads (file contents, grep hits, test output) piles up
    in the conversation and is re-sent every turn; marking the last block of the
    latest turn means all of it before that point is served from cache on the next
    call instead of being re-charged at full input price.

    Only one breakpoint is kept (plus the static system-prompt one in the loop),
    so any marker from a previous turn is cleared first — otherwise breakpoints
    would accumulate past Anthropic's limit of four. A turn whose content is a
    plain string (the first user message) has no block to mark and is skipped.
    """
    for message in messages:
        content = message.get("content")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    block.pop("cache_control", None)
    if not messages:
        return
    last_content = messages[-1].get("content")
    if isinstance(last_content, list) and last_content:
        last_block = last_content[-1]
        if isinstance(last_block, dict):
            last_block["cache_control"] = {"type": "ephemeral"}
