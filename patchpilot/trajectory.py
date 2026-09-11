"""Per-instance trajectory log (ADR-0003: observability on by default).

Every run writes one JSONL file: the first line is a ``run`` header, then one
line per event (the model's text, each tool call, each tool result, and the
final stop reason). JSONL so it streams to disk as the loop runs and stays
greppable afterwards.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TrajectoryLog:
    """Append-only JSONL writer for one instance run."""

    def __init__(self, stream: TextIO) -> None:
        self._stream = stream

    @classmethod
    def open(cls, path: str | Path) -> "TrajectoryLog":
        """Open (creating parent dirs) a trajectory file for writing."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        return cls(p.open("w", encoding="utf-8"))

    def _write(self, event: dict[str, Any]) -> None:
        event.setdefault("ts", _now())
        self._stream.write(json.dumps(event, ensure_ascii=False) + "\n")
        self._stream.flush()

    def run_started(
        self, *, instance_id: str, model: str, arm: str, step_cap: int
    ) -> None:
        self._write(
            {
                "type": "run",
                "instance_id": instance_id,
                "model": model,
                "arm": arm,
                "step_cap": step_cap,
            }
        )

    def assistant_text(self, step: int, text: str) -> None:
        self._write({"type": "assistant_text", "step": step, "text": text})

    def tool_use(self, step: int, tool: str, tool_input: dict[str, Any]) -> None:
        self._write(
            {"type": "tool_use", "step": step, "tool": tool, "input": tool_input}
        )

    def tool_result(self, step: int, output: str) -> None:
        self._write({"type": "tool_result", "step": step, "output": output})

    def stopped(self, step: int, reason: str) -> None:
        self._write({"type": "stop", "step": step, "reason": reason})

    def patch_assembled(
        self, *, stripped_files: list[str], patch_empty: bool, predictions_path: str
    ) -> None:
        """Record the post-loop patch extraction (diff strip + predictions)."""
        self._write(
            {
                "type": "patch",
                "stripped_files": stripped_files,
                "patch_empty": patch_empty,
                "predictions_path": predictions_path,
            }
        )

    def close(self) -> None:
        self._stream.close()

    def __enter__(self) -> "TrajectoryLog":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
