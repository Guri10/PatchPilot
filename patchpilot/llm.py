"""Thin wrapper over Anthropic's raw ``messages.create`` (ADR-0003).

The loop talks to an ``LLMClient`` interface, not the SDK directly, so tests can
drive it with a scripted fake and no network. ``AnthropicClient`` is the real
implementation; the SDK is imported lazily.

Messages and content blocks are passed as plain dicts (the SDK accepts them),
keeping this layer free of SDK types.
"""

from __future__ import annotations

from typing import Any, Protocol

# Room for the model to think and act each turn; output stays small because
# tool results (not prose) carry the bulk of the information.
DEFAULT_MAX_TOKENS = 4096


class LLMResponse(Protocol):
    """The parts of an Anthropic response the loop reads."""

    @property
    def stop_reason(self) -> str | None: ...

    @property
    def content(self) -> list[Any]:
        """Content blocks, each with ``.type`` and type-specific fields."""
        ...


class LLMClient(Protocol):
    """What the loop needs from a model backend."""

    def create(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_tokens: int = ...,
    ) -> LLMResponse:
        ...


class AnthropicClient:
    """Real backend: Anthropic Messages API."""

    def __init__(self, api_key: str, model: str) -> None:
        import anthropic  # type: ignore[import-untyped]

        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def create(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> LLMResponse:
        return self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=system,
            tools=tools,
            messages=messages,
        )
