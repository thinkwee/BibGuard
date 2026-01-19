"""
Sentence quality checker.

Validates:
- Sentence length (too long sentences)
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
    description = "Check sentence length and weak patterns"
    
    # Maximum recommended words per sentence
    MAX_SENTENCE_WORDS = 50
    WARNING_SENTENCE_WORDS = 40
    
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
        
        # Track which lines we've already reported on
        reported_lines = set()
        
        # --- Part 1: Check sentence lengths with correct line mapping ---
        
        in_document = True
        # Check if it looks like a full document (has documentclass)
        for i in range(min(20, len(lines))):
            if '\\documentclass' in lines[i]:
                in_document = False
                break
        
        in_math_env = False
        in_twocolumn = False
        
        # Tokenize with line numbers
        words_with_locs = []
        for line_num, line in enumerate(lines, 1):
            # Handle document boundaries
            if not in_document:
                if '\\begin{document}' in line:
                    in_document = True
                continue
            
            if '\\end{document}' in line:
                break
            
            # Skip math environments
            if re.search(r'\\begin\{(equation|align|gather|split|multline|table|figure|algorithm)\*?\}', line):
                in_math_env = True
            
            if in_math_env:
                if re.search(r'\\end\{(equation|align|gather|split|multline|table|figure|algorithm)\*?\}', line):
                    in_math_env = False
                continue
            
            # Skip twocolumn argument (title/abstract block)
            if '\\twocolumn[' in line:
                in_twocolumn = True
            
            if in_twocolumn:
                if ']' in line and not line.strip().startswith('%'): # Check for closing bracket, ignoring comments
                     # Naive check: assumes ] is at end of block
                     in_twocolumn = False
                continue
                
            if self._is_comment_line(line):
                continue
            
            # Clean line for word counting
            clean_line = self._remove_line_comment(line)
            # Remove begin/end environments
            clean_line = re.sub(r'\\(begin|end)\{[^}]*\}', ' ', clean_line)
            # Remove math
            clean_line = re.sub(r'\$[^$]+\$', ' ', clean_line)
            clean_line = re.sub(r'\\\[.*?\\\]', ' ', clean_line)
            # Remove commands but keep args (naive)
            clean_line = re.sub(r'\\[a-zA-Z]+\*?(\[[^\]]*\])*\{([^}]*)\}', r'\2', clean_line)
            clean_line = re.sub(r'\\[a-zA-Z]+\*?', ' ', clean_line)
            clean_line = re.sub(r'[{}]', '', clean_line)
            
            for word in clean_line.split():
                words_with_locs.append((word, line_num))
        
        # Analyze sentences
        current_sentence_words = []
        current_start_line = -1
        
        # Common abbreviations that don't end a sentence
        abbrevs = {
            'al.', 'fig.', 'eq.', 'sec.', 'tab.', 'i.e.', 'e.g.', 'vs.', 'cf.', 
            'dr.', 'mr.', 'ms.', 'prof.', 'etc.', 'vol.', 'no.', 'p.', 'pp.',
            'dept.', 'univ.', 'inst.', 'assn.', 'soc.', 'conf.', 'proc.'
        }
        
        for i, (word, line_num) in enumerate(words_with_locs):
            if not current_sentence_words:
                current_start_line = line_num
            
            current_sentence_words.append(word)
            
            # Check for sentence end
            # Matches . ! ? followed by optional ) ] } " '
            if re.search(r'[.!?][)\]}"\']*$', word):
                # Check if it's an abbreviation
                # Remove trailing punctuation for check
                clean_word = re.sub(r'[)\]}"\']+$', '', word).lower()
                if clean_word in abbrevs:
                    continue
                
                # Check if it's a single initial like "A." in "A. Name"
                if len(clean_word) <= 2 and clean_word.endswith('.'):
                    continue
                
                # Check sentence length
                word_count = len(current_sentence_words)
                if word_count > self.MAX_SENTENCE_WORDS:
                    if current_start_line not in reported_lines:
                        # Find the actual line content for better reporting
                        line_snippet = self._get_line_content(tex_content, current_start_line)
                        results.append(self._create_result(
                            passed=False,
                            severity=CheckSeverity.WARNING,
                            message=f"Very long sentence ({word_count} words)",
                            line_number=current_start_line,
                            line_content=line_snippet[:100],
                            suggestion=f"Consider breaking into shorter sentences (aim for <{self.MAX_SENTENCE_WORDS} words)"
                        ))
                        reported_lines.add(current_start_line)
                elif word_count > self.WARNING_SENTENCE_WORDS:
                    if current_start_line not in reported_lines:
                        line_snippet = self._get_line_content(tex_content, current_start_line)
                        results.append(self._create_result(
                            passed=False,
                            severity=CheckSeverity.INFO,
                            message=f"Long sentence ({word_count} words)",
                            line_number=current_start_line,
                            line_content=line_snippet[:100],
                            suggestion="Consider if this can be simplified"
                        ))
                        reported_lines.add(current_start_line)
                
                current_sentence_words = []
        
        # --- Part 2: Check weak patterns line-by-line ---
        
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
