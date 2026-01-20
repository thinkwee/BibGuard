"""Checkers module for paper submission quality checks."""
from .base import BaseChecker, CheckResult, CheckSeverity
from .caption_checker import CaptionChecker
from .reference_checker import ReferenceChecker
from .ai_artifacts_checker import AIArtifactsChecker
from .formatting_checker import FormattingChecker
from .anonymization_checker import AnonymizationChecker
from .number_checker import NumberChecker
from .sentence_checker import SentenceChecker
from .consistency_checker import ConsistencyChecker
from .citation_quality_checker import CitationQualityChecker
from .equation_checker import EquationChecker
from .acronym_checker import AcronymChecker

__all__ = [
    'BaseChecker',
    'CheckResult',
    'CheckSeverity',
    'CaptionChecker',
    'ReferenceChecker',
    'AIArtifactsChecker',
    'FormattingChecker',
    'AnonymizationChecker',
    'NumberChecker',
    'SentenceChecker',
    'ConsistencyChecker',
    'CitationQualityChecker',
    'EquationChecker',
    'AcronymChecker',
]


# Registry of all available checkers
CHECKER_REGISTRY = {
    'caption': CaptionChecker,
    'reference': ReferenceChecker,
    'ai_artifacts': AIArtifactsChecker,
    'formatting': FormattingChecker,
    'anonymization': AnonymizationChecker,
    'number': NumberChecker,
    'sentence': SentenceChecker,
    'consistency': ConsistencyChecker,
    'citation_quality': CitationQualityChecker,
    'equation': EquationChecker,
    'acronym': AcronymChecker,
}


def get_checker(name: str) -> BaseChecker:
    """Get a checker instance by name."""
    if name not in CHECKER_REGISTRY:
        raise ValueError(f"Unknown checker: {name}")
    return CHECKER_REGISTRY[name]()


def run_all_checkers(tex_content: str, config: dict = None) -> list:
    """Run all checkers and return combined results."""
    results = []
    config = config or {}
    
    for name, checker_class in CHECKER_REGISTRY.items():
        checker = checker_class()
        checker_results = checker.check(tex_content, config)
        results.extend(checker_results)
    
    return results
