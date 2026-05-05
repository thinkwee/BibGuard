"""
Bibliography-level checker that flags retracted DOIs.

Unlike the LaTeX-line checkers in src/checkers/, this one operates on parsed
BibEntry objects, not on a tex_content string. main.py / app.py invoke it
directly via `check_entries(entries)`.
"""
from __future__ import annotations

import concurrent.futures
import logging
from dataclasses import dataclass
from typing import Iterable, List

from src.fetchers.retraction_fetcher import RetractionFetcher, RetractionResult
from src.parsers.bib_parser import BibEntry

logger = logging.getLogger(__name__)


@dataclass
class RetractionFinding:
    entry_key: str
    doi: str
    result: RetractionResult


class RetractionChecker:
    """Concurrent batch retraction lookup."""

    def __init__(self, max_workers: int = 6):
        self.fetcher = RetractionFetcher()
        self.max_workers = max_workers

    def check_entries(self, entries: Iterable[BibEntry]) -> List[RetractionFinding]:
        """Look up retraction status for every entry that has a DOI."""
        with_doi = [e for e in entries if getattr(e, "doi", "")]
        if not with_doi:
            return []

        findings: List[RetractionFinding] = []

        def _one(entry: BibEntry):
            res = self.fetcher.check(entry.doi)
            return entry, res

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as ex:
            for entry, res in ex.map(_one, with_doi):
                if res is None:
                    continue
                if res.is_retracted or res.update_type:
                    findings.append(RetractionFinding(entry.key, entry.doi, res))
        return findings
