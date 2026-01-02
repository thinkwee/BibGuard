#!/usr/bin/env python3
"""
Bibliography Checker - Main CLI Entry Point

Validates bibliography entries against online sources and evaluates citation relevance.
"""
import argparse
import sys
from pathlib import Path

from src.parsers import BibParser, TexParser
from src.fetchers import ArxivFetcher, ScholarFetcher
from src.analyzers import MetadataComparator, UsageChecker, LLMEvaluator, DuplicateDetector
from src.analyzers.llm_evaluator import LLMBackend
from src.report.generator import ReportGenerator, EntryReport
from src.utils.progress import ProgressDisplay


def main():
    parser = argparse.ArgumentParser(
        description="Validate bibliography entries and evaluate citation relevance.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run all checks
  python main.py --bib paper.bib --tex paper.tex --enable-all
  
  # Only check metadata
  python main.py --bib paper.bib --tex paper.tex --check-metadata
  
  # Check usage and duplicates
  python main.py --bib paper.bib --tex paper.tex --check-usage --check-duplicates
  
  # Check relevance with custom LLM
  python main.py --bib paper.bib --tex paper.tex --check-relevance --llm ollama --model llama3
        """
    )
    
    # Required arguments
    parser.add_argument("--bib", required=True, help="Path to .bib file")
    parser.add_argument("--tex", required=True, help="Path to .tex file")
    
    # Feature toggles
    parser.add_argument(
        "--enable-all",
        action="store_true",
        help="Enable all checks (metadata, usage, relevance, duplicates)"
    )
    parser.add_argument(
        "--check-metadata",
        action="store_true",
        help="Check if citation metadata is correct (validate against arXiv/Scholar)"
    )
    parser.add_argument(
        "--check-usage",
        action="store_true",
        help="Check which entries are unused in the document"
    )
    parser.add_argument(
        "--check-relevance",
        action="store_true",
        help="Check citation relevance using LLM evaluation"
    )
    parser.add_argument(
        "--check-duplicates",
        action="store_true",
        help="Detect duplicate entries using fuzzy matching"
    )
    
    # LLM options (for --check-relevance)
    parser.add_argument(
        "--llm",
        choices=["ollama", "vllm", "gemini", "openai", "anthropic", "deepseek"],
        default="gemini",
        help="LLM backend for citation evaluation (default: gemini)"
    )
    parser.add_argument(
        "--llm-endpoint",
        help="Custom LLM API endpoint"
    )
    parser.add_argument(
        "--model",
        help="LLM model name (default depends on backend)"
    )
    parser.add_argument(
        "--api-key",
        help="API key (for Gemini or authenticated endpoints)"
    )
    
    # Output options
    parser.add_argument(
        "--output", "-o",
        default="report.txt",
        help="Output report file path (default: report.txt)"
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress progress output"
    )
    
    args = parser.parse_args()
    
    # Validate input files
    bib_path = Path(args.bib)
    tex_path = Path(args.tex)
    
    if not bib_path.exists():
        print(f"Error: Bib file not found: {args.bib}", file=sys.stderr)
        sys.exit(1)
    
    if not tex_path.exists():
        print(f"Error: TeX file not found: {args.tex}", file=sys.stderr)
        sys.exit(1)
    
    # Run the checker
    try:
        run_checker(args)
    except KeyboardInterrupt:
        print("\n\nInterrupted by user.", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        sys.exit(1)


def run_checker(args):
    """Run the bibliography checker."""
    progress = ProgressDisplay()
    
    # Determine which features to run
    if args.enable_all:
        check_metadata = True
        check_usage = True
        check_relevance = True
        check_duplicates = True
    else:
        check_metadata = args.check_metadata
        check_usage = args.check_usage
        check_relevance = args.check_relevance
        check_duplicates = args.check_duplicates
        
        # If no specific checks are enabled, enable all by default
        if not (check_metadata or check_usage or check_relevance or check_duplicates):
            progress.print_warning("No specific checks enabled. Running all checks by default.")
            progress.print_info("Use --check-metadata, --check-usage, --check-relevance, or --check-duplicates to run specific checks.")
            check_metadata = True
            check_usage = True
            check_relevance = True
            check_duplicates = True
    
    # Parse files
    progress.print_header("Parsing Files")
    
    progress.print_info(f"Parsing bib file: {args.bib}")
    bib_parser = BibParser()
    entries = bib_parser.parse_file(args.bib)
    progress.print_success(f"Found {len(entries)} bibliography entries")
    
    progress.print_info(f"Parsing TeX file: {args.tex}")
    tex_parser = TexParser()
    tex_parser.parse_file(args.tex)
    cited_keys = tex_parser.get_all_cited_keys()
    progress.print_success(f"Found {len(cited_keys)} unique citations")
    
    # Initialize components based on enabled features
    arxiv_fetcher = None
    scholar_fetcher = None
    comparator = None
    usage_checker = None
    llm_evaluator = None
    duplicate_detector = None
    
    if check_metadata or check_relevance:
        arxiv_fetcher = ArxivFetcher()
        
    if check_metadata:
        scholar_fetcher = ScholarFetcher()
        comparator = MetadataComparator()
    
    if check_usage:
        usage_checker = UsageChecker(tex_parser)
    
    if check_duplicates:
        duplicate_detector = DuplicateDetector()
    
    if check_relevance:
        backend = LLMBackend(args.llm)
        llm_evaluator = LLMEvaluator(
            backend=backend,
            endpoint=args.llm_endpoint,
            model=args.model,
            api_key=args.api_key
        )
        
        # Test LLM connection
        progress.print_info(f"Testing {args.llm} connection...")
        if llm_evaluator.test_connection():
            progress.print_success(f"LLM backend ({args.llm}) is accessible")
        else:
            progress.print_warning(f"Could not verify LLM backend. Evaluation may fail. Check your API key or Model Service.")
        
        # Usage checker is needed for relevance checking
        if not usage_checker:
            usage_checker = UsageChecker(tex_parser)
    
    # Initialize report generator
    report_gen = ReportGenerator()
    report_gen.set_metadata(args.bib, args.tex)
    
    # Check for duplicates first (if enabled)
    if check_duplicates:
        progress.print_header("Detecting Duplicates")
        duplicate_groups = duplicate_detector.find_duplicates(entries)
        
        if duplicate_groups:
            progress.print_warning(f"Found {len(duplicate_groups)} potential duplicate groups")
            for i, group in enumerate(duplicate_groups, 1):
                progress.print_info(f"Group {i}: {len(group.entries)} entries ({group.similarity_score:.0%} similar) - {group.reason}")
                for entry in group.entries:
                    progress.print_info(f"  - [{entry.key}] {entry.title[:60]}...")
        else:
            progress.print_success("No duplicates detected")
        
        report_gen.set_duplicate_groups(duplicate_groups)
    
    # Get missing citations (if usage check is enabled)
    if check_usage:
        missing = usage_checker.get_missing_entries(entries)
        if missing:
            progress.print_warning(f"Found {len(missing)} citations without bib entries: {', '.join(missing[:5])}")
        report_gen.set_missing_citations(missing)
    
    # Process each entry
    progress.print_header("Processing Entries")
    
    with progress.progress_context(len(entries), "Processing bibliography") as prog:
        for entry in entries:
            prog.update(entry.key, "Processing", 0)
            
            # Check usage (if enabled)
            usage_result = None
            if usage_checker:
                prog.update(entry.key, "Checking usage", 0)
                usage_result = usage_checker.check_usage(entry)
            
            # Fetch metadata and compare (if enabled)
            comparison_result = None
            if check_metadata and comparator:
                prog.update(entry.key, "Fetching metadata", 0)
                comparison_result = fetch_and_compare(
                    entry, arxiv_fetcher, scholar_fetcher, comparator
                )
            
            # LLM evaluation (if enabled and entry is used)
            evaluations = []
            if check_relevance and llm_evaluator:
                # Only evaluate if entry is used
                if usage_result and usage_result.is_used:
                    # Get abstract from fetched metadata or bib entry
                    abstract = get_abstract(entry, comparison_result, arxiv_fetcher)
                    if abstract:
                        prog.update(entry.key, f"Evaluating {len(usage_result.contexts)} citations", 0)
                        
                        for i, ctx in enumerate(usage_result.contexts, 1):
                            # Update progress for multiple citations
                            if len(usage_result.contexts) > 1:
                                prog.update(entry.key, f"Evaluating citation {i}/{len(usage_result.contexts)}", 0)
                            
                            eval_result = llm_evaluator.evaluate(
                                entry.key, ctx.full_context, abstract
                            )
                            # Add line number info
                            eval_result.line_number = ctx.line_number
                            evaluations.append(eval_result)
            
            # Create entry report
            entry_report = EntryReport(
                entry=entry,
                comparison=comparison_result,
                usage=usage_result,
                evaluations=evaluations
            )
            report_gen.add_entry_report(entry_report)
            
            # Update progress
            if comparison_result and comparison_result.is_match:
                prog.mark_success()
            elif comparison_result and comparison_result.has_issues:
                prog.mark_warning()
            else:
                prog.mark_error()
            
            prog.update(entry.key, "Done", 1)
    
    # Generate clean bib file if usage check was enabled
    if check_usage and usage_checker:
        used_entries = []
        for entry_report in report_gen.entries:
            if entry_report.usage and entry_report.usage.is_used:
                used_entries.append(entry_report.entry)
        
        if used_entries:
            bib_path = Path(args.bib)
            clean_bib_name = f"{bib_path.stem}_only_used_entry{bib_path.suffix}"
            clean_bib_path = bib_path.parent / clean_bib_name
            
            progress.print_header("Generating Clean Bib File")
            try:
                # Collect keys to keep
                keys_to_keep = {entry.key for entry in used_entries}
                bib_parser.filter_file(str(bib_path), str(clean_bib_path), keys_to_keep)
                progress.print_success(f"Saved {len(used_entries)} used entries to: {clean_bib_name}")
            except Exception as e:
                progress.print_error(f"Failed to save clean bib file: {e}")

    # Print summary
    progress.print_summary()
    
    # Generate and output report
    progress.print_header("Generating Report")
    
    report = report_gen.generate()
    
    # Save to file if specified
    if args.output:
        report_gen.save(args.output)
        progress.print_success(f"Report saved to: {args.output}")
    
    # Print to stdout
    if not args.quiet:
        print("\n" + report)


def fetch_and_compare(entry, arxiv_fetcher, scholar_fetcher, comparator):
    """
    Fetch metadata from online sources and compare with bib entry.
    
    Strategy:
    1. Try arXiv by ID (if available)
    2. Try arXiv by title search
    3. Fall back to Google Scholar
    
    Args:
        entry: BibEntry to verify
        arxiv_fetcher: ArxivFetcher instance
        scholar_fetcher: ScholarFetcher instance
        comparator: MetadataComparator instance
        
    Returns:
        ComparisonResult with match status and details
    """
    from src.utils.normalizer import TextNormalizer
    
    # Try arXiv first if we have an ID
    if entry.has_arxiv:
        arxiv_meta = arxiv_fetcher.fetch_by_id(entry.arxiv_id)
        if arxiv_meta:
            return comparator.compare_with_arxiv(entry, arxiv_meta)
    
    # Try searching arXiv by title
    if entry.title:
        results = arxiv_fetcher.search_by_title(entry.title, max_results=3)
        if results:
            # Find best match by title similarity
            best_result = None
            best_sim = 0.0
            norm1 = TextNormalizer.normalize_for_comparison(entry.title)
            
            for result in results:
                norm2 = TextNormalizer.normalize_for_comparison(result.title)
                sim = TextNormalizer.similarity_ratio(norm1, norm2)
                if sim > best_sim:
                    best_sim = sim
                    best_result = result
            
            if best_result and best_sim > 0.5:
                return comparator.compare_with_arxiv(entry, best_result)
    
    # Try Google Scholar as fallback
    if entry.title:
        scholar_result = scholar_fetcher.search_by_title(entry.title)
        if scholar_result:
            return comparator.compare_with_scholar(entry, scholar_result)
    
    # Return unable result
    return comparator.create_unable_result(
        entry, "Could not find paper in arXiv or Google Scholar"
    )


def get_abstract(entry, comparison_result, arxiv_fetcher):
    """
    Get abstract for an entry from various sources.
    
    Priority:
    1. Abstract field in bib entry
    2. arXiv API (by ID if available)
    3. arXiv search by title
    
    Args:
        entry: BibEntry to get abstract for
        comparison_result: Previous comparison result (unused but kept for API consistency)
        arxiv_fetcher: ArxivFetcher instance for API calls
        
    Returns:
        Abstract text or empty string if not found
    """
    # Check if we have abstract in bib entry
    if entry.abstract:
        return entry.abstract
    
    # Try to get from arXiv if we have an ID
    if entry.has_arxiv:
        arxiv_meta = arxiv_fetcher.fetch_by_id(entry.arxiv_id)
        if arxiv_meta and arxiv_meta.abstract:
            return arxiv_meta.abstract
    
    # Try searching arXiv by title
    if entry.title:
        results = arxiv_fetcher.search_by_title(entry.title, max_results=1)
        if results and results[0].abstract:
            return results[0].abstract
    
    return ""


if __name__ == "__main__":
    main()
