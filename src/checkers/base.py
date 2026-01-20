"""
Base checker class for paper submission quality checks.

All specific checkers inherit from BaseChecker and implement
the check() method to validate specific aspects of the TeX document.
"""
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple


class CheckSeverity(Enum):
    """Severity levels for check results."""
    ERROR = "error"         # Must fix before submission
    WARNING = "warning"     # Strongly recommended to fix
    INFO = "info"           # Suggestion or best practice


@dataclass
class CheckResult:
    """Result of a single check."""
    checker_name: str
    passed: bool
    severity: CheckSeverity
    message: str
    line_number: Optional[int] = None
    line_content: Optional[str] = None
    suggestion: Optional[str] = None
    file_path: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            'checker': self.checker_name,
            'passed': self.passed,
            'severity': self.severity.value,
            'message': self.message,
            'line': self.line_number,
            'content': self.line_content,
            'suggestion': self.suggestion,
            'file_path': self.file_path
        }


class BaseChecker(ABC):
    """
    Abstract base class for all paper submission checkers.
    
    Each checker validates a specific aspect of the paper,
    such as caption placement, reference integrity, or formatting.
    """
    
    # Checker metadata - override in subclasses
    name: str = "base"
    display_name: str = "Base Checker"
    description: str = "Base checker class"
    
    @abstractmethod
    def check(self, tex_content: str, config: dict = None) -> List[CheckResult]:
        """
        Run the check on the given TeX content.
        
        Args:
            tex_content: The full content of the TeX file
            config: Optional configuration dict (e.g., conference-specific settings)
            
        Returns:
            List of CheckResult objects describing found issues
        """
        pass
    
    def _remove_comments(self, content: str) -> str:
        """
        Remove all LaTeX comments from content.
        
        Preserves line structure (replaces comment with empty string on same line).
        Handles escaped percent signs (\\%) correctly.
        """
        lines = content.split('\n')
        result = []
        
        for line in lines:
            # Find first unescaped % 
            cleaned = self._remove_line_comment(line)
            result.append(cleaned)
        
        return '\n'.join(result)
    
    def _remove_line_comment(self, line: str) -> str:
        """Remove comment from a single line, preserving content before %."""
        i = 0
        while i < len(line):
            if line[i] == '%':
                # Check if escaped
                num_backslashes = 0
                j = i - 1
                while j >= 0 and line[j] == '\\':
                    num_backslashes += 1
                    j -= 1
                if num_backslashes % 2 == 0:
                    # Not escaped, this is a comment start
                    return line[:i]
            i += 1
        return line
    
    def _is_comment_line(self, line: str) -> bool:
        """Check if a line is entirely a comment (starts with %)."""
        stripped = line.lstrip()
        if not stripped:
            return False
        return stripped[0] == '%'
    
    def _get_non_comment_lines(self, content: str) -> List[Tuple[int, str]]:
        """
        Get all non-comment lines with their line numbers.
        
        Returns:
            List of (line_number, line_content) tuples for non-comment lines.
            Line content has inline comments removed.
        """
        lines = content.split('\n')
        result = []
        
        for line_num, line in enumerate(lines, 1):
            # Skip pure comment lines
            if self._is_comment_line(line):
                continue
            
            # Remove inline comments
            cleaned = self._remove_line_comment(line)
            
            # Skip if nothing left after removing comment
            if not cleaned.strip():
                continue
            
            result.append((line_num, cleaned))
        
        return result
    
    def _find_line_number(self, content: str, position: int) -> int:
        """Find line number for a character position in content."""
        return content[:position].count('\n') + 1
    
    def _get_line_content(self, content: str, line_number: int) -> str:
        """Get the content of a specific line."""
        lines = content.split('\n')
        if 1 <= line_number <= len(lines):
            return lines[line_number - 1].strip()
        return ""
    
    def _is_commented(self, content: str, position: int) -> bool:
        """Check if a position is within a LaTeX comment."""
        # Find the start of the current line
        line_start = content.rfind('\n', 0, position) + 1
        line_before = content[line_start:position]
        
        # Check for unescaped % before this position on the same line
        i = 0
        while i < len(line_before):
            if line_before[i] == '%':
                # Check if escaped
                num_backslashes = 0
                j = i - 1
                while j >= 0 and line_before[j] == '\\':
                    num_backslashes += 1
                    j -= 1
                if num_backslashes % 2 == 0:
                    # Not escaped, this is a comment
                    return True
            i += 1
        return False
    
    def _create_result(
        self,
        passed: bool,
        severity: CheckSeverity,
        message: str,
        line_number: Optional[int] = None,
        line_content: Optional[str] = None,
        suggestion: Optional[str] = None
    ) -> CheckResult:
        """Helper to create a CheckResult with this checker's name."""
        return CheckResult(
            checker_name=self.name,
            passed=passed,
            severity=severity,
            message=message,
            line_number=line_number,
            line_content=line_content,
            suggestion=suggestion
        )

