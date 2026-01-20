"""
Workflow configuration for reference checking.

Allows users to customize the order and enable/disable individual fetchers
in the reference verification workflow.
"""
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Optional


@dataclass
class WorkflowStep:
    """A single step in the reference checking workflow."""
    name: str
    display_name: str
    description: str
    enabled: bool = True
    priority: int = 0
    
    # Step type: 'by_id', 'by_doi', 'by_title'
    search_type: str = 'by_title'
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'WorkflowStep':
        return cls(**data)


@dataclass
class WorkflowConfig:
    """Configuration for the reference checking workflow."""
    steps: List[WorkflowStep] = field(default_factory=list)
    name: str = "default"
    description: str = "Default workflow configuration"
    
    def get_enabled_steps(self) -> List[WorkflowStep]:
        """Get only enabled steps, sorted by priority."""
        return sorted(
            [s for s in self.steps if s.enabled],
            key=lambda x: x.priority
        )
    
    def move_step_up(self, index: int) -> bool:
        """Move a step up in priority (swap with previous)."""
        if index <= 0 or index >= len(self.steps):
            return False
        self.steps[index], self.steps[index - 1] = self.steps[index - 1], self.steps[index]
        self._update_priorities()
        return True
    
    def move_step_down(self, index: int) -> bool:
        """Move a step down in priority (swap with next)."""
        if index < 0 or index >= len(self.steps) - 1:
            return False
        self.steps[index], self.steps[index + 1] = self.steps[index + 1], self.steps[index]
        self._update_priorities()
        return True
    
    def toggle_step(self, index: int) -> bool:
        """Toggle enabled status of a step."""
        if 0 <= index < len(self.steps):
            self.steps[index].enabled = not self.steps[index].enabled
            return True
        return False
    
    def _update_priorities(self):
        """Update priority values based on current order."""
        for i, step in enumerate(self.steps):
            step.priority = i
    
    def to_dict(self) -> dict:
        return {
            'name': self.name,
            'description': self.description,
            'steps': [s.to_dict() for s in self.steps]
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'WorkflowConfig':
        steps = [WorkflowStep.from_dict(s) for s in data.get('steps', [])]
        return cls(
            steps=steps,
            name=data.get('name', 'custom'),
            description=data.get('description', '')
        )
    
    def save(self, filepath: str):
        """Save workflow configuration to JSON file."""
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2)
    
    @classmethod
    def load(cls, filepath: str) -> 'WorkflowConfig':
        """Load workflow configuration from JSON file."""
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return cls.from_dict(data)


# Default workflow matching current implementation order
DEFAULT_WORKFLOW = WorkflowConfig(
    name="default",
    description="Default reference checking workflow prioritizing reliable APIs",
    steps=[
        WorkflowStep(
            name="arxiv_id",
            display_name="arXiv by ID",
            description="Look up paper by arXiv ID (highest priority for arXiv papers)",
            priority=0,
            search_type="by_id"
        ),
        WorkflowStep(
            name="crossref_doi",
            display_name="CrossRef by DOI",
            description="Look up paper by DOI (authoritative for DOIs)",
            priority=1,
            search_type="by_doi"
        ),
        WorkflowStep(
            name="semantic_scholar",
            display_name="Semantic Scholar",
            description="Official API with high quality metadata",
            priority=2,
            search_type="by_title"
        ),
        WorkflowStep(
            name="dblp",
            display_name="DBLP",
            description="Official API, especially good for CS publications",
            priority=3,
            search_type="by_title"
        ),
        WorkflowStep(
            name="openalex",
            display_name="OpenAlex",
            description="Official API with broad coverage",
            priority=4,
            search_type="by_title"
        ),
        WorkflowStep(
            name="arxiv_title",
            display_name="arXiv by Title",
            description="Search arXiv by title (fallback for non-ID lookups)",
            priority=5,
            search_type="by_title"
        ),
        WorkflowStep(
            name="crossref_title",
            display_name="CrossRef by Title",
            description="Search CrossRef by title",
            priority=6,
            search_type="by_title"
        ),
        WorkflowStep(
            name="google_scholar",
            display_name="Google Scholar",
            description="Web scraping fallback (may be rate-limited or blocked)",
            priority=7,
            search_type="by_title",
            enabled=True  # Still enabled but lowest priority
        ),
    ]
)


def get_default_workflow() -> WorkflowConfig:
    """Get a fresh copy of the default workflow."""
    return WorkflowConfig.from_dict(DEFAULT_WORKFLOW.to_dict())
