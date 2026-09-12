"""Per-instance trajectory log.

Writes one JSON object per line (JSONL) recording every step of the loop:
the model's thoughts, each bash command it runs, and the (truncated) output.
On by default per ADR-0003. The file is the audit trail for a run.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


class TrajectoryLog:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Truncate any previous run's log for this instance.
        self.path.write_text("", encoding="utf-8")

    def log(self, event: str, **data: Any) -> None:
        record = {"ts": round(time.time(), 3), "event": event, **data}
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    # Convenience wrappers for the event types the loop emits.
    def thought(self, text: str) -> None:
        self.log("thought", text=text)

    def command(self, step: int, command: str) -> None:
        self.log("command", step=step, command=command)

    def output(self, step: int, exit_code: int, output: str) -> None:
        self.log("output", step=step, exit_code=exit_code, output=output)

    def stop(self, reason: str, steps: int) -> None:
        self.log("stop", reason=reason, steps=steps)

    def score(self, resolved: bool, report: dict[str, Any]) -> None:
        self.log("score", resolved=resolved, report=report)
