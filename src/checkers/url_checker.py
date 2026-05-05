"""
URL liveness checker for bibliography entries.

Many @misc / blog / repo references rot over time. This checker does a HEAD
(falling back to a small GET) on entry.url and flags anything that returns
4xx/5xx or fails to connect.

Operates on BibEntry objects, not on tex_content. Invoked from main.py / app.py
when `submission_extra.url_liveness` is true.
"""
from __future__ import annotations

import concurrent.futures
import logging
from dataclasses import dataclass
from typing import Iterable, List, Optional

import requests

from src.utils.http import get_session
from src.parsers.bib_parser import BibEntry

logger = logging.getLogger(__name__)


@dataclass
class URLFinding:
    entry_key: str
    url: str
    status: str            # "ok" | "broken" | "unreachable" | "skipped"
    status_code: Optional[int] = None
    detail: str = ""


class URLChecker:
    """Concurrent HEAD-then-GET liveness check."""

    SKIP_PREFIXES = ("mailto:", "ftp://", "tel:", "javascript:")

    def __init__(self, max_workers: int = 8, timeout: float = 15.0):
        self.max_workers = max_workers
        self.timeout = timeout

    def _check_one(self, entry: BibEntry) -> Optional[URLFinding]:
        url = (entry.url or "").strip()
        if not url:
            return None
        if any(url.lower().startswith(p) for p in self.SKIP_PREFIXES):
            return URLFinding(entry.key, url, "skipped", detail="non-http scheme")

        session = get_session()
        try:
            r = session.head(url, allow_redirects=True, timeout=self.timeout)
            # Many servers return 405/403 for HEAD but are fine with GET; double-check with a tiny GET.
            if r.status_code in (403, 405, 501):
                r = session.get(url, allow_redirects=True, timeout=self.timeout, stream=True)
                # Don't actually read the body
                r.close()
        except requests.RequestException as e:
            logger.debug("URL check failed for %s: %s", url, e, exc_info=True)
            return URLFinding(entry.key, url, "unreachable", detail=str(e)[:120])

        if 200 <= r.status_code < 400:
            return URLFinding(entry.key, url, "ok", status_code=r.status_code)
        return URLFinding(
            entry.key, url, "broken",
            status_code=r.status_code,
            detail=f"HTTP {r.status_code}",
        )

    def check_entries(self, entries: Iterable[BibEntry]) -> List[URLFinding]:
        targets = [e for e in entries if getattr(e, "url", "")]
        if not targets:
            return []
        findings: List[URLFinding] = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as ex:
            for f in ex.map(self._check_one, targets):
                if f is not None:
                    findings.append(f)
        return findings
