"""
Sentence quality checker.

Validates:
- Weak sentence starters
- Common writing issues
"""
import re
from typing import List

from .base import BaseChecker, CheckResult, CheckSeverity


class SentenceChecker(BaseChecker):
    """Check sentence quality and readability."""
    
    name = "sentence"
    display_name = "Sentence Quality"
    description = "Check weak patterns and writing issues"
    
    # Weak sentence starters (avoid these)
    WEAK_STARTERS = [
        (r'^There\s+(is|are|was|were|has been|have been)\s+', 
         "Weak start with 'There is/are'"),
        (r'^It\s+(is|was|has been|should be noted)\s+',
         "Weak start with 'It is'"),
        (r'^This\s+(is|was|shows|demonstrates)\s+',
         "Vague 'This' without clear antecedent"),
        (r'^As\s+(mentioned|discussed|shown|noted)\s+(above|before|earlier|previously)',
         "Consider being more specific about what was mentioned"),
    ]
    
    # Weasel words and hedging
    WEASEL_PATTERNS = [
        (r'\b(many|some|most|several)\s+(researchers?|studies|papers?|works?)\s+(have\s+)?(shown?|demonstrated?|suggested?|believe)',
         "Vague attribution - consider citing specific work"),
        (r'\b(obviously|clearly|of course|needless to say|it is well known)\b',
         "Unsupported assertion - consider citing or removing"),
        (r'\b(very|really|quite|extremely|highly)\s+(important|significant|good|effective)',
         "Consider more precise language"),
        (r'\bit\s+is\s+(important|crucial|essential|necessary)\s+to\s+note\s+that',
         "Wordy phrase - consider simplifying"),
    ]
    
    # Redundant phrases
    REDUNDANT_PATTERNS = [
        (r'\bin order to\b', "Use 'to' instead of 'in order to'"),
        (r'\bdue to the fact that\b', "Use 'because' instead"),
        (r'\bat this point in time\b', "Use 'now' or 'currently'"),
        (r'\bin the event that\b', "Use 'if' instead"),
        (r'\bdespite the fact that\b', "Use 'although' instead"),
        (r'\bfor the purpose of\b', "Use 'to' or 'for' instead"),
        (r'\bwith the exception of\b', "Use 'except' instead"),
        (r'\bin close proximity to\b', "Use 'near' instead"),
        (r'\ba large number of\b', "Use 'many' instead"),
        (r'\bthe vast majority of\b', "Use 'most' instead"),
    ]
    
    def check(self, tex_content: str, config: dict = None) -> List[CheckResult]:
        results = []
        lines = tex_content.split('\n')
        
        for line_num, line in enumerate(lines, 1):
            # Skip commented lines using base class method
            if self._is_comment_line(line):
                continue
            
            # Remove inline comments using base class method
            line_content = self._remove_line_comment(line)
            
            # Check weak starters
            for pattern, message in self.WEAK_STARTERS:
                if re.search(pattern, line_content, re.IGNORECASE):
                    results.append(self._create_result(
                        passed=False,
                        severity=CheckSeverity.INFO,
                        message=message,
                        line_number=line_num,
                        line_content=line.strip()[:80]
                    ))
                    break  # One per line
            
            # Check weasel words
            for pattern, message in self.WEASEL_PATTERNS:
                match = re.search(pattern, line_content, re.IGNORECASE)
                if match:
                    results.append(self._create_result(
                        passed=False,
                        severity=CheckSeverity.INFO,
                        message=f"Hedging language: '{match.group(0)[:30]}'",
                        line_number=line_num,
                        suggestion=message
                    ))
            
            # Check redundant phrases
            for pattern, message in self.REDUNDANT_PATTERNS:
                match = re.search(pattern, line_content, re.IGNORECASE)
                if match:
                    results.append(self._create_result(
                        passed=False,
                        severity=CheckSeverity.INFO,
                        message=f"Redundant phrase: '{match.group(0)}'",
                        line_number=line_num,
                        suggestion=message
                    ))
        
        return results
