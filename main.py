#!/usr/bin/env python3
"""
BibGuard - Bibliography Checker & Paper Submission Quality Tool

Usage:
    python main.py                    # Use bibguard.yaml in current directory
    python main.py --config my.yaml   # Use specified config file
    python main.py --init             # Create default config file
    python main.py --list-templates   # List available templates
"""
import argparse
import sys
from pathlib import Path
from typing import Optional, List

from src.parsers import BibParser, TexParser
from src.fetchers import ArxivFetcher, ScholarFetcher, CrossRefFetcher, SemanticScholarFetcher, OpenAlexFetcher, DBLPFetcher
from src.analyzers import MetadataComparator, UsageChecker, LLMEvaluator, DuplicateDetector
from src.analyzers.llm_evaluator import LLMBackend
from src.report.generator import ReportGenerator, EntryReport
from src.utils.progress import ProgressDisplay
from src.config.yaml_config import BibGuardConfig, load_config, find_config_file, create_default_config
from src.config.workflow import WorkflowConfig, WorkflowStep as WFStep, get_default_workflow
from src.templates.base_template import get_template, get_all_templates
from src.checkers import CHECKER_REGISTRY, CheckResult, CheckSeverity


def main():
    parser = argparse.ArgumentParser(
        description="BibGuard: Bibliography Checker & Paper Submission Quality Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Usage Examples:
  python main.py                      # Auto-detect config.yaml in current directory
  python main.py --config my.yaml     # Use specified config file
  python main.py --init               # Create default config.yaml
  python main.py --list-templates     # List available conference templates
        """
    )
    
    parser.add_argument(
        "--config", "-c",
        help="Config file path (default: auto-detect config.yaml)"
    )
    parser.add_argument(
        "--init",
        action="store_true",
        help="Create default config.yaml in current directory"
    )
    parser.add_argument(
        "--list-templates",
        action="store_true",
        help="List all available conference templates"
    )
    
    args = parser.parse_args()
    
    # Handle --init
    if args.init:
        output = create_default_config()
        print(f"✓ Created configuration file: {output}")
        print("")
        print("  Next steps:")
        print("  1. Edit the 'bib' and 'tex' paths in config.yaml")
        print("  2. Run: python main.py --config config.yaml")
        print("")
        sys.exit(0)
    
    # Handle --list-templates
    if args.list_templates:
        from src.ui.template_selector import list_templates
        list_templates()
        sys.exit(0)
    
    # Find and load config
    config_path = args.config
    if not config_path:
        found = find_config_file()
        if found:
            config_path = str(found)
        else:
            print("Error: Config file not found")
            print("")
            print("Please run 'python main.py --init' to create config.yaml")
            print("Or use 'python main.py --config <path>' to specify a config file")
            print("")
            sys.exit(1)
    
    try:
        config = load_config(config_path)
    except FileNotFoundError:
        print(f"Error: Config file does not exist: {config_path}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: Failed to parse config file: {e}")
        sys.exit(1)
    
    # Validate required fields
    if not config.files.bib:
        print("Error: bib file path not specified in config")
        sys.exit(1)
    if not config.files.tex:
        print("Error: tex file path not specified in config")
        sys.exit(1)
    
    # Validate files exist
    if not config.bib_path.exists():
        print(f"Error: Bib file does not exist: {config.bib_path}")
        sys.exit(1)
    if not config.tex_path.exists():
        print(f"Error: TeX file does not exist: {config.tex_path}")
        sys.exit(1)
    
    # Load template if specified
    template = None
    if config.template:
        template = get_template(config.template)
        if not template:
            print(f"Error: Unknown template: {config.template}")
            print("Use --list-templates to see available templates")
            sys.exit(1)
    
    # Run the checker
    try:
        run_checker(config, template)
    except KeyboardInterrupt:
        print("\n\nCancelled")
        sys.exit(130)
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def run_checker(config: BibGuardConfig, template=None):
    """Run the bibliography checker with the given configuration."""
    progress = ProgressDisplay()
    
    # Show config info (minimal)
    if template:
        pass # Skip printing header/info here to keep output clean
    
    # Parse files
    # Parse files (silent)
    bib_parser = BibParser()
    entries = bib_parser.parse_file(str(config.bib_path))
    
    tex_parser = TexParser()
    tex_parser.parse_file(str(config.tex_path))
    cited_keys = tex_parser.get_all_cited_keys()
    
    # Read TeX content for submission checks
    tex_content = config.tex_path.read_text(encoding='utf-8', errors='replace')
    
    # Initialize components based on config
    bib_config = config.bibliography
    
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
    
    if bib_config.check_metadata or bib_config.check_relevance:
        arxiv_fetcher = ArxivFetcher()
        
    if bib_config.check_metadata:
        semantic_scholar_fetcher = SemanticScholarFetcher()
        openalex_fetcher = OpenAlexFetcher()
        dblp_fetcher = DBLPFetcher()
        crossref_fetcher = CrossRefFetcher()
        scholar_fetcher = ScholarFetcher()
        comparator = MetadataComparator()
    
    if bib_config.check_usage:
        usage_checker = UsageChecker(tex_parser)
    
    if bib_config.check_duplicates:
        duplicate_detector = DuplicateDetector()
    
    if bib_config.check_relevance:
        llm_config = config.llm
        backend = LLMBackend(llm_config.backend)
        llm_evaluator = LLMEvaluator(
            backend=backend,
            endpoint=llm_config.endpoint or None,
            model=llm_config.model or None,
            api_key=llm_config.api_key or None
        )
        
        # Test LLM connection (silent)
        llm_evaluator.test_connection()
        
        if not usage_checker:
            usage_checker = UsageChecker(tex_parser)
    
    # Initialize report generator
    report_gen = ReportGenerator(
        minimal_verified=config.output.minimal_verified,
        check_preprint_ratio=config.bibliography.check_preprint_ratio,
        preprint_warning_threshold=config.bibliography.preprint_warning_threshold
    )
    report_gen.set_metadata(str(config.bib_path), str(config.tex_path))
    
    # Run submission quality checks
    submission_results = []
    enabled_checkers = config.submission.get_enabled_checkers()
    
    for checker_name in enabled_checkers:
        if checker_name in CHECKER_REGISTRY:
            checker = CHECKER_REGISTRY[checker_name]()
            results = checker.check(tex_content, {})
            submission_results.extend(results)
    
    # Set results in report generator for summary calculation
    report_gen.set_submission_results(submission_results, template)
    
    # Check for duplicates (silent)
    if bib_config.check_duplicates and duplicate_detector:
        duplicate_groups = duplicate_detector.find_duplicates(entries)
        report_gen.set_duplicate_groups(duplicate_groups)
    
    # Check missing citations (silent)
    if bib_config.check_usage and usage_checker:
        missing = usage_checker.get_missing_entries(entries)
        report_gen.set_missing_citations(missing)
    
    # Process entries
    
    # Build workflow from config
    from src.config.workflow import WorkflowConfig, get_default_workflow, WorkflowStep as WFStep
    workflow_config = get_default_workflow()
    if config.workflow:
        workflow_config = WorkflowConfig(
            steps=[
                WFStep(
                    name=step.name,
                    display_name=step.name,
                    description=step.description,
                    enabled=step.enabled,
                    priority=i
                )
                for i, step in enumerate(config.workflow)
            ]
        )
    
    # Process entries in parallel for metadata checks
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import threading
    
    # Thread-safe progress tracking
    progress_lock = threading.Lock()
    completed_count = [0]  # Use list for mutability in closure
    
    def process_single_entry(entry):
        """Process a single entry (thread-safe)."""
        # Check usage
        usage_result = None
        if usage_checker:
            usage_result = usage_checker.check_usage(entry)
        
        # Fetch and compare metadata
        comparison_result = None
        if bib_config.check_metadata and comparator:
            comparison_result = fetch_and_compare_with_workflow(
                entry, workflow_config, arxiv_fetcher, crossref_fetcher,
                scholar_fetcher, semantic_scholar_fetcher, openalex_fetcher,
                dblp_fetcher, comparator
            )
        
        # LLM evaluation (keep sequential per entry)
        evaluations = []
        if bib_config.check_relevance and llm_evaluator:
            if usage_result and usage_result.is_used:
                abstract = get_abstract(entry, comparison_result, arxiv_fetcher)
                if abstract:
                    for ctx in usage_result.contexts:
                        eval_result = llm_evaluator.evaluate(
                            entry.key, ctx.full_context, abstract
                        )
                        eval_result.line_number = ctx.line_number
                        evaluations.append(eval_result)
        
        # Create entry report
        entry_report = EntryReport(
            entry=entry,
            comparison=comparison_result,
            usage=usage_result,
            evaluations=evaluations
        )
        
        return entry_report, comparison_result
    
    # Determine number of workers (max 10 to avoid overwhelming APIs)
    max_workers = min(10, len(entries))
    
    with progress.progress_context(len(entries), "Processing bibliography") as prog:
        # Use ThreadPoolExecutor for parallel processing
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_entry = {executor.submit(process_single_entry, entry): entry for entry in entries}
            
            # Process completed tasks
            for future in as_completed(future_to_entry):
                entry = future_to_entry[future]
                try:
                    entry_report, comparison_result = future.result()
                    
                    # Thread-safe progress update
                    with progress_lock:
                        report_gen.add_entry_report(entry_report)
                        
                        # Update progress
                        if comparison_result and comparison_result.is_match:
                            prog.mark_success()
                        elif comparison_result and comparison_result.has_issues:
                            prog.mark_warning()
                        else:
                            prog.mark_error()
                        
                        completed_count[0] += 1
                        prog.update(entry.key, "Done", 1)
                        
                except Exception as e:
                    with progress_lock:
                        prog.mark_error()
                        progress.print_error(f"Error processing {entry.key}: {e}")
                        completed_count[0] += 1
                        prog.update(entry.key, "Failed", 1)
    
    # Summary will be printed at the very end
    
    # Generate reports and organize outputs (silent)
    
    # Create output directory
    output_dir = config.output_dir_path
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Copy input files to output directory
    import shutil
    bib_copy_path = output_dir / config.bib_path.name
    tex_copy_path = output_dir / config.tex_path.name
    
    shutil.copy2(config.bib_path, bib_copy_path)
    shutil.copy2(config.tex_path, tex_copy_path)
    # 1. Bibliography Report
    bib_report_path = output_dir / "bibliography_report.md"
    report_gen.save_bibliography_report(str(bib_report_path))
    
    # 2. LaTeX Quality Report
    if submission_results:
        latex_report_path = output_dir / "latex_quality_report.md"
        report_gen.save_latex_quality_report(
            str(latex_report_path),
            submission_results,
            template
        )
        
        # 3. Line-by-Line Report
        from src.report.line_report import generate_line_report
        line_report_path = output_dir / "line_by_line_report.md"
        generate_line_report(
            tex_content=tex_content,
            tex_path=str(config.tex_path),
            results=submission_results,
            output_path=str(line_report_path)
        )
    
    # 4. Clean bib file (if generated earlier)
    if bib_config.check_usage and usage_checker:
        used_entries = [er.entry for er in report_gen.entries if er.usage and er.usage.is_used]
        if used_entries:
            clean_bib_path = output_dir / f"{config.bib_path.stem}_only_used.bib"
            try:
                keys_to_keep = {entry.key for entry in used_entries}
                bib_parser.filter_file(str(config.bib_path), str(clean_bib_path), keys_to_keep)
            except Exception as e:
                pass
    
    # Print beautiful console summary
    if not config.output.quiet:
        bib_stats, latex_stats = report_gen.get_summary_stats()
        progress.print_detailed_summary(bib_stats, latex_stats, str(output_dir.absolute()))


def fetch_and_compare_with_workflow(
    entry, workflow_config, arxiv_fetcher, crossref_fetcher, scholar_fetcher,
    semantic_scholar_fetcher, openalex_fetcher, dblp_fetcher, comparator
):
    """Fetch metadata from online sources using the configured workflow."""
    from src.utils.normalizer import TextNormalizer
    
    all_results = []
    enabled_steps = workflow_config.get_enabled_steps()
    
    for step in enabled_steps:
        result = None
        
        if step.name == "arxiv_id" and entry.has_arxiv and arxiv_fetcher:
            arxiv_meta = arxiv_fetcher.fetch_by_id(entry.arxiv_id)
            if arxiv_meta:
                result = comparator.compare_with_arxiv(entry, arxiv_meta)
        
        elif step.name == "crossref_doi" and entry.doi and crossref_fetcher:
            crossref_result = crossref_fetcher.search_by_doi(entry.doi)
            if crossref_result:
                result = comparator.compare_with_crossref(entry, crossref_result)
        
        elif step.name == "semantic_scholar" and entry.title and semantic_scholar_fetcher:
            ss_result = None
            if entry.doi:
                ss_result = semantic_scholar_fetcher.fetch_by_doi(entry.doi)
            if not ss_result:
                ss_result = semantic_scholar_fetcher.search_by_title(entry.title)
            if ss_result:
                result = comparator.compare_with_semantic_scholar(entry, ss_result)
        
        elif step.name == "dblp" and entry.title and dblp_fetcher:
            dblp_result = dblp_fetcher.search_by_title(entry.title)
            if dblp_result:
                result = comparator.compare_with_dblp(entry, dblp_result)
        
        elif step.name == "openalex" and entry.title and openalex_fetcher:
            oa_result = None
            if entry.doi:
                oa_result = openalex_fetcher.fetch_by_doi(entry.doi)
            if not oa_result:
                oa_result = openalex_fetcher.search_by_title(entry.title)
            if oa_result:
                result = comparator.compare_with_openalex(entry, oa_result)
        
        elif step.name == "arxiv_title" and entry.title and arxiv_fetcher:
            results = arxiv_fetcher.search_by_title(entry.title, max_results=3)
            if results:
                best_result = None
                best_sim = 0.0
                norm1 = TextNormalizer.normalize_for_comparison(entry.title)
                
                for r in results:
                    norm2 = TextNormalizer.normalize_for_comparison(r.title)
                    sim = TextNormalizer.similarity_ratio(norm1, norm2)
                    if sim > best_sim:
                        best_sim = sim
                        best_result = r
                
                if best_result and best_sim > 0.5:
                    result = comparator.compare_with_arxiv(entry, best_result)
        
        elif step.name == "crossref_title" and entry.title and crossref_fetcher:
            crossref_result = crossref_fetcher.search_by_title(entry.title)
            if crossref_result:
                result = comparator.compare_with_crossref(entry, crossref_result)
        
        elif step.name == "google_scholar" and entry.title and scholar_fetcher:
            scholar_result = scholar_fetcher.search_by_title(entry.title)
            if scholar_result:
                result = comparator.compare_with_scholar(entry, scholar_result)
        
        if result:
            all_results.append(result)
            if result.is_match:
                return result
    
    if all_results:
        all_results.sort(key=lambda r: r.confidence, reverse=True)
        return all_results[0]
    
    return comparator.create_unable_result(entry, "Unable to find this paper in any data source")


def get_abstract(entry, comparison_result, arxiv_fetcher):
    """Get abstract for an entry from various sources."""
    if entry.abstract:
        return entry.abstract
    
    if entry.has_arxiv and arxiv_fetcher:
        arxiv_meta = arxiv_fetcher.fetch_by_id(entry.arxiv_id)
        if arxiv_meta and arxiv_meta.abstract:
            return arxiv_meta.abstract
    
    if entry.title and arxiv_fetcher:
        results = arxiv_fetcher.search_by_title(entry.title, max_results=1)
        if results and results[0].abstract:
            return results[0].abstract
    
    return ""


if __name__ == "__main__":
    main()
