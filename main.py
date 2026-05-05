#!/usr/bin/env python3
"""
BibGuard - Bibliography Checker & Paper Submission Quality Tool

Usage:
    python main.py                    # Use bibguard.yaml in current directory
    python main.py --config my.yaml   # Use specified config file
    python main.py --init             # Create default config file
    python main.py --list-templates   # List available templates
    python main.py --quick            # Skip network-bound metadata/relevance/url checks
    python main.py --format json,html,markdown
    python main.py --verbose          # DEBUG-level logs to stderr
"""
import argparse
import logging
import sys
from pathlib import Path
from typing import Optional, List

from src.parsers import BibParser, TexParser
from src.fetchers import ArxivFetcher, ScholarFetcher, CrossRefFetcher, SemanticScholarFetcher, OpenAlexFetcher, DBLPFetcher
from src.analyzers import MetadataComparator, UsageChecker, LLMEvaluator, DuplicateDetector
from src.analyzers.llm_evaluator import LLMBackend
from src.report.generator import ReportGenerator, EntryReport
from src.utils.progress import ProgressDisplay
from src.utils.logging_setup import setup as setup_logging
from src.utils import http as http_layer
from src.utils.validation import validate_bib, validate_tex, format_report
from src.config.yaml_config import BibGuardConfig, load_config, find_config_file, create_default_config
from src.config.workflow import WorkflowConfig, WorkflowStep as WFStep, get_default_workflow
from src.templates.base_template import get_template, get_all_templates
from src.checkers import CHECKER_REGISTRY, CheckResult, CheckSeverity
from src.checkers.retraction_checker import RetractionChecker
from src.checkers.url_checker import URLChecker

logger = logging.getLogger("bibguard")


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
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Skip network-bound checks (metadata, retraction, URL liveness, LLM)",
    )
    parser.add_argument(
        "--format",
        default=None,
        help="Comma-separated list of output formats (markdown, html, json). Defaults to config.",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose (DEBUG) logging to stderr",
    )

    args = parser.parse_args()
    setup_logging("DEBUG" if args.verbose else None)
    
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
    
    # CLI overrides
    if args.quick:
        config.bibliography.check_metadata = False
        config.bibliography.check_relevance = False
        config.submission_extra.url_liveness = False
        config.submission_extra.retraction = False
    if args.format:
        config.output.formats = [s.strip() for s in args.format.split(",") if s.strip()]

    # Configure shared HTTP layer (retry + cache + UA)
    http_layer.configure(
        contact_email=config.network.contact_email,
        cache_enabled=config.network.cache_enabled,
        cache_ttl_hours=config.network.cache_ttl_hours,
        retry_total=config.network.retry_total,
        retry_backoff_factor=config.network.retry_backoff_factor,
    )
    # Apply BIBGUARD_DISABLE_SOURCES (if set) by pre-tripping breakers.
    http_layer.reset_breakers()

    # Validate required fields
    mode_dir = bool(config.files.input_dir)

    if mode_dir:
        input_dir = config.input_dir_path
        if not input_dir.exists() or not input_dir.is_dir():
            print(f"Error: Input directory does not exist or is not a directory: {input_dir}")
            sys.exit(1)

        tex_files = list(input_dir.rglob("*.tex"))
        bib_files = list(input_dir.rglob("*.bib"))

        if not tex_files:
            print(f"Error: No .tex files found in {input_dir}")
            sys.exit(1)
        if not bib_files:
            print(f"Error: No .bib files found in {input_dir}")
            sys.exit(1)

        config._tex_files = tex_files
        config._bib_files = bib_files
    else:
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

        config._tex_files = [config.tex_path]
        config._bib_files = [config.bib_path]

    # Pre-flight content validation (R6)
    any_fatal = False
    for bp in config._bib_files:
        rep = validate_bib(bp)
        msg = format_report(rep, label=bp.name)
        if msg:
            print(msg)
        if not rep.ok:
            any_fatal = True
    for tp in config._tex_files:
        rep = validate_tex(tp)
        msg = format_report(rep, label=tp.name)
        if msg:
            print(msg)
        if not rep.ok:
            any_fatal = True
    if any_fatal:
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
        print("\n\n[BibGuard] Interrupted. Partial reports (if any) are in the output dir.")
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
    
    # Parse files (silent)
    bib_parser = BibParser()
    entries = []
    for bib_path in config._bib_files:
        entries.extend(bib_parser.parse_file(str(bib_path)))
    
    tex_parser = TexParser()
    tex_contents = {}
    merged_citations = {}
    merged_all_keys = set()
    
    for tex_path in config._tex_files:
        cits = tex_parser.parse_file(str(tex_path))
        # Accumulate citations
        for k, v in cits.items():
            if k not in merged_citations:
                merged_citations[k] = []
            merged_citations[k].extend(v)
        # Accumulate keys
        merged_all_keys.update(tex_parser.get_all_cited_keys())
        # Store content
        tex_contents[str(tex_path)] = tex_path.read_text(encoding='utf-8', errors='replace')
    
    # Inject merged data back into parser for components that use it
    tex_parser.citations = merged_citations
    tex_parser.all_keys = merged_all_keys
    
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
    report_gen.set_metadata(
        [str(f) for f in config._bib_files],
        [str(f) for f in config._tex_files]
    )
    
    # Build the per-checker config dict (glossary, template, etc.)
    checker_config = {
        "glossary_preferred": config.glossary.preferred,
        "glossary_acronyms": config.glossary.acronyms,
        "template": template,
    }

    # Run submission quality checks
    submission_results = []
    enabled_checkers = list(config.submission.get_enabled_checkers())
    if template is not None and "template" not in enabled_checkers:
        enabled_checkers.append("template")

    for checker_name in enabled_checkers:
        if checker_name in CHECKER_REGISTRY:
            checker = CHECKER_REGISTRY[checker_name]()
            for tex_path_str, content in tex_contents.items():
                # Run the checker on this file. We deliberately do NOT tag
                # `r.file_path = tex_path_str` because user-facing reports
                # never expose local tex paths (basename or full).
                results = checker.check(content, checker_config)
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

    # Retraction lookups (F1)
    if config.submission_extra.retraction:
        try:
            findings = RetractionChecker().check_entries(entries)
            report_gen.set_retraction_findings(findings)
            if findings:
                logger.info("Retraction check found %d flagged entries", len(findings))
        except Exception as e:
            logger.debug("Retraction check failed: %s", e)

    # URL liveness (F2)
    if config.submission_extra.url_liveness:
        try:
            url_findings = URLChecker().check_entries(entries)
            report_gen.set_url_findings(url_findings)
            broken = sum(1 for f in url_findings if f.status != "ok")
            if broken:
                logger.info("URL liveness check: %d broken URL(s)", broken)
        except Exception as e:
            logger.debug("URL liveness check failed: %s", e)
    
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
                        eval_result.file_path = ctx.file_path
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
    
    interrupted = False
    with progress.progress_context(len(entries), "Processing bibliography") as prog:
        # Use ThreadPoolExecutor for parallel processing
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_entry = {executor.submit(process_single_entry, entry): entry for entry in entries}

            # Process completed tasks
            try:
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
            except KeyboardInterrupt:
                interrupted = True
                logger.warning("Interrupted by user; cancelling remaining work and saving partial reports")
                for f in future_to_entry:
                    f.cancel()
    
    # Generate reports and organize outputs (silent)
    
    # Create output directory
    output_dir = config.output_dir_path
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Copy input files to output directory
    import shutil
    for bib_path in config._bib_files:
        shutil.copy2(bib_path, output_dir / bib_path.name)
    for tex_path in config._tex_files:
        shutil.copy2(tex_path, output_dir / tex_path.name)
    requested_formats = {f.lower() for f in (config.output.formats or ["markdown", "html"])}

    # 1. Bibliography Report (markdown)
    if "markdown" in requested_formats:
        bib_report_path = output_dir / "bibliography_report.md"
        report_gen.save_bibliography_report(str(bib_report_path))

        # 2. LaTeX Quality Report (markdown)
        if submission_results:
            latex_report_path = output_dir / "latex_quality_report.md"
            report_gen.save_latex_quality_report(
                str(latex_report_path),
                submission_results,
                template,
            )

    # 4. Self-contained HTML (★)
    if "html" in requested_formats:
        try:
            report_gen.save_html(str(output_dir / "report.html"))
        except Exception as e:
            logger.warning("Failed to write HTML report: %s", e)

    # 5. JSON output
    if "json" in requested_formats:
        try:
            report_gen.save_json(str(output_dir / "report.json"))
        except Exception as e:
            logger.warning("Failed to write JSON report: %s", e)

    # 6. Clean bib file (if generated earlier)
    if bib_config.check_usage and usage_checker:
        used_entries = [er.entry for er in report_gen.entries if er.usage and er.usage.is_used]
        if used_entries:
            try:
                keys_to_keep = {entry.key for entry in used_entries}
                if len(config._bib_files) == 1:
                    clean_bib_path = output_dir / f"{config._bib_files[0].stem}_only_used.bib"
                    bib_parser.filter_file(str(config._bib_files[0]), str(clean_bib_path), keys_to_keep)
                else:
                    clean_bib_path = output_dir / "merged_only_used.bib"
                    with open(clean_bib_path, 'w', encoding='utf-8') as f:
                        for entry in used_entries:
                            f.write(getattr(entry, "raw", "") + "\n\n")
            except Exception as e:
                logger.debug("Failed to write cleaned bib file: %s", e)

    if interrupted:
        print("[BibGuard] Saved partial reports for completed entries.")
    
    # Print beautiful console summary
    if not config.output.quiet:
        bib_stats, latex_stats = report_gen.get_summary_stats()
        progress.print_detailed_summary(bib_stats, latex_stats, str(output_dir.absolute()))


def fetch_and_compare_with_workflow(
    entry, workflow_config, arxiv_fetcher, crossref_fetcher, scholar_fetcher,
    semantic_scholar_fetcher, openalex_fetcher, dblp_fetcher, comparator
):
    """
    Fetch metadata across all configured sources and pick the best match.

    Delegates the heavy lifting to ``app_helper.fetch_and_compare_with_workflow``,
    which runs identifier-based and title-based lookups in parallel and uses
    cross-source corroboration to decide is_match. Google Scholar is consulted
    only as a last-resort fallback because scraping is fragile and frequently
    blocked.
    """
    from app_helper import fetch_and_compare_with_workflow as _parallel_lookup

    primary = _parallel_lookup(
        entry, workflow_config, arxiv_fetcher, crossref_fetcher,
        semantic_scholar_fetcher, openalex_fetcher, dblp_fetcher, comparator,
    )

    if primary and primary.source != "unable":
        return primary

    # Last-resort Google Scholar fallback (web scraping; frequently blocked).
    if entry.title and scholar_fetcher:
        try:
            scholar_result = scholar_fetcher.search_by_title(entry.title)
            if scholar_result:
                return comparator.compare_with_scholar(entry, scholar_result)
        except Exception as e:
            logger.warning(
                "Google Scholar fallback failed for entry=%s: %s",
                getattr(entry, "key", "<unknown>"), e, exc_info=True,
            )

    return primary or comparator.create_unable_result(
        entry, "Unable to find this paper in any data source"
    )


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
