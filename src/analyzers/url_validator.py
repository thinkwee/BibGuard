"""
URL and DOI validator.
Checks if URLs/DOIs are valid and accessible.
"""
import re
import time
from dataclasses import dataclass
from typing import Optional, List
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from ..parsers.bib_parser import BibEntry
from ..utils.logger import get_logger
from ..utils.cache import get_cache


@dataclass
class URLValidationResult:
    """Result of URL/DOI validation."""
    entry_key: str
    url: str
    url_type: str  # 'url', 'doi', 'arxiv'
    is_valid: bool
    status_code: Optional[int]
    error: Optional[str]


class URLValidator:
    """
    Validates URL and DOI accessibility.
    
    Performs HEAD requests to check if URLs are accessible.
    Validates DOI format and resolution.
    """
    
    DOI_PATTERN = re.compile(r'^10\.\d{4,}/[^\s]+$')
    ARXIV_PATTERN = re.compile(r'arxiv\.org/(abs|pdf)/(\d{4}\.\d{4,5}|[a-z-]+/\d+)')
    
    REQUEST_TIMEOUT = 10  # seconds
    MAX_WORKERS = 5
    
    def __init__(self):
        """Initialize validator."""
        self.logger = get_logger()
        self.cache = get_cache()
    
    def validate_entry(self, entry: BibEntry) -> List[URLValidationResult]:
        """
        Validate all URLs in a single entry.
        
        Args:
            entry: BibEntry to validate
            
        Returns:
            List of validation results
        """
        results = []
        
        # Check URL field
        if entry.url:
            result = self._validate_url(entry.key, entry.url, 'url')
            results.append(result)
        
        # Check DOI field
        if entry.doi:
            result = self._validate_doi(entry.key, entry.doi)
            results.append(result)
        
        # Check for arXiv URLs in various fields
        arxiv_url = self._extract_arxiv_url(entry)
        if arxiv_url:
            result = self._validate_url(entry.key, arxiv_url, 'arxiv')
            results.append(result)
        
        return results
    
    def validate_all(self, entries: List[BibEntry], max_workers: int = MAX_WORKERS) -> List[URLValidationResult]:
        """
        Validate all entries concurrently.
        
        Args:
            entries: List of entries to validate
            max_workers: Number of concurrent workers
            
        Returns:
            List of validation results (only invalid ones)
        """
        all_results = []
        
        # Collect all URLs to validate
        urls_to_check = []
        for entry in entries:
            if entry.url:
                urls_to_check.append((entry.key, entry.url, 'url'))
            if entry.doi:
                urls_to_check.append((entry.key, entry.doi, 'doi'))
        
        if not urls_to_check:
            return []
        
        # Validate concurrently
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {}
            for key, url, url_type in urls_to_check:
                if url_type == 'doi':
                    future = executor.submit(self._validate_doi, key, url)
                else:
                    future = executor.submit(self._validate_url, key, url, url_type)
                futures[future] = (key, url)
            
            for future in as_completed(futures):
                try:
                    result = future.result()
                    if not result.is_valid:
                        all_results.append(result)
                except Exception as e:
                    key, url = futures[future]
                    self.logger.error(f"Validation error for {key}: {e}")
        
        return all_results
    
    def _validate_url(self, entry_key: str, url: str, url_type: str) -> URLValidationResult:
        """Validate a URL by sending a HEAD request."""
        # Check cache
        cache_key = f"url:{url}"
        cached = self.cache.get("url", cache_key)
        if cached is not None:
            return URLValidationResult(
                entry_key=entry_key,
                url=url,
                url_type=url_type,
                is_valid=cached.get('is_valid', False),
                status_code=cached.get('status_code'),
                error=cached.get('error')
            )
        
        try:
            response = requests.head(
                url,
                timeout=self.REQUEST_TIMEOUT,
                allow_redirects=True,
                headers={'User-Agent': 'BibGuard/2.0'}
            )
            
            # Some servers don't support HEAD, try GET
            if response.status_code == 405:
                response = requests.get(
                    url,
                    timeout=self.REQUEST_TIMEOUT,
                    allow_redirects=True,
                    headers={'User-Agent': 'BibGuard/2.0'},
                    stream=True  # Don't download body
                )
            
            is_valid = response.status_code < 400
            result = URLValidationResult(
                entry_key=entry_key,
                url=url,
                url_type=url_type,
                is_valid=is_valid,
                status_code=response.status_code,
                error=None if is_valid else f"HTTP {response.status_code}"
            )
            
        except requests.Timeout:
            result = URLValidationResult(
                entry_key=entry_key,
                url=url,
                url_type=url_type,
                is_valid=False,
                status_code=None,
                error="Request timeout"
            )
        except requests.RequestException as e:
            result = URLValidationResult(
                entry_key=entry_key,
                url=url,
                url_type=url_type,
                is_valid=False,
                status_code=None,
                error=str(e)[:100]
            )
        
        # Cache result
        self.cache.set("url", cache_key, {
            'is_valid': result.is_valid,
            'status_code': result.status_code,
            'error': result.error
        })
        
        return result
    
    def _validate_doi(self, entry_key: str, doi: str) -> URLValidationResult:
        """Validate a DOI."""
        # Normalize DOI
        doi = doi.strip()
        if doi.startswith('https://doi.org/'):
            doi = doi[16:]
        elif doi.startswith('http://doi.org/'):
            doi = doi[15:]
        elif doi.startswith('doi:'):
            doi = doi[4:]
        
        # Check format
        if not self.DOI_PATTERN.match(doi):
            return URLValidationResult(
                entry_key=entry_key,
                url=doi,
                url_type='doi',
                is_valid=False,
                status_code=None,
                error="Invalid DOI format"
            )
        
        # Check resolution
        doi_url = f"https://doi.org/{doi}"
        return self._validate_url(entry_key, doi_url, 'doi')
    
    def _extract_arxiv_url(self, entry: BibEntry) -> Optional[str]:
        """Extract arXiv URL from entry if present."""
        # Check URL field
        if entry.url and 'arxiv.org' in entry.url:
            return entry.url
        
        # Check eprint field in raw entry
        eprint = entry.raw_entry.get('eprint', '')
        if eprint and 'arxiv' in entry.raw_entry.get('archiveprefix', '').lower():
            return f"https://arxiv.org/abs/{eprint}"
        
        return None
