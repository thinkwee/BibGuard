"""
Line-by-line report generator.

Generates a report that follows the TeX file structure,
showing issues in order of appearance in the document.
"""
import re
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, field
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from ..checkers.base import CheckResult, CheckSeverity


@dataclass
class LineIssue:
    """An issue associated with a specific line or range."""
    start_line: int
    end_line: int
    line_content: str
    issues: List[CheckResult] = field(default_factory=list)
    block_type: Optional[str] = None  # 'figure', 'table', 'equation', etc.


class LineByLineReportGenerator:
    """
    Generates a report organized by TeX file line order.
    
    Groups consecutive lines and special environments into blocks,
    then outputs issues in the order they appear in the document.
    """
    
    # LaTeX environments that should be grouped as blocks
    BLOCK_ENVIRONMENTS = [
        'figure', 'figure*', 'table', 'table*', 'tabular', 'tabular*',
        'equation', 'equation*', 'align', 'align*', 'gather', 'gather*',
        'algorithm', 'algorithm2e', 'algorithmic', 'lstlisting',
        'verbatim', 'minted', 'tikzpicture', 'minipage', 'subfigure',
    ]
    
    def __init__(self, tex_content: str, tex_path: str):
        self.tex_content = tex_content
        self.tex_path = tex_path
        self.lines = tex_content.split('\n')
        self.line_issues: Dict[int, List[CheckResult]] = defaultdict(list)
        self.blocks: List[Tuple[int, int, str]] = []  # (start, end, env_type)
        
        # Parse block environments
        self._parse_blocks()
    
    def _parse_blocks(self):
        """Find all block environments in the TeX content."""
        for env in self.BLOCK_ENVIRONMENTS:
            env_escaped = env.replace('*', r'\*')
            pattern = re.compile(
                rf'\\begin\{{{env_escaped}\}}.*?\\end\{{{env_escaped}\}}',
                re.DOTALL
            )
            
            for match in pattern.finditer(self.tex_content):
                start_line = self._pos_to_line(match.start())
                end_line = self._pos_to_line(match.end())
                self.blocks.append((start_line, end_line, env))
        
        # Sort blocks by start line
        self.blocks.sort(key=lambda x: x[0])
    
    def _pos_to_line(self, pos: int) -> int:
        """Convert character position to line number (1-indexed)."""
        return self.tex_content[:pos].count('\n') + 1
    
    def add_results(self, results: List[CheckResult]):
        """Add check results to the line-by-line mapping."""
        for result in results:
            if result.passed:
                continue
            
            line_num = result.line_number or 0
            if line_num > 0:
                self.line_issues[line_num].append(result)
    
    def _get_block_for_line(self, line_num: int) -> Optional[Tuple[int, int, str]]:
        """Check if a line is part of a block environment."""
        for start, end, env_type in self.blocks:
            if start <= line_num <= end:
                return (start, end, env_type)
        return None
    
    def _get_block_content(self, start: int, end: int) -> str:
        """Get content for a block of lines."""
        block_lines = self.lines[start-1:end]
        if len(block_lines) > 10:
            # Truncate long blocks
            return '\n'.join(block_lines[:5]) + '\n  [...]\n' + '\n'.join(block_lines[-3:])
        return '\n'.join(block_lines)
    
    def _severity_icon(self, severity: CheckSeverity) -> str:
        """Get icon for severity level."""
        icons = {
            CheckSeverity.ERROR: '🔴',
            CheckSeverity.WARNING: '🟡',
            CheckSeverity.INFO: '🔵',
        }
        return icons.get(severity, '⚪')
    
    def generate(self) -> str:
        """Generate the line-by-line report."""
        lines = []
        
        # Header
        lines.append("# BibGuard Line-by-Line Report")
        lines.append("")
        lines.append(f"**File:** `{Path(self.tex_path).name}`")
        lines.append(f"**Generated at:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")
        lines.append("---")
        lines.append("")
        
        # Summary counts
        error_count = sum(1 for issues in self.line_issues.values() 
                        for r in issues if r.severity == CheckSeverity.ERROR)
        warning_count = sum(1 for issues in self.line_issues.values() 
                          for r in issues if r.severity == CheckSeverity.WARNING)
        info_count = sum(1 for issues in self.line_issues.values() 
                        for r in issues if r.severity == CheckSeverity.INFO)
        
        lines.append("## 📊 Overview")
        lines.append("")
        lines.append(f"| 🔴 Errors | 🟡 Warnings | 🔵 Suggestions |")
        lines.append(f"|:---------:|:-----------:|:--------------:|")
        lines.append(f"| {error_count} | {warning_count} | {info_count} |")
        lines.append("")
        lines.append("---")
        lines.append("")
        
        if not self.line_issues:
            lines.append("🎉 **No issues found!**")
            return '\n'.join(lines)
        
        # Process lines in order
        lines.append("## 📝 Line-by-Line Details")
        lines.append("")
        
        processed_lines = set()
        sorted_line_nums = sorted(self.line_issues.keys())
        
        for line_num in sorted_line_nums:
            if line_num in processed_lines:
                continue
            
            issues = self.line_issues[line_num]
            if not issues:
                continue
            
            # Check if this line is part of a block
            block = self._get_block_for_line(line_num)
            
            if block:
                start, end, env_type = block
                
                # Mark all lines in block as processed
                for ln in range(start, end + 1):
                    processed_lines.add(ln)
                
                # Collect all issues in this block
                block_issues = []
                for ln in range(start, end + 1):
                    if ln in self.line_issues:
                        block_issues.extend(self.line_issues[ln])
                
                if block_issues:
                    lines.append(f"### 📦 `{env_type}` Environment (Lines {start}-{end})")
                    lines.append("")
                    lines.append("```latex")
                    lines.append(self._get_block_content(start, end))
                    lines.append("```")
                    lines.append("")
                    
                    # Group issues by type
                    for issue in block_issues:
                        icon = self._severity_icon(issue.severity)
                        lines.append(f"- {icon} **{issue.message}**")
                        if issue.suggestion:
                            lines.append(f"  - 💡 {issue.suggestion}")
                    
                    lines.append("")
            else:
                # Single line
                processed_lines.add(line_num)
                
                # Use custom line_content from CheckResult if available, otherwise get from file
                custom_content = None
                for issue in issues:
                    if issue.line_content:
                        custom_content = issue.line_content
                        break
                
                line_content = custom_content if custom_content else (
                    self.lines[line_num - 1] if line_num <= len(self.lines) else ""
                )
                
                lines.append(f"### Line {line_num}")
                lines.append("")
                lines.append("```latex")
                lines.append(line_content)
                lines.append("```")
                lines.append("")
                
                for issue in issues:
                    icon = self._severity_icon(issue.severity)
                    lines.append(f"- {icon} **{issue.message}**")
                    if issue.suggestion:
                        lines.append(f"  - 💡 {issue.suggestion}")
                
                lines.append("")
        
        # Footer
        lines.append("---")
        lines.append("")
        lines.append("*Report generated by BibGuard*")
        
        return '\n'.join(lines)
    
    def save(self, filepath: str):
        """Save report to file."""
        content = self.generate()
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)


def generate_line_report(
    tex_content: str, 
    tex_path: str, 
    results: List[CheckResult], 
    output_path: str
) -> str:
    """
    Generate a line-by-line report from check results.
    
    Args:
        tex_content: The TeX file content
        tex_path: Path to the TeX file
        results: List of check results from all checkers
        output_path: Where to save the report
    
    Returns:
        Path to the generated report
    """
    generator = LineByLineReportGenerator(tex_content, tex_path)
    generator.add_results(results)
    generator.save(output_path)
    return output_path
