import requests
import time
import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

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
        """
        Search DBLP by title.
        
        Args:
            title: Paper title to search for
            
        Returns:
            DBLPResult if found, None otherwise
        """
        self._wait_for_rate_limit()
        
        params = {
            "q": title,
            "format": "json",
            "h": 3  # Limit to top 3 hits
        }
        
        try:
            response = requests.get(self.BASE_URL, params=params, timeout=10)
            
            if response.status_code == 429:
                self.logger.warning("DBLP rate limit exceeded. Waiting longer...")
                time.sleep(5)
                return None
                
            if response.status_code != 200:
                self.logger.warning(f"DBLP API error: {response.status_code}")
                return None
                
            data = response.json()
            return self._parse_response(data, title)
            
        except Exception as e:
            self.logger.error(f"Error fetching from DBLP: {e}")
            return None

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
            self.logger.error(f"Error parsing DBLP response: {e}")
            return None
