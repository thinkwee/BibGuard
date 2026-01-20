"""
YAML configuration loader for BibGuard.

Loads configuration from YAML file and provides defaults.
"""
import yaml
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


@dataclass
class FilesConfig:
    """File path configuration."""
    bib: str = ""
    tex: str = ""
    input_dir: str = ""  # Directory to recursive search for .tex and .bib files
    output_dir: str = "bibguard_output"  # Output directory for all generated files


@dataclass
class BibliographyConfig:
    """Bibliography check configuration."""
    check_metadata: bool = True
    check_usage: bool = True
    check_duplicates: bool = True
    check_preprint_ratio: bool = True
    preprint_warning_threshold: float = 0.50
    check_relevance: bool = False


@dataclass
class SubmissionConfig:
    """Submission quality check configuration."""
    
    # Format checks
    caption: bool = True
    reference: bool = True
    formatting: bool = True
    equation: bool = True
    
    # Writing quality
    ai_artifacts: bool = True
    sentence: bool = True
    consistency: bool = True
    
    # Academic standards
    acronym: bool = True
    number: bool = True
    citation_quality: bool = True
    
    # Review compliance
    anonymization: bool = True
    
    def get_enabled_checkers(self) -> List[str]:
        """Get list of enabled checker names."""
        checkers = []
        if self.caption:
            checkers.append('caption')
        if self.reference:
            checkers.append('reference')
        if self.formatting:
            checkers.append('formatting')
        if self.equation:
            checkers.append('equation')
        if self.ai_artifacts:
            checkers.append('ai_artifacts')
        if self.sentence:
            checkers.append('sentence')
        if self.consistency:
            checkers.append('consistency')
        if self.acronym:
            checkers.append('acronym')
        if self.number:
            checkers.append('number')
        if self.citation_quality:
            checkers.append('citation_quality')
        if self.anonymization:
            checkers.append('anonymization')
        return checkers


@dataclass
class WorkflowStep:
    """Single step in the reference check workflow."""
    name: str
    enabled: bool = True
    description: str = ""


@dataclass
class LLMConfig:
    """LLM configuration for relevance checking."""
    backend: str = "gemini"
    model: str = ""
    endpoint: str = ""
    api_key: str = ""


@dataclass 
class OutputConfig:
    """Output configuration."""
    quiet: bool = False
    minimal_verified: bool = False


@dataclass
class BibGuardConfig:
    """Complete BibGuard configuration."""
    files: FilesConfig = field(default_factory=FilesConfig)
    template: str = ""
    bibliography: BibliographyConfig = field(default_factory=BibliographyConfig)
    submission: SubmissionConfig = field(default_factory=SubmissionConfig)
    workflow: List[WorkflowStep] = field(default_factory=list)
    llm: LLMConfig = field(default_factory=LLMConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    
    # Internal fields to store discovered files in directory mode
    _bib_files: List[Path] = field(default_factory=list)
    _tex_files: List[Path] = field(default_factory=list)
    
    # Path to the config file (for resolving relative paths)
    _config_dir: Path = field(default_factory=lambda: Path.cwd())
    
    def resolve_path(self, path: str) -> Path:
        """Resolve a path relative to the config file directory."""
        p = Path(path)
        if p.is_absolute():
            return p
        return self._config_dir / p
    
    @property
    def bib_path(self) -> Path:
        return self.resolve_path(self.files.bib)
    
    @property
    def tex_path(self) -> Path:
        return self.resolve_path(self.files.tex)
    
    @property
    def input_dir_path(self) -> Path:
        return self.resolve_path(self.files.input_dir)
    
    @property
    def output_dir_path(self) -> Path:
        return self.resolve_path(self.files.output_dir)


def load_config(config_path: str) -> BibGuardConfig:
    """Load configuration from YAML file."""
    path = Path(config_path)
    
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    
    with open(path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f) or {}
    
    config = BibGuardConfig()
    config._config_dir = path.parent.absolute()
    
    # Parse files section
    if 'files' in data:
        files = data['files']
        config.files = FilesConfig(
            bib=files.get('bib', ''),
            tex=files.get('tex', ''),
            input_dir=files.get('input_dir', ''),
            output_dir=files.get('output_dir', 'bibguard_output')
        )
    
    # Parse template
    config.template = data.get('template', '')
    
    # Parse bibliography section
    if 'bibliography' in data:
        bib = data['bibliography']
        config.bibliography = BibliographyConfig(
            check_metadata=bib.get('check_metadata', True),
            check_usage=bib.get('check_usage', True),
            check_duplicates=bib.get('check_duplicates', True),
            check_preprint_ratio=bib.get('check_preprint_ratio', True),
            preprint_warning_threshold=bib.get('preprint_warning_threshold', 0.50),
            check_relevance=bib.get('check_relevance', False)
        )
    
    # Parse submission section
    if 'submission' in data:
        sub = data['submission']
        config.submission = SubmissionConfig(
            caption=sub.get('caption', True),
            reference=sub.get('reference', True),
            formatting=sub.get('formatting', True),
            equation=sub.get('equation', True),
            ai_artifacts=sub.get('ai_artifacts', True),
            sentence=sub.get('sentence', True),
            consistency=sub.get('consistency', True),
            acronym=sub.get('acronym', True),
            number=sub.get('number', True),
            citation_quality=sub.get('citation_quality', True),
            anonymization=sub.get('anonymization', True)
        )
    
    # Parse workflow section
    if 'workflow' in data:
        config.workflow = [
            WorkflowStep(
                name=step.get('name', ''),
                enabled=step.get('enabled', True),
                description=step.get('description', '')
            )
            for step in data['workflow']
        ]
    
    # Parse LLM section
    if 'llm' in data:
        llm = data['llm']
        config.llm = LLMConfig(
            backend=llm.get('backend', 'gemini'),
            model=llm.get('model', ''),
            endpoint=llm.get('endpoint', ''),
            api_key=llm.get('api_key', '')
        )
    
    # Parse output section
    if 'output' in data:
        out = data['output']
        config.output = OutputConfig(
            quiet=out.get('quiet', False),
            minimal_verified=out.get('minimal_verified', False)
        )
    
    return config


def find_config_file() -> Optional[Path]:
    """Find config file in current directory or parent directories."""
    config_names = ['config.yaml', 'bibguard.yaml', 'bibguard.yml', '.bibguard.yaml', '.bibguard.yml']
    
    current = Path.cwd()
    
    for _ in range(5):  # Check up to 5 levels
        for name in config_names:
            config_path = current / name
            if config_path.exists():
                return config_path
        
        parent = current.parent
        if parent == current:
            break
        current = parent
    
    return None


def create_default_config(output_path: str = "config.yaml"):
    """Create a default config file."""
    default = """# BibGuard Configuration File

files:
  bib: "paper.bib"
  tex: "paper.tex"
  output_dir: "bibguard_output"

template: ""

bibliography:
  check_metadata: true
  check_usage: true
  check_duplicates: true
  check_preprint_ratio: true
  preprint_warning_threshold: 0.50
  check_relevance: false

submission:
  caption: true
  reference: true
  formatting: true
  equation: true
  ai_artifacts: true
  sentence: true
  consistency: true
  acronym: true
  number: true
  citation_quality: true
  anonymization: true

llm:
  backend: "gemini"
  model: ""
  api_key: ""

output:
  quiet: false
  minimal_verified: false
"""
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(default)
    
    return output_path
