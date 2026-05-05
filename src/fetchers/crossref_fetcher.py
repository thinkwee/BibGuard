"""
CrossRef API fetcher for bibliography metadata.

CrossRef provides free, reliable access to metadata for academic publications.
No API key required, no rate limiting for reasonable use.
"""
import logging
import requests
from dataclasses import dataclass
from typing import Optional, List
import time

from src.utils.http import get_session, is_open, record_failure, record_success

logger = logging.getLogger(__name__)
_SOURCE = "crossref"


@dataclass
class CrossRefResult:
    """Metadata result from CrossRef API."""
    title: str
    authors: List[str]
    year: str
    doi: str
    publisher: str
    container_title: str  # Journal/conference name
    abstract: str = ""
    url: str = ""
    
    
class CrossRefFetcher:
    """
    Fetcher for CrossRef API.
    
    CrossRef is a reliable, free API for academic metadata.
    Much more reliable than Google Scholar scraping.
    """
    
    BASE_URL = "https://api.crossref.org/works"
    RATE_LIMIT_DELAY = 1.0  # Be polite
    
    def __init__(self, mailto: Optional[str] = None):
        """
        Initialize CrossRef fetcher.

        The shared HTTP session already carries a polite-pool User-Agent built
        from `network.contact_email`. `mailto` here is kept for backward
        compatibility but no longer overrides the session header.
        """
        self.mailto = mailto
        self._last_request_time = 0.0

    def _rate_limit(self):
        """Ensure rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.RATE_LIMIT_DELAY:
            time.sleep(self.RATE_LIMIT_DELAY - elapsed)
        self._last_request_time = time.time()

    def _get_headers(self) -> dict:
        return {'Accept': 'application/json'}
    
    def search_by_title(self, title: str, max_results: int = 5) -> Optional[CrossRefResult]:
        """Top-1 result. See `search_by_title_multi` for the candidate list."""
        results = self.search_by_title_multi(title, max_results=max_results)
        return results[0] if results else None

    def search_by_title_multi(self, title: str, max_results: int = 5) -> List[CrossRefResult]:
        """Return up to `max_results` candidates so callers can pick the best match."""
        if is_open(_SOURCE):
            return []
        self._rate_limit()

        params = {
            'query.title': title,
            'rows': max_results,
            'select': 'title,author,published-print,published-online,DOI,publisher,container-title,abstract'
        }

        try:
            response = get_session().get(
                self.BASE_URL,
                params=params,
                headers=self._get_headers(),
                timeout=(5, 8),
            )
            response.raise_for_status()

            data = response.json()
            if data.get('status') != 'ok':
                return []

            items = data.get('message', {}).get('items', []) or []
            out: List[CrossRefResult] = []
            for it in items:
                parsed = self._parse_item(it)
                if parsed:
                    out.append(parsed)
            record_success(_SOURCE)
            return out

        except requests.RequestException as e:
            logger.debug("CrossRef search_by_title(%s) failed: %s", title[:60], e, exc_info=True)
            record_failure(_SOURCE)
            return []
    
    def search_by_doi(self, doi: str) -> Optional[CrossRefResult]:
        """Fetch metadata by DOI. Honors circuit breaker."""
        if is_open(_SOURCE):
            return None
        self._rate_limit()

        doi = doi.replace('https://doi.org/', '').replace('http://doi.org/', '')

        try:
            response = get_session().get(
                f"{self.BASE_URL}/{doi}",
                headers=self._get_headers(),
                timeout=(5, 8),
            )
            response.raise_for_status()

            data = response.json()

            if data.get('status') != 'ok':
                return None

            item = data.get('message', {})
            record_success(_SOURCE)
            return self._parse_item(item)

        except requests.RequestException as e:
            logger.debug("CrossRef search_by_doi(%s) failed: %s", doi, e, exc_info=True)
            record_failure(_SOURCE)
            return None
    
    def _parse_item(self, item: dict) -> Optional[CrossRefResult]:
        """Parse a CrossRef API item into CrossRefResult."""
        try:
            # Get title
            titles = item.get('title', [])
            title = titles[0] if titles else ""
            
            if not title:
                return None
            
            # Get authors
            authors = []
            for author in item.get('author', []):
                given = author.get('given', '')
                family = author.get('family', '')
                if family:
                    if given:
                        authors.append(f"{given} {family}")
                    else:
                        authors.append(family)
            
            # Get year (try published-print first, then published-online)
            year = ""
            for date_field in ['published-print', 'published-online', 'created']:
                date_parts = item.get(date_field, {}).get('date-parts', [[]])
                if date_parts and date_parts[0]:
                    year = str(date_parts[0][0])
                    break
            
            # Get DOI
            doi = item.get('DOI', '')
            
            # Get publisher
            publisher = item.get('publisher', '')
            
            # Get container title (journal/conference name)
            container_titles = item.get('container-title', [])
            container_title = container_titles[0] if container_titles else ""
            
            # Get abstract (if available)
            abstract = item.get('abstract', '')
            
            # Build URL
            url = f"https://doi.org/{doi}" if doi else ""
            
            return CrossRefResult(
                title=title,
                authors=authors,
                year=year,
                doi=doi,
                publisher=publisher,
                container_title=container_title,
                abstract=abstract,
                url=url
            )
            
        except (KeyError, IndexError, TypeError):
            return None
