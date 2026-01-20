"""
Acronym and abbreviation checker.

Validates that:
- Acronyms found in text have corresponding full forms defined
- Acronyms are used after their definition
- Only checks acronyms that have matching full forms in the document
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
    
    # Enhanced pattern to find defined acronyms with LaTeX formatting support
    # Matches: "Full Name (ACRONYM)", "(ACRONYM; Full Name)", "Full Name (\textbf{ACRONYM})", etc.
    DEFINITION_PATTERN = re.compile(
        r'([A-Z][a-zA-Z\s\-]+)\s*\((?:\\(?:textbf|emph|textit|texttt)\{)?([A-Z]{3,}s?)(?:\})?\)|'  # Full Name (ABC) or Full Name (\textbf{ABC})
        r'\((?:\\(?:textbf|emph|textit|texttt)\{)?([A-Z]{3,}s?)(?:\})?;\s*([A-Za-z\s\-]+)\)',  # (ABC; Full Name) or (\textbf{ABC}; Full Name)
        re.MULTILINE
    )
    
    # Pattern to find standalone acronyms (3+ capital letters)
    ACRONYM_PATTERN = re.compile(r'\b([A-Z]{3,}s?)\b')
    
    # Comprehensive list of common acronyms that don't need definition
    COMMON_ACRONYMS = {
        # Hardware & Computing
        'GPU', 'CPU', 'TPU', 'RAM', 'ROM', 'SSD', 'HDD', 'USB', 'BIOS', 'OS',
        'API', 'SDK', 'IDE', 'GUI', 'CLI', 'URL', 'URI', 'DNS', 'IP', 'TCP',
        'HTTP', 'HTTPS', 'FTP', 'SSH', 'SSL', 'TLS', 'VPN', 'LAN', 'WAN',
        
        # File Formats & Standards
        'PDF', 'HTML', 'CSS', 'XML', 'JSON', 'YAML', 'CSV', 'TSV', 'SQL',
        'UTF', 'ASCII', 'JPEG', 'PNG', 'GIF', 'SVG', 'MP3', 'MP4', 'ZIP',
        
        # AI & Machine Learning (General)
        'AI', 'ML', 'DL', 'NN', 'ANN', 'DNN', 'CNN', 'RNN', 'LSTM', 'GRU',
        'GAN', 'VAE', 'MLP', 'SVM', 'KNN', 'PCA', 'ICA', 'LDA', 'EM',
        'SGD', 'ADAM', 'RMSPROP', 'ADAGRAD', 'LBFGS',
        
        # NLP & Language Models
        'NLP', 'LLM', 'GPT', 'BERT', 'BART', 'T5', 'ELECTRA', 'ROBERTA',
        'NER', 'POS', 'QA', 'MT', 'ASR', 'TTS', 'NMT', 'SMT',
        'BLEU', 'ROUGE', 'METEOR', 'CIDEr', 'SPICE', 'WER', 'CER',
        
        # Computer Vision
        'CV', 'OCR', 'YOLO', 'RCNN', 'SSD', 'FCN', 'UNET', 'RESNET', 'VGG',
        'RGB', 'HSV', 'YUV', 'SIFT', 'SURF', 'ORB', 'HOG', 'SSIM', 'PSNR',
        
        # Reinforcement Learning
        'RL', 'DQN', 'DDPG', 'PPO', 'A3C', 'TRPO', 'SAC', 'TD3', 'MDP',
        'POMDP', 'RLHF', 'RLAIF',
        
        # Metrics & Evaluation
        'F1', 'AUC', 'ROC', 'PR', 'MAP', 'NDCG', 'MRR', 'MSE', 'MAE', 'RMSE',
        'MAPE', 'R2', 'IoU', 'AP', 'mAP', 'FPS', 'FLOPs', 'FLOPS',
        
        # Data & Statistics
        'IID', 'OOD', 'KL', 'JS', 'EMD', 'MMD', 'ELBO', 'VI', 'MCMC',
        'MLE', 'MAP', 'EM', 'GMM', 'HMM', 'CRF', 'MRF',
        
        # Academic & Organizations
        'IEEE', 'ACM', 'AAAI', 'IJCAI', 'ICML', 'ICLR', 'NEURIPS', 'NIPS',
        'ACL', 'EMNLP', 'NAACL', 'COLING', 'EACL', 'CVPR', 'ICCV', 'ECCV',
        'SIGIR', 'KDD', 'WWW', 'CIKM', 'WSDM', 'ICDE', 'VLDB', 'SIGMOD',
        'AAAI', 'IJCAI', 'AISTATS', 'UAI', 'COLT', 'ALT',
        
        # Methods & Techniques (Common in ML papers)
        'SOTA', 'E2E', 'RAG', 'CoT', 'ToT', 'GoT', 'ICL', 'FSL', 'ZSL',
        'PEFT', 'LORA', 'QLORA', 'SFT', 'DPO', 'SPIN', 'URPO', 'SPELL',
        'STaR', 'ReST', 'RRHF', 'RAFT', 'LIMA', 'ORPO',
        
        # Misc
        'USD', 'EUR', 'GBP', 'EU', 'US', 'UK', 'UN', 'NATO', 'NASA',
        'ID', 'UID', 'UUID', 'MD5', 'SHA', 'AES', 'RSA', 'JWT',
        'CRUD', 'REST', 'SOAP', 'RPC', 'AJAX', 'DOM', 'OOP', 'MVC',
        'CI', 'CD', 'DevOps', 'AWS', 'GCP', 'GPU', 'NPU', 'ASIC', 'FPGA',
    }
    
    def check(self, tex_content: str, config: dict = None) -> List[CheckResult]:
        results = []
        
        # Remove comments using base class method
        content = self._remove_comments(tex_content)
        
        # Find all defined acronyms with their positions
        defined_acronyms = self._find_definitions(content)
        
        # Find all acronym usages (excluding special contexts)
        all_usages = self._find_all_usages(content)
        
        # NEW: Find potential full forms for each acronym
        acronym_full_forms = self._find_potential_full_forms(content, all_usages.keys())
        
        # Check for undefined acronyms (only those with matching full forms)
        for acronym, positions in all_usages.items():
            if acronym in self.COMMON_ACRONYMS:
                continue
            
            # Skip if no matching full form found in document
            if acronym not in acronym_full_forms:
                continue
            
            if acronym not in defined_acronyms:
                # First usage should define it
                first_pos = positions[0]
                line_num = self._find_line_number(content, first_pos)
                full_form = acronym_full_forms[acronym]
                
                results.append(self._create_result(
                    passed=False,
                    severity=CheckSeverity.WARNING,
                    message=f"Acronym '{acronym}' used without definition (possible full form: '{full_form}')",
                    line_number=line_num,
                    suggestion=f"Define on first use: '{full_form} ({acronym})'"
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
    
    def _find_potential_full_forms(self, content: str, acronyms: Set[str]) -> Dict[str, str]:
        """Find potential full forms for acronyms by matching capital letters."""
        full_forms = {}
        
        for acronym in acronyms:
            if acronym in self.COMMON_ACRONYMS:
                continue
            
            # Build regex pattern to match full form
            # For "ABC", match words starting with A, B, C
            acronym_clean = acronym.rstrip('s')  # Remove plural
            if len(acronym_clean) < 3:
                continue
            
            # Create pattern: match sequence of words where first letters spell the acronym
            # Allow optional words in between (like "of", "the", "and")
            pattern_parts = []
            for i, letter in enumerate(acronym_clean):
                if i == 0:
                    # First word must start with the letter
                    pattern_parts.append(f'{letter}[a-z]+')
                else:
                    # Subsequent words: allow optional filler words
                    pattern_parts.append(f'(?:\\s+(?:of|the|and|for|in|on|with|to)\\s+)?\\s+{letter}[a-z]+')
            
            full_pattern = r'\b' + ''.join(pattern_parts) + r'\b'
            
            try:
                matches = re.finditer(full_pattern, content, re.IGNORECASE)
                for match in matches:
                    candidate = match.group(0)
                    
                    # Skip if candidate contains common non-content words
                    # These words indicate the match is part of a sentence, not an acronym full form
                    excluded_words = {
                        'that', 'the', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
                        'or', 'not', 'no', 'yes', 'if', 'but', 'as', 'at', 'by', 'from',
                        'has', 'have', 'had', 'do', 'does', 'did', 'will', 'would', 'should',
                        'can', 'could', 'may', 'might', 'must', 'shall',
                        'this', 'these', 'those', 'such', 'which', 'what', 'who', 'when', 'where',
                        'how', 'why', 'all', 'each', 'every', 'some', 'any', 'many', 'much',
                        'more', 'most', 'less', 'few', 'several', 'other', 'another'
                    }
                    
                    candidate_words = re.findall(r'\b[A-Za-z]+\b', candidate.lower())
                    if any(word in excluded_words for word in candidate_words):
                        continue
                    
                    # Verify: extract first letters and check if they match acronym
                    words = re.findall(r'\b[A-Z][a-z]+', candidate, re.IGNORECASE)
                    # Filter out filler words (allowed in between but not counted)
                    filler_words = {'of', 'and', 'for', 'in', 'on', 'with', 'to', 'a', 'an'}
                    meaningful_words = [w for w in words if w.lower() not in filler_words]
                    
                    if len(meaningful_words) >= len(acronym_clean):
                        first_letters = ''.join(w[0].upper() for w in meaningful_words[:len(acronym_clean)])
                        if first_letters == acronym_clean:
                            full_forms[acronym] = candidate
                            break  # Found a match, use the first one
            except re.error:
                # Invalid regex, skip this acronym
                continue
        
        return full_forms
    
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
        """Find all acronym usages, excluding special contexts."""
        usages = defaultdict(list)
        
        for match in self.ACRONYM_PATTERN.finditer(content):
            acronym = match.group(1).rstrip('s')
            pos = match.start()
            
            # Skip if in special context
            if self._is_in_special_context(content, pos, acronym):
                continue
            
            usages[acronym].append(pos)
        
        return usages
    
    def _is_in_special_context(self, content: str, pos: int, acronym: str) -> bool:
        """Check if acronym at position is in a special context that should be ignored."""
        # Get surrounding context
        start = max(0, pos - 50)
        end = min(len(content), pos + len(acronym) + 50)
        before = content[start:pos]
        after = content[pos + len(acronym):end]
        
        # Skip if inside definition parentheses: (ACRONYM)
        if before.endswith('(') and after.startswith(')'):
            return True
        
        # Skip if inside LaTeX command: \ACRONYM or \command{ACRONYM}
        if before.rstrip().endswith('\\'):
            return True
        
        # Skip if inside label: \label{...:ACRONYM...}
        if r'\label{' in before[-20:] and '}' in after[:20]:
            return True
        
        # Skip if inside ref: \ref{...:ACRONYM...}
        if re.search(r'\\(?:ref|cite|autoref|cref|eqref)\{[^}]*$', before[-30:]):
            return True
        
        # Skip if inside URL: \url{...ACRONYM...} or http://...ACRONYM...
        if r'\url{' in before[-20:] or 'http' in before[-20:]:
            return True
        
        # Skip if inside math mode (simple heuristic)
        # Count $ signs before position
        dollar_count = before.count('$') - before.count(r'\$')
        if dollar_count % 2 == 1:  # Odd number means we're inside math mode
            return True
        
        # Skip if inside \begin{equation} or similar
        if re.search(r'\\begin\{(?:equation|align|gather|math|displaymath)\*?\}', before[-100:]):
            if not re.search(r'\\end\{(?:equation|align|gather|math|displaymath)\*?\}', before[-100:]):
                return True
        
        # Skip if it looks like a LaTeX command argument: \command[ACRONYM]
        if before.endswith('[') and after.startswith(']'):
            return True
        
        # Skip if part of a file path or extension
        if '.' in before[-5:] or '/' in before[-10:]:
            return True
        
        return False
