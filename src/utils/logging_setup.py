"""
Logging bootstrap and per-run capture utilities.

Design goals
------------
1. **One env var to rule them all.** ``BIBGUARD_LOG=DEBUG`` (or
   ``BIBGUARD_DEBUG=1``) turns on full tracebacks across the codebase. Default
   is WARNING so stdout stays quiet during normal runs.

2. **Always-on file log.** Even at WARNING console level we still write a
   rotating DEBUG log to ``~/.cache/bibguard/logs/bibguard.log`` (override with
   ``BIBGUARD_LOG_FILE``). That way, when something blows up mid-run you can
   ``tail`` or grep the file after the fact — no need to rerun with --verbose.

3. **Pinpoint location.** Formatter includes ``filename:lineno`` so any log
   line tells you exactly which source line emitted it.

4. **Per-run capture for the UI.** ``capture_run()`` is a context manager that
   returns a buffer + path. The Gradio app attaches it at the start of each
   check, then ships the resulting log as a downloadable artifact alongside
   the HTML report.
"""
from __future__ import annotations

import logging
import logging.handlers
import os
import sys
import tempfile
from contextlib import contextmanager
from io import StringIO
from pathlib import Path
from typing import Iterator, Optional

# Format used for both console and file. ``%(filename)s:%(lineno)d`` is the
# important addition — it makes any traceback-free warning still navigable.
_FMT = "%(asctime)s %(levelname)-7s %(name)s %(filename)s:%(lineno)d — %(message)s"
_DATEFMT = "%H:%M:%S"


def _resolve(level: str | int) -> int:
    if isinstance(level, int):
        return level
    return getattr(logging, str(level).upper(), logging.WARNING)


def _default_log_path() -> Path:
    override = os.environ.get("BIBGUARD_LOG_FILE", "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / ".cache" / "bibguard" / "logs" / "bibguard.log"


def setup(level: str | int | None = None, *, quiet: bool = False,
          log_file: Optional[Path | str] = None) -> Path:
    """
    Configure root logger.

    Console level is controlled by ``level`` / ``BIBGUARD_LOG`` / ``quiet``.
    Regardless of console level, a DEBUG-level rotating file is *always*
    written so failures are reproducible after the fact.

    Returns the path to the active log file (useful for surfacing in the UI).
    """
    # Resolve console level
    if quiet:
        console_level = logging.ERROR
    elif os.environ.get("BIBGUARD_DEBUG", "").strip() in ("1", "true", "yes"):
        console_level = logging.DEBUG
    elif level is not None:
        console_level = _resolve(level)
    else:
        console_level = _resolve(os.environ.get("BIBGUARD_LOG", "WARNING"))

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)  # let handlers filter; root keeps everything

    # ------------------------------------------------------------- console
    # If we already attached a console handler, reuse it (avoids duplicates
    # when modules import this multiple times).
    console_handler = None
    for h in root.handlers:
        if getattr(h, "_bibguard_console", False):
            console_handler = h
            break
    if console_handler is None:
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler._bibguard_console = True  # type: ignore[attr-defined]
        console_handler.setFormatter(logging.Formatter(fmt=_FMT, datefmt=_DATEFMT))
        root.addHandler(console_handler)
    console_handler.setLevel(console_level)

    # ------------------------------------------------------------- file
    log_path = Path(log_file).expanduser() if log_file else _default_log_path()
    file_handler: Optional[logging.handlers.RotatingFileHandler] = None
    for h in root.handlers:
        if getattr(h, "_bibguard_file", False):
            file_handler = h  # type: ignore[assignment]
            break
    try:
        if file_handler is None:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.handlers.RotatingFileHandler(
                str(log_path), maxBytes=2_000_000, backupCount=3, encoding="utf-8",
            )
            file_handler._bibguard_file = True  # type: ignore[attr-defined]
            file_handler.setFormatter(logging.Formatter(fmt=_FMT, datefmt=_DATEFMT))
            file_handler.setLevel(logging.DEBUG)
            root.addHandler(file_handler)
    except OSError as e:
        # Non-fatal: filesystem unavailable, fall back to stderr-only.
        root.warning("File logging disabled (%s); stderr only.", e)

    # Quiet down noisy third-party loggers unless we're in DEBUG console mode.
    if console_level > logging.DEBUG:
        for noisy in ("urllib3", "requests", "requests_cache", "bibtexparser"):
            logging.getLogger(noisy).setLevel(logging.WARNING)
    else:
        for noisy in ("urllib3", "requests", "requests_cache", "bibtexparser"):
            logging.getLogger(noisy).setLevel(logging.INFO)

    return log_path


@contextmanager
def capture_run(target_path: Optional[Path] = None) -> Iterator[tuple[Path, "_RunStats"]]:
    """
    Attach a temporary DEBUG-level file handler for the duration of a single run.

    Yields ``(path, stats)`` where:
      * ``path`` is the per-run log file written into the report's output dir
        (or a temp file if ``target_path`` is None).
      * ``stats`` exposes ``warnings`` / ``errors`` counters so the UI can
        surface "N warnings logged" without reading the file.

    Used by ``app.py`` so each Gradio run produces a self-contained
    ``bibguard.log`` next to ``report.html`` that the user can download.
    """
    path = target_path or Path(tempfile.NamedTemporaryFile(
        suffix=".log", prefix="bibguard_run_", delete=False
    ).name)
    path.parent.mkdir(parents=True, exist_ok=True)

    handler = logging.FileHandler(str(path), mode="w", encoding="utf-8")
    handler.setFormatter(logging.Formatter(fmt=_FMT, datefmt=_DATEFMT))
    handler.setLevel(logging.DEBUG)

    stats = _RunStats()
    handler.addFilter(stats)  # filters can also count

    root = logging.getLogger()
    root.addHandler(handler)
    try:
        yield path, stats
    finally:
        try:
            handler.flush()
            handler.close()
        except Exception:
            pass
        try:
            root.removeHandler(handler)
        except ValueError:
            pass


class _RunStats(logging.Filter):
    """Logging filter that just counts warning+ records (always returns True)."""

    def __init__(self) -> None:
        super().__init__()
        self.warnings = 0
        self.errors = 0
        self.exceptions = 0

    def filter(self, record: logging.LogRecord) -> bool:  # type: ignore[override]
        if record.levelno >= logging.ERROR:
            self.errors += 1
            if record.exc_info:
                self.exceptions += 1
        elif record.levelno >= logging.WARNING:
            self.warnings += 1
        return True
