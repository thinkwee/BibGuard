"""
CrossRef API fetcher for bibliography metadata.

CrossRef provides free, reliable access to metadata for academic publications.
No API key required, no rate limiting for reasonable use.
"""
import requests
from dataclasses import dataclass
from typing import Optional, List
import time


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
    
    def __init__(self, mailto: str = "bibguard@example.com"):
        """
        Initialize CrossRef fetcher.
        
        Args:
            mailto: Email for polite pool (gets better rate limits)
        """
        self.mailto = mailto
        self._last_request_time = 0.0
        self._session = requests.Session()
    
    def _rate_limit(self):
        """Ensure rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.RATE_LIMIT_DELAY:
            time.sleep(self.RATE_LIMIT_DELAY - elapsed)
        self._last_request_time = time.time()
    
    def _get_headers(self) -> dict:
        """Get request headers with mailto for polite pool."""
        return {
            'User-Agent': f'BibGuard/1.0 (mailto:{self.mailto})',
            'Accept': 'application/json',
        }
    
    def search_by_title(self, title: str, max_results: int = 5) -> Optional[CrossRefResult]:
        """
        Search for a paper by title.
        
        Args:
            title: Paper title to search for
            max_results: Maximum number of results to retrieve
            
        Returns:
            Best matching CrossRefResult or None if not found
        """
        self._rate_limit()
        
        params = {
            'query.title': title,
            'rows': max_results,
            'select': 'title,author,published-print,published-online,DOI,publisher,container-title,abstract'
        }
        
        try:
            response = self._session.get(
                self.BASE_URL,
                params=params,
                headers=self._get_headers(),
                timeout=30
            )
            response.raise_for_status()
            
            data = response.json()
            
            if data.get('status') != 'ok':
                return None
            
            items = data.get('message', {}).get('items', [])
            
            if not items:
                return None
            
            # Return best match (first result, as CrossRef ranks by relevance)
            return self._parse_item(items[0])
            
        except requests.RequestException:
            return None
    
    def search_by_doi(self, doi: str) -> Optional[CrossRefResult]:
        """
        Fetch metadata by DOI.
        
        Args:
            doi: DOI of the paper
            
        Returns:
            CrossRefResult or None if not found
        """
        self._rate_limit()
        
        # Clean DOI (remove https://doi.org/ prefix if present)
        doi = doi.replace('https://doi.org/', '').replace('http://doi.org/', '')
        
        try:
            response = self._session.get(
                f"{self.BASE_URL}/{doi}",
                headers=self._get_headers(),
                timeout=30
            )
            response.raise_for_status()
            
            data = response.json()
            
            if data.get('status') != 'ok':
                return None
            
            item = data.get('message', {})
            return self._parse_item(item)
            
        except requests.RequestException:
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
