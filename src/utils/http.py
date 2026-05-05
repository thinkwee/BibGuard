"""
Shared HTTP client: pooled session + auto-retry + optional on-disk cache.

All fetchers should go through `get_session()` instead of bare `requests.get`.
This gives them consistent retry/backoff on 429/5xx, polite-pool User-Agent,
and (when enabled) SQLite-backed response caching to skip re-querying the
same URL on re-runs.

The application-level circuit breaker (``is_open`` / ``record_failure``) is
the primary defense against bad networks: any source that fails twice gets
skipped for the rest of the run. urllib3's own retry is intentionally
narrow (5xx only, no connect/read retries) so the breaker can trip fast.

For deploys where you know certain sources won't work (e.g. HF Spaces
egress IPs are routinely blocked by DBLP and arxiv), set
``BIBGUARD_DISABLE_SOURCES=dblp,arxiv`` to permanently mark those breakers
as open at startup so we never even try them.
"""
from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Optional

import requests
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

logger = logging.getLogger(__name__)

# Global per-process state
_lock = threading.Lock()
_settings: dict = {
    "contact_email": "",
    "cache_enabled": True,
    "cache_ttl_hours": 24,
    "retry_total": 5,
    "retry_backoff_factor": 1.5,
    "cache_dir": None,  # Path or None
}
_session: Optional[requests.Session] = None


def configure(
    contact_email: str = "",
    cache_enabled: bool = True,
    cache_ttl_hours: int = 24,
    retry_total: int = 5,
    retry_backoff_factor: float = 1.5,
    cache_dir: Optional[Path] = None,
) -> None:
    """Configure HTTP layer. Call once at startup before any fetcher is used."""
    global _session
    with _lock:
        _settings.update({
            "contact_email": contact_email or "",
            "cache_enabled": cache_enabled,
            "cache_ttl_hours": int(cache_ttl_hours),
            "retry_total": int(retry_total),
            "retry_backoff_factor": float(retry_backoff_factor),
            "cache_dir": cache_dir,
        })
        # Force rebuild on next get_session()
        _session = None


def user_agent() -> str:
    """Build a polite User-Agent string. Includes contact email if configured."""
    email = _settings.get("contact_email") or ""
    if email:
        return f"BibGuard/1.0 (+https://github.com/thinkwee/BibGuard; mailto:{email})"
    return "BibGuard/1.0 (+https://github.com/thinkwee/BibGuard)"


def _build_session() -> requests.Session:
    """Construct a Session with retry and (optionally) caching."""
    cache_enabled = _settings["cache_enabled"]
    ttl = _settings["cache_ttl_hours"] * 3600

    if cache_enabled:
        try:
            from requests_cache import CachedSession  # type: ignore
            cache_dir = _settings.get("cache_dir")
            if cache_dir is None:
                cache_dir = Path.home() / ".cache" / "bibguard"
            cache_dir.mkdir(parents=True, exist_ok=True)
            session = CachedSession(
                cache_name=str(cache_dir / "http_cache"),
                backend="sqlite",
                expire_after=ttl,
                allowable_methods=("GET", "HEAD"),
                allowable_codes=(200, 203, 300, 301, 308),
                stale_if_error=True,
            )
            logger.debug("HTTP cache enabled: %s (ttl=%ss)", cache_dir, ttl)
        except ImportError:
            logger.info(
                "requests-cache not installed; running without HTTP cache. "
                "Install via `pip install requests-cache` for big speedups on re-runs."
            )
            session = requests.Session()
    else:
        session = requests.Session()

    # Retry policy is deliberately surgical:
    #   - 429 NOT in status_forcelist: rate-limit means "back off", not "retry";
    #     retrying just blocks the thread while a parallel source could answer.
    #   - connect=0, read=0: do NOT retry on ConnectionReset / ReadTimeout /
    #     ConnectError. On hostile-network deploys (e.g. HF Spaces' egress IPs
    #     are sometimes blocked by DBLP / arxiv export), these errors persist
    #     across retries — retries just multiply the wall-clock penalty
    #     before our application-level circuit breaker can trip the source.
    #   - status retries are capped at min(retry_total, 2) for genuine 5xx,
    #     which are usually transient.
    # The application-level circuit breaker (below) is the source-of-truth
    # for "stop hitting this host"; urllib3's job is just one fast attempt.
    status_retries = min(int(_settings["retry_total"]), 2)
    retry = Retry(
        total=status_retries,
        connect=0,
        read=0,
        status=status_retries,
        backoff_factor=_settings["retry_backoff_factor"],
        status_forcelist=(500, 502, 503, 504),
        allowed_methods=("GET", "HEAD"),
        raise_on_status=False,
        respect_retry_after_header=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=20, pool_maxsize=20)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({"User-Agent": user_agent()})
    return session


def get_session() -> requests.Session:
    """Return the shared, configured Session. Thread-safe."""
    global _session
    if _session is None:
        with _lock:
            if _session is None:
                _session = _build_session()
    return _session


def reset_for_tests() -> None:
    """Drop the shared session. Used by tests to force a rebuild."""
    global _session
    with _lock:
        _session = None


# ---------------------------------------------------------------------------
# Circuit breaker: trip a source after N consecutive failures so the rest of
# the run skips it instead of paying its rate-limit/timeout penalty per entry.
# ---------------------------------------------------------------------------
_breakers: dict[str, dict] = {}
_breakers_lock = threading.Lock()


def is_open(source: str) -> bool:
    """True if the source's circuit is currently tripped (skip it)."""
    with _breakers_lock:
        b = _breakers.get(source)
        return bool(b and b.get("open"))


def record_failure(source: str, threshold: int = 2) -> bool:
    """Note a failure for `source`; trip the breaker after `threshold`.

    The default of 2 is intentionally aggressive: with urllib3 retries on
    connection/read errors disabled (see ``_build_session``), each failure
    completes in 1-3 seconds. Two quick fails ≈ 4-6 s wasted before the
    source is shut off for the rest of the run, which is far cheaper than
    the alternative of paying the timeout-per-entry on bad networks (HF
    Spaces' egress IP being blocked by DBLP, e.g.).

    Returns True if the breaker is now (or was already) open.
    """
    with _breakers_lock:
        b = _breakers.setdefault(source, {"failures": 0, "open": False})
        b["failures"] += 1
        if b["failures"] >= threshold:
            if not b["open"]:
                logger.warning(
                    "Circuit breaker tripped for %s after %d failures; "
                    "skipping for the rest of this run.",
                    source, b["failures"],
                )
            b["open"] = True
        return b["open"]


def record_success(source: str) -> None:
    """Reset the failure counter on a success."""
    with _breakers_lock:
        b = _breakers.get(source)
        if b:
            b["failures"] = 0
            b["open"] = False


def reset_breakers() -> None:
    """Clear all breaker state (called at the start of a fresh run).

    After clearing, sources listed in ``BIBGUARD_DISABLE_SOURCES`` (comma- or
    space-separated, case-insensitive) are immediately re-marked as open so
    the run never even attempts them. Useful on hostile-network deploys.
    """
    with _breakers_lock:
        _breakers.clear()
    disabled = os.environ.get("BIBGUARD_DISABLE_SOURCES", "")
    for raw in disabled.replace(",", " ").split():
        name = raw.strip().lower()
        if not name:
            continue
        with _breakers_lock:
            _breakers[name] = {"failures": 9999, "open": True, "disabled": True}
        logger.info("Source %r pre-disabled via BIBGUARD_DISABLE_SOURCES", name)
