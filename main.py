#!/usr/bin/env python3
"""
Bibliography Checker - Main CLI Entry Point

Validates bibliography entries against online sources and evaluates citation relevance.
"""
import argparse
import sys
from pathlib import Path

from src.parsers import BibParser, TexParser
from src.fetchers import ArxivFetcher, ScholarFetcher, CrossRefFetcher, SemanticScholarFetcher, OpenAlexFetcher, DBLPFetcher
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
        default="report.md",
        help="Output report file path (default: report.md)"
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
    crossref_fetcher = None
    scholar_fetcher = None
    semantic_scholar_fetcher = None
    openalex_fetcher = None
    dblp_fetcher = None
    comparator = None
    usage_checker = None
    llm_evaluator = None
    duplicate_detector = None
    
    if check_metadata or check_relevance:
        arxiv_fetcher = ArxivFetcher()
        
    if check_metadata:
        semantic_scholar_fetcher = SemanticScholarFetcher()  # Free API, no key needed
        openalex_fetcher = OpenAlexFetcher()  # Free API, no key needed
        dblp_fetcher = DBLPFetcher() # Free API, no key needed
        crossref_fetcher = CrossRefFetcher()
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
                    progress.print_info(f"  - [{entry.key}] {entry.title}")
        else:
            progress.print_success("No duplicates detected")
        
        report_gen.set_duplicate_groups(duplicate_groups)
    
    # Get missing citations (if usage check is enabled)
    if check_usage:
        missing = usage_checker.get_missing_entries(entries)
        if missing:
            progress.print_warning(f"Found {len(missing)} citations without bib entries: {', '.join(missing)}")
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
                    entry, arxiv_fetcher, crossref_fetcher, scholar_fetcher, 
                    semantic_scholar_fetcher, openalex_fetcher, dblp_fetcher, comparator
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
    
    # Print to stdout (Summary and Issues only)
    if not args.quiet:
        console_output = report_gen.generate_console_output()
        print("\n" + console_output)


def fetch_and_compare(entry, arxiv_fetcher, crossref_fetcher, scholar_fetcher, 
                      semantic_scholar_fetcher, openalex_fetcher, dblp_fetcher, comparator):
    """
    Fetch metadata from online sources and compare with bib entry.
    
    New Strategy (Prioritize reliable APIs):
    1. Try arXiv by ID (if available)
    2. Try CrossRef by DOI (Authoritative for DOIs)
    3. Try Semantic Scholar (Official API)
    4. Try DBLP (Official API, high quality for CS)
    5. Try OpenAlex (Official API)
    6. Try arXiv by title search
    7. Try CrossRef by title search
    8. Fall back to Google Scholar (scraping, may be blocked)
    
    Args:
        entry: BibEntry to verify
        arxiv_fetcher: ArxivFetcher instance
        crossref_fetcher: CrossRefFetcher instance
        scholar_fetcher: ScholarFetcher instance
        semantic_scholar_fetcher: SemanticScholarFetcher instance
        openalex_fetcher: OpenAlexFetcher instance
        dblp_fetcher: DBLPFetcher instance
        comparator: MetadataComparator instance
        
    Returns:
        ComparisonResult with match status and details
    """
    from src.utils.normalizer import TextNormalizer
    
    all_results = []  # Collect all comparison results
    
    # 1. Try arXiv by ID (Highest Priority)
    if entry.has_arxiv:
        arxiv_meta = arxiv_fetcher.fetch_by_id(entry.arxiv_id)
        if arxiv_meta:
            result = comparator.compare_with_arxiv(entry, arxiv_meta)
            all_results.append(result)
            if result.is_match:
                return result

    # 2. Try CrossRef by DOI (Authoritative for DOIs)
    if entry.doi and crossref_fetcher:
        crossref_result = crossref_fetcher.search_by_doi(entry.doi)
        if crossref_result:
            result = comparator.compare_with_crossref(entry, crossref_result)
            all_results.append(result)
            if result.is_match:
                return result

    # 3. Try Semantic Scholar (High Priority, Reliable API)
    if entry.title and semantic_scholar_fetcher:
        # Try DOI first if available
        ss_result = None
        if entry.doi:
            ss_result = semantic_scholar_fetcher.fetch_by_doi(entry.doi)
        
        # Fallback to title search
        if not ss_result:
            ss_result = semantic_scholar_fetcher.search_by_title(entry.title)
            
        if ss_result:
            result = comparator.compare_with_semantic_scholar(entry, ss_result)
            all_results.append(result)
            if result.is_match:
                return result

    # 4. Try DBLP (High Priority for CS)
    if entry.title and dblp_fetcher:
        dblp_result = dblp_fetcher.search_by_title(entry.title)
        if dblp_result:
            result = comparator.compare_with_dblp(entry, dblp_result)
            all_results.append(result)
            if result.is_match:
                return result

    # 5. Try OpenAlex (High Priority, Broad Coverage)
    if entry.title and openalex_fetcher:
        # Try DOI first if available
        oa_result = None
        if entry.doi:
            oa_result = openalex_fetcher.fetch_by_doi(entry.doi)
            
        # Fallback to title search
        if not oa_result:
            oa_result = openalex_fetcher.search_by_title(entry.title)
            
        if oa_result:
            result = comparator.compare_with_openalex(entry, oa_result)
            all_results.append(result)
            if result.is_match:
                return result
    
    # 6. Try searching arXiv by title
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
                result = comparator.compare_with_arxiv(entry, best_result)
                all_results.append(result)
                if result.is_match:
                    return result
    
    # 7. Try CrossRef (Reliable)
    if entry.title and crossref_fetcher:
        crossref_result = crossref_fetcher.search_by_title(entry.title)
        if crossref_result:
            result = comparator.compare_with_crossref(entry, crossref_result)
            all_results.append(result)
            if result.is_match:
                return result
    
    # 8. Try Google Scholar as last resort (May be blocked)
    if entry.title and scholar_fetcher:
        scholar_result = scholar_fetcher.search_by_title(entry.title)
        if scholar_result:
            result = comparator.compare_with_scholar(entry, scholar_result)
            all_results.append(result)
            # If it's a match, return immediately
            if result.is_match:
                return result
    
    # No matches found, return the result with highest confidence
    if all_results:
        # Sort by confidence (descending) and return the best one
        all_results.sort(key=lambda r: r.confidence, reverse=True)
        return all_results[0]
    
    # No results at all, return unable
    return comparator.create_unable_result(
        entry, "Could not find paper in arXiv, Semantic Scholar, DBLP, OpenAlex, CrossRef, or Google Scholar"
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
