"""
AI artifacts checker.

Detects leftover text from AI writing assistants that should be removed
before submission, such as:
- Conversational responses ("Sure, here is...")
- Placeholder text
- Markdown formatting artifacts
- Common AI response patterns
"""
import re
from typing import List, Tuple

from .base import BaseChecker, CheckResult, CheckSeverity


class AIArtifactsChecker(BaseChecker):
    """Detect AI-generated text artifacts that should be removed."""
    
    name = "ai_artifacts"
    display_name = "AI Artifacts"
    description = "Detect leftover AI assistant text and placeholders"
    
    # Conversational AI patterns (case insensitive)
    # These are phrases that clearly indicate a dialogue between user and AI assistant
    AI_CONVERSATION_PATTERNS = [
        # Responses to requests
        (r'\bsure[,!]?\s*(here\s+is|i\'ll|i\s+will|let\s+me)\b', "Conversational AI response"),
        (r'\bi\'?d\s+be\s+happy\s+to\b', "Conversational AI response"),
        (r'\bi\'?m\s+happy\s+to\s+help\b', "Conversational AI response"),
        (r'\bcertainly[!,]\s*here\b', "Conversational AI response"),
        (r'\bof\s+course[!,]\s*(here|i)\b', "Conversational AI response"),
        (r'\babsolutely[!,]\s*(here|let\s+me)\b', "Conversational AI response"),
        
        # Self-identification
        (r'\bas\s+an?\s+ai\s+(language\s+)?model\b', "AI self-reference"),
        (r'\bas\s+a\s+large\s+language\s+model\b', "AI self-reference"),
        (r'\bmy\s+knowledge\s+cutoff\b', "AI knowledge cutoff reference"),
        
        # Explanatory transitions typical of chat
        (r'\blet\s+me\s+(explain|help|clarify|break\s+this\s+down)\b', "Conversational AI response"),
        (r'\bhere\'?s\s+(a|an|the|my)\s+(revised|updated|improved|rewrite)\b', "Conversational AI response"),
        (r'\bhere\s+is\s+(the|a|an)\s+(summary|breakdown|explanation|code|example)\b', "Conversational AI response"),
        
        # Closing/Politeness
        (r'\bhope\s+this\s+helps\b', "Conversational AI closing"),
        (r'\bfeel\s+free\s+to\s+ask\b', "Conversational AI closing"),
        (r'\blet\s+me\s+know\s+if\b', "Conversational AI closing"),
        (r'\bthank\s+you\s+for\s+(asking|your\s+question)\b', "Conversational AI response"),
        (r'\bgreat\s+question[!,]?\b', "Conversational AI response"),
        (r'\b(excellent|good|great)\s+point\b', "Conversational AI response"),
        
        # Instructions/Meta-commentary
        (r'\bbased\s+on\s+the\s+information\s+provided\b', "Conversational AI response"),
        (r'\b(remember|note)\s+that\b', "Conversational AI instruction"),
        (r'\bplease\s+note\s+that\b', "Conversational AI instruction"),
    ]
    
    # Placeholder patterns
    PLACEHOLDER_PATTERNS = [
        (r'\[insert\s+[^\]]+\s*here\]', "Placeholder text"),
        (r'\[add\s+[^\]]+\]', "Placeholder text"),
        (r'\[todo[:\s][^\]]*\]', "TODO placeholder"),
        (r'\btodo\s*:\s*.{0,50}', "TODO comment"),
        (r'\bfixme\s*:\s*.{0,50}', "FIXME comment"),
        (r'\bxxx\b', "XXX placeholder"),
        (r'\byour[\s_-]*(name|email|institution|university)\b', "Placeholder for personal info"),
        (r'author[\s_-]*name', "Author name placeholder"),
        (r'your\.?email@example\.com', "Email placeholder"),
        (r'example@(example\.com|university\.edu)', "Email placeholder"),
        (r'\[citation\s+needed\]', "Citation needed placeholder"),
    ]
    
    # Markdown artifacts (should not appear in LaTeX)
    MARKDOWN_PATTERNS = [
        (r'^\s*#{1,6}\s+\w', "Markdown header"),
        (r'\*\*[^*]+\*\*', "Markdown bold"),
        (r'(?<!\*)\*[^*\s][^*]*[^*\s]\*(?!\*)', "Markdown italic"),
        (r'(?<!`)`[^`\n]+`(?!`)', "Markdown inline code"),
        (r'```[\s\S]*?```', "Markdown code block"),
        (r'^\s*[-*+]\s+\w', "Markdown bullet point"),
        (r'^\s*\d+\.\s+\w', "Markdown numbered list"),
        (r'\[([^\]]+)\]\(([^)]+)\)', "Markdown link"),
    ]
    

    
    def check(self, tex_content: str, config: dict = None) -> List[CheckResult]:
        results = []
        lines = tex_content.split('\n')
        
        # Track if we are inside a verbatim-like environment
        in_verbatim = False
        verbatim_envs = ['verbatim', 'lstlisting', 'minted', 'comment', 'raw', 'filecontents', 'tcolorbox']
        
        # Check each line
        for line_num, line in enumerate(lines, 1):
            # Check for environment boundaries
            # Handle \begin{env}
            if re.search(r'\\begin\{(' + '|'.join(verbatim_envs) + r')\*?\}', line):
                in_verbatim = True
                continue # Skip the begin line itself
            
            # Handle \end{env}
            if re.search(r'\\end\{(' + '|'.join(verbatim_envs) + r')\*?\}', line):
                in_verbatim = False
                continue # Skip the end line itself
                
            # Skip checks if inside verbatim environment
            if in_verbatim:
                continue
                
            # Skip commented lines using base class method
            if self._is_comment_line(line):
                continue
            
            # Remove inline comments for checking using base class method
            line_to_check = self._remove_line_comment(line)
            
            # Check AI conversation patterns
            for pattern, description in self.AI_CONVERSATION_PATTERNS:
                if re.search(pattern, line_to_check, re.IGNORECASE):
                    results.append(self._create_result(
                        passed=False,
                        severity=CheckSeverity.ERROR,
                        message=f"{description} detected",
                        line_number=line_num,
                        line_content=line.strip()[:100],
                        suggestion="Remove AI-generated conversational text"
                    ))
                    break  # One match per line for this category
            
            # Check placeholder patterns
            for pattern, description in self.PLACEHOLDER_PATTERNS:
                match = re.search(pattern, line_to_check, re.IGNORECASE)
                if match:
                    results.append(self._create_result(
                        passed=False,
                        severity=CheckSeverity.WARNING,
                        message=f"{description}: '{match.group(0)[:50]}'",
                        line_number=line_num,
                        line_content=line.strip()[:100],
                        suggestion="Replace placeholder with actual content or remove"
                    ))
            
            # Check Markdown patterns (less strict - might be intentional in some cases)
            for pattern, description in self.MARKDOWN_PATTERNS:
                # Skip if line looks like a LaTeX command (starts with \)
                if line_to_check.strip().startswith('\\'):
                    continue
                
                # Special handling for bullet points: ensure space after
                if "bullet point" in description:
                    # Skip if it looks like a math subtraction or negative number
                    if re.search(r'[-+]\d', line_to_check):
                        continue
                    # Skip if inside math mode (simple heuristic)
                    if '$' in line_to_check:
                        continue
                
                # Special handling for italics: avoid matching math mode like $x*y$
                if "italic" in description:
                    if '$' in line_to_check:
                        continue
                
                if re.search(pattern, line_to_check):
                    results.append(self._create_result(
                        passed=False,
                        severity=CheckSeverity.INFO,
                        message=f"Possible {description} in LaTeX",
                        line_number=line_num,
                        line_content=line.strip()[:100],
                        suggestion="Convert to LaTeX formatting or remove if unintentional"
                    ))
        
        return results
