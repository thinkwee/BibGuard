"""
Report generator for bibliography check results.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from pathlib import Path

from ..parsers.bib_parser import BibEntry
from ..analyzers.metadata_comparator import ComparisonResult
from ..analyzers.usage_checker import UsageResult
from ..analyzers.llm_evaluator import EvaluationResult
from ..analyzers.duplicate_detector import DuplicateGroup


@dataclass
class EntryReport:
    """Complete report for a single bib entry."""
    entry: BibEntry
    comparison: Optional[ComparisonResult]
    usage: Optional[UsageResult]
    evaluations: list[EvaluationResult]


class ReportGenerator:
    """Generates formatted text reports."""
    
    def __init__(self):
        self.entries: list[EntryReport] = []
        self.missing_citations: list[str] = []
        self.duplicate_groups: list[DuplicateGroup] = []
        self.bib_file: str = ""
        self.tex_file: str = ""
    
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
    
    def generate(self) -> str:
        """Generate the full text report."""
        lines = []
        
        # Header
        lines.extend(self._generate_header())
        lines.append("")
        
        # Summary statistics
        lines.extend(self._generate_summary())
        lines.append("")
        
        # Duplicate detection
        if self.duplicate_groups:
            lines.extend(self._generate_duplicates_section())
            lines.append("")
        
        # Metadata validation results
        lines.extend(self._generate_metadata_section())
        lines.append("")
        
        # Usage analysis
        lines.extend(self._generate_usage_section())
        lines.append("")
        
        # LLM evaluation results
        lines.extend(self._generate_evaluation_section())
        lines.append("")
        
        # Recommendations
        lines.extend(self._generate_recommendations())
        lines.append("")
        
        # Footer
        lines.extend(self._generate_footer())
        
        return "\n".join(lines)
    
    def _generate_header(self) -> list[str]:
        """Generate report header."""
        width = 80
        lines = [
            "╔" + "═" * (width - 2) + "╗",
            "║" + "Bibliography Validation Report".center(width - 2) + "║",
            "╠" + "═" * (width - 2) + "╣",
        ]
        
        # File info
        bib_name = Path(self.bib_file).name if self.bib_file else "N/A"
        tex_name = Path(self.tex_file).name if self.tex_file else "N/A"
        
        lines.append("║" + f"  Bib File: {bib_name}".ljust(width - 2) + "║")
        lines.append("║" + f"  TeX File: {tex_name}".ljust(width - 2) + "║")
        lines.append("║" + f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}".ljust(width - 2) + "║")
        lines.append("╚" + "═" * (width - 2) + "╝")
        
        return lines
    
    def _generate_summary(self) -> list[str]:
        """Generate summary statistics."""
        lines = []
        lines.append("┌" + "─" * 40 + "┐")
        lines.append("│" + " SUMMARY ".center(40) + "│")
        lines.append("├" + "─" * 40 + "┤")
        
        total = len(self.entries)
        verified = sum(1 for e in self.entries if e.comparison and e.comparison.is_match)
        issues = sum(1 for e in self.entries if e.comparison and e.comparison.has_issues)
        used = sum(1 for e in self.entries if e.usage and e.usage.is_used)
        unused = total - used
        evaluated_entries = sum(1 for e in self.entries if e.evaluations)
        total_evaluations = sum(len(e.evaluations) for e in self.entries)
        relevant_citations = sum(
            sum(1 for eval_res in e.evaluations if eval_res.is_relevant)
            for e in self.entries
        )
        
        lines.append("│" + f"  Total Entries:          {total:>5}".ljust(40) + "│")
        lines.append("│" + f"  Verified (match):       {verified:>5}".ljust(40) + "│")
        lines.append("│" + f"  With Issues:            {issues:>5}".ljust(40) + "│")
        lines.append("│" + f"  Used in TeX:            {used:>5}".ljust(40) + "│")
        lines.append("│" + f"  Unused:                 {unused:>5}".ljust(40) + "│")
        lines.append("│" + f"  Duplicate Groups:       {len(self.duplicate_groups):>5}".ljust(40) + "│")
        lines.append("│" + f"  Entries Evaluated:      {evaluated_entries:>5}".ljust(40) + "│")
        lines.append("│" + f"  Total Citations Checked:{total_evaluations:>5}".ljust(40) + "│")
        lines.append("│" + f"  Relevant Citations:     {relevant_citations:>5}".ljust(40) + "│")
        lines.append("│" + f"  Missing Bib Entries:    {len(self.missing_citations):>5}".ljust(40) + "│")
        lines.append("└" + "─" * 40 + "┘")
        
        return lines
    
    def _generate_duplicates_section(self) -> list[str]:
        """Generate duplicate detection section."""
        lines = []
        lines.append("")
        lines.append("=" * 80)
        lines.append(" DUPLICATE DETECTION ".center(80))
        lines.append("=" * 80)
        
        if not self.duplicate_groups:
            lines.append("")
            lines.append("  ✓ No duplicate entries detected")
            return lines
        
        lines.append("")
        lines.append(f"Found {len(self.duplicate_groups)} potential duplicate groups:")
        
        for i, group in enumerate(self.duplicate_groups, 1):
            lines.append("")
            lines.append(f"┌─ Duplicate Group {i} " + "─" * (60 - len(str(i))))
            lines.append(f"│  Similarity: {group.similarity_score:.0%}")
            lines.append(f"│  Reason: {group.reason}")
            lines.append(f"│  Entries ({len(group.entries)}):")
            
            for entry in group.entries:
                lines.append(f"│    • [{entry.key}]")
                lines.append(f"│      Title: {self._truncate(entry.title, 60)}")
                if entry.year:
                    lines.append(f"│      Year: {entry.year}")
            
            lines.append("└" + "─" * 75)
        
        return lines
    
    def _generate_metadata_section(self) -> list[str]:
        """Generate metadata validation section."""
        lines = []
        lines.append("")
        lines.append("=" * 80)
        lines.append(" METADATA VALIDATION ".center(80))
        lines.append("=" * 80)
        
        for entry_report in self.entries:
            entry = entry_report.entry
            comp = entry_report.comparison
            
            lines.append("")
            lines.append(f"┌─ [{entry.key}] " + "─" * max(0, 70 - len(entry.key)))
            lines.append(f"│  Type: {entry.entry_type}")
            lines.append(f"│  Title: {self._truncate(entry.title, 60)}")
            
            if comp:
                status = "✓ MATCH" if comp.is_match else "✗ MISMATCH"
                lines.append(f"│  Source: {comp.source.upper()}")
                lines.append(f"│  Status: {status}")
                lines.append(f"│  Confidence: {comp.confidence:.1%}")
                
                # Show all discrepancies if confidence is not 100%
                if comp.confidence < 0.999:
                    lines.append("│  Discrepancies:")
                    
                    # Check Title
                    if comp.title_similarity < 0.999:
                        status = "Mismatch" if not comp.title_match else "Minor variation"
                        lines.append(f"│    - Title {status} (similarity: {comp.title_similarity:.1%})")
                        lines.append(f"│      Bib: '{comp.bib_title}'")
                        lines.append(f"│      Fetched: '{comp.fetched_title}'")
                    
                    # Check Author
                    if comp.author_similarity < 0.999:
                        status = "Mismatch" if not comp.author_match else "Minor variation"
                        lines.append(f"│    - Author {status} (similarity: {comp.author_similarity:.1%})")
                        lines.append(f"│      Bib: {', '.join(comp.bib_authors)}")
                        lines.append(f"│      Fetched: {', '.join(comp.fetched_authors)}")
                    
                    # Check Year
                    if not comp.year_match:
                        lines.append(f"│    - Year mismatch: bib='{comp.bib_year}', fetched='{comp.fetched_year}'")
                    
                    # Other issues (e.g. unable to fetch)
                    for issue in comp.issues:
                        # Skip standard mismatch messages as we handled them above with more detail
                        if "mismatch" in issue and ("Title" in issue or "Author" in issue or "Year" in issue):
                            continue
                        lines.append(f"│    - {issue}")
            else:
                lines.append("│  Status: Unable to verify")
            
            lines.append("└" + "─" * 75)
        
        return lines
    
    def _generate_usage_section(self) -> list[str]:
        """Generate usage analysis section."""
        lines = []
        lines.append("")
        lines.append("=" * 80)
        lines.append(" CITATION USAGE ANALYSIS ".center(80))
        lines.append("=" * 80)
        
        # Unused entries
        unused = [e for e in self.entries if e.usage and not e.usage.is_used]
        if unused:
            lines.append("")
            lines.append("┌─ Unused Entries (not cited in TeX) " + "─" * 40)
            for entry_report in unused:
                lines.append(f"│  ⚠ {entry_report.entry.key}")
            lines.append("└" + "─" * 75)
        else:
            lines.append("")
            lines.append("  ✓ All bib entries are cited in the document")
        
        # Missing citations
        if self.missing_citations:
            lines.append("")
            lines.append("┌─ Missing Bib Entries (cited but not in bib) " + "─" * 30)
            for key in self.missing_citations:
                lines.append(f"│  ✗ {key}")
            lines.append("└" + "─" * 75)
        
        # Usage statistics
        lines.append("")
        lines.append("┌─ Citation Frequency " + "─" * 55)
        used_entries = sorted(
            [(e.entry.key, e.usage.usage_count) for e in self.entries if e.usage and e.usage.is_used],
            key=lambda x: x[1],
            reverse=True
        )
        for key, count in used_entries:
            bar = "█" * min(count, 20)
            lines.append(f"│  {key} {count:3}x {bar}")
        lines.append("└" + "─" * 75)
        
        return lines
    
    def _generate_evaluation_section(self) -> list[str]:
        """Generate LLM evaluation section."""
        lines = []
        lines.append("")
        lines.append("=" * 80)
        lines.append(" CITATION RELEVANCE ANALYSIS (LLM) ".center(80))
        lines.append("=" * 80)
        
        evaluated = [e for e in self.entries if e.evaluations]
        
        if not evaluated:
            lines.append("")
            lines.append("  (No LLM evaluation performed or all evaluations failed)")
            return lines
        
        # Collect all evaluations
        all_evaluations = []
        for entry_report in evaluated:
            for eval_res in entry_report.evaluations:
                all_evaluations.append((entry_report.entry, eval_res))
        
        # Group by score (High to Low)
        evals_by_score = {5: [], 4: [], 3: [], 2: [], 1: [], 0: []}
        for entry, eval_res in all_evaluations:
            score = eval_res.relevance_score
            if score not in evals_by_score:
                score = 0
            evals_by_score[score].append((entry, eval_res))
            
        # Generate report by score groups
        score_labels = {
            5: "Highly Relevant (5/5)",
            4: "Relevant (4/5)",
            3: "Somewhat Relevant (3/5)",
            2: "Marginally Relevant (2/5)",
            1: "Not Relevant (1/5)",
            0: "Unknown/Error"
        }
        
        for score in range(5, -1, -1):
            group_evals = evals_by_score[score]
            if not group_evals:
                continue
                
            lines.append("")
            lines.append(f"┌─ {score_labels[score]} ({len(group_evals)} citations) " + "─" * 30)
            
            for entry, eval_res in group_evals:
                lines.append(f"│  • [{entry.key}]")
                if eval_res.line_number:
                    lines.append(f"│    Line: {eval_res.line_number}")
                
                # Show context
                lines.append(f"│    Context:")
                context_lines = self._wrap_text(f"\"{eval_res.context_used}\"", 70)
                for line in context_lines:
                    lines.append(f"│      {line}")
                
                # Show explanation
                lines.append(f"│    Explanation:")
                explanation_lines = self._wrap_text(eval_res.explanation, 70)
                for line in explanation_lines:
                    lines.append(f"│      {line}")
                
                lines.append("│" + "─" * 75)
            
            lines.append("└" + "─" * 75)
        
        return lines
    
    def _generate_recommendations(self) -> list[str]:
        """Generate recommendations section."""
        lines = []
        lines.append("")
        lines.append("=" * 80)
        lines.append(" RECOMMENDATIONS ".center(80))
        lines.append("=" * 80)
        lines.append("")
        
        recommendations = []
        
        # Check for unused entries
        unused = [e for e in self.entries if e.usage and not e.usage.is_used]
        if unused:
            recommendations.append(
                f"• Remove {len(unused)} unused bibliography entries or add citations for them."
            )
        
        # Check for missing entries
        if self.missing_citations:
            recommendations.append(
                f"• Add {len(self.missing_citations)} missing bibliography entries:"
            )
            for key in self.missing_citations:
                recommendations.append(f"    - {key}")
        
        # Check for metadata issues
        issues = [e for e in self.entries if e.comparison and e.comparison.has_issues]
        if issues:
            recommendations.append(
                f"• Review {len(issues)} entries with metadata discrepancies."
            )
        
        # Check for low relevance scores
        low_relevance_citations = []
        for e in self.entries:
            for ev in e.evaluations:
                if ev.relevance_score <= 2:
                    low_relevance_citations.append((e.entry.key, ev))
        
        if low_relevance_citations:
            recommendations.append(
                f"• Review {len(low_relevance_citations)} specific citations with low relevance scores (≤2/5):"
            )
            # List all low relevance citations
            for key, ev in low_relevance_citations:
                line_info = f" at line {ev.line_number}" if ev.line_number else ""
                recommendations.append(f"    - [{key}]{line_info}: Score {ev.relevance_score}/5")
        
        # Check for unverifiable entries
        unverifiable = [e for e in self.entries if e.comparison and e.comparison.source == "unable"]
        if unverifiable:
            recommendations.append(
                f"• {len(unverifiable)} entries could not be verified online. Consider adding arXiv IDs or DOIs."
            )
        
        if not recommendations:
            recommendations.append("✓ No major issues found. Your bibliography looks good!")
        
        for rec in recommendations:
            lines.append(f"  {rec}")
        
        return lines
    
    def _generate_footer(self) -> list[str]:
        """Generate report footer."""
        lines = []
        lines.append("")
        lines.append("─" * 80)
        lines.append("End of Report".center(80))
        lines.append("─" * 80)
        return lines
    
    def _truncate(self, text: str, max_len: int) -> str:
        """Return full text without truncation."""
        if not text:
            return ""
        # Remove newlines but don't truncate
        return text.replace("\n", " ")
    
    def _wrap_text(self, text: str, width: int) -> list[str]:
        """Wrap text to specified width."""
        if not text:
            return []
        
        words = text.split()
        lines = []
        current_line = []
        current_len = 0
        
        for word in words:
            if current_len + len(word) + 1 <= width:
                current_line.append(word)
                current_len += len(word) + 1
            else:
                if current_line:
                    lines.append(" ".join(current_line))
                current_line = [word]
                current_len = len(word)
        
        if current_line:
            lines.append(" ".join(current_line))
        
        return lines
    
    def save(self, filepath: str):
        """Save report to file."""
        content = self.generate()
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
