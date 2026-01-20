"""
LaTeX file parser for citation extraction.
"""
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class CitationContext:
    """Represents a citation with its context."""
    key: str
    line_number: int
    command: str  # e.g., \cite, \citep, \citet
    context_before: str  # Text before citation
    context_after: str   # Text after citation
    full_context: str    # Full surrounding context
    raw_line: str        # The raw line containing the citation
    file_path: Optional[str] = None # Added


class TexParser:
    """Parser for .tex files."""
    
    # Citation command patterns
    CITE_PATTERNS = [
        # Standard citation commands
        r'\\cite(?:p|t|alp|alt|author|year|yearpar)?\*?\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}',
        # natbib commands
        r'\\citep?\*?\s*(?:\[[^\]]*\])?\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}',
        r'\\citet?\*?\s*(?:\[[^\]]*\])?\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}',
        # biblatex commands
        r'\\(?:auto|text|paren|foot|super)cite\*?\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}',
        r'\\(?:full|short)cite\*?\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}',
    ]
    
    # Compiled pattern for finding any citation
    CITE_REGEX = re.compile(
        r'\\(cite[a-z]*)\*?\s*(?:\[[^\]]*\])?\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}',
        re.IGNORECASE
    )
    
    def __init__(self):
        self.citations: dict[str, list[CitationContext]] = {}
        self.all_keys: set[str] = set()
        self.lines: list[str] = []
        self.content: str = ""
        self.current_filepath: Optional[str] = None
    
    def parse_file(self, filepath: str) -> dict[str, list[CitationContext]]:
        """Parse a .tex file and extract all citations."""
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"TeX file not found: {filepath}")
        
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
        
        self.current_filepath = filepath
        return self.parse_content(content)
    
    def parse_content(self, content: str) -> dict[str, list[CitationContext]]:
        """Parse tex content and extract citations."""
        self.content = content
        self.lines = content.split('\n')
        self.citations = {}
        self.all_keys = set()
        
        # Remove comments
        content_no_comments = self._remove_comments(content)
        
        # Find all citations line by line
        for line_num, line in enumerate(self.lines, 1):
            # Skip comment lines
            if line.strip().startswith('%'):
                continue
            
            # Remove inline comments for matching
            line_no_comment = re.sub(r'(?<!\\)%.*$', '', line)
            
            # Find all citations in this line
            for match in self.CITE_REGEX.finditer(line_no_comment):
                command = match.group(1)
                keys_str = match.group(2)
                
                # Split multiple keys (e.g., \cite{key1, key2})
                keys = [k.strip() for k in keys_str.split(',')]
                
                for key in keys:
                    if not key:
                        continue
                    
                    self.all_keys.add(key)
                    
                    # Extract context
                    context = self._extract_context(line_num)
                    
                    citation = CitationContext(
                        key=key,
                        line_number=line_num,
                        command=f'\\{command}',
                        context_before=context['before'],
                        context_after=context['after'],
                        full_context=context['full'],
                        raw_line=line,
                        file_path=self.current_filepath
                    )
                    
                    if key not in self.citations:
                        self.citations[key] = []
                    self.citations[key].append(citation)
        
        return self.citations
    
    def _remove_comments(self, content: str) -> str:
        """Remove LaTeX comments from content."""
        # Remove line comments (but keep escaped %)
        lines = content.split('\n')
        cleaned = []
        for line in lines:
            # Remove inline comments
            result = re.sub(r'(?<!\\)%.*$', '', line)
            cleaned.append(result)
        return '\n'.join(cleaned)
    
    def _extract_context(self, line_num: int, context_sentences: int = 2) -> dict:
        """Extract surrounding context for a citation (sentences)."""
        # Get a larger window of lines first to ensure we capture full sentences
        start_line = max(0, line_num - 10)
        end_line = min(len(self.lines), line_num + 10)
        
        # Combine lines into a single text block
        raw_block = ' '.join(self.lines[start_line:end_line])
        
        # Clean the block first to make sentence splitting easier
        clean_block = self._clean_text(raw_block)
        
        # Find the citation in the clean block (approximation)
        # Since we cleaned the text, we can't find the exact \cite command easily.
        # Instead, we'll use the raw lines to find the citation index, then map to clean text.
        # However, a simpler approach for LLM context is to just return the cleaned text 
        # centered around the line.
        
        # Better approach:
        # 1. Get the raw line content
        current_raw_line = self.lines[line_num - 1]
        
        # 2. Get surrounding lines
        before_lines = self.lines[start_line:line_num - 1]
        after_lines = self.lines[line_num:end_line]
        
        # 3. Clean everything
        current_clean = self._clean_text(current_raw_line)
        before_clean = self._clean_text(' '.join(before_lines))
        after_clean = self._clean_text(' '.join(after_lines))
        
        # 4. Split into sentences (simple splitting by .!?)
        def split_sentences(text):
            return re.split(r'(?<=[.!?])\s+', text)
            
        before_sentences = split_sentences(before_clean)
        after_sentences = split_sentences(after_clean)
        
        # Take last N sentences from before
        context_before = ' '.join(before_sentences[-context_sentences:]) if before_sentences else ""
        
        # Take first N sentences from after
        context_after = ' '.join(after_sentences[:context_sentences]) if after_sentences else ""
        
        # Combine
        full_context = f"{context_before} {current_clean} {context_after}".strip()
        
        return {
            'before': context_before,
            'after': context_after,
            'full': full_context
        }
    
    def _clean_text(self, text: str) -> str:
        """Clean LaTeX text for readability."""
        # Remove common LaTeX commands but keep text content
        text = re.sub(r'\\[a-zA-Z]+\*?(?:\[[^\]]*\])*\s*', ' ', text)
        # Remove braces
        text = re.sub(r'[{}]', '', text)
        # Normalize whitespace
        text = re.sub(r'\s+', ' ', text)
        return text.strip()
    
    def is_cited(self, key: str) -> bool:
        """Check if a key is cited in the document."""
        return key in self.all_keys
    
    def get_citation_contexts(self, key: str) -> list[CitationContext]:
        """Get all citation contexts for a key."""
        return self.citations.get(key, [])
    
    def get_all_cited_keys(self) -> set[str]:
        """Get all citation keys found in the document."""
        return self.all_keys.copy()
