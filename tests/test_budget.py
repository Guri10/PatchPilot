"""Offline unit tests for the cost guardrails (issue #3).

The budget module is pure arithmetic + threshold logic: the model registry
(name -> id + pricing), the per-call token cost, and the tracker that decides
when a single instance or the whole run has spent too much. All offline — no
Anthropic client, no sandbox.
"""

import pytest

from patchpilot import budget as bud
from patchpilot.budget import (
    BudgetExceeded,
    BudgetTracker,
    TokenUsage,
    resolve_model,
    set_cache_breakpoint,
    token_cost,
)


class TestResolveModel:
    def test_friendly_haiku_and_sonnet(self):
        haiku_id, haiku = resolve_model("haiku")
        sonnet_id, sonnet = resolve_model("sonnet")
        assert "haiku" in haiku_id.lower()
        assert "sonnet" in sonnet_id.lower()
        # Sonnet costs more per token than Haiku (the whole point of the swap).
        assert sonnet.input_per_mtok > haiku.input_per_mtok

    def test_case_insensitive(self):
        assert resolve_model("HAIKU")[0] == resolve_model("haiku")[0]

    def test_raw_model_id_passes_through_as_unknown(self):
        # A raw id we don't know is still usable; pricing falls back to the
        # most expensive known model so cost is never silently under-counted.
        model_id, spec = resolve_model("claude-something-new-1")
        assert model_id == "claude-something-new-1"
        assert spec.input_per_mtok == max(
            m.input_per_mtok for m in bud.MODELS.values()
        )


class TestTokenCost:
    def test_plain_input_output(self):
        _, haiku = resolve_model("haiku")  # $1 / $5 per MTok
        usage = TokenUsage(input_tokens=1_000_000, output_tokens=1_000_000)
        assert token_cost(haiku, usage) == pytest.approx(6.0)

    def test_cache_write_and_read_priced(self):
        _, haiku = resolve_model("haiku")
        # 1M cache-write @ 1.25x input ($1.25) + 1M cache-read @ 0.1x ($0.10).
        usage = TokenUsage(cache_write_tokens=1_000_000, cache_read_tokens=1_000_000)
        assert token_cost(haiku, usage) == pytest.approx(1.35)

    def test_zero_usage_is_free(self):
        _, sonnet = resolve_model("sonnet")
        assert token_cost(sonnet, TokenUsage()) == 0.0


class TestBudgetTracker:
    def _tracker(self):
        return BudgetTracker(instance_cap_usd=1.0, global_cap_usd=5.0)

    def test_starts_empty(self):
        t = self._tracker()
        assert t.instance_cost == 0.0
        assert t.total_cost == 0.0
        assert not t.instance_exceeded()
        assert not t.global_exceeded()

    def test_add_usage_accumulates_both_counters(self):
        t = self._tracker()
        _, haiku = resolve_model("haiku")
        cost = t.add_usage(haiku, TokenUsage(output_tokens=100_000))  # $0.50
        assert cost == pytest.approx(0.5)
        assert t.instance_cost == pytest.approx(0.5)
        assert t.total_cost == pytest.approx(0.5)

    def test_instance_cap_tripped(self):
        t = self._tracker()
        _, haiku = resolve_model("haiku")
        t.add_usage(haiku, TokenUsage(output_tokens=300_000))  # $1.50 > $1.00
        assert t.instance_exceeded()
        assert not t.global_exceeded()

    def test_start_instance_resets_only_the_instance_counter(self):
        t = self._tracker()
        _, haiku = resolve_model("haiku")
        t.add_usage(haiku, TokenUsage(output_tokens=300_000))  # $1.50
        t.start_instance()
        assert t.instance_cost == 0.0
        assert t.total_cost == pytest.approx(1.5)  # global survives
        assert not t.instance_exceeded()

    def test_global_cap_spans_instances(self):
        t = self._tracker()
        _, haiku = resolve_model("haiku")
        for _ in range(4):
            t.add_usage(haiku, TokenUsage(output_tokens=300_000))  # $1.50 each
            t.start_instance()
        # 4 * $1.50 = $6.00 > $5.00 global, even though each instance reset.
        assert t.global_exceeded()

    def test_add_compute_counts_toward_budget(self):
        t = self._tracker()
        t.add_compute(10.0, rate_usd_per_sec=0.1)  # $1.00
        assert t.instance_cost == pytest.approx(1.0)
        assert t.total_cost == pytest.approx(1.0)

    def test_add_compute_bills_through_without_double_charging(self):
        t = self._tracker()
        # "through" semantics: pass the running elapsed total each time; only the
        # unbilled part is charged, so per-turn + teardown calls don't stack.
        t.add_compute(10.0, rate_usd_per_sec=0.1)  # bills 10s -> $1.00
        t.add_compute(10.0, rate_usd_per_sec=0.1)  # same total -> $0.00
        t.add_compute(12.0, rate_usd_per_sec=0.1)  # +2s -> $0.20
        assert t.instance_cost == pytest.approx(1.2)

    def test_start_instance_rebills_a_fresh_sandbox_clock(self):
        t = self._tracker()
        t.add_compute(10.0, rate_usd_per_sec=0.1)  # $1.00
        t.start_instance()  # next sandbox's elapsed restarts at 0
        t.add_compute(5.0, rate_usd_per_sec=0.1)  # bills the full 5s -> $0.50
        assert t.instance_cost == pytest.approx(0.5)
        assert t.total_cost == pytest.approx(1.5)

    def test_check_raises_only_when_global_exceeded(self):
        t = BudgetTracker(instance_cap_usd=1.0, global_cap_usd=5.0)
        _, haiku = resolve_model("haiku")
        t.add_usage(haiku, TokenUsage(output_tokens=300_000))  # $1.50
        # Instance over, global under: no raise (loop stops cleanly instead).
        t.raise_if_global_exceeded()
        t.add_usage(haiku, TokenUsage(output_tokens=1_000_000))  # +$5.00 -> $6.50
        with pytest.raises(BudgetExceeded):
            t.raise_if_global_exceeded()


class TestCacheBreakpoint:
    def _msgs(self):
        return [
            {"role": "user", "content": [{"type": "text", "text": "a"}]},
            {
                "role": "assistant",
                "content": [{"type": "text", "text": "b"}],
            },
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "1", "content": "x"},
                    {"type": "tool_result", "tool_use_id": "2", "content": "y"},
                ],
            },
        ]

    def test_breakpoint_on_last_block_of_last_message(self):
        msgs = self._msgs()
        set_cache_breakpoint(msgs)
        last_block = msgs[-1]["content"][-1]
        assert last_block["cache_control"] == {"type": "ephemeral"}
        # The earlier block in the same turn is not a breakpoint.
        assert "cache_control" not in msgs[-1]["content"][0]

    def test_only_one_rolling_breakpoint(self):
        msgs = self._msgs()
        set_cache_breakpoint(msgs)
        # Simulate a later turn: append a new user message and re-mark.
        msgs.append(
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "3", "content": "z"}]}
        )
        set_cache_breakpoint(msgs)
        marked = [
            b
            for m in msgs
            for b in m["content"]
            if isinstance(b, dict) and "cache_control" in b
        ]
        assert len(marked) == 1
        assert msgs[-1]["content"][-1]["cache_control"] == {"type": "ephemeral"}

    def test_empty_messages_is_a_noop(self):
        set_cache_breakpoint([])  # must not raise

    def test_string_content_message_is_skipped(self):
        # The very first user turn uses a plain string, not a block list.
        msgs = [{"role": "user", "content": "hello"}]
        set_cache_breakpoint(msgs)
        assert msgs[0]["content"] == "hello"
