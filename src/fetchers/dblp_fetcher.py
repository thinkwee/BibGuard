import requests
import time
import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

from src.utils.http import get_session, is_open, record_failure, record_success

_SOURCE = "dblp"

@dataclass
class DBLPResult:
    title: str
    authors: List[str]
    year: str
    venue: str
    url: str
    doi: Optional[str] = None

class DBLPFetcher:
    """Fetcher for DBLP API."""
    
    BASE_URL = "https://dblp.org/search/publ/api"
    
    def __init__(self):
        self.last_request_time = 0
        # DBLP asks for 1-2 seconds between requests. We'll use 1.5s to be safe.
        self.rate_limit_delay = 1.5
        self.logger = logging.getLogger(__name__)

    def _wait_for_rate_limit(self):
        """Ensure we don't exceed rate limits."""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - elapsed)
        self.last_request_time = time.time()

    def search_by_title(self, title: str) -> Optional[DBLPResult]:
        """Top-1 result. See `search_by_title_multi` for the candidate list."""
        results = self.search_by_title_multi(title, max_results=5)
        return results[0] if results else None

    def search_by_title_multi(self, title: str, max_results: int = 5) -> List[DBLPResult]:
        """Return up to `max_results` DBLP hits. Honors circuit breaker."""
        if is_open(_SOURCE):
            return []
        self._wait_for_rate_limit()

        params = {"q": title, "format": "json", "h": max_results}

        try:
            response = get_session().get(self.BASE_URL, params=params, timeout=8)

            if response.status_code == 429:
                self.logger.warning("DBLP rate limit exceeded; tripping breaker")
                record_failure(_SOURCE, threshold=2)  # DBLP 429 is sticky
                return []

            if response.status_code != 200:
                self.logger.debug("DBLP API status %s for title=%r", response.status_code, title[:60])
                record_failure(_SOURCE)
                return []

            data = response.json()
            record_success(_SOURCE)
            return self._parse_response_multi(data)

        except Exception as e:
            self.logger.debug("Error fetching from DBLP for title=%r: %s", title[:60], e, exc_info=True)
            record_failure(_SOURCE)
            return []

    def _parse_response_multi(self, data: Dict[str, Any]) -> List[DBLPResult]:
        out: List[DBLPResult] = []
        try:
            hits = data.get("result", {}).get("hits", {}).get("hit", []) or []
            for hit in hits:
                info = hit.get("info", {}) or {}
                authors_data = info.get("authors", {}).get("author", [])
                authors: List[str] = []
                if isinstance(authors_data, list):
                    authors = [a.get("text", "") for a in authors_data if isinstance(a, dict)]
                elif isinstance(authors_data, dict):
                    authors = [authors_data.get("text", "")]
                title = info.get("title", "") or ""
                if title.endswith("."):
                    title = title[:-1]
                doi = info.get("doi", "")
                out.append(DBLPResult(
                    title=title,
                    authors=[a for a in authors if a],
                    year=info.get("year", ""),
                    venue=info.get("venue", ""),
                    url=info.get("url", ""),
                    doi=doi if doi else None,
                ))
        except Exception as e:
            self.logger.error("DBLP parse failed: %s", e, exc_info=True)
        return out

    def _parse_response(self, data: Dict[str, Any], query_title: str) -> Optional[DBLPResult]:
        """Parse DBLP JSON response."""
        try:
            result = data.get("result", {})
            hits = result.get("hits", {}).get("hit", [])
            
            if not hits:
                return None
            
            # Find best match
            best_hit = None
            
            # Simple check: first hit is usually the best in DBLP for exact title match
            # But we can do a quick normalization check if needed.
            # For now, let's take the first hit that is a publication (not a person/venue)
            # The search/publ/api endpoint should only return publications.
            
            best_hit = hits[0]
            info = best_hit.get("info", {})
            
            # Extract authors
            authors_data = info.get("authors", {}).get("author", [])
            authors = []
            if isinstance(authors_data, list):
                authors = [a.get("text", "") for a in authors_data]
            elif isinstance(authors_data, dict):
                authors = [authors_data.get("text", "")]
                
            # Extract other fields
            title = info.get("title", "")
            year = info.get("year", "")
            venue = info.get("venue", "")
            url = info.get("url", "")
            doi = info.get("doi", "")
            
            # Clean title (DBLP titles often end with a dot)
            if title.endswith("."):
                title = title[:-1]
            
            return DBLPResult(
                title=title,
                authors=authors,
                year=year,
                venue=venue,
                url=url,
                doi=doi if doi else None
            )
            
        except Exception as e:
            self.logger.error("Error parsing DBLP response: %s", e, exc_info=True)
            return None
