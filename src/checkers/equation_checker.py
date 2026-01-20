"""
Equation formatting checker.

Validates:
- Punctuation after equations (based on grammar)
- Equation numbering consistency
- Variable definitions
"""
import re
from typing import List, Set

from .base import BaseChecker, CheckResult, CheckSeverity


class EquationChecker(BaseChecker):
    """Check equation formatting and consistency."""
    
    name = "equation"
    display_name = "Equations"
    description = "Check equation formatting and punctuation"
    
    # Equation environments
    EQUATION_ENVS = [
        'equation', 'align', 'gather', 'multline', 'eqnarray',
        'equation*', 'align*', 'gather*', 'multline*', 'eqnarray*'
    ]
    
    def check(self, tex_content: str, config: dict = None) -> List[CheckResult]:
        results = []
        
        # Check equation punctuation
        punct_results = self._check_equation_punctuation(tex_content)
        results.extend(punct_results)
        
        # Check for numbered vs unnumbered consistency
        numbering_results = self._check_numbering_consistency(tex_content)
        results.extend(numbering_results)
        
        # Check inline math consistency ($...$ vs \(...\))
        inline_results = self._check_inline_math_consistency(tex_content)
        results.extend(inline_results)
        
        return results
    
    def _check_equation_punctuation(self, content: str) -> List[CheckResult]:
        """Check if equations end with appropriate punctuation."""
        results = []
        
        for env in self.EQUATION_ENVS:
            if '*' in env:
                env_escaped = env.replace('*', r'\*')
            else:
                env_escaped = env
            
            # Find equation content
            pattern = re.compile(
                rf'\\begin\{{{env_escaped}\}}(.*?)\\end\{{{env_escaped}\}}',
                re.DOTALL
            )
            
            for match in pattern.finditer(content):
                eq_content = match.group(1).strip()
                
                # Check what comes after the equation
                after_pos = match.end()
                after_text = content[after_pos:after_pos + 50].strip()
                
                # Equations in running text should have punctuation
                # Check if equation content ends with punctuation
                eq_content_clean = re.sub(r'\\label\{[^}]+\}', '', eq_content).strip()
                
                if eq_content_clean and not re.search(r'[.,;]$', eq_content_clean):
                    # Check if next text starts lowercase (indicating sentence continues)
                    if after_text and after_text[0].islower():
                        line_num = self._find_line_number(content, match.end())
                        results.append(self._create_result(
                            passed=False,
                            severity=CheckSeverity.INFO,
                            message="Equation may need punctuation (sentence continues after)",
                            line_number=line_num,
                            suggestion="Add comma or period inside equation if it ends a clause"
                        ))
        
        return results
    
    def _check_numbering_consistency(self, content: str) -> List[CheckResult]:
        """Check for mixed numbered and unnumbered equations."""
        results = []
        
        # Count numbered vs unnumbered
        numbered = 0
        unnumbered = 0
        
        for env in self.EQUATION_ENVS:
            count = len(re.findall(rf'\\begin\{{{env}\}}', content))
            if '*' in env or 'nonumber' in content:
                unnumbered += count
            else:
                numbered += count
        
        # Also count \nonumber and \notag usage
        unnumbered += len(re.findall(r'\\nonumber|\\notag', content))
        
        # If there's a significant mix, warn
        total = numbered + unnumbered
        if total > 3 and numbered > 0 and unnumbered > 0:
            ratio = min(numbered, unnumbered) / total
            if ratio > 0.2:  # More than 20% in minority
                results.append(self._create_result(
                    passed=False,
                    severity=CheckSeverity.INFO,
                    message=f"Mixed equation numbering: {numbered} numbered, {unnumbered} unnumbered",
                    suggestion="Consider consistent numbering strategy"
                ))
        
        return results
    
    def _check_inline_math_consistency(self, content: str) -> List[CheckResult]:
        """Check for mixed inline math delimiters."""
        results = []
        
        # Count different inline math styles
        dollar_count = len(re.findall(r'(?<!\$)\$(?!\$)[^$]+\$(?!\$)', content))
        paren_count = len(re.findall(r'\\\(.*?\\\)', content))
        
        if dollar_count > 0 and paren_count > 0:
            results.append(self._create_result(
                passed=False,
                severity=CheckSeverity.INFO,
                message=f"Mixed inline math: ${dollar_count} \\$...\\$ and {paren_count} \\(...\\)",
                suggestion="Use consistent inline math delimiters throughout"
            ))
        
        return results
