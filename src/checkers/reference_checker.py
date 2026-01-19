"""
Cross-reference checker.

Validates that:
- All figures and tables are referenced in text
- All labels have corresponding references
- Appendix sections are referenced in main text
"""
import re
from typing import List, Set, Tuple

from .base import BaseChecker, CheckResult, CheckSeverity


class ReferenceChecker(BaseChecker):
    """Check cross-reference integrity in the document."""
    
    name = "reference"
    display_name = "Cross-References"
    description = "Verify all figures, tables, and sections are properly referenced"
    
    # Label pattern: \label{prefix:name}
    LABEL_PATTERN = re.compile(r'\\label\{([^}]+)\}')
    
    # Reference patterns
    REF_PATTERNS = [
        re.compile(r'\\ref\{([^}]+)\}'),
        re.compile(r'\\autoref\{([^}]+)\}'),
        re.compile(r'\\cref\{([^}]+)\}'),
        re.compile(r'\\Cref\{([^}]+)\}'),
        re.compile(r'\\eqref\{([^}]+)\}'),
        re.compile(r'\\pageref\{([^}]+)\}'),
        re.compile(r'\\nameref\{([^}]+)\}'),
    ]
    
    # Appendix detection
    APPENDIX_START_PATTERN = re.compile(r'\\appendix\b|\\begin\{appendix\}')
    SECTION_PATTERN = re.compile(r'\\section\*?\{([^}]+)\}')
    
    def check(self, tex_content: str, config: dict = None) -> List[CheckResult]:
        results = []
        
        # Extract all labels and their positions
        labels = self._extract_labels(tex_content)
        
        # Extract all references
        references = self._extract_references(tex_content)
        
        # Find unreferenced labels
        for label, (line_num, line_content) in labels.items():
            if label not in references:
                # Determine severity based on label type
                severity = self._get_severity_for_label(label)
                label_type = self._get_label_type(label)
                
                results.append(self._create_result(
                    passed=False,
                    severity=severity,
                    message=f"Unreferenced {label_type}: '{label}'",
                    line_number=line_num,
                    line_content=line_content,
                    suggestion=f"Add \\ref{{{label}}} or \\autoref{{{label}}} where appropriate"
                ))
        
        # Find undefined references (refs without labels)
        for ref, (line_num, line_content) in references.items():
            if ref not in labels:
                results.append(self._create_result(
                    passed=False,
                    severity=CheckSeverity.ERROR,
                    message=f"Reference to undefined label: '{ref}'",
                    line_number=line_num,
                    line_content=line_content,
                    suggestion=f"Add \\label{{{ref}}} to the target element or fix the reference"
                ))
        
        # Check appendix sections
        appendix_results = self._check_appendix_references(tex_content, labels, references)
        results.extend(appendix_results)
        
        return results
    
    def _extract_labels(self, content: str) -> dict:
        """Extract all labels with their line numbers."""
        labels = {}
        for match in self.LABEL_PATTERN.finditer(content):
            if not self._is_commented(content, match.start()):
                label = match.group(1)
                line_num = self._find_line_number(content, match.start())
                line_content = self._get_line_content(content, line_num)
                labels[label] = (line_num, line_content)
        return labels
    
    def _extract_references(self, content: str) -> dict:
        """Extract all references with their line numbers."""
        references = {}
        for pattern in self.REF_PATTERNS:
            for match in pattern.finditer(content):
                if not self._is_commented(content, match.start()):
                    # Handle comma-separated refs like \ref{fig:a,fig:b}
                    refs_str = match.group(1)
                    for ref in refs_str.split(','):
                        ref = ref.strip()
                        if ref and ref not in references:
                            # Skip if ref looks like command parameter (#1, #2)
                            if ref.startswith('#') and len(ref) == 2 and ref[1].isdigit():
                                continue
                            
                            # Skip if inside \newcommand or \renewcommand definition
                            line_num = self._find_line_number(content, match.start())
                            line_content = self._get_line_content(content, line_num)
                            if re.search(r'\\(new|renew|provide)command', line_content):
                                continue
                            
                            references[ref] = (line_num, line_content)
        return references
    
    def _get_label_type(self, label: str) -> str:
        """Determine the type of a label based on its prefix."""
        if ':' in label:
            prefix = label.split(':')[0].lower()
            type_map = {
                'fig': 'figure',
                'tab': 'table',
                'sec': 'section',
                'eq': 'equation',
                'alg': 'algorithm',
                'lst': 'listing',
                'app': 'appendix',
            }
            return type_map.get(prefix, 'label')
        return 'label'
    
    def _get_severity_for_label(self, label: str) -> CheckSeverity:
        """Determine severity based on label type."""
        label_type = self._get_label_type(label)
        
        # Figures and tables should always be referenced
        if label_type in ('figure', 'table'):
            return CheckSeverity.WARNING
        
        # Equations might not always need explicit reference
        if label_type == 'equation':
            return CheckSeverity.INFO
        
        return CheckSeverity.INFO
    
    def _check_appendix_references(
        self, 
        content: str, 
        labels: dict, 
        references: dict
    ) -> List[CheckResult]:
        """Check that appendix sections are referenced in main text."""
        results = []
        
        # Find where appendix starts
        appendix_match = self.APPENDIX_START_PATTERN.search(content)
        if not appendix_match:
            return results
        
        appendix_start = appendix_match.start()
        main_content = content[:appendix_start]
        appendix_content = content[appendix_start:]
        
        # Find section labels in appendix
        for match in self.LABEL_PATTERN.finditer(appendix_content):
            if self._is_commented(appendix_content, match.start()):
                continue
            
            label = match.group(1)
            
            # Check if this label is for a section
            if 'sec' in label.lower() or 'app' in label.lower():
                # Check if referenced in main text (before appendix)
                is_referenced = False
                for pattern in self.REF_PATTERNS:
                    if pattern.search(main_content) and label in main_content:
                        for m in pattern.finditer(main_content):
                            if label in m.group(1):
                                is_referenced = True
                                break
                    if is_referenced:
                        break
                
                if not is_referenced:
                    line_num = self._find_line_number(content, appendix_start + match.start())
                    results.append(self._create_result(
                        passed=False,
                        severity=CheckSeverity.WARNING,
                        message=f"Appendix section '{label}' is not referenced in main text",
                        line_number=line_num,
                        suggestion="Add a reference to this appendix section in the main text"
                    ))
        
        return results
