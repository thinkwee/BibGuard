"""
Formatting checker.

Validates common LaTeX formatting issues:
- Citation formatting consistency
- Non-breaking spaces before citations
- Special character escaping
- Whitespace issues
"""
import re
from typing import List

from .base import BaseChecker, CheckResult, CheckSeverity


class FormattingChecker(BaseChecker):
    """Check for common LaTeX formatting issues."""
    
    name = "formatting"
    display_name = "Formatting"
    description = "Check citation style, spacing, and special characters"
    
    # Citation commands
    CITE_COMMANDS = ['cite', 'citep', 'citet', 'citealt', 'citealp', 
                     'citeauthor', 'citeyear', 'autocite', 'textcite',
                     'parencite', 'footcite']
    
    # Pattern for citations without non-breaking space
    # Matches: "word \cite" but not "word~\cite"
    CITE_NO_NBSP_PATTERN = re.compile(r'(\w)\s+(\\cite\w*\{)')
    
    # Pattern for multiple consecutive spaces
    MULTI_SPACE_PATTERN = re.compile(r'(?<!\\)  +')
    
    # Pattern for unescaped special characters (outside math mode)
    SPECIAL_CHARS = {
        '%': r'(?<!\\)%',  # Unescaped %
        '&': r'(?<!\\)&(?![a-zA-Z]+;)',  # Unescaped & (not HTML entities)
        '#': r'(?<!\\)#',  # Unescaped #
        '_': r'(?<![\\$])_(?![^$]*\$)',  # Unescaped _ outside math
        '^': r'(?<![\\$])\^(?![^$]*\$)',  # Unescaped ^ outside math
    }
    
    # Multiple blank lines pattern (3 or more blank lines)
    MULTI_BLANK_PATTERN = re.compile(r'\n\s*\n\s*\n\s*\n')
    
    def check(self, tex_content: str, config: dict = None) -> List[CheckResult]:
        results = []
        lines = tex_content.split('\n')
        
        # Track citation style consistency
        cite_styles = {'parenthetical': 0, 'textual': 0, 'plain': 0}
        
        for line_num, line in enumerate(lines, 1):
            # Skip commented lines using base class method
            if self._is_comment_line(line):
                continue
            
            # Remove inline comments using base class method
            line_content = self._remove_line_comment(line)
            
            # Check citation non-breaking space
            for match in self.CITE_NO_NBSP_PATTERN.finditer(line_content):
                results.append(self._create_result(
                    passed=False,
                    severity=CheckSeverity.INFO,
                    message="Citation without non-breaking space",
                    line_number=line_num,
                    line_content=line.strip()[:100],
                    suggestion="Use ~ before \\cite (e.g., 'text~\\cite{key}')"
                ))
            
            # Track citation styles
            for cmd in self.CITE_COMMANDS:
                if re.search(rf'\\{cmd}\b', line_content):
                    if cmd in ['citep', 'parencite', 'autocite']:
                        cite_styles['parenthetical'] += 1
                    elif cmd in ['citet', 'textcite']:
                        cite_styles['textual'] += 1
                    elif cmd == 'cite':
                        cite_styles['plain'] += 1
        
        # Check citation style consistency
        styles_used = [s for s, count in cite_styles.items() if count > 0]
        if len(styles_used) > 1:
            results.append(self._create_result(
                passed=False,
                severity=CheckSeverity.INFO,
                message=f"Mixed citation styles detected: {', '.join(styles_used)}",
                suggestion="Consider using consistent citation style throughout"
            ))
        
        # Check for multiple blank lines (3 or more)
        for match in self.MULTI_BLANK_PATTERN.finditer(tex_content):
            line_num = self._find_line_number(tex_content, match.start())
            # Count how many blank lines
            blank_count = match.group(0).count('\n') - 1
            
            # Get context: the line before, blank lines, and the line after
            start_pos = match.start()
            end_pos = match.end()
            
            # Find the line before the blank lines
            prev_line_start = tex_content.rfind('\n', 0, start_pos) + 1
            prev_line_end = start_pos
            prev_line = tex_content[prev_line_start:prev_line_end].rstrip()
            
            # Find the line after the blank lines
            next_line_end = tex_content.find('\n', end_pos)
            if next_line_end == -1:
                next_line_end = len(tex_content)
            next_line = tex_content[end_pos:next_line_end].rstrip()
            
            # Create visual representation with warning markers
            blank_lines = '\n'.join([f"> blank line ⚠️"] * blank_count)
            line_content = f"{prev_line}\n{blank_lines}\n{next_line}"
            
            results.append(self._create_result(
                passed=False,
                severity=CheckSeverity.INFO,
                message=f"Multiple blank lines ({blank_count} consecutive blank lines)",
                line_number=line_num,
                line_content=line_content,
                suggestion="Reduce to single blank line or use \\vspace"
            ))
        
        # Check for common issues with special characters
        results.extend(self._check_special_chars(tex_content, lines))
        
        return results
    
    def _check_special_chars(self, content: str, lines: List[str]) -> List[CheckResult]:
        """Check for unescaped special characters."""
        results = []
        
        # Find math environments to skip
        math_regions = self._find_math_regions(content)
        
        for line_num, line in enumerate(lines, 1):
            # Skip commented lines using base class method
            if self._is_comment_line(line):
                continue
            
            # Remove inline comments using base class method
            line_content = self._remove_line_comment(line)
            
            # Get position of this line in full content
            line_start = sum(len(l) + 1 for l in lines[:line_num-1])
            
            # Check for unescaped & (common error)
            for match in re.finditer(r'(?<!\\)&(?![a-zA-Z]+;)', line_content):
                pos = line_start + match.start()
                # Skip if in math
                if not self._in_math_region(pos, math_regions):
                    # Also skip if inside tabular
                    if not self._in_environment(content, pos, ['tabular', 'array', 'align', 'matrix']):
                        results.append(self._create_result(
                            passed=False,
                            severity=CheckSeverity.WARNING,
                            message="Unescaped & outside tabular/math environment",
                            line_number=line_num,
                            line_content=line.strip()[:100],
                            suggestion="Use \\& to escape"
                        ))
        
        return results
    
    def _find_math_regions(self, content: str) -> List[tuple]:
        """Find regions that are inside math mode."""
        regions = []
        
        # Inline math $ ... $
        for match in re.finditer(r'(?<!\\)\$(?!\$)(.*?)(?<!\\)\$', content, re.DOTALL):
            regions.append((match.start(), match.end()))
        
        # Display math $$ ... $$
        for match in re.finditer(r'(?<!\\)\$\$(.*?)(?<!\\)\$\$', content, re.DOTALL):
            regions.append((match.start(), match.end()))
        
        # \[ ... \]
        for match in re.finditer(r'\\\[(.*?)\\\]', content, re.DOTALL):
            regions.append((match.start(), match.end()))
        
        # Math environments
        for env in ['equation', 'align', 'gather', 'multline', 'displaymath']:
            pattern = rf'\\begin\{{{env}\*?\}}(.*?)\\end\{{{env}\*?\}}'
            for match in re.finditer(pattern, content, re.DOTALL):
                regions.append((match.start(), match.end()))
        
        return regions
    
    def _in_math_region(self, pos: int, regions: List[tuple]) -> bool:
        """Check if position is inside a math region."""
        return any(start <= pos <= end for start, end in regions)
    
    def _in_environment(self, content: str, pos: int, env_names: List[str]) -> bool:
        """Check if position is inside any of the given environments."""
        for env in env_names:
            # Find all instances of this environment
            pattern = rf'\\begin\{{{env}\*?\}}(.*?)\\end\{{{env}\*?\}}'
            for match in re.finditer(pattern, content, re.DOTALL):
                if match.start() <= pos <= match.end():
                    return True
        return False
