"""
CrossRef API fetcher.
Provides DOI verification and metadata lookup.
"""
import time
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict, Any

import requests

from ..utils.logger import get_logger
from ..utils.cache import get_cache


@dataclass
class CrossRefResult:
    """Paper metadata from CrossRef."""
    doi: str
    title: str
    authors: List[str]
    year: Optional[int]
    publisher: str
    container_title: str  # Journal or conference name
    type: str  # journal-article, proceedings-article, etc.
    url: str
    is_valid: bool
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for caching."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CrossRefResult':
        """Create from cached dictionary."""
        return cls(**data)


class CrossRefFetcher:
    """
    Fetches paper metadata from CrossRef API.
    
    API Docs: https://api.crossref.org/swagger-ui/index.html
    Rate limit: ~50 requests/second (with Polite pool)
    """
    
    API_BASE = "https://api.crossref.org"
    RATE_LIMIT_DELAY = 1.0  # Conservative rate limiting
    
    def __init__(self, email: Optional[str] = None):
        """
        Initialize fetcher.
        
        Args:
            email: Contact email for Polite pool (faster rate limits)
        """
        self.email = email or "bibguard@example.com"
        self._last_request_time = 0.0
        self.logger = get_logger()
        self.cache = get_cache()
    
    def _rate_limit(self) -> None:
        """Ensure rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.RATE_LIMIT_DELAY:
            time.sleep(self.RATE_LIMIT_DELAY - elapsed)
        self._last_request_time = time.time()
    
    def _get_headers(self) -> Dict[str, str]:
        """Get request headers with Polite pool identifier."""
        return {
            'User-Agent': f'BibGuard/2.0 (mailto:{self.email})',
            'Accept': 'application/json'
        }
    
    def fetch_by_doi(self, doi: str) -> Optional[CrossRefResult]:
        """
        Fetch paper metadata by DOI.
        
        Args:
            doi: Paper DOI (e.g., '10.1000/xyz123')
            
        Returns:
            Paper metadata or None if not found
        """
        # Normalize DOI
        doi = doi.strip()
        if doi.startswith('https://doi.org/'):
            doi = doi[16:]
        elif doi.startswith('http://doi.org/'):
            doi = doi[15:]
        elif doi.startswith('doi:'):
            doi = doi[4:]
        
        # Check cache
        cache_key = f"doi:{doi}"
        cached = self.cache.get("crossref", cache_key)
        if cached:
            return CrossRefResult.from_dict(cached)
        
        self._rate_limit()
        
        try:
            response = requests.get(
                f"{self.API_BASE}/works/{doi}",
                headers=self._get_headers(),
                timeout=30
            )
            
            if response.status_code == 404:
                self.logger.info(f"DOI not found in CrossRef: {doi}")
                return None
            
            response.raise_for_status()
            data = response.json()
            
        except requests.RequestException as e:
            self.logger.error(f"CrossRef DOI lookup failed for '{doi}': {e}")
            return None
        
        result = self._parse_work(data.get('message', {}), doi)
        if result:
            self.cache.set("crossref", cache_key, result.to_dict())
        
        return result
    
    def search_by_title(self, title: str, limit: int = 5) -> List[CrossRefResult]:
        """
        Search for papers by title.
        
        Args:
            title: Paper title
            limit: Maximum results
            
        Returns:
            List of matching papers
        """
        # Check cache
        cache_key = f"search:{title}"
        cached = self.cache.get("crossref", cache_key)
        if cached:
            return [CrossRefResult.from_dict(r) for r in cached]
        
        self._rate_limit()
        
        params = {
            'query.title': title,
            'rows': limit,
            'select': 'DOI,title,author,published,publisher,container-title,type,URL'
        }
        
        try:
            response = requests.get(
                f"{self.API_BASE}/works",
                params=params,
                headers=self._get_headers(),
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            
        except requests.RequestException as e:
            self.logger.error(f"CrossRef search failed for '{title[:50]}': {e}")
            return []
        
        results = []
        for item in data.get('message', {}).get('items', []):
            doi = item.get('DOI', '')
            result = self._parse_work(item, doi)
            if result:
                results.append(result)
        
        # Cache results
        if results:
            self.cache.set("crossref", cache_key, [r.to_dict() for r in results])
        
        return results
    
    def verify_doi(self, doi: str) -> bool:
        """
        Verify if a DOI is valid and resolvable.
        
        Args:
            doi: DOI to verify
            
        Returns:
            True if valid, False otherwise
        """
        result = self.fetch_by_doi(doi)
        return result is not None and result.is_valid
    
    def _parse_work(self, data: Dict[str, Any], doi: str) -> Optional[CrossRefResult]:
        """Parse API response into result object."""
        try:
            # Extract title
            titles = data.get('title', [])
            title = titles[0] if titles else ''
            
            # Extract authors
            authors = []
            for author in data.get('author', []):
                given = author.get('given', '')
                family = author.get('family', '')
                if family:
                    name = f"{given} {family}".strip()
                    authors.append(name)
            
            # Extract year (try multiple date fields for better coverage)
            year = None
            for date_field in ['published', 'published-print', 'published-online', 'created']:
                date_data = data.get(date_field, {})
                date_parts = date_data.get('date-parts', [[]])
                if date_parts and date_parts[0]:
                    year = date_parts[0][0]
                    break
            
            # Extract container title (journal/conference)
            container_titles = data.get('container-title', [])
            container_title = container_titles[0] if container_titles else ''
            
            return CrossRefResult(
                doi=doi,
                title=title,
                authors=authors,
                year=year,
                publisher=data.get('publisher', ''),
                container_title=container_title,
                type=data.get('type', ''),
                url=data.get('URL', f'https://doi.org/{doi}'),
                is_valid=True
            )
            
        except Exception as e:
            self.logger.warning(f"Failed to parse CrossRef response: {e}")
            return None
