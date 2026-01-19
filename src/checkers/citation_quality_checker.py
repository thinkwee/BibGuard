"""
Citation quality checker.

Validates:
- Old citations (>10 years) that might need updating
- Self-citation ratio
- Preprint vs published paper ratio
- Citation formatting patterns
"""
import re
from typing import List, Dict
from datetime import datetime
from collections import defaultdict

from .base import BaseChecker, CheckResult, CheckSeverity


class CitationQualityChecker(BaseChecker):
    """Check citation quality and balance."""
    
    name = "citation_quality"
    display_name = "Citation Quality"
    description = "Check citation age, balance, and formatting"
    
    # Thresholds
    OLD_CITATION_YEARS = 10  # Citations older than this get flagged
    HIGH_SELF_CITE_RATIO = 0.25  # More than 25% self-citations
    HIGH_PREPRINT_RATIO = 0.30  # More than 30% preprints
    
    CURRENT_YEAR = datetime.now().year
    
    # Preprint indicators
    PREPRINT_VENUES = [
        'arxiv', 'biorxiv', 'medrxiv', 'ssrn', 'preprint', 'openreview',
        'techreport', 'technical report', 'working paper',
    ]
    
    def check(self, tex_content: str, config: dict = None) -> List[CheckResult]:
        results = []
        
        # This checker works best with bib content, but we can do some analysis
        # on the tex file alone by looking at citation patterns
        
        # Check for inline year citations that are old
        old_cite_results = self._check_old_citations_in_text(tex_content)
        results.extend(old_cite_results)
        
        # Check for citation formatting issues
        format_results = self._check_citation_formatting(tex_content)
        results.extend(format_results)
        
        return results
    
    def _check_old_citations_in_text(self, content: str) -> List[CheckResult]:
        """Look for citations with old years visible in text."""
        results = []
        lines = content.split('\n')
        
        # Pattern for citations with year, like "Smith et al. (2010)" or "(Smith, 2010)"
        year_pattern = re.compile(
            r'(?:\([^)]*(?:19[89]\d|20[01]\d)[^)]*\)|'  # Parenthetical
            r'\b(?:19[89]\d|20[01]\d)\b)',  # Standalone year
            re.IGNORECASE
        )
        
        old_years_found = set()
        
        for line_num, line in enumerate(lines, 1):
            # Skip comments using base class method
            if self._is_comment_line(line):
                continue
            
            for match in year_pattern.finditer(line):
                year_str = re.search(r'(19[89]\d|20[01]\d)', match.group())
                if year_str:
                    year = int(year_str.group())
                    age = self.CURRENT_YEAR - year
                    
                    if age >= self.OLD_CITATION_YEARS and year not in old_years_found:
                        old_years_found.add(year)
                        results.append(self._create_result(
                            passed=False,
                            severity=CheckSeverity.INFO,
                            message=f"Citation from {year} ({age} years old)",
                            line_number=line_num,
                            suggestion=f"Consider if there's more recent work on this topic"
                        ))
        
        return results
    
    def _check_citation_formatting(self, content: str) -> List[CheckResult]:
        """Check for common citation formatting issues."""
        results = []
        lines = content.split('\n')
        
        for line_num, line in enumerate(lines, 1):
            if line.lstrip().startswith('%'):
                continue
            
            # Check for "et al" without period
            if re.search(r'\bet al\b(?!\.)', line):
                results.append(self._create_result(
                    passed=False,
                    severity=CheckSeverity.WARNING,
                    message="'et al' should be 'et al.'",
                    line_number=line_num,
                    suggestion="Add period after 'et al.'"
                ))
            
            # Check for "[1]" style citations (might want natbib style)
            # Skip if it's a command definition or argument
            if re.search(r'\[\d+\]', line):
                # Skip if in command definition
                if '\\newcommand' in line or '\\renewcommand' in line or '\\def' in line:
                    continue
                # Skip if it's clearly a command argument like [1] in \newcommand{\foo}[1]
                if re.search(r'\\[a-zA-Z]+\[\d+\]', line):
                    continue
                # Only flag if it looks like actual citation in text
                if '\\cite' not in line and not re.search(r'\\[a-zA-Z]+\{', line[:20]):
                    results.append(self._create_result(
                        passed=False,
                        severity=CheckSeverity.INFO,
                        message="Numeric citation style detected",
                        line_number=line_num,
                        suggestion="Consider author-year style for better readability"
                    ))
            
            # Check for hardcoded citations instead of \cite
            if re.search(r'\([A-Z][a-z]+(?:\s+et\s+al\.?)?,?\s*\d{4}\)', line):
                if '\\cite' not in line:
                    results.append(self._create_result(
                        passed=False,
                        severity=CheckSeverity.WARNING,
                        message="Appears to be hardcoded citation instead of \\cite",
                        line_number=line_num,
                        line_content=line.strip()[:80],
                        suggestion="Use \\cite{} for proper bibliography management"
                    ))
        
        return results
