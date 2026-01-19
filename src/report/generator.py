"""
Report generator for bibliography check results.
"""
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List
from pathlib import Path

from ..parsers.bib_parser import BibEntry
from ..analyzers.metadata_comparator import ComparisonResult
from ..analyzers.usage_checker import UsageResult
from ..analyzers.llm_evaluator import EvaluationResult
from ..analyzers.duplicate_detector import DuplicateGroup
from ..checkers.base import CheckResult, CheckSeverity


@dataclass
class EntryReport:
    """Complete report for a single bib entry."""
    entry: BibEntry
    comparison: Optional[ComparisonResult]
    usage: Optional[UsageResult]
    evaluations: list[EvaluationResult]


class ReportGenerator:
    """Generates formatted markdown reports."""
    
    def __init__(self, minimal_verified: bool = False):
        self.entries: list[EntryReport] = []
        self.missing_citations: list[str] = []
        self.duplicate_groups: list[DuplicateGroup] | None = None  # None means check not run
        self.bib_file: str = ""
        self.tex_file: str = ""
        self.minimal_verified = minimal_verified  # Whether to show minimal info for verified entries
        self.submission_results: List[CheckResult] = []  # Submission quality check results
        self.template = None  # Conference template if used

    
    def add_entry_report(self, report: EntryReport):
        """Add an entry report."""
        self.entries.append(report)
    
    def set_metadata(self, bib_file: str, tex_file: str):
        """Set source file information."""
        self.bib_file = bib_file
        self.tex_file = tex_file
    
    def set_missing_citations(self, missing: list[str]):
        """Set list of citations without bib entries."""
        self.missing_citations = missing
    
    def set_duplicate_groups(self, groups: list[DuplicateGroup]):
        """Set list of duplicate entry groups."""
        self.duplicate_groups = groups
    
    def set_submission_results(self, results: List[CheckResult], template=None):
        """Set submission quality check results."""
        self.submission_results = results
        self.template = template
    
    def generate(self) -> str:
        """Generate the full markdown report."""
        lines = []
        
        # Header
        lines.extend(self._generate_header())
        lines.append("")
        
        # Disclaimer
        lines.extend(self._generate_disclaimer())
        lines.append("")
        
        # Summary statistics
        lines.extend(self._generate_summary())
        lines.append("")
        
        # ⚠️ Critical Issues (Detailed) - Bibliography-related issues
        lines.extend(self._generate_issues_section())
        lines.append("")
        
        # ✅ Verified Entries (Clean)
        lines.extend(self._generate_verified_section())
        lines.append("")
        
        # 📋 Submission Quality Checks (LaTeX quality checks)
        if self.submission_results:
            lines.extend(self._generate_submission_section())
            lines.append("")
        
        # Footer
        lines.extend(self._generate_footer())
        
        return "\n".join(lines)

    def get_summary_stats(self) -> tuple[dict, dict]:
        """Get summary statistics as dictionaries for console display (Issues only)."""
        total = len(self.entries)
        
        # Bibliography issues breakdown
        title_mismatches = 0
        author_mismatches = 0
        year_mismatches = 0
        low_relevance = 0
        unable_to_verify = 0
        
        for e in self.entries:
            # Metadata issues
            if e.comparison:
                if e.comparison.has_issues:
                    # Categorize issues
                    has_title = False
                    has_author = False
                    has_year = False
                    
                    for issue in e.comparison.issues:
                        if "Title mismatch" in issue: has_title = True
                        elif "Author mismatch" in issue: has_author = True
                        elif "Year mismatch" in issue: has_year = True
                        elif "Unable to find" in issue: unable_to_verify += 1
                    
                    if has_title: title_mismatches += 1
                    if has_author: author_mismatches += 1
                    if has_year: year_mismatches += 1
            
            # Relevance issues
            if any(ev.relevance_score <= 2 for ev in e.evaluations):
                low_relevance += 1

        bib_stats = {}
        if title_mismatches > 0: bib_stats["Title Mismatches"] = title_mismatches
        if author_mismatches > 0: bib_stats["Author Mismatches"] = author_mismatches
        if year_mismatches > 0: bib_stats["Year Mismatches"] = year_mismatches
        if low_relevance > 0: bib_stats["Low Relevance"] = low_relevance
        if unable_to_verify > 0: bib_stats["Unable to Verify"] = unable_to_verify
        
        if self.duplicate_groups:
            bib_stats["Duplicate Groups"] = len(self.duplicate_groups)
        
        if self.missing_citations:
            bib_stats["Missing Bib Entries"] = len(self.missing_citations)
            
        unused = [e for e in self.entries if e.usage and not e.usage.is_used]
        if unused:
            bib_stats["Unused Entries"] = len(unused)
        
        # LaTeX stats - Group by precise Rule Names
        latex_stats = {}
        
        # Rule mapping for professional display names
        RULE_MAPPING = {
            "Very long sentence": "Sentence Length (Critical)",
            "Long sentence": "Sentence Length (Warning)",
            "Possible Markdown bullet point": "Markdown Bullet Point",
            "Possible Markdown numbered list": "Markdown Numbered List",
            "Possible Markdown italic": "Markdown Italic",
            "Possible Markdown bold": "Markdown Bold",
            "Inconsistent hyphenation": "Hyphenation Inconsistency",
            "Inconsistent spelling": "Spelling Inconsistency",
            "Unreferenced figure": "Unreferenced Figure",
            "Unreferenced table": "Unreferenced Table",
            "Unreferenced section": "Unreferenced Section",
            "Unreferenced label": "Unreferenced Label",
            "Multiple blank lines": "Multiple Blank Lines",
            "Citation from": "Old Citation (10+ years)",
            "Hedging language": "Hedging/Vague Language",
            "Redundant phrase": "Redundant Phrasing",
            "Weak start with": "Weak Sentence Starter",
            "Unescaped &": "Unescaped Special Character",
            "Citation without non-breaking space": "Missing Non-breaking Space (~)",
            "Mixed citation styles": "Mixed Citation Styles",
            "Mixed inline math": "Mixed Math Notation",
            "Appendix section": "Unreferenced Appendix",
            "Missing space before unit": "Unit Spacing Issue"
        }

        for r in self.submission_results:
            if r.passed:
                continue
            
            raw_msg = r.message
            rule_name = "Unknown Rule"
            
            # Match against our professional rule names
            matched = False
            for pattern, official_name in RULE_MAPPING.items():
                if pattern in raw_msg:
                    rule_name = official_name
                    matched = True
                    break
            
            if not matched:
                # Fallback: Clean the message (remove dynamic parts)
                clean_msg = re.sub(r"\(.*?\)", "", raw_msg)
                clean_msg = re.sub(r"'.*?'", "", clean_msg)
                clean_msg = re.sub(r"\d+", "", clean_msg)
                rule_name = clean_msg.split(":")[0].strip()
            
            if rule_name not in latex_stats:
                latex_stats[rule_name] = 0
            latex_stats[rule_name] += 1
        
        return bib_stats, latex_stats

    def generate_console_output(self) -> str:
        """Generate console-friendly output (Summary + Issues only)."""
        lines = []
        
        # Summary statistics
        lines.extend(self._generate_summary())
        lines.append("")
        
        # Critical Issues
        lines.extend(self._generate_issues_section())
        lines.append("")
        
        return "\n".join(lines)
    
    def _generate_header(self) -> list[str]:
        """Generate report header."""
        bib_name = Path(self.bib_file).name if self.bib_file else "N/A"
        tex_name = Path(self.tex_file).name if self.tex_file else "N/A"
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        return [
            "# Bibliography Validation Report",
            "",
            f"**Generated:** {timestamp}",
            "",
            "| File Type | Filename |",
            "|-----------|----------|",
            f"| **Bib File** | `{bib_name}` |",
            f"| **TeX File** | `{tex_name}` |"
        ]

    def _generate_disclaimer(self) -> list[str]:
        """Generate disclaimer section."""
        return [
            "> **⚠️ Disclaimer:** This report is generated by an automated tool. While BibGuard strives for accuracy, it may produce false positives or miss certain issues. **This tool cannot replace human review.** Please manually verify all reported issues before making changes to your bibliography."
        ]
    
    def _generate_summary(self) -> list[str]:
        """Generate summary statistics."""
        total = len(self.entries)
        
        # Check availability of results
        has_metadata = any(e.comparison is not None for e in self.entries)
        has_usage = any(e.usage is not None for e in self.entries)
        has_eval = any(len(e.evaluations) > 0 for e in self.entries)
        
        # Calculate Verified/Issues
        # Note: _is_verified depends on _has_issues. 
        # If a check wasn't run, it won't contribute to issues.
        verified = sum(1 for e in self.entries if self._is_verified(e))
        issues = sum(1 for e in self.entries if self._has_issues(e))
        
        # Usage stats
        if has_usage:
            used = sum(1 for e in self.entries if e.usage and e.usage.is_used)
            unused = total - used
            used_str = str(used)
            unused_str = str(unused)
            missing_str = str(len(self.missing_citations))
        else:
            used_str = "N/A"
            unused_str = "N/A"
            missing_str = "N/A"
            
        # Duplicate stats - show N/A if check wasn't run (duplicate_groups is None means not checked)
        if self.duplicate_groups is None:
            dup_str = "N/A"
        else:
            dup_str = str(len(self.duplicate_groups))

        return [
            "## 📊 Summary",
            "",
            "### 📚 Bibliography Statistics",
            "",
            "| Metric | Count |",
            "|--------|-------|",
            f"| **Total Entries** | {total} |",
            f"| ✅ **Verified (Clean)** | {verified} |",
            f"| ⚠️ **With Issues** | {issues} |",
            f"| 📝 **Used in TeX** | {used_str} |",
            f"| 🗑️ **Unused** | {unused_str} |",
            f"| 🔄 **Duplicate Groups** | {dup_str} |",
            f"| ❌ **Missing Bib Entries** | {missing_str} |",
            "",
            "### 📋 LaTeX Quality Checks",
            "",
            self._get_submission_summary()
        ]
    
    def _get_submission_summary(self) -> str:
        """Generate submission quality summary table."""
        if not self.submission_results:
            return "*No quality checks were performed.*"
        
        # Count by severity
        error_count = sum(1 for r in self.submission_results if r.severity == CheckSeverity.ERROR)
        warning_count = sum(1 for r in self.submission_results if r.severity == CheckSeverity.WARNING)
        info_count = sum(1 for r in self.submission_results if r.severity == CheckSeverity.INFO)
        
        lines = [
            "| Severity | Count |",
            "|----------|-------|",
            f"| 🔴 **Errors** | {error_count} |",
            f"| 🟡 **Warnings** | {warning_count} |",
            f"| 🔵 **Suggestions** | {info_count} |"
        ]
        return "\n".join(lines)
    
    def _is_verified(self, entry: EntryReport) -> bool:
        """Check if entry is clean (no issues)."""
        return not self._has_issues(entry)

    def _has_issues(self, entry: EntryReport) -> bool:
        """Check if entry has any issues."""
        # Metadata issues
        if entry.comparison and entry.comparison.has_issues:
            return True
        # LLM issues (low relevance)
        if any(ev.relevance_score <= 2 for ev in entry.evaluations):
            return True
        # NOTE: We don't include usage issues (unused) here because
        # unused entries are already shown in the "Unused Entries" section
        return False
    
    def _has_metadata_or_relevance_issues(self, entry: EntryReport) -> bool:
        """Check if entry has metadata or relevance issues (excluding duplicate/unused)."""
        # Metadata issues
        if entry.comparison and entry.comparison.has_issues:
            return True
        # LLM issues (low relevance)
        if any(ev.relevance_score <= 2 for ev in entry.evaluations):
            return True
        return False

    def _generate_issues_section(self) -> list[str]:
        """Generate detailed section for entries with issues."""
        lines = ["## ⚠️ Critical Issues Detected", ""]
        
        has_any_issues = False
        
        # 1. Missing Citations
        if self.missing_citations:
            has_any_issues = True
            lines.append("### ❌ Missing Bibliography Entries")
            lines.append("The following keys are cited in the TeX file but missing from the .bib file:")
            lines.append("")
            for key in self.missing_citations:
                lines.append(f"- `{key}`")
            lines.append("")

        # 2. Duplicate Entries
        if self.duplicate_groups:
            has_any_issues = True
            lines.append("### 🔄 Duplicate Entries")
            for i, group in enumerate(self.duplicate_groups, 1):
                lines.append(f"#### Group {i} (Similarity: {group.similarity_score:.0%})")
                lines.append(f"**Reason:** {group.reason}")
                lines.append("")
                lines.append("| Key | Title | Year |")
                lines.append("|-----|-------|------|")
                for entry in group.entries:
                    lines.append(f"| `{entry.key}` | {entry.title} | {entry.year} |")
                lines.append("")

        # 3. Unused Entries
        unused = [e for e in self.entries if e.usage and not e.usage.is_used]
        if unused:
            has_any_issues = True
            lines.append("### 🗑️ Unused Entries")
            lines.append("The following entries are in the .bib file but NOT cited in the TeX file:")
            lines.append("")
            for e in unused:
                lines.append(f"- `{e.entry.key}`: *{e.entry.title}*")
            lines.append("")

        # 4. Metadata Mismatches & Low Relevance
        issue_entries = [e for e in self.entries if self._has_metadata_or_relevance_issues(e)]
        
        if issue_entries:
            has_any_issues = True
            lines.append("### ⚠️ Metadata & Relevance Issues")
            
            for entry_report in issue_entries:
                lines.extend(self._format_entry_detail(entry_report, is_verified=False))

        if not has_any_issues:
            lines.append("🎉 **No critical issues found!**")

        return lines

    def _generate_verified_section(self) -> list[str]:
        """Generate section for verified entries."""
        lines = ["## ✅ Verified Entries", ""]
        
        verified = [e for e in self.entries if self._is_verified(e)]
        
        if not verified:
            lines.append("_No verified entries found._")
            return lines
            
        lines.append(f"Found **{len(verified)}** entries with correct metadata.")
        lines.append("")
        
        # Use a collapsible details block for clean UI
        lines.append("<details>")
        lines.append("<summary>Click to view verified entries</summary>")
        lines.append("")
        
        for entry_report in verified:
            lines.extend(self._format_entry_detail(entry_report, minimal=self.minimal_verified, is_verified=True))
            
        lines.append("</details>")
        return lines

    def _format_entry_detail(self, report: EntryReport, minimal: bool = False, is_verified: bool = False) -> list[str]:
        """Format a single entry report in Markdown."""
        entry = report.entry
        comp = report.comparison
        lines = []
        
        # Title header - use checkmark for verified entries, warning for issues
        icon = "✅" if is_verified else "⚠️"
        lines.append(f"#### {icon} `{entry.key}`")
        lines.append(f"**Title:** {entry.title}")
        lines.append("")
        
        # Metadata Status
        if comp:
            status_icon = "✅" if comp.is_match else "❌"
            lines.append(f"- **Metadata Status:** {status_icon} {comp.source.upper()} (Confidence: {comp.confidence:.1%})")
            
            if comp.has_issues and not minimal:
                lines.append("  - **Discrepancies:**")
                for issue in comp.issues:
                     # Format mismatch details nicely
                    if "Mismatch" in issue or "mismatch" in issue:
                        lines.append(f"    - 🔴 {issue}")
                        if "Title" in issue:
                            lines.append(f"      - **Bib:** `{comp.bib_title}`")
                            lines.append(f"      - **Fetched:** `{comp.fetched_title}`")
                        elif "Author" in issue:
                            lines.append(f"      - **Bib:** `{', '.join(comp.bib_authors)}`")
                            lines.append(f"      - **Fetched:** `{', '.join(comp.fetched_authors)}`")
                    else:
                        lines.append(f"    - 🔸 {issue}")
        
        # Relevance Status
        if report.evaluations and not minimal:
            lines.append("- **Relevance Analysis:**")
            for eval_res in report.evaluations:
                score_icon = "🟢" if eval_res.relevance_score >= 4 else ("🟡" if eval_res.relevance_score == 3 else "🔴")
                lines.append(f"  - {score_icon} **Score {eval_res.relevance_score}/5** ({eval_res.score_label})")
                if eval_res.line_number:
                    lines.append(f"    - Line {eval_res.line_number}")
                lines.append(f"    - *\"{eval_res.explanation}\"*")

        lines.append("")
        lines.append("---")
        lines.append("")
        return lines
    
    def _generate_submission_section(self) -> list[str]:
        """Generate section for submission quality check results."""
        lines = ["## 📋 Submission Quality Checks", ""]
        
        # Template info
        if self.template:
            lines.append(f"**Conference Template:** {self.template.name}")
            lines.append(f"**Page Limit:** {self.template.page_limit_review} (review) / {self.template.page_limit_camera} (camera-ready)")
            if self.template.mandatory_sections:
                lines.append(f"**Required Sections:** {', '.join(self.template.mandatory_sections)}")
            lines.append("")
        
        # Count by severity
        errors = [r for r in self.submission_results if r.severity == CheckSeverity.ERROR and not r.passed]
        warnings = [r for r in self.submission_results if r.severity == CheckSeverity.WARNING and not r.passed]
        infos = [r for r in self.submission_results if r.severity == CheckSeverity.INFO and not r.passed]
        
        # Summary
        if errors or warnings or infos:
            lines.append("| Severity | Count |")
            lines.append("|----------|-------|")
            if errors:
                lines.append(f"| 🔴 **Errors** | {len(errors)} |")
            if warnings:
                lines.append(f"| 🟡 **Warnings** | {len(warnings)} |")
            if infos:
                lines.append(f"| 🔵 **Suggestions** | {len(infos)} |")
            lines.append("")
        else:
            lines.append("🎉 **No submission issues found!**")
            lines.append("")
            return lines
        
        # Group by checker
        by_checker = {}
        for result in self.submission_results:
            if result.passed:
                continue
            if result.checker_name not in by_checker:
                by_checker[result.checker_name] = []
            by_checker[result.checker_name].append(result)
        
        # Display errors first
        if errors:
            lines.append("### 🔴 Critical Errors")
            lines.append("")
            for result in errors:
                lines.append(f"- **{result.message}**")
                if result.line_number:
                    lines.append(f"  - Line {result.line_number}")
                if result.line_content:
                    lines.append(f"  - `{result.line_content[:80]}`")
                if result.suggestion:
                    lines.append(f"  - 💡 *{result.suggestion}*")
            lines.append("")
        
        # Display warnings
        if warnings:
            lines.append("### 🟡 Warnings")
            lines.append("")
            for result in warnings:
                lines.append(f"- {result.message}")
                if result.line_number:
                    lines.append(f"  - Line {result.line_number}")
                if result.suggestion:
                    lines.append(f"  - 💡 *{result.suggestion}*")
            lines.append("")
        
        # Display suggestions (collapsible)
        if infos:
            lines.append("### 🔵 Suggestions")
            lines.append("<details>")
            lines.append("<summary>Click to view suggestions</summary>")
            lines.append("")
            for result in infos:
                lines.append(f"- {result.message}")
                if result.line_number:
                    lines.append(f"  - Line {result.line_number}")
                if result.suggestion:
                    lines.append(f"  - 💡 *{result.suggestion}*")
            lines.append("")
            lines.append("</details>")
            lines.append("")
        
        return lines

    def _generate_footer(self) -> list[str]:
        """Generate report footer."""
        return [
            "",
            "---",
            f"Report generated by **BibGuard** on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        ]
    
    def save(self, filepath: str):
        """Save report to file."""
        content = self.generate()
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
    
    def save_bibliography_report(self, filepath: str):
        """Generate and save bibliography-only report (all bib-related checks)."""
        lines = []
        
        # Header
        lines.append("# Bibliography Validation Report")
        lines.append("")
        lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")
        bib_name = Path(self.bib_file).name if self.bib_file else "N/A"
        tex_name = Path(self.tex_file).name if self.tex_file else "N/A"
        lines.append("| File Type | Filename |")
        lines.append("|-----------|----------|")
        lines.append(f"| **Bib File** | `{bib_name}` |")
        lines.append(f"| **TeX File** | `{tex_name}` |")
        lines.append("")
        
        # Disclaimer
        lines.extend(self._generate_disclaimer())
        lines.append("")
        
        # Summary - Bibliography only
        total = len(self.entries)
        verified = sum(1 for e in self.entries if self._is_verified(e))
        issues = sum(1 for e in self.entries if self._has_issues(e))
        
        has_usage = any(e.usage is not None for e in self.entries)
        if has_usage:
            used = sum(1 for e in self.entries if e.usage and e.usage.is_used)
            unused = total - used
            used_str = str(used)
            unused_str = str(unused)
            missing_str = str(len(self.missing_citations))
        else:
            used_str = "N/A"
            unused_str = "N/A"
            missing_str = "N/A"
        
        if self.duplicate_groups is None:
            dup_str = "N/A"
        else:
            dup_str = str(len(self.duplicate_groups))
        
        lines.append("## 📊 Summary")
        lines.append("")
        lines.append("| Metric | Count |")
        lines.append("|--------|-------|")
        lines.append(f"| **Total Entries** | {total} |")
        lines.append(f"| ✅ **Verified (Clean)** | {verified} |")
        lines.append(f"| ⚠️ **With Issues** | {issues} |")
        lines.append(f"| 📝 **Used in TeX** | {used_str} |")
        lines.append(f"| 🗑️ **Unused** | {unused_str} |")
        lines.append(f"| 🔄 **Duplicate Groups** | {dup_str} |")
        lines.append(f"| ❌ **Missing Bib Entries** | {missing_str} |")
        lines.append("")
        
        # Issues section
        lines.extend(self._generate_issues_section())
        lines.append("")
        
        # Verified entries
        lines.extend(self._generate_verified_section())
        lines.append("")
        
        # Footer
        lines.extend(self._generate_footer())
        
        content = "\n".join(lines)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
    
    def save_latex_quality_report(self, filepath: str, submission_results: List[CheckResult], template=None):
        """Generate and save LaTeX quality report (all tex-related quality checks)."""
        lines = []
        
        # Header
        lines.append("# LaTeX Quality Report")
        lines.append("")
        lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")
        tex_name = Path(self.tex_file).name if self.tex_file else "N/A"
        lines.append(f"**TeX File:** `{tex_name}`")
        lines.append("")
        
        if template:
            lines.append(f"**Template:** {template.name}")
            lines.append("")
        
        # Disclaimer
        lines.append("> **⚠️ Note:** This report contains automated quality checks for your LaTeX document. Please review all suggestions carefully before making changes.")
        lines.append("")
        
        # Summary
        error_count = sum(1 for r in submission_results if r.severity == CheckSeverity.ERROR)
        warning_count = sum(1 for r in submission_results if r.severity == CheckSeverity.WARNING)
        info_count = sum(1 for r in submission_results if r.severity == CheckSeverity.INFO)
        
        lines.append("## 📊 Summary")
        lines.append("")
        lines.append("| Severity | Count |")
        lines.append("|----------|-------|")
        lines.append(f"| 🔴 **Errors** | {error_count} |")
        lines.append(f"| 🟡 **Warnings** | {warning_count} |")
        lines.append(f"| 🔵 **Suggestions** | {info_count} |")
        lines.append("")
        
        # Detailed issues
        self.submission_results = submission_results
        self.template = template
        lines.extend(self._generate_submission_section())
        lines.append("")
        
        # Footer
        lines.append("---")
        lines.append("")
        lines.append(f"Report generated by **BibGuard** on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        content = "\n".join(lines)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)

