"""
Per-entry metadata verification: parallel multi-source lookup with corroboration.

Strategy (in order):
  1. **Identifier lookups, in parallel**:
        - DOI → CrossRef, Semantic Scholar, OpenAlex
        - arXiv ID → arXiv, Semantic Scholar
     If the bib entry has either, this stage usually returns 2-3 independent
     hits within a few hundred ms. Identifier lookups are far more reliable
     than title search because the identifier is unique.

  2. **Title searches across sources, in parallel** (always run as corroboration,
     even if identifiers were found): Semantic Scholar, OpenAlex, DBLP, CrossRef,
     arXiv. Each source returns top-K candidates; we keep the candidate whose
     title most closely matches the bib title.

  3. **Score & corroborate**:
        - Pick the result with the highest per-source confidence.
        - If ≥2 sources independently report the same title (sim ≥ 0.95) we
          mark `is_match=True` even when individual confidences are middling
          — multi-source agreement is the single strongest signal.
        - Tightened thresholds: title sim ≥ 0.88 + year diff ≤ 1 (or year empty)
          to declare a single-source match. Single-source matches that disagree
          with corroborating sources are downgraded.

The function still returns a single ComparisonResult so the rest of the
pipeline doesn't change. Extra evidence (sources tried, agreement count) is
stuffed into the `issues` field as informational notes when relevant.
"""
from __future__ import annotations

import concurrent.futures as cf
import logging
from typing import List, Optional, Tuple

from src.utils.normalizer import TextNormalizer

logger = logging.getLogger(__name__)

# Year tolerance for "match" (preprint vs published often differ by 1y).
_YEAR_TOL = 1
# Title similarity required for single-source match.
_TITLE_MATCH_TIGHT = 0.88
# Title similarity required to count as "corroborating" another source.
_TITLE_AGREE = 0.95


def _title_sim(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    a_n = TextNormalizer.normalize_for_comparison(a)
    b_n = TextNormalizer.normalize_for_comparison(b)
    if not a_n or not b_n:
        return 0.0
    jacc = TextNormalizer.similarity_ratio(a_n, b_n)
    if max(len(a_n), len(b_n)) < 200:
        lev = TextNormalizer.levenshtein_similarity(a_n, b_n)
        return max(jacc, lev)
    return jacc


def _year_close(y1: str, y2: str) -> bool:
    """True if years are missing on either side or within ±1."""
    y1, y2 = (y1 or "").strip(), (y2 or "").strip()
    if not y1 or not y2:
        return True
    try:
        return abs(int(y1[:4]) - int(y2[:4])) <= _YEAR_TOL
    except ValueError:
        return False


def _pick_best_candidate(bib_title: str, candidates: list) -> Tuple[Optional[object], float]:
    """Pick the candidate whose title most closely matches `bib_title`."""
    best, best_sim = None, 0.0
    for c in candidates:
        sim = _title_sim(bib_title, getattr(c, "title", "") or "")
        if sim > best_sim:
            best, best_sim = c, sim
    return best, best_sim


def fetch_and_compare_with_workflow(
    entry,
    workflow_steps,  # accepted for API compat; ignored — strategy is fixed
    arxiv_fetcher,
    crossref_fetcher,
    semantic_scholar_fetcher,
    openalex_fetcher,
    dblp_fetcher,
    comparator,
):
    """Look up `entry` across all available sources in parallel and return a single ComparisonResult."""
    has_doi = bool(getattr(entry, "doi", "") or "")
    has_arxiv = bool(getattr(entry, "has_arxiv", False))
    has_title = bool(getattr(entry, "title", "") or "")

    if not (has_doi or has_arxiv or has_title):
        return comparator.create_unable_result(entry, "Entry has no DOI, arXiv ID, or title to look up")

    # ------------------------------------------------------------------ stage 1
    # Tasks are tuples of (source_name, callable returning ComparisonResult or None).
    tasks: list[tuple[str, callable]] = []

    # Identifier-based lookups (high precision).
    if has_doi and crossref_fetcher:
        def _t_cr_doi(e=entry):
            r = crossref_fetcher.search_by_doi(e.doi)
            return comparator.compare_with_crossref(e, r) if r else None
        tasks.append(("crossref(doi)", _t_cr_doi))

    if has_doi and semantic_scholar_fetcher:
        def _t_s2_doi(e=entry):
            r = semantic_scholar_fetcher.fetch_by_doi(e.doi)
            return comparator.compare_with_semantic_scholar(e, r) if r else None
        tasks.append(("s2(doi)", _t_s2_doi))

    if has_doi and openalex_fetcher:
        def _t_oa_doi(e=entry):
            r = openalex_fetcher.fetch_by_doi(e.doi)
            return comparator.compare_with_openalex(e, r) if r else None
        tasks.append(("openalex(doi)", _t_oa_doi))

    if has_arxiv and arxiv_fetcher:
        def _t_arxiv_id(e=entry):
            r = arxiv_fetcher.fetch_by_id(e.arxiv_id)
            return comparator.compare_with_arxiv(e, r) if r else None
        tasks.append(("arxiv(id)", _t_arxiv_id))

    if has_arxiv and semantic_scholar_fetcher and not has_doi:
        # If we already queried S2 by DOI we don't double-bill.
        def _t_s2_arxiv(e=entry):
            r = semantic_scholar_fetcher.fetch_by_arxiv_id(e.arxiv_id)
            return comparator.compare_with_semantic_scholar(e, r) if r else None
        tasks.append(("s2(arxiv)", _t_s2_arxiv))

    # Title-based lookups (always run as corroboration if title available).
    if has_title:
        if semantic_scholar_fetcher and not has_doi and not has_arxiv:
            def _t_s2_title(e=entry):
                cands = semantic_scholar_fetcher.search_by_title_multi(e.title, max_results=5)
                best, _ = _pick_best_candidate(e.title, cands)
                return comparator.compare_with_semantic_scholar(e, best) if best else None
            tasks.append(("s2(title)", _t_s2_title))

        if openalex_fetcher and not has_doi:
            def _t_oa_title(e=entry):
                cands = openalex_fetcher.search_by_title_multi(e.title, max_results=5)
                best, _ = _pick_best_candidate(e.title, cands)
                return comparator.compare_with_openalex(e, best) if best else None
            tasks.append(("openalex(title)", _t_oa_title))

        if dblp_fetcher:
            def _t_dblp_title(e=entry):
                cands = dblp_fetcher.search_by_title_multi(e.title, max_results=5)
                best, _ = _pick_best_candidate(e.title, cands)
                return comparator.compare_with_dblp(e, best) if best else None
            tasks.append(("dblp(title)", _t_dblp_title))

        if crossref_fetcher and not has_doi:
            def _t_cr_title(e=entry):
                cands = crossref_fetcher.search_by_title_multi(e.title, max_results=5)
                best, _ = _pick_best_candidate(e.title, cands)
                return comparator.compare_with_crossref(e, best) if best else None
            tasks.append(("crossref(title)", _t_cr_title))

        if arxiv_fetcher and not has_arxiv:
            def _t_arxiv_title(e=entry):
                cands = arxiv_fetcher.search_by_title(e.title, max_results=5)
                best, _ = _pick_best_candidate(e.title, cands)
                return comparator.compare_with_arxiv(e, best) if best else None
            tasks.append(("arxiv(title)", _t_arxiv_title))

    if not tasks:
        return comparator.create_unable_result(entry, "No fetchers configured")

    # Run in parallel with EARLY EXIT.
    #
    # Strategy:
    #   - Submit every task to a pool.
    #   - Drain `as_completed` with a SHORT poll deadline.
    #   - Stop early as soon as we have one high-confidence match (≥0.85)
    #     plus at least one corroborating result whose title aligns.
    #   - Hard ceiling: 18s total wall-clock per entry. Whatever finished
    #     by then is what we use; the rest is cancelled so we don't pay
    #     the slowest-source penalty (a 80s-rate-limited S2 retry, e.g.).
    results: list = []
    sources_tried: list[str] = []
    entry_key = getattr(entry, "key", "<unknown>")
    deadline = __import__("time").monotonic() + 18.0
    HIGH_CONF = 0.85

    def _have_corroborated(rs: list) -> bool:
        if not rs:
            return False
        rs_sorted = sorted(rs, key=lambda r: r.confidence, reverse=True)
        primary = rs_sorted[0]
        if primary.confidence < HIGH_CONF:
            return False
        for other in rs_sorted[1:]:
            if other.fetched_title and _title_sim(primary.fetched_title,
                                                  other.fetched_title) >= _TITLE_AGREE:
                return True
        return False

    pool = cf.ThreadPoolExecutor(max_workers=min(8, len(tasks)))
    future_to_name = {pool.submit(fn): name for name, fn in tasks}
    try:
        pending = set(future_to_name)
        while pending:
            remaining = deadline - __import__("time").monotonic()
            if remaining <= 0:
                logger.debug("Entry=%s: 18s deadline reached, %d sources still pending",
                             entry_key, len(pending))
                break
            done, pending = cf.wait(pending, timeout=min(remaining, 2.0),
                                    return_when=cf.FIRST_COMPLETED)
            for fut in done:
                name = future_to_name[fut]
                sources_tried.append(name)
                try:
                    r = fut.result(timeout=0)
                except Exception as e:
                    logger.warning(
                        "Lookup failed for entry=%s source=%s: %s",
                        entry_key, name, e, exc_info=True,
                    )
                    continue
                if r is not None:
                    results.append(r)
            if _have_corroborated(results):
                logger.debug("Entry=%s: corroborated early after %d sources", entry_key, len(results))
                break
    finally:
        # Cancel anything still in the queue; threads already running can't
        # be killed, but they'll finish quietly without blocking us.
        for fut in future_to_name:
            if not fut.done():
                fut.cancel()
        pool.shutdown(wait=False, cancel_futures=True)

    if not results:
        return comparator.create_unable_result(
            entry,
            f"Tried {len(tasks)} sources ({', '.join(sources_tried) or 'none'}) — no metadata returned"
        )

    # ------------------------------------------------------------------ stage 2: pick + corroborate
    # Sort by confidence; pick top.
    results.sort(key=lambda r: r.confidence, reverse=True)
    primary = results[0]

    # Count corroborating sources that report a title within sim ≥ _TITLE_AGREE
    # of the primary's fetched_title.
    primary_title = primary.fetched_title
    agree_count = 0
    distinct_sources = set()
    for r in results:
        if r is primary:
            continue
        if not r.fetched_title:
            continue
        if _title_sim(primary_title, r.fetched_title) >= _TITLE_AGREE:
            agree_count += 1
            distinct_sources.add(r.source)

    # ------------------------------------------------------------------ stage 3: refine match decision
    # Tighten / loosen `is_match` based on corroboration + year tolerance.
    title_ok_tight = primary.title_similarity >= _TITLE_MATCH_TIGHT
    year_ok_loose = _year_close(primary.bib_year, primary.fetched_year)

    if agree_count >= 1 and title_ok_tight:
        primary.is_match = True
    elif title_ok_tight and primary.author_match and year_ok_loose:
        primary.is_match = True
    elif primary.is_match and not (title_ok_tight and year_ok_loose):
        # Original heuristic said match but our stricter rule disagrees.
        primary.is_match = False
        if not any("stricter check" in i.lower() for i in primary.issues):
            primary.issues.append(
                "Marked unverified by stricter check (title/year tolerance not met)."
            )

    # Boost / annotate confidence with corroboration signal.
    if agree_count >= 1:
        # Each corroborating source bumps confidence toward 1.0.
        bonus = min(0.25, 0.1 + 0.05 * agree_count)
        primary.confidence = min(1.0, primary.confidence + bonus)
        # Positive note — goes to `notes`, NOT `issues`. Otherwise verified
        # entries would display a misleading "1 issue(s)" badge.
        primary.notes.append(
            f"Corroborated by {agree_count} other source(s): {', '.join(sorted(distinct_sources))}."
        )

    # Year-only mismatch with otherwise solid match: drop the hard issue
    # and record a soft note instead (preprint/published year difference).
    if (primary.title_match and primary.author_match and not primary.year_match
            and year_ok_loose and primary.bib_year and primary.fetched_year):
        primary.issues = [
            i for i in primary.issues if not i.startswith("Year mismatch")
        ]
        primary.notes.append(
            f"Year differs by ≤1 ({primary.bib_year} vs {primary.fetched_year}) — "
            "likely preprint/published difference, treated as match."
        )

    return primary
