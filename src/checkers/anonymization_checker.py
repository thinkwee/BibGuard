"""
Anonymization checker.

For double-blind review submissions, checks for:
- Author name leaks in acknowledgments
- Personal URLs (GitHub, personal pages)
- Self-citations that reveal identity
- Institutional information in comments
"""
import re
from typing import List

from .base import BaseChecker, CheckResult, CheckSeverity


class AnonymizationChecker(BaseChecker):
    """Check for anonymization issues in double-blind submissions."""
    
    name = "anonymization"
    display_name = "Anonymization"
    description = "Detect potential identity leaks in double-blind submissions"
    
    # Patterns for identity-revealing content
    PERSONAL_URL_PATTERNS = [
        (r'github\.com/[a-zA-Z0-9_-]+', "GitHub profile URL"),
        (r'gitlab\.com/[a-zA-Z0-9_-]+', "GitLab profile URL"),
        (r'twitter\.com/[a-zA-Z0-9_]+', "Twitter profile URL"),
        (r'linkedin\.com/in/[a-zA-Z0-9_-]+', "LinkedIn profile URL"),
        (r'huggingface\.co/[a-zA-Z0-9_-]+', "HuggingFace profile URL"),
        (r'~[a-zA-Z]+/', "Personal university page"),
        (r'people\.[a-zA-Z]+\.edu', "Academic personal page"),
        (r'homes\.[a-zA-Z]+\.(edu|ac\.[a-z]+)', "Academic home page"),
    ]
    
    # Anonymous submission indicators (should be present)
    ANONYMOUS_MARKERS = [
        r'\\author\{[^}]*anonymous[^}]*\}',
        r'anonymous\s+submission',
        r'\\runningauthor\{[^}]*\}',  # Should be empty or generic
    ]
    
    # Potentially revealing patterns
    SELF_CITE_PATTERNS = [
        r'\\cite[pt]?\{[^}]*\}\s*(?:show|demonstrate|propose|present|introduce)',
        r'(?:our|we)\s+(?:previous|prior|earlier)\s+(?:work|paper|study)',
        r'(?:as\s+)?(?:we|the\s+authors?)\s+(?:have\s+)?(?:shown|demonstrated|proved)',
    ]
    
    # Acknowledgment patterns
    ACK_PATTERN = re.compile(
        r'\\(?:section\*?\{acknowledgment|begin\{ack)',
        re.IGNORECASE
    )
    
    def check(self, tex_content: str, config: dict = None) -> List[CheckResult]:
        results = []
        lines = tex_content.split('\n')
        
        # Check if this is a review submission (look for anonymous author)
        is_review_version = self._is_review_version(tex_content)
        
        if not is_review_version:
            # If camera-ready, skip anonymization checks
            results.append(self._create_result(
                passed=True,
                severity=CheckSeverity.INFO,
                message="Document appears to be camera-ready version (not checking anonymization)"
            ))
            return results
        
        # Check for personal URLs
        for line_num, line in enumerate(lines, 1):
            # Skip comments, but still check for leaks in comments!
            if self._is_comment_line(line):
                for pattern, desc in self.PERSONAL_URL_PATTERNS:
                    if re.search(pattern, line, re.IGNORECASE):
                        results.append(self._create_result(
                            passed=False,
                            severity=CheckSeverity.WARNING,
                            message=f"{desc} in comment (could be revealed when compiling)",
                            line_number=line_num,
                            line_content=line.strip()[:100],
                            suggestion="Remove or anonymize URL even in comments"
                        ))
                continue
            
            for pattern, desc in self.PERSONAL_URL_PATTERNS:
                if re.search(pattern, line, re.IGNORECASE):
                    results.append(self._create_result(
                        passed=False,
                        severity=CheckSeverity.ERROR,
                        message=f"{desc} may reveal author identity",
                        line_number=line_num,
                        line_content=line.strip()[:100],
                        suggestion="Replace with anonymized URL or remove for review"
                    ))
        
        # Check acknowledgments section
        ack_results = self._check_acknowledgments(tex_content, lines)
        results.extend(ack_results)
        
        # Check for self-revealing citations
        for line_num, line in enumerate(lines, 1):
            # Skip comments using base class method
            if self._is_comment_line(line):
                continue
            
            for pattern in self.SELF_CITE_PATTERNS:
                if re.search(pattern, line, re.IGNORECASE):
                    results.append(self._create_result(
                        passed=False,
                        severity=CheckSeverity.WARNING,
                        message="Potentially self-revealing citation pattern",
                        line_number=line_num,
                        line_content=line.strip()[:100],
                        suggestion="Rephrase to avoid revealing authorship (e.g., 'Prior work shows...')"
                    ))
        
        # Check for \author content
        author_results = self._check_author_field(tex_content)
        results.extend(author_results)
        
        return results
    
    def _is_review_version(self, content: str) -> bool:
        """Detect if this is a review (anonymous) version."""
        # Check for common anonymous submission markers
        review_indicators = [
            r'review',
            r'submitted\s+to',
            r'under\s+review',
            r'anonymous',
            r'\\usepackage\[review\]',
        ]
        
        for indicator in review_indicators:
            if re.search(indicator, content[:2000], re.IGNORECASE):
                return True
        
        # Check for camera-ready indicators (negative)
        camera_indicators = [
            r'\\usepackage\[accepted\]',
            r'\\usepackage\[final\]',
            r'camera[\s-]?ready',
        ]
        
        for indicator in camera_indicators:
            if re.search(indicator, content[:2000], re.IGNORECASE):
                return False
        
        # Default to review version (safer)
        return True
    
    def _check_acknowledgments(self, content: str, lines: List[str]) -> List[CheckResult]:
        """Check acknowledgments section for identity leaks."""
        results = []
        
        # Find acknowledgment section
        ack_match = self.ACK_PATTERN.search(content)
        if not ack_match:
            return results
        
        # Find the line number
        ack_line = self._find_line_number(content, ack_match.start())
        
        # Check if it's commented out
        actual_line = lines[ack_line - 1] if ack_line <= len(lines) else ""
        if not actual_line.lstrip().startswith('%'):
            results.append(self._create_result(
                passed=False,
                severity=CheckSeverity.WARNING,
                message="Acknowledgments section found - should be commented out for review",
                line_number=ack_line,
                suggestion="Comment out acknowledgments with % for anonymous submission"
            ))
        
        return results
    
    def _check_author_field(self, content: str) -> List[CheckResult]:
        """Check \\author{} field for revealing content."""
        results = []
        
        # Find \author{...} - handle multiline
        author_pattern = re.compile(r'\\author\s*\{', re.DOTALL)
        match = author_pattern.search(content)
        
        if match:
            # Extract author content (handle nested braces)
            start = match.end()
            brace_count = 1
            i = start
            while i < len(content) and brace_count > 0:
                if content[i] == '{':
                    brace_count += 1
                elif content[i] == '}':
                    brace_count -= 1
                i += 1
            
            author_content = content[start:i-1]
            line_num = self._find_line_number(content, match.start())
            
            # Check if author content looks anonymous
            if not re.search(r'anonymous|author\s*names?\s*hidden', author_content, re.IGNORECASE):
                # Check if it's not using \Anonymous or similar
                if not re.search(r'\\(Anonymous|blindauthor)', author_content):
                    # Might contain real author info
                    if re.search(r'[A-Z][a-z]+\s+[A-Z][a-z]+', author_content):
                        results.append(self._create_result(
                            passed=False,
                            severity=CheckSeverity.ERROR,
                            message="Author field may contain real names",
                            line_number=line_num,
                            suggestion="Replace with 'Anonymous' or use anonymization command"
                        ))
        
        return results
