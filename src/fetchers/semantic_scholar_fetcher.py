"""
Semantic Scholar API fetcher.
Official API with high quality metadata and generous rate limits.
"""
import logging
import time
from dataclasses import dataclass
from typing import Optional

import requests

from src.utils.http import get_session, is_open, record_failure, record_success

logger = logging.getLogger(__name__)
_SOURCE = "s2"


@dataclass
class SemanticScholarResult:
    """Search result from Semantic Scholar API."""
    title: str
    authors: list[str]
    year: str
    abstract: str
    paper_id: str
    citation_count: int
    url: str


class SemanticScholarFetcher:
    """
    Fetcher using Semantic Scholar's official API.
    
    API Docs: https://api.semanticscholar.org/
    Rate Limits:
    - Without API key: 100 requests per 5 minutes
    - With API key: 5,000 requests per 5 minutes (free)
    """
    
    BASE_URL = "https://api.semanticscholar.org/graph/v1"
    RATE_LIMIT_DELAY = 0.5  # Conservative delay (120 req/min max)
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Semantic Scholar fetcher. Uses shared session; api_key is added per-call
        as a header so the cache key includes it.
        """
        self.api_key = api_key
        self._last_request_time = 0.0

    def _headers(self) -> dict:
        if self.api_key:
            return {'x-api-key': self.api_key}
        return {}
    
    def _rate_limit(self):
        """Ensure rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.RATE_LIMIT_DELAY:
            time.sleep(self.RATE_LIMIT_DELAY - elapsed)
        self._last_request_time = time.time()
    
    def search_by_title(self, title: str, max_results: int = 5) -> Optional[SemanticScholarResult]:
        """Return the top-1 search result. See `search_by_title_multi` for the full list."""
        results = self.search_by_title_multi(title, max_results=max_results)
        return results[0] if results else None

    def search_by_title_multi(self, title: str, max_results: int = 5) -> list[SemanticScholarResult]:
        """
        Return up to `max_results` candidate results so callers can pick the best match.
        """
        if is_open(_SOURCE):
            return []
        self._rate_limit()

        url = f"{self.BASE_URL}/paper/search"
        params = {
            'query': title,
            'limit': max_results,
            'fields': 'title,authors,year,abstract,paperId,citationCount,url'
        }

        try:
            response = get_session().get(url, params=params, headers=self._headers(), timeout=8)
            response.raise_for_status()
            data = response.json()

            papers = data.get('data', [])
            results: list[SemanticScholarResult] = []
            for p in papers:
                parsed = self._parse_paper(p)
                if parsed:
                    results.append(parsed)
            record_success(_SOURCE)
            return results

        except requests.RequestException as e:
            logger.debug("S2 search_by_title(%s) failed: %s", title[:60], e, exc_info=True)
            record_failure(_SOURCE)
            return []
    
    def fetch_by_doi(self, doi: str) -> Optional[SemanticScholarResult]:
        """Fetch paper metadata by DOI. Honors circuit breaker."""
        if is_open(_SOURCE):
            return None
        self._rate_limit()

        url = f"{self.BASE_URL}/paper/DOI:{doi}"
        params = {
            'fields': 'title,authors,year,abstract,paperId,citationCount,url'
        }

        try:
            response = get_session().get(url, params=params, headers=self._headers(), timeout=8)
            response.raise_for_status()
            data = response.json()
            record_success(_SOURCE)
            return self._parse_paper(data)

        except requests.RequestException as e:
            logger.debug("S2 fetch_by_doi(%s) failed: %s", doi, e, exc_info=True)
            record_failure(_SOURCE)
            return None

    def fetch_by_arxiv_id(self, arxiv_id: str) -> Optional[SemanticScholarResult]:
        """Fetch paper metadata by arXiv ID. Honors circuit breaker."""
        if is_open(_SOURCE):
            return None
        self._rate_limit()

        clean_id = arxiv_id.replace('arXiv:', '')
        url = f"{self.BASE_URL}/paper/ARXIV:{clean_id}"
        params = {
            'fields': 'title,authors,year,abstract,paperId,citationCount,url'
        }

        try:
            response = get_session().get(url, params=params, headers=self._headers(), timeout=8)
            response.raise_for_status()
            data = response.json()
            record_success(_SOURCE)
            return self._parse_paper(data)

        except requests.RequestException as e:
            logger.debug("S2 fetch_by_arxiv_id(%s) failed: %s", arxiv_id, e, exc_info=True)
            record_failure(_SOURCE)
            return None

    def _parse_paper(self, paper_data: dict) -> Optional[SemanticScholarResult]:
        """Parse paper data from API response."""
        try:
            # Extract author names
            authors = []
            for author in paper_data.get('authors', []):
                name = author.get('name', '')
                if name:
                    authors.append(name)
            
            # Get year (may be None)
            year = paper_data.get('year')
            year_str = str(year) if year else ""
            
            return SemanticScholarResult(
                title=paper_data.get('title', ''),
                authors=authors,
                year=year_str,
                abstract=paper_data.get('abstract', ''),
                paper_id=paper_data.get('paperId', ''),
                citation_count=paper_data.get('citationCount', 0),
                url=paper_data.get('url', '')
            )
        except (KeyError, TypeError):
            return None
