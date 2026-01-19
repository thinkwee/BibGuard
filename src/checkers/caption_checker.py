"""
Caption placement checker.

Validates that:
- Table captions appear ABOVE the table content
- Figure captions appear BELOW the figure content
"""
import re
from typing import List

from .base import BaseChecker, CheckResult, CheckSeverity


class CaptionChecker(BaseChecker):
    """Check for correct caption placement in tables and figures."""
    
    name = "caption"
    display_name = "Caption Placement"
    description = "Verify table captions are above and figure captions are below"
    
    # Patterns for environments
    TABLE_ENV_PATTERN = re.compile(
        r'\\begin\{table\*?\}(.*?)\\end\{table\*?\}',
        re.DOTALL | re.IGNORECASE
    )
    FIGURE_ENV_PATTERN = re.compile(
        r'\\begin\{figure\*?\}(.*?)\\end\{figure\*?\}',
        re.DOTALL | re.IGNORECASE
    )
    
    # Content patterns
    CAPTION_PATTERN = re.compile(r'\\caption\s*[\[{]')
    TABULAR_PATTERN = re.compile(r'\\begin\{tabular')
    INCLUDEGRAPHICS_PATTERN = re.compile(r'\\includegraphics')
    TIKZ_PATTERN = re.compile(r'\\begin\{tikzpicture\}')
    
    def check(self, tex_content: str, config: dict = None) -> List[CheckResult]:
        results = []
        
        # Check table environments
        for match in self.TABLE_ENV_PATTERN.finditer(tex_content):
            env_content = match.group(1)
            env_start = match.start()
            
            # Skip if commented
            if self._is_commented(tex_content, env_start):
                continue
            
            result = self._check_table_caption(env_content, tex_content, env_start)
            if result:
                results.append(result)
        
        # Check figure environments
        for match in self.FIGURE_ENV_PATTERN.finditer(tex_content):
            env_content = match.group(1)
            env_start = match.start()
            
            # Skip if commented
            if self._is_commented(tex_content, env_start):
                continue
            
            result = self._check_figure_caption(env_content, tex_content, env_start)
            if result:
                results.append(result)
        
        return results
    
    def _check_table_caption(self, env_content: str, full_content: str, env_start: int) -> CheckResult:
        """Check that table caption is above tabular content."""
        caption_match = self.CAPTION_PATTERN.search(env_content)
        tabular_match = self.TABULAR_PATTERN.search(env_content)
        
        if not caption_match:
            line_num = self._find_line_number(full_content, env_start)
            return self._create_result(
                passed=False,
                severity=CheckSeverity.WARNING,
                message="Table environment missing caption",
                line_number=line_num,
                suggestion="Add \\caption{} before \\begin{tabular}"
            )
        
        if not tabular_match:
            # Table without tabular content - skip
            return None
        
        # Caption should come BEFORE tabular
        if caption_match.start() > tabular_match.start():
            line_num = self._find_line_number(full_content, env_start + caption_match.start())
            return self._create_result(
                passed=False,
                severity=CheckSeverity.ERROR,
                message="Table caption should be placed ABOVE the table content",
                line_number=line_num,
                line_content=self._get_line_content(full_content, line_num),
                suggestion="Move \\caption{} before \\begin{tabular}"
            )
        
        return None
    
    def _check_figure_caption(self, env_content: str, full_content: str, env_start: int) -> CheckResult:
        """Check that figure caption is below image content."""
        caption_match = self.CAPTION_PATTERN.search(env_content)
        graphics_match = self.INCLUDEGRAPHICS_PATTERN.search(env_content)
        tikz_match = self.TIKZ_PATTERN.search(env_content)
        
        # Find the actual content (either graphics or tikz)
        content_match = graphics_match or tikz_match
        
        if not caption_match:
            line_num = self._find_line_number(full_content, env_start)
            return self._create_result(
                passed=False,
                severity=CheckSeverity.WARNING,
                message="Figure environment missing caption",
                line_number=line_num,
                suggestion="Add \\caption{} after \\includegraphics"
            )
        
        if not content_match:
            # Figure without graphics/tikz - could be custom content, skip
            return None
        
        # Caption should come AFTER content
        if caption_match.start() < content_match.start():
            line_num = self._find_line_number(full_content, env_start + caption_match.start())
            return self._create_result(
                passed=False,
                severity=CheckSeverity.ERROR,
                message="Figure caption should be placed BELOW the figure content",
                line_number=line_num,
                line_content=self._get_line_content(full_content, line_num),
                suggestion="Move \\caption{} after \\includegraphics"
            )
        
        return None
