"""
arXiv metadata fetcher using the public API.
"""
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict, Any
from urllib.parse import quote

import requests

from ..utils.logger import get_logger
from ..utils.cache import get_cache


@dataclass
class ArxivMetadata:
    """Metadata fetched from arXiv."""
    arxiv_id: str
    title: str
    authors: List[str]
    abstract: str
    published: str
    updated: str
    categories: List[str]
    primary_category: str
    doi: str
    journal_ref: str
    comment: str
    pdf_url: str
    abs_url: str
    
    @property
    def year(self) -> str:
        """Extract year from published date."""
        if self.published:
            match = re.match(r'(\d{4})', self.published)
            if match:
                return match.group(1)
        return ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for caching."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ArxivMetadata':
        """Create from cached dictionary."""
        return cls(**data)


class ArxivFetcher:
    """Fetches metadata from arXiv API."""
    
    API_BASE = "http://export.arxiv.org/api/query"
    RATE_LIMIT_DELAY = 3.0  # seconds between requests
    
    def __init__(self) -> None:
        self._last_request_time: float = 0.0
        self.logger = get_logger()
        self.cache = get_cache()
    
    def _rate_limit(self) -> None:
        """Ensure rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.RATE_LIMIT_DELAY:
            time.sleep(self.RATE_LIMIT_DELAY - elapsed)
        self._last_request_time = time.time()
    
    def fetch_by_id(self, arxiv_id: str) -> Optional[ArxivMetadata]:
        """Fetch metadata by arXiv ID."""
        # Clean up ID
        arxiv_id = arxiv_id.strip()
        arxiv_id = re.sub(r'^arXiv:', '', arxiv_id, flags=re.IGNORECASE)
        
        # Check cache
        cache_key = f"id:{arxiv_id}"
        cached = self.cache.get("arxiv", cache_key)
        if cached:
            return ArxivMetadata.from_dict(cached)
        
        self._rate_limit()
        
        params = {
            'id_list': arxiv_id,
            'max_results': 1
        }
        
        try:
            response = requests.get(
                self.API_BASE,
                params=params,
                timeout=30,
                headers={'User-Agent': 'BibGuard/2.0 (mailto:user@example.com)'}
            )
            response.raise_for_status()
        except requests.RequestException as e:
            self.logger.error(f"arXiv fetch failed for ID '{arxiv_id}': {e}")
            return None
        
        result = self._parse_response(response.text)
        
        # Cache result
        if result:
            self.cache.set("arxiv", cache_key, result.to_dict())
        
        return result
    
    def search_by_title(self, title: str, max_results: int = 5) -> List[ArxivMetadata]:
        """Search arXiv by title."""
        # Check cache
        cache_key = f"search:{title}"
        cached = self.cache.get("arxiv", cache_key)
        if cached:
            return [ArxivMetadata.from_dict(r) for r in cached]
        
        self._rate_limit()
        
        # Clean up title for search
        clean_title = re.sub(r'[^\w\s]', ' ', title)
        clean_title = re.sub(r'\s+', ' ', clean_title).strip()
        
        # Build search query
        search_query = f'ti:"{clean_title}"'
        
        params = {
            'search_query': search_query,
            'max_results': max_results,
            'sortBy': 'relevance',
            'sortOrder': 'descending'
        }
        
        try:
            response = requests.get(
                self.API_BASE,
                params=params,
                timeout=30,
                headers={'User-Agent': 'BibGuard/2.0 (mailto:user@example.com)'}
            )
            response.raise_for_status()
        except requests.RequestException as e:
            self.logger.error(f"arXiv search failed for '{title[:50]}': {e}")
            return []
        
        results = self._parse_response_multiple(response.text)
        
        # Cache results
        if results:
            self.cache.set("arxiv", cache_key, [r.to_dict() for r in results])
        
        return results
    
    def _parse_response(self, xml_content: str) -> Optional[ArxivMetadata]:
        """Parse single entry response."""
        results = self._parse_response_multiple(xml_content)
        return results[0] if results else None
    
    def _parse_response_multiple(self, xml_content: str) -> List[ArxivMetadata]:
        """Parse multiple entries from response."""
        results: List[ArxivMetadata] = []
        results = []
        
        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError:
            return results
        
        # Define namespaces
        ns = {
            'atom': 'http://www.w3.org/2005/Atom',
            'arxiv': 'http://arxiv.org/schemas/atom'
        }
        
        entries = root.findall('atom:entry', ns)
        
        for entry in entries:
            try:
                metadata = self._parse_entry(entry, ns)
                if metadata:
                    results.append(metadata)
            except Exception:
                continue
        
        return results
    
    def _parse_entry(self, entry: ET.Element, ns: dict) -> Optional[ArxivMetadata]:
        """Parse a single entry element."""
        # Get ID
        id_elem = entry.find('atom:id', ns)
        if id_elem is None or id_elem.text is None:
            return None
        
        abs_url = id_elem.text.strip()
        
        # Extract arXiv ID from URL
        match = re.search(r'arxiv\.org/abs/(.+)$', abs_url)
        arxiv_id = match.group(1) if match else ""
        
        # Get title
        title_elem = entry.find('atom:title', ns)
        title = self._clean_text(title_elem.text) if title_elem is not None and title_elem.text else ""
        
        # Get abstract
        summary_elem = entry.find('atom:summary', ns)
        abstract = self._clean_text(summary_elem.text) if summary_elem is not None and summary_elem.text else ""
        
        # Get authors
        authors = []
        for author_elem in entry.findall('atom:author', ns):
            name_elem = author_elem.find('atom:name', ns)
            if name_elem is not None and name_elem.text:
                authors.append(name_elem.text.strip())
        
        # Get dates
        published_elem = entry.find('atom:published', ns)
        published = published_elem.text.strip() if published_elem is not None and published_elem.text else ""
        
        updated_elem = entry.find('atom:updated', ns)
        updated = updated_elem.text.strip() if updated_elem is not None and updated_elem.text else ""
        
        # Get categories
        categories = []
        for cat_elem in entry.findall('atom:category', ns):
            term = cat_elem.get('term')
            if term:
                categories.append(term)
        
        primary_cat_elem = entry.find('arxiv:primary_category', ns)
        primary_category = primary_cat_elem.get('term', '') if primary_cat_elem is not None else ""
        
        # Get DOI
        doi_elem = entry.find('arxiv:doi', ns)
        doi = doi_elem.text.strip() if doi_elem is not None and doi_elem.text else ""
        
        # Get journal reference
        journal_elem = entry.find('arxiv:journal_ref', ns)
        journal_ref = journal_elem.text.strip() if journal_elem is not None and journal_elem.text else ""
        
        # Get comment
        comment_elem = entry.find('arxiv:comment', ns)
        comment = comment_elem.text.strip() if comment_elem is not None and comment_elem.text else ""
        
        # Build PDF URL
        pdf_url = abs_url.replace('/abs/', '/pdf/') + '.pdf'
        
        return ArxivMetadata(
            arxiv_id=arxiv_id,
            title=title,
            authors=authors,
            abstract=abstract,
            published=published,
            updated=updated,
            categories=categories,
            primary_category=primary_category,
            doi=doi,
            journal_ref=journal_ref,
            comment=comment,
            pdf_url=pdf_url,
            abs_url=abs_url
        )
    
    def _clean_text(self, text: str) -> str:
        """Clean up text from XML."""
        if not text:
            return ""
        # Normalize whitespace
        text = re.sub(r'\s+', ' ', text)
        return text.strip()
