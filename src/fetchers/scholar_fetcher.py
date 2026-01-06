"""
Google Scholar search (scraping-based fallback).
"""
import re
import time
import random
from dataclasses import dataclass
from typing import Optional

import requests
from bs4 import BeautifulSoup


@dataclass
class ScholarResult:
    """Search result from Google Scholar."""
    title: str
    authors: str
    year: str
    snippet: str
    url: str
    cited_by: int
    

class ScholarFetcher:
    """
    Fallback fetcher using Google Scholar search.
    
    Note: This uses scraping and may be blocked. 
    Use rate limiting and respect robots.txt.
    """
    
    SEARCH_URL = "https://scholar.google.com/scholar"
    RATE_LIMIT_DELAY = 10.0  # Conservative delay to avoid blocking (was 5.0)
    MAX_RETRIES = 2  # Retry on failures
    
    USER_AGENTS = [
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0',
    ]
    
    def __init__(self):
        self._last_request_time = 0.0
        self._session = requests.Session()
        self._request_count = 0
        self._blocked = False  # Track if we've been blocked
    
    def _rate_limit(self):
        """Ensure rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        # Add more randomness to avoid detection (3-5 seconds extra)
        delay = self.RATE_LIMIT_DELAY + random.uniform(3, 5)
        if elapsed < delay:
            time.sleep(delay - elapsed)
        self._last_request_time = time.time()
    
    def _get_headers(self) -> dict:
        """Get request headers with random user agent."""
        return {
            'User-Agent': random.choice(self.USER_AGENTS),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
    
    def search(self, query: str, max_results: int = 5) -> list[ScholarResult]:
        """
        Search Google Scholar.
        
        Returns list of search results.
        Note: This may fail if blocked by Google.
        """
        # If we've been blocked, don't waste time
        if self._blocked:
            return []
        
        self._rate_limit()
        self._request_count += 1
        
        params = {
            'q': query,
            'hl': 'en',
            'num': min(max_results, 10)  # Scholar max is 10 per page
        }
        
        try:
            response = self._session.get(
                self.SEARCH_URL,
                params=params,
                headers=self._get_headers(),
                timeout=30
            )
            response.raise_for_status()
        except requests.RequestException as e:
            return []
        
        # Check if we're blocked
        if 'unusual traffic' in response.text.lower() or response.status_code == 429:
            self._blocked = True
            print(f"⚠️  Google Scholar blocked after {self._request_count} requests. Skipping further Scholar queries.")
            return []
        
        return self._parse_results(response.text, max_results)
    
    def search_by_title(self, title: str) -> Optional[ScholarResult]:
        """Search for a specific paper by title."""
        # Use quotes for exact title match
        query = f'"{title}"'
        results = self.search(query, max_results=3)
        
        if not results:
            # Try without quotes
            results = self.search(title, max_results=5)
        
        return results[0] if results else None
    
    def _parse_results(self, html: str, max_results: int) -> list[ScholarResult]:
        """Parse search results from HTML."""
        results = []
        soup = BeautifulSoup(html, 'lxml')
        
        # Find all result entries
        entries = soup.find_all('div', class_='gs_ri')
        
        for entry in entries[:max_results]:
            try:
                result = self._parse_entry(entry)
                if result:
                    results.append(result)
            except Exception:
                continue
        
        return results
    
    def _parse_entry(self, entry) -> Optional[ScholarResult]:
        """Parse a single search result entry."""
        # Get title
        title_elem = entry.find('h3', class_='gs_rt')
        if not title_elem:
            return None
        
        # Get title text and URL
        title_link = title_elem.find('a')
        if title_link:
            title = title_link.get_text(strip=True)
            url = title_link.get('href', '')
        else:
            title = title_elem.get_text(strip=True)
            url = ''
        
        # Clean title (remove [PDF], [HTML] markers)
        title = re.sub(r'^\[(PDF|HTML|BOOK|CITATION)\]\s*', '', title)
        
        # Get authors and year from the green line
        meta_elem = entry.find('div', class_='gs_a')
        authors = ""
        year = ""
        
        if meta_elem:
            meta_text = meta_elem.get_text(strip=True)
            
            # Extract year first
            year_match = re.search(r'\b(19|20)\d{2}\b', meta_text)
            if year_match:
                year = year_match.group(0)
            
            # Parse authors more carefully
            # Format is usually: "Author1, Author2 - Journal, Year - Publisher"
            # or sometimes: "Author1, Author2 - Journal/Conference - Year"
            parts = meta_text.split(' - ')
            if parts:
                author_part = parts[0].strip()
                
                # Clean up author field - remove year if it leaked in
                if year:
                    # Remove year and anything after it from author field
                    author_part = re.sub(r',?\s*' + re.escape(year) + r'.*$', '', author_part)
                
                # Remove common journal/venue keywords that might have leaked
                # Handle patterns like "the journal of", "the proceedings", etc.
                author_part = re.sub(r'\s+the\s+(journal|proceedings|conference|symposium|workshop|transactions|magazine|review|annals)\s+.*$', '', author_part, flags=re.IGNORECASE)
                
                # Also handle without "the" prefix
                author_part = re.sub(r'\s+(journal|proceedings|conference|symposium|workshop|transactions|magazine|review|annals)\s+.*$', '', author_part, flags=re.IGNORECASE)
                
                # Remove standalone "the" at the end (in case it's left over)
                author_part = re.sub(r'\s+the\s*$', '', author_part, flags=re.IGNORECASE)
                
                # Remove trailing commas and whitespace
                author_part = author_part.rstrip(', ').strip()
                
                authors = author_part
        
        # Get snippet
        snippet_elem = entry.find('div', class_='gs_rs')
        snippet = snippet_elem.get_text(strip=True) if snippet_elem else ""
        
        # Get cited by count
        cited_by = 0
        cited_elem = entry.find('a', string=re.compile(r'Cited by \d+'))
        if cited_elem:
            match = re.search(r'Cited by (\d+)', cited_elem.get_text())
            if match:
                cited_by = int(match.group(1))
        
        return ScholarResult(
            title=title,
            authors=authors,
            year=year,
            snippet=snippet,
            url=url,
            cited_by=cited_by
        )
