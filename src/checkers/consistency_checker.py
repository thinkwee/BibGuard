"""
Terminology consistency checker.

Validates:
- Consistent spelling of the same term
- Consistent hyphenation
- Consistent capitalization of technical terms
"""
import re
from typing import List, Dict, Set
from collections import defaultdict

from .base import BaseChecker, CheckResult, CheckSeverity


class ConsistencyChecker(BaseChecker):
    """Check terminology and spelling consistency."""
    
    name = "consistency"
    display_name = "Consistency"
    description = "Check for inconsistent terminology and spelling"
    
    # Known variant pairs (canonical -> variants)
    KNOWN_VARIANTS = {
        # Hyphenation variants
        'self-supervised': ['self supervised', 'selfsupervised'],
        'pre-trained': ['pre trained', 'pretrained'],
        'fine-tuned': ['fine tuned', 'finetuned'],
        'state-of-the-art': ['state of the art', 'stateoftheart'],
        'real-world': ['real world', 'realworld'],
        'end-to-end': ['end to end', 'endtoend', 'e2e'],
        'large-scale': ['large scale', 'largescale'],
        'long-term': ['long term', 'longterm'],
        'short-term': ['short term', 'shortterm'],
        'multi-task': ['multi task', 'multitask'],
        'multi-modal': ['multi modal', 'multimodal'],
        'cross-lingual': ['cross lingual', 'crosslingual'],
        'zero-shot': ['zero shot', 'zeroshot'],
        'few-shot': ['few shot', 'fewshot'],
        'in-context': ['in context', 'incontext'],
        
        # British vs American
        'color': ['colour'],
        'behavior': ['behaviour'],
        'modeling': ['modelling'],
        'optimization': ['optimisation'],
        'generalization': ['generalisation'],
        'regularization': ['regularisation'],
        'analyze': ['analyse'],
        'utilize': ['utilise'],
        
        # Common term variants
        'dataset': ['data set', 'data-set'],
        'benchmark': ['bench mark', 'bench-mark'],
        'baseline': ['base line', 'base-line'],
        'downstream': ['down stream', 'down-stream'],
        'upstream': ['up stream', 'up-stream'],
        'encoder': ['en-coder'],
        'decoder': ['de-coder'],
    }
    
    # Capitalization variants to track
    CAPITALIZATION_TERMS = [
        'transformer', 'attention', 'bert', 'gpt', 'lstm', 'cnn', 'rnn',
        'encoder', 'decoder', 'embedding', 'softmax', 'sigmoid', 'relu',
    ]
    
    def check(self, tex_content: str, config: dict = None) -> List[CheckResult]:
        results = []
        
        # Remove comments
        content = re.sub(r'(?<!\\)%.*$', '', tex_content, flags=re.MULTILINE)
        content_lower = content.lower()
        
        # Check for known variant inconsistencies
        for canonical, variants in self.KNOWN_VARIANTS.items():
            found_forms = []
            
            # Check canonical form
            if re.search(rf'\b{re.escape(canonical)}\b', content, re.IGNORECASE):
                found_forms.append(canonical)
            
            # Check variants
            for variant in variants:
                if re.search(rf'\b{re.escape(variant)}\b', content, re.IGNORECASE):
                    found_forms.append(variant)
            
            if len(found_forms) > 1:
                results.append(self._create_result(
                    passed=False,
                    severity=CheckSeverity.WARNING,
                    message=f"Inconsistent spelling: {', '.join(found_forms)}",
                    suggestion=f"Use '{canonical}' consistently throughout"
                ))
        
        # Check hyphenated word consistency
        hyphen_results = self._check_hyphenation_consistency(content)
        results.extend(hyphen_results)
        
        # Check capitalization consistency
        cap_results = self._check_capitalization_consistency(content)
        results.extend(cap_results)
        
        return results
    
    def _check_hyphenation_consistency(self, content: str) -> List[CheckResult]:
        """Find words that appear both hyphenated and non-hyphenated."""
        results = []
        
        # Common terms that should always be hyphenated (exceptions)
        ALWAYS_HYPHENATED = {
            'state-of-the-art', 'end-to-end', 'real-time', 'real-world',
            'fine-tuning', 'fine-grained', 'large-scale', 'small-scale',
            'multi-task', 'multi-modal', 'cross-domain', 'cross-lingual',
            'self-supervised', 'self-attention', 'co-training', 'pre-training',
            'post-processing', 'pre-processing', 'well-known', 'well-defined',
            'high-quality', 'low-quality', 'long-term', 'short-term'
        }
        
        # Find all hyphenated words
        hyphenated = set(re.findall(r'\b([a-z]+-[a-z]+(?:-[a-z]+)*)\b', content, re.IGNORECASE))
        
        for hyph_word in hyphenated:
            # Skip if it's a known compound that should always be hyphenated
            if hyph_word.lower() in ALWAYS_HYPHENATED:
                continue
            
            # Create non-hyphenated version
            non_hyph = hyph_word.replace('-', ' ')
            combined = hyph_word.replace('-', '')
            
            # Check if non-hyphenated version exists
            if re.search(rf'\b{re.escape(non_hyph)}\b', content, re.IGNORECASE):
                results.append(self._create_result(
                    passed=False,
                    severity=CheckSeverity.INFO,
                    message=f"Inconsistent hyphenation: '{hyph_word}' vs '{non_hyph}'",
                    suggestion="Choose one form and use it consistently"
                ))
            elif re.search(rf'\b{re.escape(combined)}\b', content, re.IGNORECASE):
                results.append(self._create_result(
                    passed=False,
                    severity=CheckSeverity.INFO,
                    message=f"Inconsistent hyphenation: '{hyph_word}' vs '{combined}'",
                    suggestion="Choose one form and use it consistently"
                ))
        
        return results
    
    def _check_capitalization_consistency(self, content: str) -> List[CheckResult]:
        """Check if technical terms have consistent capitalization."""
        results = []
        
        for term in self.CAPITALIZATION_TERMS:
            # Find all case variations
            pattern = re.compile(rf'\b{term}\b', re.IGNORECASE)
            matches = pattern.findall(content)
            
            if len(matches) > 1:
                # Check if there are mixed capitalizations
                unique_forms = set(matches)
                if len(unique_forms) > 1:
                    forms_str = ', '.join(f"'{f}'" for f in unique_forms)
                    results.append(self._create_result(
                        passed=False,
                        severity=CheckSeverity.INFO,
                        message=f"Inconsistent capitalization: {forms_str}",
                        suggestion="Use consistent capitalization for technical terms"
                    ))
        
        return results
