"""Modal sandbox lifecycle for one instance (see ADR-0002).

One sandbox per instance: create it from the official SWE-bench image, exec
shell commands into it, read the repo's ``git diff`` at the end, tear it down.
The Mac only orchestrates; all tool execution happens in the cloud sandbox on
the same image sb-cli grades on, so there is zero env drift.

``Sandbox`` is the interface the loop and tools depend on; ``ModalSandbox`` is
the real implementation (Modal imported lazily so the package loads without it).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .dataset import TESTBED_PATH, instance_image_name

# A generous per-command ceiling; a single agent command should never run this
# long, and Modal bills scale-to-zero so an idle sandbox is cheap.
DEFAULT_COMMAND_TIMEOUT = 300
# Overall sandbox lifetime; the loop tears it down explicitly well before this.
DEFAULT_SANDBOX_TIMEOUT = 3600


@dataclass
class ExecResult:
    """Result of running one shell command in the sandbox."""

    exit_code: int
    stdout: str
    stderr: str

    @property
    def output(self) -> str:
        """Combined stdout+stderr, as the agent should see it."""
        if self.stderr and self.stdout:
            return f"{self.stdout}\n{self.stderr}"
        return self.stdout or self.stderr


class Sandbox(Protocol):
    """The execution surface the agent's tools run against."""

    def exec(self, command: str, *, timeout: int = ...) -> ExecResult:
        """Run a shell command and return its result."""
        ...

    def git_diff(self) -> str:
        """Return the working-tree diff of the repo (new files included)."""
        ...

    def teardown(self) -> None:
        """Terminate the sandbox and release its resources."""
        ...


class ModalSandbox:
    """A Modal Sandbox running one SWE-bench instance image.

    Use as a context manager so the sandbox is always torn down::

        with ModalSandbox.create(instance_id) as sb:
            sb.exec("pytest ...")
    """

    def __init__(self, modal_sandbox: object, *, workdir: str = TESTBED_PATH) -> None:
        self._sb = modal_sandbox
        self._workdir = workdir

    @classmethod
    def create(
        cls,
        instance_id: str,
        *,
        image_override: str | None = None,
        app_name: str = "patchpilot",
        sandbox_timeout: int = DEFAULT_SANDBOX_TIMEOUT,
    ) -> "ModalSandbox":
        """Create a sandbox from the instance's official SWE-bench image.

        Modal pulls and caches the image on first use; subsequent runs of the
        same instance reuse the cached layers.
        """
        import modal  # type: ignore[import-untyped]

        image_name = image_override or instance_image_name(instance_id)
        app = modal.App.lookup(app_name, create_if_missing=True)
        image = modal.Image.from_registry(image_name)
        sb = modal.Sandbox.create(
            "sleep",
            "infinity",
            image=image,
            app=app,
            timeout=sandbox_timeout,
        )
        return cls(sb)

    def exec(self, command: str, *, timeout: int = DEFAULT_COMMAND_TIMEOUT) -> ExecResult:
        proc = self._sb.exec(  # type: ignore[attr-defined]
            "bash",
            "-lc",
            f"cd {self._workdir} && {command}",
            timeout=timeout,
        )
        stdout = proc.stdout.read()
        stderr = proc.stderr.read()
        proc.wait()
        return ExecResult(
            exit_code=proc.returncode or 0,
            stdout=stdout,
            stderr=stderr,
        )

    def git_diff(self) -> str:
        # Stage everything (so newly-created files show up), then diff the index
        # against HEAD. HEAD is the instance's base commit, so this is exactly
        # the patch to submit.
        self.exec("git add -A")
        result = self.exec("git diff --cached")
        return result.stdout

    def teardown(self) -> None:
        try:
            self._sb.terminate()  # type: ignore[attr-defined]
        except Exception:
            # Teardown is best-effort; Modal reaps idle sandboxes anyway.
            pass

    def __enter__(self) -> "ModalSandbox":
        return self

    def __exit__(self, *exc: object) -> None:
        self.teardown()
