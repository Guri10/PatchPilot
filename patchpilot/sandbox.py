"""Modal sandbox running the official SWE-bench instance image (ADR-0002).

The agent's tools are a thin ``exec`` layer into this sandbox; grading runs the
same way in a fresh sandbox from the same image. The Mac only orchestrates —
the repo, its dependencies, and the conda env all live in the image.
"""

from __future__ import annotations

import base64
from types import TracebackType

import modal

APP_NAME = "patchpilot"
TESTBED = "/testbed"


class InstanceSandbox:
    """A single Modal sandbox booted from a SWE-bench instance image.

    Use as a context manager so the sandbox is always torn down::

        with InstanceSandbox(spec.image) as sb:
            code, out = sb.exec("pytest -q")
    """

    def __init__(self, image_tag: str, timeout: int = 1800):
        self.image_tag = image_tag
        self.timeout = timeout
        self._sandbox: modal.Sandbox | None = None

    def start(self) -> "InstanceSandbox":
        app = modal.App.lookup(APP_NAME, create_if_missing=True)
        image = modal.Image.from_registry(self.image_tag)
        self._sandbox = modal.Sandbox.create(
            app=app, image=image, timeout=self.timeout, workdir=TESTBED
        )
        return self

    def exec(
        self, command: str, workdir: str = TESTBED, timeout: int | None = None
    ) -> tuple[int, str]:
        """Run ``command`` in a login shell; return (exit_code, combined output).

        stderr is merged into stdout at the shell level (``2>&1`` around the
        command) so everything lands on one captured pipe, in the order the
        shell produced it. This matters two ways: SWE-bench's eval script emits
        its ``>>>>> Start/End Test Output`` markers via ``set -x`` tracing (which
        goes to stderr) — the log parser needs them alongside the test results —
        and reading a single stream avoids the deadlock of draining two PIPE
        streams sequentially when a process fills the unread one's buffer.
        """
        if self._sandbox is None:
            raise RuntimeError("sandbox not started")
        # Subshell keeps the redirect self-contained regardless of what the
        # command does internally (its own set -x, pipes, heredocs).
        wrapped = f"( {command}\n) 2>&1"
        proc = self._sandbox.exec("bash", "-lc", wrapped, workdir=workdir, timeout=timeout)
        out = proc.stdout.read()
        code = proc.wait()
        return code, out

    def write_file(self, path: str, content: str) -> None:
        """Write ``content`` to ``path`` in the sandbox, base64-safe.

        The encoded blob is passed as one shell argument. Fine for the small
        files we write (patches, eval scripts — a few KB); a file large enough
        to approach ARG_MAX would need piping via stdin instead. Not a concern
        for SWE-bench Lite instances.
        """
        encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
        code, out = self.exec(
            f"echo {encoded} | base64 -d > {path}", workdir="/"
        )
        if code != 0:
            raise RuntimeError(f"write_file {path} failed ({code}): {out}")

    def terminate(self) -> None:
        if self._sandbox is not None:
            self._sandbox.terminate()
            self._sandbox = None

    def __enter__(self) -> "InstanceSandbox":
        return self.start()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.terminate()
