"""
Semantic Scholar API fetcher.
Official API with high quality metadata and generous rate limits.
"""
import time
from dataclasses import dataclass
from typing import Optional

import requests


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
        Initialize Semantic Scholar fetcher.
        
        Args:
            api_key: Optional API key for higher rate limits (free from semanticscholar.org)
        """
        self.api_key = api_key
        self._last_request_time = 0.0
        self._session = requests.Session()
        
        if api_key:
            self._session.headers.update({'x-api-key': api_key})
    
    def _rate_limit(self):
        """Ensure rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.RATE_LIMIT_DELAY:
            time.sleep(self.RATE_LIMIT_DELAY - elapsed)
        self._last_request_time = time.time()
    
    def search_by_title(self, title: str, max_results: int = 5) -> Optional[SemanticScholarResult]:
        """
        Search for a paper by title.
        
        Args:
            title: Paper title to search for
            max_results: Maximum number of results to fetch (default: 5)
            
        Returns:
            SemanticScholarResult if found, None otherwise
        """
        self._rate_limit()
        
        url = f"{self.BASE_URL}/paper/search"
        params = {
            'query': title,
            'limit': max_results,
            'fields': 'title,authors,year,abstract,paperId,citationCount,url'
        }
        
        try:
            response = self._session.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            papers = data.get('data', [])
            if not papers:
                return None
            
            # Return the first (most relevant) result
            return self._parse_paper(papers[0])
            
        except requests.RequestException:
            return None
    
    def fetch_by_doi(self, doi: str) -> Optional[SemanticScholarResult]:
        """
        Fetch paper metadata by DOI.
        
        Args:
            doi: DOI of the paper
            
        Returns:
            SemanticScholarResult if found, None otherwise
        """
        self._rate_limit()
        
        url = f"{self.BASE_URL}/paper/DOI:{doi}"
        params = {
            'fields': 'title,authors,year,abstract,paperId,citationCount,url'
        }
        
        try:
            response = self._session.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            return self._parse_paper(data)
            
        except requests.RequestException:
            return None
    
    def fetch_by_arxiv_id(self, arxiv_id: str) -> Optional[SemanticScholarResult]:
        """
        Fetch paper metadata by arXiv ID.
        
        Args:
            arxiv_id: arXiv ID (e.g., "2301.12345" or "arXiv:2301.12345")
            
        Returns:
            SemanticScholarResult if found, None otherwise
        """
        self._rate_limit()
        
        # Clean arXiv ID (remove "arXiv:" prefix if present)
        clean_id = arxiv_id.replace('arXiv:', '')
        
        url = f"{self.BASE_URL}/paper/ARXIV:{clean_id}"
        params = {
            'fields': 'title,authors,year,abstract,paperId,citationCount,url'
        }
        
        try:
            response = self._session.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            return self._parse_paper(data)
            
        except requests.RequestException:
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
