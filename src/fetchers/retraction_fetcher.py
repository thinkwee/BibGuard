"""
Retraction Watch / CrossRef retraction lookup.

CrossRef exposes an `update-to` relation on retracted works. We query the
CrossRef Works API for a DOI and check the `update-to` and `update-policy`
fields. Retraction Watch's own API requires registration; CrossRef coverage
is broad enough to catch the majority of retracted ML/NLP papers.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import requests

from src.utils.http import get_session

logger = logging.getLogger(__name__)


@dataclass
class RetractionResult:
    is_retracted: bool
    update_type: str = ""        # "retraction", "correction", "expression-of-concern", ...
    notice_doi: str = ""
    notice_label: str = ""
    notice_url: str = ""


class RetractionFetcher:
    """Look up retraction status of a DOI via CrossRef."""

    BASE_URL = "https://api.crossref.org/works"

    # We treat any of these as a hard red flag
    HARD_FLAGS = {"retraction", "withdrawal", "removal"}
    SOFT_FLAGS = {"expression-of-concern", "correction", "erratum"}

    def __init__(self, mailto: Optional[str] = None):
        self.mailto = mailto

    def check(self, doi: str) -> Optional[RetractionResult]:
        """Return RetractionResult or None on lookup failure."""
        if not doi:
            return None
        # Normalize DOI (strip URL prefix)
        doi = doi.replace("https://doi.org/", "").replace("http://doi.org/", "").strip()
        if not doi:
            return None

        try:
            response = get_session().get(
                f"{self.BASE_URL}/{doi}",
                headers={"Accept": "application/json"},
                timeout=20,
            )
            if response.status_code == 404:
                return None
            response.raise_for_status()
        except requests.RequestException as e:
            logger.debug("Retraction lookup failed for %s: %s", doi, e, exc_info=True)
            return None

        try:
            data = response.json()
        except ValueError:
            return None

        if data.get("status") != "ok":
            return None

        msg = data.get("message", {}) or {}
        # CrossRef puts retraction notices under "update-to": [{"DOI": ..., "type": "retraction", ...}]
        # and the *original* paper that is retracted has the notice as `update-to` or in `relation`.
        notices = []
        for upd in msg.get("update-to") or []:
            t = (upd.get("type") or "").lower().replace("_", "-")
            if t:
                notices.append((t, upd.get("DOI", ""), upd.get("label", "")))
        # Some retraction *notices themselves* have type:"retraction" in the work itself.
        msg_type = (msg.get("type") or "").lower()
        if msg_type in self.HARD_FLAGS:
            notices.append((msg_type, doi, msg.get("title", [""])[0] if msg.get("title") else ""))

        if not notices:
            return RetractionResult(is_retracted=False)

        # Pick the most severe
        for t, ndoi, label in notices:
            if t in self.HARD_FLAGS:
                return RetractionResult(
                    is_retracted=True,
                    update_type=t,
                    notice_doi=ndoi,
                    notice_label=label,
                    notice_url=f"https://doi.org/{ndoi}" if ndoi else "",
                )
        # Soft flag: not retraction but worth surfacing
        t, ndoi, label = notices[0]
        return RetractionResult(
            is_retracted=False,
            update_type=t,
            notice_doi=ndoi,
            notice_label=label,
            notice_url=f"https://doi.org/{ndoi}" if ndoi else "",
        )
