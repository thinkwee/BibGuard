"""
Number and unit formatting checker.

Validates:
- Numbers 0-9 should be spelled out (except in formulas/tables)
- Consistent unit formatting (space between number and unit)
- Percentage format consistency
"""
import re
from typing import List

from .base import BaseChecker, CheckResult, CheckSeverity


class NumberChecker(BaseChecker):
    """Check number and unit formatting."""
    
    name = "number"
    display_name = "Numbers & Units"
    description = "Check number spelling and unit formatting"
    
    # Small numbers that should be spelled out
    SMALL_NUMBERS = re.compile(r'\b([0-9])\b(?!\s*[%°×\.\d])')
    
    # Units that should have space before them
    UNITS_NEED_SPACE = [
        'GB', 'MB', 'KB', 'TB', 'PB',  # Storage
        'GHz', 'MHz', 'kHz', 'Hz',  # Frequency
        'ms', 'ns', 'μs', 'us',  # Time
        'km', 'cm', 'mm', 'm',  # Length (careful with 'm')
        'kg', 'mg', 'g',  # Weight
        'FLOPs', 'FLOPS', 'GFLOPS', 'TFLOPS',  # Compute
        'K', 'M', 'B', 'T',  # Large number suffixes
    ]
    
    # Pattern for number directly attached to unit (no space)
    NO_SPACE_PATTERN = None  # Built in __init__
    
    # Percentage patterns
    PERCENT_WITH_SPACE = re.compile(r'\d\s+%')  # "50 %" is wrong
    
    # Inconsistent percentage usage
    PERCENT_WORD = re.compile(r'\d+\s+percent\b', re.IGNORECASE)
    PERCENT_SYMBOL = re.compile(r'\d+%')
    
    def __init__(self):
        super().__init__()
        # Build pattern for units without space
        units_pattern = '|'.join(re.escape(u) for u in self.UNITS_NEED_SPACE)
        self.NO_SPACE_PATTERN = re.compile(rf'(\d)({units_pattern})\b')
    
    def check(self, tex_content: str, config: dict = None) -> List[CheckResult]:
        results = []
        lines = tex_content.split('\n')
        
        # Track percentage style for consistency check
        uses_symbol = False
        uses_word = False
        
        for line_num, line in enumerate(lines, 1):
            # Skip comments using base class method
            if self._is_comment_line(line):
                continue
            
            # Skip lines that are likely in math/tables
            if self._in_special_context(line):
                continue
            
            # Skip lines that look like math formulas (contain common math commands)
            if re.search(r'\\(frac|sum|prod|int|partial|nabla|approx|neq|leq|geq|log|ln|exp|sin|cos|tan|alpha|beta|gamma|delta|theta|sigma|omega|left|right)', line):
                continue
            
            line_content = re.sub(r'(?<!\\)%.*$', '', line)
            
            # Check for space before percent sign
            for match in self.PERCENT_WITH_SPACE.finditer(line_content):
                results.append(self._create_result(
                    passed=False,
                    severity=CheckSeverity.WARNING,
                    message="Space before percent sign",
                    line_number=line_num,
                    suggestion="Remove space: '50%' not '50 %'"
                ))
            
            # Track percentage style
            if self.PERCENT_WORD.search(line_content):
                uses_word = True
            if self.PERCENT_SYMBOL.search(line_content):
                uses_symbol = True
        
        # Check percentage consistency
        if uses_word and uses_symbol:
            results.append(self._create_result(
                passed=False,
                severity=CheckSeverity.INFO,
                message="Mixed percentage notation: both '%' and 'percent' used",
                suggestion="Use consistent notation throughout the paper"
            ))
        
        return results
    
    def _in_special_context(self, line: str) -> bool:
        """Check if line is in a context where number rules don't apply."""
        special_patterns = [
            r'\\begin\{(tabular|array|equation|align|gather)',
            r'\\includegraphics',
            r'\\caption',
            r'\\label',
            r'\\ref',
            r'^\s*&',  # Table cell
            r'\$.*\$',  # Inline math
        ]
        return any(re.search(p, line) for p in special_patterns)
