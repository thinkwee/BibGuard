"""
Conference-template conformance checker.

Reads the rich rule set defined in :mod:`src.templates.base_template` and runs
per-venue checks against the LaTeX source. Each rule fragment lives in its own
small private method so adding new conferences (or new rules) doesn't bloat the
public ``check`` method.

Severity convention used here:

* ``ERROR``    — desk-reject material if uncorrected (NeurIPS missing checklist,
                 ACL missing Limitations, double-blind \\author leak).
* ``WARNING``  — likely a real problem but might be a false positive (style
                 package mismatch, identifying URL).
* ``INFO``     — soft reminder that something MUST happen later (camera-ready
                 sections, lay summaries, font requirements, page-limit
                 estimation that the .tex source can't actually verify).
"""
from __future__ import annotations

import re
from typing import List, Optional

from .base import BaseChecker, CheckResult, CheckSeverity


# ------------------------------------------------------------------ helpers ---

# Match \section{X}, \subsection{X}, \paragraph{X}, optionally starred,
# allowing an optional [short] argument before the {body}.
def _section_pattern(name: str) -> re.Pattern:
    return re.compile(
        r'\\(?:section|subsection|paragraph)\*?\s*(?:\[[^\]]*\])?\s*\{[^}]*?'
        + re.escape(name) + r'[^}]*\}',
        re.IGNORECASE,
    )


# Domains/URL patterns that strongly de-anonymize an author. Whitelisted
# domains (which legitimately appear in CV/ML papers without leaking identity)
# are excluded.
_IDENTIFYING_URL_PATTERNS = [
    re.compile(r'\bgithub\.com/(?!anonymous)[A-Za-z0-9_\-]+/', re.IGNORECASE),
    re.compile(r'\b[A-Za-z0-9_\-]+\.github\.io\b', re.IGNORECASE),
    re.compile(r'\bgitlab\.com/(?!anonymous)[A-Za-z0-9_\-]+/', re.IGNORECASE),
    re.compile(r'\bbitbucket\.org/(?!anonymous)[A-Za-z0-9_\-]+/', re.IGNORECASE),
    re.compile(r'\b(?:huggingface\.co|wandb\.ai)/(?!anonymous)[A-Za-z0-9_\-]+/', re.IGNORECASE),
    re.compile(r'\b(?:linkedin|twitter|x)\.com/[A-Za-z0-9_\-]+', re.IGNORECASE),
]

# URLs that are explicitly anonymous-friendly and should NOT be flagged.
_ANONYMOUS_URL_HINTS = re.compile(
    r'(anonymous|anon|blind|review|submission|4open\.science)', re.IGNORECASE,
)

# Capture URLs from \url{...}, \href{...}{...}, and bare http(s)://...
_URL_FROM_TEX = re.compile(
    r'\\(?:url|href)\s*\{([^}]+)\}|(?<![/\w])(https?://[^\s,)\\]+)',
)

# Acknowledgments macros / sections used by various templates.
_ACK_PATTERNS = [
    re.compile(r'\\section\*?\s*\{\s*Acknowledg\w*\s*\}', re.IGNORECASE),
    re.compile(r'\\acknowledgments?\s*\{', re.IGNORECASE),
    re.compile(r'\\begin\{acks\}', re.IGNORECASE),
]

# NeurIPS Paper Checklist markers — the official template either calls
# \input{neurips_paper_checklist} or includes a \section*{NeurIPS Paper Checklist}.
_NEURIPS_CHECKLIST_PATTERNS = [
    re.compile(r'\\section\*?\s*\{[^}]*Paper\s+Checklist[^}]*\}', re.IGNORECASE),
    re.compile(r'\\input\{[^}]*paper[_\-]?checklist[^}]*\}', re.IGNORECASE),
    re.compile(r'\\input\{[^}]*neurips[_\-]?\d{0,4}[_\-]?checklist[^}]*\}', re.IGNORECASE),
    re.compile(r'\\paperchecklist\b', re.IGNORECASE),
]

# Reproducibility Statement (ICLR / NeurIPS).
_REPRO_SECTION = re.compile(
    r'\\section\*?\s*\{[^}]*Reproducibility[^}]*\}', re.IGNORECASE,
)

# Document-class options carry the paper size.
_DOCCLASS_RE = re.compile(
    r'\\documentclass\s*(?:\[([^\]]*)\])?\s*\{([^}]+)\}'
)

# A very rough regex for figures/tables INSIDE the Limitations section
# (used to enforce ACL "discussion only" rule).
_FLOAT_OR_NEW_SECTION_RE = re.compile(
    r'\\begin\{(?:table|figure|algorithm)\*?\}|\\section\*?\s*\{', re.IGNORECASE,
)


# ----------------------------------------------------------------- checker ---

class TemplateChecker(BaseChecker):
    name = "template"
    display_name = "Conference Template"
    description = "Verify per-venue submission rules (sections, style, anonymity, deliverables)"

    def check(self, tex_content: str, config: dict = None) -> List[CheckResult]:
        config = config or {}
        template = config.get("template")
        if template is None:
            return []

        content = self._remove_comments(tex_content)
        results: List[CheckResult] = []

        self._check_mandatory_sections(template, content, results)
        self._check_camera_only_sections(template, content, results)
        self._check_style_package(template, content, results)
        self._check_doc_class(template, content, results)
        self._check_paper_size(template, content, results)

        if template.double_blind:
            self._check_double_blind_author(template, content, results)
            if template.forbid_identifying_urls:
                self._check_identifying_urls(template, content, results)
            if template.forbid_acks_in_review:
                self._check_acknowledgments(template, content, results)

        if template.requires_paper_checklist:
            self._check_paper_checklist(template, content, results)
        if template.requires_reproducibility_statement:
            self._check_reproducibility_statement(template, content, results)
        if template.requires_lay_summary_camera:
            self._inform_lay_summary(template, results)
        if template.requires_type1_fonts:
            self._inform_type1_fonts(template, results)
        if template.min_main_pages > 0:
            self._inform_min_pages(template, results)

        if "Limitations" in template.mandatory_sections:
            self._check_limitations_content(template, content, results)

        return results

    # ============================================================== sections ==

    def _check_mandatory_sections(self, template, content: str, results: List[CheckResult]):
        for section in template.mandatory_sections or []:
            if not _section_pattern(section).search(content):
                results.append(self._create_result(
                    passed=False,
                    severity=CheckSeverity.ERROR,
                    message=f"[{template.name}] Missing mandatory section: '{section}'",
                    suggestion=f"Add `\\section{{{section}}}` (required by {template.name}).",
                ))

    def _check_camera_only_sections(self, template, content: str, results: List[CheckResult]):
        for section in template.mandatory_camera_sections or []:
            if not _section_pattern(section).search(content):
                results.append(self._create_result(
                    passed=False,
                    severity=CheckSeverity.INFO,
                    message=(
                        f"[{template.name}] Camera-ready section '{section}' not found. "
                        "Required for the camera-ready version, optional for review."
                    ),
                    suggestion=f"Add `\\section{{{section}}}` before References for camera-ready.",
                ))

    # =================================================== style / typesetting ==

    def _check_style_package(self, template, content: str, results: List[CheckResult]):
        pkg = (template.style_package or "").strip()
        if not pkg:
            return
        pkg_re = re.compile(
            r'\\(?:usepackage|documentclass)(?:\[[^\]]*\])?\s*\{\s*'
            + re.escape(pkg) + r'\s*\}'
        )
        if not pkg_re.search(content):
            results.append(self._create_result(
                passed=False,
                severity=CheckSeverity.WARNING,
                message=(
                    f"[{template.name}] Style package '{pkg}' not found. "
                    "If you really are submitting to this venue, your template may be wrong."
                ),
                suggestion=f"Use the official `{pkg}` style package.",
            ))

    def _check_doc_class(self, template, content: str, results: List[CheckResult]):
        wanted = (template.doc_class or "").strip()
        if not wanted:
            return
        m = _DOCCLASS_RE.search(content)
        actual = m.group(2).strip() if m else ""
        if actual.lower() != wanted.lower():
            results.append(self._create_result(
                passed=False,
                severity=CheckSeverity.WARNING,
                message=(
                    f"[{template.name}] Expected `\\documentclass{{{wanted}}}`, "
                    f"found `{actual or 'none'}`."
                ),
                suggestion=f"Use the official document class `{wanted}` (Springer LNCS for ECCV).",
            ))

    def _check_paper_size(self, template, content: str, results: List[CheckResult]):
        wanted = (template.paper_size or "").lower()
        if wanted not in {"letter", "a4"}:
            return
        m = _DOCCLASS_RE.search(content)
        if not m:
            return
        opts = (m.group(1) or "").lower()
        actual = None
        if "letterpaper" in opts or "letter" in opts:
            actual = "letter"
        elif "a4paper" in opts or "a4" in opts:
            actual = "a4"
        if actual and actual != wanted:
            results.append(self._create_result(
                passed=False,
                severity=CheckSeverity.WARNING,
                message=(
                    f"[{template.name}] Expected paper size '{wanted}', "
                    f"document class is set to '{actual}'."
                ),
                suggestion=f"Use `\\documentclass[{wanted}paper]{{...}}`.",
            ))

    # ================================================================ blinding =

    def _check_double_blind_author(self, template, content: str, results: List[CheckResult]):
        m = re.search(r'\\author\s*(?:\[[^\]]*\])?\s*\{([^}]*)\}', content)
        if not m:
            return
        body = m.group(1)
        if not body.strip():
            return
        if re.search(r'(anonymous|hidden|blind|submission)', body, re.IGNORECASE):
            return
        line_num = self._find_line_number(content, m.start())
        results.append(self._create_result(
            passed=False,
            severity=CheckSeverity.ERROR,
            message=f"[{template.name}] Double-blind: \\author appears to contain identifying info",
            line_number=line_num,
            line_content=body.strip(),
            suggestion=r"Replace \author with anonymous placeholder during review.",
        ))

    def _check_identifying_urls(self, template, content: str, results: List[CheckResult]):
        for m in _URL_FROM_TEX.finditer(content):
            url = (m.group(1) or m.group(2) or "").strip()
            if not url:
                continue
            if _ANONYMOUS_URL_HINTS.search(url):
                continue
            for pat in _IDENTIFYING_URL_PATTERNS:
                if pat.search(url):
                    line_num = self._find_line_number(content, m.start())
                    results.append(self._create_result(
                        passed=False,
                        severity=CheckSeverity.WARNING,
                        message=(
                            f"[{template.name}] Possible identifying URL during double-blind review: "
                            f"{url[:120]}"
                        ),
                        line_number=line_num,
                        line_content=url,
                        suggestion=(
                            "Use Anonymous GitHub (https://anonymous.4open.science) or remove "
                            "the link until the camera-ready version."
                        ),
                    ))
                    break  # one finding per URL

    def _check_acknowledgments(self, template, content: str, results: List[CheckResult]):
        for pat in _ACK_PATTERNS:
            m = pat.search(content)
            if m:
                line_num = self._find_line_number(content, m.start())
                results.append(self._create_result(
                    passed=False,
                    severity=CheckSeverity.WARNING,
                    message=(
                        f"[{template.name}] Acknowledgments section detected; "
                        f"{template.short_name.upper()} requires omitting it during review."
                    ),
                    line_number=line_num,
                    suggestion=(
                        "Comment out or wrap acks in `\\if<reviewmode>...\\fi` so they only "
                        "appear in the camera-ready version."
                    ),
                ))
                return  # one finding is enough

    # ============================================== per-venue special items ===

    def _check_paper_checklist(self, template, content: str, results: List[CheckResult]):
        for pat in _NEURIPS_CHECKLIST_PATTERNS:
            if pat.search(content):
                return
        results.append(self._create_result(
            passed=False,
            severity=CheckSeverity.ERROR,
            message=(
                f"[{template.name}] NeurIPS Paper Checklist not found. "
                "NeurIPS desk-rejects submissions without the checklist."
            ),
            suggestion=(
                "Add `\\input{neurips_paper_checklist}` (or paste the official template) "
                "after References / supplementary."
            ),
        ))

    def _check_reproducibility_statement(self, template, content: str, results: List[CheckResult]):
        if _REPRO_SECTION.search(content):
            return
        results.append(self._create_result(
            passed=False,
            severity=CheckSeverity.INFO,
            message=(
                f"[{template.name}] Reproducibility Statement not found. "
                "It's encouraged (~1 page) and does not count toward the page limit."
            ),
            suggestion=(
                "Add `\\section*{Reproducibility Statement}` before References summarizing "
                "code/data/seeds/hyperparameter availability."
            ),
        ))

    def _inform_lay_summary(self, template, results: List[CheckResult]):
        results.append(self._create_result(
            passed=False,
            severity=CheckSeverity.INFO,
            message=(
                f"[{template.name}] Lay summary required at camera-ready time "
                "(plain-language summary submitted via OpenReview)."
            ),
            suggestion="Draft a 1–2 paragraph plain-language summary now to avoid a last-minute scramble.",
        ))

    def _inform_type1_fonts(self, template, results: List[CheckResult]):
        results.append(self._create_result(
            passed=False,
            severity=CheckSeverity.INFO,
            message=(
                f"[{template.name}] Embedded fonts must be Type-1 only — verify with "
                "`pdffonts <paper.pdf>`. Cannot be checked from .tex source alone."
            ),
            suggestion="Compile with `pdflatex` (not XeLaTeX/LuaLaTeX) and convert any Type-3 fonts.",
        ))

    def _inform_min_pages(self, template, results: List[CheckResult]):
        results.append(self._create_result(
            passed=False,
            severity=CheckSeverity.INFO,
            message=(
                f"[{template.name}] Main text must be at least {template.min_main_pages} pages "
                f"and at most {template.page_limit_review} pages. Cannot be measured from source."
            ),
            suggestion=(
                f"Compile and confirm the rendered PDF stays within "
                f"{template.min_main_pages}–{template.page_limit_review} pages of main text."
            ),
        ))

    # ============================================ ACL family: Limitations rule

    def _check_limitations_content(self, template, content: str, results: List[CheckResult]):
        # Find the Limitations section span up to the next \section or end of doc.
        m = re.search(
            r'(\\section\*?\s*(?:\[[^\]]*\])?\s*\{[^}]*Limitations[^}]*\})',
            content, re.IGNORECASE,
        )
        if not m:
            return  # mandatory_sections check already flagged absence
        start = m.end()
        nxt = re.search(r'\\section\*?\s*\{', content[start:], re.IGNORECASE)
        end = start + nxt.start() if nxt else len(content)
        section_body = content[start:end]
        # Discussion-only rule: no floats, no nested \section
        if _FLOAT_OR_NEW_SECTION_RE.search(section_body):
            line_num = self._find_line_number(content, start)
            results.append(self._create_result(
                passed=False,
                severity=CheckSeverity.WARNING,
                message=(
                    f"[{template.name}] Limitations section appears to contain floats or a "
                    "nested section. ACL/EMNLP/NAACL require Limitations to be discussion only."
                ),
                line_number=line_num,
                suggestion=(
                    "Move tables/figures/algorithms out of Limitations into the main body or "
                    "appendix; Limitations should be prose-only."
                ),
            ))
