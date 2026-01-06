"""
OpenAlex API fetcher.
Free and open API for scholarly metadata.
"""
import time
from dataclasses import dataclass
from typing import Optional

import requests


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
        """
        Initialize OpenAlex fetcher.
        
        Args:
            email: Optional email for polite pool (faster rate limits)
        """
        self.email = email
        self._last_request_time = 0.0
        self._session = requests.Session()
        
        # Set user agent (required by OpenAlex)
        self._session.headers.update({
            'User-Agent': 'BibGuard/1.0 (https://github.com/thinkwee/BibGuard; mailto:bibguard@example.com)'
        })
        
        # Add email to polite pool if provided
        if email:
            self._session.headers.update({'From': email})
    
    def _rate_limit(self):
        """Ensure rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.RATE_LIMIT_DELAY:
            time.sleep(self.RATE_LIMIT_DELAY - elapsed)
        self._last_request_time = time.time()
    
    def search_by_title(self, title: str, max_results: int = 5) -> Optional[OpenAlexResult]:
        """
        Search for a paper by title.
        
        Args:
            title: Paper title to search for
            max_results: Maximum number of results to fetch (default: 5)
            
        Returns:
            OpenAlexResult if found, None otherwise
        """
        self._rate_limit()
        
        url = f"{self.BASE_URL}/works"
        params = {
            'search': title,
            'per-page': max_results
        }
        
        try:
            response = self._session.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            results = data.get('results', [])
            if not results:
                return None
            
            # Return the first (most relevant) result
            return self._parse_work(results[0])
            
        except requests.RequestException:
            return None
    
    def fetch_by_doi(self, doi: str) -> Optional[OpenAlexResult]:
        """
        Fetch paper metadata by DOI.
        
        Args:
            doi: DOI of the paper
            
        Returns:
            OpenAlexResult if found, None otherwise
        """
        self._rate_limit()
        
        # OpenAlex uses DOI URLs
        doi_url = f"https://doi.org/{doi}"
        url = f"{self.BASE_URL}/works/{doi_url}"
        
        try:
            response = self._session.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            return self._parse_work(data)
            
        except requests.RequestException:
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
