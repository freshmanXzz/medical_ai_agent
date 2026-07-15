"""Capture third-party runtime output outside the interactive consultation."""

from __future__ import annotations

from contextlib import contextmanager, redirect_stderr, redirect_stdout
from datetime import datetime
from pathlib import Path
from typing import Iterator
import warnings


def get_runtime_log_path() -> Path:
    project_root = Path(__file__).resolve().parents[2]
    log_dir = project_root / "log" / "runtime"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / f"{datetime.now():%Y-%m-%d}.log"


@contextmanager
def capture_runtime_output() -> Iterator[Path]:
    """Redirect stdout/stderr noise from models and libraries to a log file."""
    log_path = get_runtime_log_path()
    with log_path.open("a", encoding="utf-8") as stream:
        stream.write(f"\n[{datetime.now():%Y-%m-%d %H:%M:%S}] runtime output\n")
        stream.flush()
        with warnings.catch_warnings(record=True) as captured_warnings:
            warnings.simplefilter("always")
            with redirect_stdout(stream), redirect_stderr(stream):
                yield log_path
            for warning in captured_warnings:
                stream.write(
                    warnings.formatwarning(
                        warning.message,
                        warning.category,
                        warning.filename,
                        warning.lineno,
                    )
                )
