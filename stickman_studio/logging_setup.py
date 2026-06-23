"""
logging_setup.py
================
Project-wide logging. Logs to both the console (rich) and a per-run
file inside the project folder, so every API rate-limit warning and
retry is captured for later inspection.
"""

from __future__ import annotations

import logging
from pathlib import Path

try:
    from rich.logging import RichHandler

    _HAVE_RICH = True
except Exception:  # pragma: no cover
    _HAVE_RICH = False


_CONFIGURED = False


def configure_logging(level: str = "INFO", log_file: Path | None = None) -> None:
    """Idempotently configure root logging."""
    global _CONFIGURED

    root = logging.getLogger()
    root.setLevel(level)

    if not _CONFIGURED:
        if _HAVE_RICH:
            console = RichHandler(rich_tracebacks=True, markup=False)
            console.setFormatter(logging.Formatter("%(message)s", datefmt="%H:%M:%S"))
        else:
            console = logging.StreamHandler()
            console.setFormatter(
                logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")
            )
        root.addHandler(console)
        _CONFIGURED = True

    # Attach (or refresh) a file handler when a project log path is known.
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        # Avoid duplicate file handlers for the same path.
        for h in root.handlers:
            if isinstance(h, logging.FileHandler) and getattr(h, "_sm_path", None) == str(
                log_file
            ):
                break
        else:
            fh = logging.FileHandler(log_file, encoding="utf-8")
            fh.setFormatter(
                logging.Formatter(
                    "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
                )
            )
            fh._sm_path = str(log_file)  # type: ignore[attr-defined]
            root.addHandler(fh)

    # Quiet noisy gRPC/absl chatter unless we are debugging.
    if level != "DEBUG":
        for noisy in ("google", "grpc", "urllib3", "absl"):
            logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
