"""
Field completeness checker for bibliography entries.
Validates required fields based on entry type.
"""
from dataclasses import dataclass
from typing import List, Dict, Set

from ..parsers.bib_parser import BibEntry


@dataclass
class FieldCompletenessResult:
    """Result of field completeness check."""
    entry_key: str
    entry_type: str
    missing_required: List[str]
    missing_recommended: List[str]
    is_complete: bool
    
    @property
    def has_issues(self) -> bool:
        """Check if there are any missing fields."""
        return len(self.missing_required) > 0 or len(self.missing_recommended) > 0


class FieldCompletenessChecker:
    """
    Checks if bibliography entries have all required fields.
    
    Based on BibTeX standards:
    https://www.bibtex.com/e/entry-types/
    """
    
    # Required fields by entry type
    REQUIRED_FIELDS: Dict[str, Set[str]] = {
        'article': {'author', 'title', 'journal', 'year'},
        'book': {'author', 'title', 'publisher', 'year'},  # author OR editor
        'inbook': {'author', 'title', 'publisher', 'year'},
        'incollection': {'author', 'title', 'booktitle', 'publisher', 'year'},
        'inproceedings': {'author', 'title', 'booktitle', 'year'},
        'conference': {'author', 'title', 'booktitle', 'year'},  # alias for inproceedings
        'mastersthesis': {'author', 'title', 'school', 'year'},
        'phdthesis': {'author', 'title', 'school', 'year'},
        'techreport': {'author', 'title', 'institution', 'year'},
        'manual': {'title'},
        'misc': set(),  # No required fields
        'unpublished': {'author', 'title', 'note'},
    }
    
    # Recommended (but not required) fields
    RECOMMENDED_FIELDS: Dict[str, Set[str]] = {
        'article': {'volume', 'pages', 'doi'},
        'book': {'isbn'},
        'inproceedings': {'pages', 'doi'},
        'conference': {'pages', 'doi'},
        'phdthesis': {'address'},
        'mastersthesis': {'address'},
    }
    
    def __init__(self):
        """Initialize checker."""
        pass
    
    def check_entry(self, entry: BibEntry) -> FieldCompletenessResult:
        """
        Check a single entry for field completeness.
        
        Args:
            entry: BibEntry to check
            
        Returns:
            FieldCompletenessResult with missing fields
        """
        entry_type = entry.entry_type.lower()
        
        # Get required fields for this type
        required = self.REQUIRED_FIELDS.get(entry_type, set())
        recommended = self.RECOMMENDED_FIELDS.get(entry_type, set())
        
        # Check which required fields are missing
        missing_required = []
        for field in required:
            if not self._has_field(entry, field):
                # Special case: book can have author OR editor
                if entry_type == 'book' and field == 'author':
                    if self._has_field(entry, 'editor'):
                        continue
                missing_required.append(field)
        
        # Check which recommended fields are missing
        missing_recommended = []
        for field in recommended:
            if not self._has_field(entry, field):
                missing_recommended.append(field)
        
        return FieldCompletenessResult(
            entry_key=entry.key,
            entry_type=entry_type,
            missing_required=missing_required,
            missing_recommended=missing_recommended,
            is_complete=len(missing_required) == 0
        )
    
    def check_all(self, entries: List[BibEntry]) -> List[FieldCompletenessResult]:
        """
        Check all entries for field completeness.
        
        Args:
            entries: List of BibEntry objects
            
        Returns:
            List of results (only entries with issues)
        """
        results = []
        for entry in entries:
            result = self.check_entry(entry)
            if result.has_issues:
                results.append(result)
        return results
    
    def _has_field(self, entry: BibEntry, field: str) -> bool:
        """Check if entry has a non-empty field."""
        # Map field name to BibEntry attribute
        field_mapping = {
            'author': 'author',
            'title': 'title',
            'year': 'year',
            'journal': 'journal',
            'booktitle': 'booktitle',
            'publisher': 'publisher',
            'volume': 'volume',
            'number': 'number',
            'pages': 'pages',
            'doi': 'doi',
            'url': 'url',
            'abstract': 'abstract',
        }
        
        # Direct attribute access
        if field in field_mapping:
            value = getattr(entry, field_mapping[field], '')
            return bool(value and value.strip())
        
        # Check raw_entry for other fields
        if field in entry.raw_entry:
            value = entry.raw_entry[field]
            return bool(value and str(value).strip())
        
        return False
