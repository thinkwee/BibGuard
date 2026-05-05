"""
Conference template definitions.

Each template captures conference-specific submission requirements that we can
mechanically verify from the LaTeX source. Things that genuinely require a
compiled PDF (page count, font embedding, image bleed) are documented in
``extra_rules`` so the report still surfaces them as reminders to the author.

The dataclass keeps every legacy field present (``name``, ``short_name``,
``page_limit_review/camera``, ``double_blind``, ``mandatory_sections``,
``optional_sections``, ``style_package``, ``checkers``, ``extra_rules``) so
older callers in ``src/ui/template_selector.py`` and the report generator
keep working unchanged.
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
    """Conference-specific submission requirements with verifiable per-venue rules."""

    # === Identity ===
    name: str
    short_name: str
    field: ConferenceField

    # === Page budget ===
    page_limit_review: int
    page_limit_camera: int
    references_excluded: bool = True       # references don't count toward limit
    appendix_excluded: bool = True
    limitations_excluded: bool = False     # ACL family puts Limitations outside the budget
    ethics_excluded: bool = False          # ACL family / ICLR exclude ethics
    min_main_pages: int = 0                # ICLR strictly requires >=6

    # === Anonymity (double-blind) ===
    double_blind: bool = True
    forbid_identifying_urls: bool = False  # strict CVPR/ICCV/ECCV anonymization
    forbid_acks_in_review: bool = False    # acknowledgments must be omitted in review
    arxiv_allowed: bool = True             # most modern venues permit arXiv preprints

    # === Captions ===
    caption_table_above: bool = True
    caption_figure_below: bool = True

    # === Required content ===
    mandatory_sections: List[str] = field(default_factory=list)
    mandatory_camera_sections: List[str] = field(default_factory=list)
    optional_sections: List[str] = field(default_factory=list)

    # === Template / typesetting ===
    style_package: str = ""        # \usepackage{<style_package>} expected in preamble
    doc_class: str = ""            # \documentclass{<doc_class>} expected (e.g. 'llncs')
    paper_size: str = ""           # 'letter' | 'a4' | '' (skip)
    single_column: bool = False
    font_size_pt: int = 0          # 0 = skip

    # === Per-venue special deliverables ===
    requires_paper_checklist: bool = False           # NeurIPS desk-rejects without it
    requires_reproducibility_statement: bool = False # ICLR / NeurIPS encourage
    requires_lay_summary_camera: bool = False        # ICML camera-ready
    requires_type1_fonts: bool = False               # ICML

    # === Backwards-compat fields ===
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
            'mandatory_camera_sections': self.mandatory_camera_sections,
            'optional_sections': self.optional_sections,
            'checkers': self.checkers,
        }


# ============================================================================
# NLP Conferences (ACL, EMNLP, NAACL) — share the *ACL style files
# ============================================================================

ACL_TEMPLATE = ConferenceTemplate(
    name="ACL 2025",
    short_name="acl",
    field=ConferenceField.NLP,
    page_limit_review=8,
    page_limit_camera=9,
    references_excluded=True,
    limitations_excluded=True,
    ethics_excluded=True,
    double_blind=True,
    arxiv_allowed=True,
    mandatory_sections=["Limitations"],
    optional_sections=["Ethical Considerations", "Ethics Statement"],
    style_package="acl",
    paper_size="a4",
    extra_rules={
        "format": "Two-column, A4 paper, 11pt",
        "limitations_content": "Discussion only — no new methods/figures/results inside Limitations",
        "appendix": "Allowed after references",
        "responsible_nlp_checklist": "ARR Responsible NLP Research checklist (separate, not inline)",
    },
)

EMNLP_TEMPLATE = ConferenceTemplate(
    name="EMNLP 2024",
    short_name="emnlp",
    field=ConferenceField.NLP,
    page_limit_review=8,                # long paper review
    page_limit_camera=9,
    references_excluded=True,
    limitations_excluded=True,
    ethics_excluded=True,
    double_blind=True,
    arxiv_allowed=True,
    mandatory_sections=["Limitations"],
    optional_sections=["Ethical Considerations", "Ethics Statement"],
    style_package="acl",                # *ACL share the same acl.sty
    paper_size="a4",
    extra_rules={
        "short_paper": "4 pages for short papers (5 camera-ready), excluding refs/limitations/ethics",
        "submission_route": "Submitted via ACL Rolling Review (ARR)",
        "limitations_content": "Discussion only — no new methods/figures/results inside Limitations",
    },
)

NAACL_TEMPLATE = ConferenceTemplate(
    name="NAACL 2025",
    short_name="naacl",
    field=ConferenceField.NLP,
    page_limit_review=8,
    page_limit_camera=9,
    references_excluded=True,
    limitations_excluded=True,
    ethics_excluded=True,
    double_blind=True,
    arxiv_allowed=True,
    mandatory_sections=["Limitations"],
    optional_sections=["Ethical Considerations", "Ethics Statement"],
    style_package="acl",
    paper_size="a4",
    extra_rules={
        "review_system": "ACL Rolling Review (ARR)",
        "format": "Two-column, A4 paper",
    },
)

# ============================================================================
# Computer Vision Conferences (CVPR, ICCV, ECCV) — strict double-blind
# ============================================================================

CVPR_TEMPLATE = ConferenceTemplate(
    name="CVPR 2025",
    short_name="cvpr",
    field=ConferenceField.CV,
    page_limit_review=8,
    page_limit_camera=8,                  # No extra page for camera-ready
    references_excluded=True,
    double_blind=True,
    forbid_identifying_urls=True,
    forbid_acks_in_review=True,
    arxiv_allowed=True,
    style_package="cvpr",
    paper_size="letter",
    extra_rules={
        "supplementary": "Separate PDF allowed; reviewers not obligated to view",
        "rebuttal": "1 page max; no external links; no new contributions",
        "anonymous_code": "Use Anonymous GitHub (https://anonymous.4open.science) for code links",
    },
)

ICCV_TEMPLATE = ConferenceTemplate(
    name="ICCV 2025",
    short_name="iccv",
    field=ConferenceField.CV,
    page_limit_review=8,
    page_limit_camera=8,
    references_excluded=True,
    double_blind=True,
    forbid_identifying_urls=True,
    forbid_acks_in_review=True,
    arxiv_allowed=True,
    style_package="iccv",
    paper_size="letter",
    extra_rules={
        "format": "Two-column, 10pt Times font",
        "supplementary": "Optional PDF; same deadline as main paper",
        "anonymous_code": "Use Anonymous GitHub for code links during review",
    },
)

ECCV_TEMPLATE = ConferenceTemplate(
    name="ECCV 2024",
    short_name="eccv",
    field=ConferenceField.CV,
    page_limit_review=14,
    page_limit_camera=14,
    references_excluded=True,
    double_blind=True,
    forbid_identifying_urls=True,
    forbid_acks_in_review=True,
    arxiv_allowed=True,
    style_package="",                     # uses LNCS style file, not a usepackage
    doc_class="llncs",
    paper_size="a4",
    extra_rules={
        "format": "Springer LNCS format — use llncs.cls",
        "headings": "Capitalize first letter of headings except articles/prepositions/conjunctions",
        "fonts": "Use the LNCS default font; do NOT switch to Times",
    },
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
    references_excluded=True,
    appendix_excluded=True,
    double_blind=True,
    arxiv_allowed=True,
    requires_paper_checklist=True,
    requires_reproducibility_statement=True,
    optional_sections=["Broader Impact", "Broader Impacts"],
    style_package="neurips_2025",
    paper_size="letter",
    single_column=True,
    extra_rules={
        "checklist": "MANDATORY — papers without the NeurIPS Paper Checklist are desk rejected",
        "checklist_position": "After references and supplementary material; outside page limit",
        "appendix": "Technical appendix follows checklist; no page limit",
        "single_pdf": "Single PDF: main content + references + checklist + appendix",
    },
)

ICML_TEMPLATE = ConferenceTemplate(
    name="ICML 2025",
    short_name="icml",
    field=ConferenceField.ML,
    page_limit_review=8,
    page_limit_camera=9,
    references_excluded=True,
    appendix_excluded=True,
    double_blind=True,
    arxiv_allowed=True,
    mandatory_camera_sections=["Impact Statement"],
    requires_lay_summary_camera=True,
    requires_type1_fonts=True,
    style_package="icml2025",
    paper_size="letter",
    single_column=True,
    font_size_pt=10,
    extra_rules={
        "fonts": "Type-1 fonts only; embed all fonts in the PDF",
        "lay_summary": "Plain-language summary required at camera-ready submission (OpenReview)",
        "impact_statement": "Required (broader impact + ethics) at camera-ready, before References",
        "compile_with": "Use pdflatex for best results",
    },
)

ICLR_TEMPLATE = ConferenceTemplate(
    name="ICLR 2025",
    short_name="iclr",
    field=ConferenceField.ML,
    page_limit_review=10,
    page_limit_camera=10,
    references_excluded=True,
    ethics_excluded=True,
    min_main_pages=6,
    double_blind=True,
    arxiv_allowed=True,
    requires_reproducibility_statement=True,
    optional_sections=["Ethics Statement", "Reproducibility Statement"],
    style_package="iclr2025_conference",
    paper_size="letter",
    single_column=True,
    extra_rules={
        "format": "10pt Times New Roman, 11pt vertical spacing",
        "submission": "OpenReview only",
        "page_limit": "Strictly 6–10 pages of main text; 11th main-text page = desk reject",
        "reproducibility_statement": "Encouraged at end of main text, before references; <=1 page; doesn't count toward limit",
    },
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
