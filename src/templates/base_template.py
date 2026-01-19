"""
Conference template definitions.

Each template contains conference-specific formatting requirements
and rules for paper submission quality checking.
"""
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from enum import Enum


class ConferenceField(Enum):
    """Research field categories."""
    NLP = "Natural Language Processing"
    CV = "Computer Vision"
    ML = "Machine Learning"


@dataclass
class ConferenceTemplate:
    """
    Template containing conference-specific submission requirements.
    
    Attributes:
        name: Full conference name (e.g., "ACL 2025")
        short_name: Short identifier (e.g., "acl")
        field: Research field category
        page_limit_review: Page limit for review submission (main content only)
        page_limit_camera: Page limit for camera-ready (main content only)
        double_blind: Whether the conference uses double-blind review
        caption_table_above: Whether table captions should be above
        caption_figure_below: Whether figure captions should be below
        mandatory_sections: List of required sections (e.g., ["Limitations"])
        optional_sections: List of encouraged sections
        style_package: Name of the LaTeX style package
        checkers: List of checker names to run for this template
        extra_rules: Additional conference-specific rules
    """
    name: str
    short_name: str
    field: ConferenceField
    page_limit_review: int
    page_limit_camera: int
    double_blind: bool = True
    caption_table_above: bool = True
    caption_figure_below: bool = True
    mandatory_sections: List[str] = field(default_factory=list)
    optional_sections: List[str] = field(default_factory=list)
    style_package: str = ""
    checkers: List[str] = field(default_factory=lambda: [
        'caption', 'reference', 'ai_artifacts', 'formatting', 'anonymization'
    ])
    extra_rules: Dict[str, str] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            'name': self.name,
            'short_name': self.short_name,
            'field': self.field.value,
            'page_limit_review': self.page_limit_review,
            'page_limit_camera': self.page_limit_camera,
            'double_blind': self.double_blind,
            'mandatory_sections': self.mandatory_sections,
            'optional_sections': self.optional_sections,
            'checkers': self.checkers,
        }


# ============================================================================
# NLP Conferences (ACL, EMNLP, NAACL)
# ============================================================================

ACL_TEMPLATE = ConferenceTemplate(
    name="ACL 2025",
    short_name="acl",
    field=ConferenceField.NLP,
    page_limit_review=8,
    page_limit_camera=9,
    double_blind=True,
    mandatory_sections=["Limitations"],
    optional_sections=["Ethical Considerations"],
    style_package="acl2025",
    extra_rules={
        "format": "Two-column, A4 paper",
        "references": "Unlimited pages for references",
        "appendix": "Allowed after references, two-column format",
    }
)

EMNLP_TEMPLATE = ConferenceTemplate(
    name="EMNLP 2024",
    short_name="emnlp",
    field=ConferenceField.NLP,
    page_limit_review=8,
    page_limit_camera=9,
    double_blind=True,
    mandatory_sections=["Limitations"],
    optional_sections=["Ethics Statement"],
    style_package="emnlp2024",
    extra_rules={
        "format": "Two-column, single-spaced",
        "short_paper": "4 pages for short papers (5 camera-ready)",
    }
)

NAACL_TEMPLATE = ConferenceTemplate(
    name="NAACL 2025",
    short_name="naacl",
    field=ConferenceField.NLP,
    page_limit_review=8,
    page_limit_camera=9,
    double_blind=True,
    mandatory_sections=["Limitations"],
    optional_sections=["Ethics Statement"],
    style_package="naacl2025",
    extra_rules={
        "review_system": "ACL Rolling Review (ARR)",
        "format": "Two-column, A4 paper",
    }
)

# ============================================================================
# Computer Vision Conferences (CVPR, ICCV, ECCV)
# ============================================================================

CVPR_TEMPLATE = ConferenceTemplate(
    name="CVPR 2025",
    short_name="cvpr",
    field=ConferenceField.CV,
    page_limit_review=8,
    page_limit_camera=8,  # No extra page for camera-ready
    double_blind=True,
    mandatory_sections=[],
    optional_sections=[],
    style_package="cvpr",
    extra_rules={
        "strict_anonymity": "No links to websites that reveal identity",
        "supplementary": "Separate PDF allowed, no page limit",
        "references": "No limit on references",
    }
)

ICCV_TEMPLATE = ConferenceTemplate(
    name="ICCV 2025",
    short_name="iccv",
    field=ConferenceField.CV,
    page_limit_review=8,
    page_limit_camera=8,
    double_blind=True,
    mandatory_sections=[],
    optional_sections=[],
    style_package="iccv",
    extra_rules={
        "format": "Two-column, 10pt Times font",
        "supplementary": "Optional PDF for extra material",
    }
)

ECCV_TEMPLATE = ConferenceTemplate(
    name="ECCV 2024",
    short_name="eccv",
    field=ConferenceField.CV,
    page_limit_review=14,
    page_limit_camera=14,
    double_blind=True,
    mandatory_sections=[],
    optional_sections=[],
    style_package="eccv",
    extra_rules={
        "format": "Springer LNCS format",
        "template": "Do not use TIMES font, use default template font",
        "headings": "Capitalize except articles/prepositions/conjunctions",
    }
)

# ============================================================================
# Machine Learning Conferences (NeurIPS, ICML, ICLR)
# ============================================================================

NEURIPS_TEMPLATE = ConferenceTemplate(
    name="NeurIPS 2025",
    short_name="neurips",
    field=ConferenceField.ML,
    page_limit_review=9,
    page_limit_camera=10,
    double_blind=True,
    mandatory_sections=["Paper Checklist"],
    optional_sections=["Broader Impact"],
    style_package="neurips_2025",
    extra_rules={
        "checklist": "NeurIPS paper checklist is MANDATORY, desk reject without it",
        "appendix": "Technical appendix after checklist, no page limit",
        "format": "Single PDF including main content, references, and checklist",
    }
)

ICML_TEMPLATE = ConferenceTemplate(
    name="ICML 2025",
    short_name="icml",
    field=ConferenceField.ML,
    page_limit_review=8,
    page_limit_camera=9,
    double_blind=True,
    mandatory_sections=["Impact Statement"],  # Required for camera-ready
    optional_sections=["Acknowledgments"],
    style_package="icml2025",
    extra_rules={
        "font": "10 point Times, embedded Type-1 fonts only",
        "lay_summary": "Plain language summary required for accepted papers",
        "format": "Use pdflatex for best results",
    }
)

ICLR_TEMPLATE = ConferenceTemplate(
    name="ICLR 2025",
    short_name="iclr",
    field=ConferenceField.ML,
    page_limit_review=10,
    page_limit_camera=10,
    double_blind=True,
    mandatory_sections=[],
    optional_sections=["Ethics Statement", "Reproducibility Statement"],
    style_package="iclr2025_conference",
    extra_rules={
        "format": "10pt Times New Roman, 11pt vertical spacing",
        "submission": "Via OpenReview",
        "min_pages": "Main text must be between 6 and 10 pages",
    }
)

# ============================================================================
# Template Registry
# ============================================================================

TEMPLATE_REGISTRY: Dict[str, ConferenceTemplate] = {
    # NLP
    'acl': ACL_TEMPLATE,
    'emnlp': EMNLP_TEMPLATE,
    'naacl': NAACL_TEMPLATE,
    # CV
    'cvpr': CVPR_TEMPLATE,
    'iccv': ICCV_TEMPLATE,
    'eccv': ECCV_TEMPLATE,
    # ML
    'neurips': NEURIPS_TEMPLATE,
    'icml': ICML_TEMPLATE,
    'iclr': ICLR_TEMPLATE,
}


def get_template(name: str) -> Optional[ConferenceTemplate]:
    """Get a conference template by short name."""
    return TEMPLATE_REGISTRY.get(name.lower())


def get_all_templates() -> Dict[str, ConferenceTemplate]:
    """Get all available templates."""
    return TEMPLATE_REGISTRY.copy()


def get_templates_by_field(field: ConferenceField) -> List[ConferenceTemplate]:
    """Get templates filtered by research field."""
    return [t for t in TEMPLATE_REGISTRY.values() if t.field == field]
