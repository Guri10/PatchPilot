"""Command-line entrypoint: run PatchPilot against one instance.

    python -m patchpilot --instance-id django__django-11099 --submit
"""

from __future__ import annotations

import argparse
import sys

from pathlib import Path

from .config import DEFAULT_STEP_CAP, ConfigError, RunConfig
from .env import DEFAULT_ENV_FILE, find_dotenv, load_dotenv


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="patchpilot",
        description="Run the PatchPilot issue-guided spine against one "
        "SWE-bench Lite instance.",
    )
    p.add_argument("--instance-id", required=True, help="SWE-bench Lite instance id")
    p.add_argument("--model", default=None, help="model id (default: Sonnet)")
    p.add_argument(
        "--step-cap",
        type=int,
        default=None,
        help=f"max agent steps (default: {DEFAULT_STEP_CAP})",
    )
    p.add_argument("--runs-dir", default=None, help="output dir (default: runs/)")
    p.add_argument(
        "--image",
        default=None,
        help="override the SWE-bench image (default: derived from instance id)",
    )
    p.add_argument(
        "--submit",
        action="store_true",
        help="submit predictions to sb-cli and print the score",
    )
    p.add_argument(
        "--env-file",
        default=DEFAULT_ENV_FILE,
        help="path to a .env file to load (default: nearest .env found by "
        "searching up from the current directory; skipped if none). Real "
        "environment variables always take precedence.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    # Fill config from a .env, without overriding the real environment. With the
    # default, search upward so one repo-root .env serves every worktree under
    # it; an explicit --env-file is used exactly as given.
    if args.env_file == DEFAULT_ENV_FILE:
        env_path = find_dotenv() or Path(DEFAULT_ENV_FILE)
    else:
        env_path = Path(args.env_file)
    load_dotenv(env_path)
    try:
        config = RunConfig.from_env(
            args.instance_id,
            model=args.model,
            step_cap=args.step_cap,
            runs_dir=args.runs_dir,
            image_override=args.image,
        )
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2

    # Imported here so `--help` and config errors don't require the runtime deps.
    from .run import run_instance

    summary = run_instance(config, submit_score=args.submit)

    print(f"instance:   {summary.instance_id}")
    print(f"stop:       {summary.stop_reason} after {summary.steps} step(s)")
    print(f"prediction: {summary.predictions_path}")
    if summary.patch_is_empty:
        print("warning:    the submitted patch is empty (no source changes)")
    if summary.resolved is not None:
        print(f"score:      {'RESOLVED' if summary.resolved else 'NOT RESOLVED'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
