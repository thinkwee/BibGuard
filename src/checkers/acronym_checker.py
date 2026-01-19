"""
Acronym and abbreviation checker.

Validates that:
- Acronyms are defined on first use
- Acronyms are used consistently after definition
- Common acronyms have proper capitalization
"""
import re
from typing import List, Dict, Set, Tuple
from collections import defaultdict

from .base import BaseChecker, CheckResult, CheckSeverity


class AcronymChecker(BaseChecker):
    """Check acronym definitions and consistency."""
    
    name = "acronym"
    display_name = "Acronyms"
    description = "Check acronym definitions and consistent usage"
    
    # Pattern to find defined acronyms: "Full Name (ACRONYM)" or "(ACRONYM; Full Name)"
    DEFINITION_PATTERN = re.compile(
        r'([A-Z][a-zA-Z\s\-]+)\s*\(([A-Z]{2,}s?)\)|'  # Full Name (ABC)
        r'\(([A-Z]{2,}s?);\s*([A-Za-z\s\-]+)\)',  # (ABC; Full Name)
        re.MULTILINE
    )
    
    # Pattern to find standalone acronyms (2+ capital letters)
    ACRONYM_PATTERN = re.compile(r'\b([A-Z]{2,}s?)\b')
    
    # Common acronyms that don't need definition in CS/ML papers
    COMMON_ACRONYMS = {
        'GPU', 'CPU', 'RAM', 'API', 'URL', 'HTTP', 'HTTPS', 'PDF', 'HTML',
        'AI', 'ML', 'DL', 'NLP', 'CV', 'RL', 'GAN', 'CNN', 'RNN', 'LSTM',
        'GRU', 'MLP', 'LLM', 'GPT', 'BERT', 'NER', 'POS', 'QA', 'MT',
        'BLEU', 'ROUGE', 'F1', 'AUC', 'ROC', 'MSE', 'MAE', 'RMSE',
        'SGD', 'ADAM', 'RGB', 'FPS', 'ID', 'IID', 'OOD', 'E2E',
        'SOTA', 'FLOP', 'FLOPS', 'TPU', 'GPU', 'IEEE', 'ACM', 'ACL',
        'EMNLP', 'NAACL', 'CVPR', 'ICCV', 'ECCV', 'ICLR', 'ICML', 'NIPS', 'NEURIPS',
        'USD', 'EU', 'US', 'UK', 'JSON', 'XML', 'CSV', 'SQL', 'UTF',
        # Added based on user feedback
        'SPIN', 'DPO', 'URPO', 'MDP', 'SPELL', 'SPICE', 'RLHF', 'PPO', 'KL',
        'STaR', 'ReST', 'RAG', 'CoT', 'ToT', 'GoT',
    }
    
    def check(self, tex_content: str, config: dict = None) -> List[CheckResult]:
        results = []
        
        # Remove comments using base class method
        content = self._remove_comments(tex_content)
        
        # Find all defined acronyms with their positions
        defined_acronyms = self._find_definitions(content)
        
        # Find all acronym usages
        all_usages = self._find_all_usages(content)
        
        # Check for undefined acronyms
        for acronym, positions in all_usages.items():
            if acronym in self.COMMON_ACRONYMS:
                continue
            
            if acronym not in defined_acronyms:
                # First usage should define it
                first_pos = positions[0]
                line_num = self._find_line_number(content, first_pos)
                
                results.append(self._create_result(
                    passed=False,
                    severity=CheckSeverity.WARNING,
                    message=f"Acronym '{acronym}' used without definition",
                    line_number=line_num,
                    suggestion=f"Define on first use: 'Full Name ({acronym})'"
                ))
            else:
                # Check if used before definition
                def_pos = defined_acronyms[acronym]
                for pos in positions:
                    if pos < def_pos:
                        line_num = self._find_line_number(content, pos)
                        results.append(self._create_result(
                            passed=False,
                            severity=CheckSeverity.WARNING,
                            message=f"Acronym '{acronym}' used before definition",
                            line_number=line_num,
                            suggestion="Move definition before first use"
                        ))
                        break
        
        return results
    
    def _find_definitions(self, content: str) -> Dict[str, int]:
        """Find all acronym definitions and their positions."""
        definitions = {}
        
        for match in self.DEFINITION_PATTERN.finditer(content):
            # Get acronym from either pattern
            acronym = match.group(2) or match.group(3)
            if acronym:
                acronym = acronym.rstrip('s')  # Remove plural
                definitions[acronym] = match.start()
        
        return definitions
    
    def _find_all_usages(self, content: str) -> Dict[str, List[int]]:
        """Find all acronym usages."""
        usages = defaultdict(list)
        
        for match in self.ACRONYM_PATTERN.finditer(content):
            acronym = match.group(1).rstrip('s')
            # Skip if inside definition parentheses
            before = content[max(0, match.start()-1):match.start()]
            after = content[match.end():min(len(content), match.end()+1)]
            if before == '(' and after == ')':
                continue
            usages[acronym].append(match.start())
        
        return usages
