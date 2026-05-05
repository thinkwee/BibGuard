"""
OpenAlex API fetcher.
Free and open API for scholarly metadata.
"""
import logging
import time
from dataclasses import dataclass
from typing import Optional

import requests

from src.utils.http import get_session, is_open, record_failure, record_success

logger = logging.getLogger(__name__)
_SOURCE = "openalex"


@dataclass
class OpenAlexResult:
    """Search result from OpenAlex API."""
    title: str
    authors: list[str]
    year: str
    abstract: str
    doi: str
    citation_count: int
    url: str


class OpenAlexFetcher:
    """
    Fetcher using OpenAlex's free API.
    
    API Docs: https://docs.openalex.org/
    Rate Limits:
    - 100,000 requests per day
    - 10 requests per second (very generous)
    - No API key required (but polite pool recommended)
    """
    
    BASE_URL = "https://api.openalex.org"
    RATE_LIMIT_DELAY = 0.1  # 10 req/sec max
    
    def __init__(self, email: Optional[str] = None):
        """OpenAlex fetcher. Shared session UA already includes contact email."""
        self.email = email
        self._last_request_time = 0.0

    def _rate_limit(self):
        """Ensure rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.RATE_LIMIT_DELAY:
            time.sleep(self.RATE_LIMIT_DELAY - elapsed)
        self._last_request_time = time.time()
    
    def search_by_title(self, title: str, max_results: int = 5) -> Optional[OpenAlexResult]:
        """Top-1 result. See `search_by_title_multi` for the candidate list."""
        results = self.search_by_title_multi(title, max_results=max_results)
        return results[0] if results else None

    def search_by_title_multi(self, title: str, max_results: int = 5) -> list[OpenAlexResult]:
        """Return up to `max_results` candidates. Honors circuit breaker."""
        if is_open(_SOURCE):
            return []
        self._rate_limit()

        url = f"{self.BASE_URL}/works"
        params = {'search': title, 'per-page': max_results}

        try:
            response = get_session().get(url, params=params, timeout=8)
            response.raise_for_status()
            data = response.json()
            out: list[OpenAlexResult] = []
            for w in data.get('results', []) or []:
                parsed = self._parse_work(w)
                if parsed:
                    out.append(parsed)
            record_success(_SOURCE)
            return out
        except requests.RequestException as e:
            logger.debug("OpenAlex search_by_title(%s) failed: %s", title[:60], e, exc_info=True)
            record_failure(_SOURCE)
            return []
    
    def fetch_by_doi(self, doi: str) -> Optional[OpenAlexResult]:
        """Fetch paper metadata by DOI. Honors circuit breaker."""
        if is_open(_SOURCE):
            return None
        self._rate_limit()

        doi_url = f"https://doi.org/{doi}"
        url = f"{self.BASE_URL}/works/{doi_url}"

        try:
            response = get_session().get(url, timeout=8)
            response.raise_for_status()
            data = response.json()
            record_success(_SOURCE)
            return self._parse_work(data)

        except requests.RequestException as e:
            logger.debug("OpenAlex fetch_by_doi(%s) failed: %s", doi, e, exc_info=True)
            record_failure(_SOURCE)
            return None
    
    def _parse_work(self, work_data: dict) -> Optional[OpenAlexResult]:
        """Parse work data from API response."""
        try:
            # Extract title
            title = work_data.get('title', '')
            
            # Extract authors
            authors = []
            authorships = work_data.get('authorships', [])
            for authorship in authorships:
                author = authorship.get('author', {})
                name = author.get('display_name', '')
                if name:
                    authors.append(name)
            
            # Get publication year
            year = work_data.get('publication_year')
            year_str = str(year) if year else ""
            
            # Get abstract (inverted index format)
            abstract = ""
            abstract_inverted = work_data.get('abstract_inverted_index')
            if abstract_inverted:
                # Reconstruct abstract from inverted index
                abstract = self._reconstruct_abstract(abstract_inverted)
            
            # Get DOI
            doi = work_data.get('doi', '')
            if doi and doi.startswith('https://doi.org/'):
                doi = doi.replace('https://doi.org/', '')
            
            # Get citation count
            citation_count = work_data.get('cited_by_count', 0)
            
            # Get URL
            url = work_data.get('id', '')  # OpenAlex ID URL
            
            return OpenAlexResult(
                title=title,
                authors=authors,
                year=year_str,
                abstract=abstract,
                doi=doi,
                citation_count=citation_count,
                url=url
            )
        except (KeyError, TypeError):
            return None
    
    def _reconstruct_abstract(self, inverted_index: dict) -> str:
        """
        Reconstruct abstract text from inverted index.
        
        OpenAlex stores abstracts in inverted index format:
        {"word": [position1, position2, ...], ...}
        """
        if not inverted_index:
            return ""
        
        try:
            # Create a list to hold words at their positions
            max_pos = max(max(positions) for positions in inverted_index.values())
            words = [''] * (max_pos + 1)
            
            # Place each word at its positions
            for word, positions in inverted_index.items():
                for pos in positions:
                    words[pos] = word
            
            # Join words with spaces
            return ' '.join(word for word in words if word)
        except (ValueError, TypeError):
            return ""
