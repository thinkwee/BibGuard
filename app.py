#!/usr/bin/env python3
"""
BibGuard Gradio web app — minimalist iframe layout.

The right pane embeds the self-contained ``report.html`` produced by
``src/report/html_report.py`` via ``<iframe srcdoc=...>``. This makes the
generated report the single source of truth (per-section filters, full-text
search, dark mode, inline span highlighting all live inside it) and avoids
re-rendering the same content inside Gradio with stale styles.
"""
from __future__ import annotations

import base64
import logging
import os
import tempfile
import time
from pathlib import Path

import gradio as gr

from src.parsers import BibParser, TexParser
from src.fetchers import (
    ArxivFetcher, CrossRefFetcher, SemanticScholarFetcher,
    OpenAlexFetcher, DBLPFetcher,
)
from src.analyzers import MetadataComparator, UsageChecker, DuplicateDetector
from src.report.generator import ReportGenerator, EntryReport
from src.config.yaml_config import (
    BibGuardConfig, BibliographyConfig, SubmissionConfig, OutputConfig,
)
from src.config.workflow import get_default_workflow
from src.checkers import CHECKER_REGISTRY
from src.checkers.retraction_checker import RetractionChecker
from src.checkers.url_checker import URLChecker
from src.utils import http as http_layer
from src.utils.logging_setup import setup as setup_logging, capture_run
from src.utils.validation import validate_bib, validate_tex, format_report
from app_helper import fetch_and_compare_with_workflow

LOG_PATH = setup_logging(os.environ.get("BIBGUARD_LOG", "WARNING"))
logger = logging.getLogger("bibguard.app")
logger.info("BibGuard app starting (log file: %s)", LOG_PATH)

# Configure HTTP layer once at import time.
http_layer.configure(
    contact_email=os.environ.get("BIBGUARD_CONTACT_EMAIL", ""),
    cache_enabled=True,
    cache_ttl_hours=24,
    retry_total=5,
    retry_backoff_factor=1.5,
)


# --------------------------------------------------------------------- presets

PRESETS = {
    "Quick": {
        "check_metadata": False, "check_duplicates": True, "check_usage": True, "check_preprint_ratio": True,
        "url_liveness": False, "retraction": False,
        "submission": {"caption": True, "reference": True, "formatting": True, "equation": True,
                       "ai_artifacts": True, "sentence": True, "consistency": True, "acronym": True,
                       "number": True, "citation_quality": True, "anonymization": True},
    },
    "Standard": {
        "check_metadata": False, "check_duplicates": True, "check_usage": True, "check_preprint_ratio": True,
        "url_liveness": False, "retraction": True,
        "submission": {"caption": True, "reference": True, "formatting": True, "equation": True,
                       "ai_artifacts": True, "sentence": True, "consistency": True, "acronym": True,
                       "number": True, "citation_quality": True, "anonymization": True},
    },
    "Strict": {
        "check_metadata": True, "check_duplicates": True, "check_usage": True, "check_preprint_ratio": True,
        "url_liveness": True, "retraction": True,
        "submission": {"caption": True, "reference": True, "formatting": True, "equation": True,
                       "ai_artifacts": True, "sentence": True, "consistency": True, "acronym": True,
                       "number": True, "citation_quality": True, "anonymization": True},
    },
}


# ----------------------------------------------------------------------- CSS

CUSTOM_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

* { font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif; }

/* Reserve space for the vertical scrollbar so expanding the Advanced
   accordion (or anything else that adds content) doesn't shift the
   layout horizontally. `overflow-y: scroll` on html is the universal
   fallback for browsers without scrollbar-gutter.
   `overflow-x: hidden` on body kills any page-width jitter coming from
   inner elements that briefly overflow during streaming updates. */
html { scrollbar-gutter: stable; overflow-y: scroll; overflow-x: hidden; }
body { overflow-x: hidden; }

.gradio-container {
    max-width: 1400px !important;
    margin: 0 auto !important;
    padding: 0 20px !important;
    box-sizing: border-box !important;
    width: 100% !important;
    overflow-x: hidden !important;
}

/* Header strip */
.bg-header {
    padding: 14px 4px 12px !important;
    border-bottom: 1px solid #e5e7eb;
    margin-bottom: 14px;
}

/* ==================================================================
   Top toolbar — single horizontal row with all primary controls.
   Every primary control has the SAME explicit 56px height. The little
   filename/info chip beneath sits in a fixed 18px slot. The columns
   wrap that into a 78px tall toolbar that's identical across cells.
   ================================================================== */
.bg-toolbar {
    margin-bottom: 14px;
    gap: 10px !important;
    align-items: flex-start !important;
}
.bg-toolbar .gr-form { gap: 0 !important; }
.bg-toolbar .gr-block { border: none !important; box-shadow: none !important; padding: 0 !important; }

/* Common: any direct primary control fills column width */
.bg-toolbar > * { width: 100% !important; }

/* ---- Upload buttons ---- */
.bg-upload-btn,
.bg-upload-btn > .wrap,
.bg-upload-btn > div {
    height: 56px !important;
    min-height: 56px !important;
    max-height: 56px !important;
    width: 100% !important;
}
.bg-upload-btn button {
    height: 56px !important;
    min-height: 56px !important;
    max-height: 56px !important;
    width: 100% !important;
    padding: 0 14px !important;
    font-size: 13px !important;
    font-weight: 500 !important;
    border-radius: 8px !important;
    border: 1px dashed #cbd5e1 !important;
    background: #f8fafc !important;
    color: #334155 !important;
    transition: border 0.15s, background 0.15s !important;
    line-height: 1 !important;
}
.bg-upload-btn button:hover {
    border-color: #2563eb !important;
    background: #eff6ff !important;
    color: #1e3a8a !important;
}

/* ---- Run / Stop button (same column, visibility-swapped) ---- */
.bg-run-btn,
.bg-run-btn > .wrap,
.bg-run-btn > div {
    height: 56px !important;
    min-height: 56px !important;
    max-height: 56px !important;
    width: 100% !important;
}
.bg-run-btn button {
    height: 56px !important;
    min-height: 56px !important;
    max-height: 56px !important;
    width: 100% !important;
    font-weight: 600 !important;
    border-radius: 8px !important;
    font-size: 14px !important;
    line-height: 1 !important;
    padding: 0 16px !important;
}
.bg-stop-btn button {
    background: #dc2626 !important;
    color: white !important;
    border: none !important;
}
.bg-stop-btn button:hover { background: #b91c1c !important; }

/* ---- Preset radio as horizontal pill chips ---- */
.bg-preset,
.bg-preset > div,
.bg-preset > .wrap {
    height: 56px !important;
    min-height: 56px !important;
    max-height: 56px !important;
    padding: 0 !important;
}
.bg-preset > label,
.bg-preset .label-wrap { display: none !important; }
.bg-preset .wrap,
.bg-preset > div > div,
.bg-preset fieldset {
    display: flex !important;
    flex-direction: row !important;
    gap: 4px !important;
    flex-wrap: nowrap !important;
    width: 100% !important;
    height: 56px !important;
    align-items: stretch !important;
    border: none !important;
    padding: 0 !important;
    margin: 0 !important;
}
.bg-preset label {
    flex: 1 1 0 !important;
    margin: 0 !important;
    padding: 0 8px !important;
    height: 56px !important;
    min-height: 56px !important;
    max-height: 56px !important;
    border-radius: 8px !important;
    font-size: 13px !important;
    font-weight: 500 !important;
    border: 1px solid #e5e7eb !important;
    background: #ffffff !important;
    cursor: pointer !important;
    text-align: center !important;
    display: inline-flex !important;
    align-items: center !important;
    justify-content: center !important;
    line-height: 1 !important;
    color: #475569 !important;
    transition: background 0.15s, border 0.15s !important;
    white-space: nowrap !important;
}
.bg-preset label:hover { background: #f8fafc !important; border-color: #cbd5e1 !important; }
.bg-preset input[type="radio"] { display: none !important; }
.bg-preset label.selected,
.bg-preset label:has(input:checked) {
    background: #1e3a8a !important;
    color: #ffffff !important;
    border-color: #1e3a8a !important;
}

/* ---- Caption chip beneath each toolbar control ---- */
.bg-fname {
    font-size: 11.5px;
    color: #94a3b8;
    padding: 4px 8px 0 8px;
    line-height: 1.3;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    height: 18px;
    box-sizing: content-box;
}
.bg-fname.ok { color: #166534; font-weight: 500; }

/* ==================================================================
   Advanced settings — gr.Row with each Checkbox as its own card.
   Trick: `display: contents` on Gradio's intermediate wrapper makes
   it vanish from the layout tree, so the actual checkbox blocks
   become direct flex children of .bg-row. Card style is applied to
   each block, not the wrapper, so we get N cards per row instead of
   one big box.
   ================================================================== */
.bg-row {
    display: flex !important;
    flex-direction: row !important;
    gap: 10px !important;
    align-items: stretch !important;
    padding: 4px 0 !important;
}

/* Flatten Gradio's intermediate `.form` / `.gr-form` wrapper so its
   children become direct flex items of .bg-row. */
.bg-row > .form,
.bg-row > .gr-form {
    display: contents !important;
}
/* Some Gradio versions emit a plain `<div>` wrapper instead of `.form`.
   We can't safely `display: contents` every direct div (the spacer is
   one), but if the wrapper has only blocks inside, contents flatten it. */
.bg-row > div:not(.bg-row-spacer):not(.gr-block):not(.block) {
    display: contents !important;
}

/* Each individual checkbox block = a card */
.bg-row .gr-block,
.bg-row .block {
    flex: 1 1 0 !important;
    min-width: 0 !important;
    background: #f8fafc !important;
    border: 1px solid #e5e7eb !important;
    border-radius: 8px !important;
    padding: 8px 12px !important;
    box-shadow: none !important;
    transition: background 0.15s, border 0.15s !important;
}
.bg-row .gr-block:hover,
.bg-row .block:hover {
    background: #eff6ff !important;
    border-color: #cbd5e1 !important;
}
.bg-row label,
.bg-row .gr-checkbox label {
    font-size: 13px !important;
    font-weight: 500 !important;
    line-height: 1.3 !important;
    color: #334155 !important;
    margin: 0 !important;
    padding: 0 !important;
}
.bg-row .gr-info, .bg-row [class*="info"] { display: none !important; }

/* Spacer — invisible flex item that just preserves alignment */
.bg-row .bg-row-spacer {
    flex: 1 1 0 !important;
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    padding: 0 !important;
    visibility: hidden !important;
}

/* ==================================================================
   Status strip — thin one-liner above the report.
   The Gradio HTML wrapper itself is pinned to its parent column's width
   so no inner content can change the page geometry during streaming.
   ================================================================== */
#bg-status-wrap,
#bg-status-wrap > * {
    width: 100% !important;
    max-width: 100% !important;
    min-width: 0 !important;
    box-sizing: border-box !important;
    overflow-x: hidden !important;
}
.bg-status {
    padding: 10px 14px;
    border-radius: 10px;
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    font-size: 12.5px;
    line-height: 1.45;
    color: #334155;
    margin: 8px 0 12px 0;
    max-width: 100%;
    overflow: hidden;       /* never let inline content widen the page */
    box-sizing: border-box;
}
.bg-status-row {
    display: flex;
    align-items: center;
    gap: 14px;
    flex-wrap: nowrap;      /* one row, ellipsize the middle */
    min-width: 0;
    width: 100%;
}
.bg-status .bg-status-stage {
    font-weight: 600;
    color: #1e3a8a;
    display: inline-flex;
    align-items: center;
    gap: 8px;
    flex-shrink: 0;
    white-space: nowrap;
}
.bg-status .bg-status-detail {
    color: #475569;
    flex: 1 1 0;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}
.bg-status .bg-status-detail code {
    background: #eef2ff;
    padding: 1px 6px;
    border-radius: 4px;
    font-size: 11.5px;
    color: #1e3a8a;
}
.bg-status .bg-status-meta {
    color: #64748b;
    font-size: 11.5px;
    display: inline-flex;
    flex-wrap: nowrap;
    gap: 12px;
    flex-shrink: 0;
    white-space: nowrap;
}
.bg-status.done { background: #f0fdf4; border-color: #bbf7d0; }
.bg-status.done .bg-status-stage { color: #166534; }
.bg-status.error { background: #fef2f2; border-color: #fecaca; }
.bg-status.error .bg-status-stage { color: #b91c1c; }
.bg-status .spin {
    display: inline-block;
    width: 10px; height: 10px;
    border: 2px solid #cbd5e1;
    border-top-color: #2563eb;
    border-radius: 50%;
    animation: bg-spin 0.9s linear infinite;
}
@keyframes bg-spin { to { transform: rotate(360deg); } }

/* ==================================================================
   Report area — full-width iframe.
   ================================================================== */
.bg-main { padding: 0 !important; }
.bg-report-iframe {
    width: 100%;
    height: 80vh;
    min-height: 620px;
    border: 1px solid #e5e7eb;
    border-radius: 12px;
    background: white;
    box-shadow: 0 1px 2px rgba(0,0,0,0.04);
}

/* Empty / error placeholder (full-width, centered card) */
.bg-empty {
    display: flex; align-items: center; justify-content: center;
    flex-direction: column; gap: 14px;
    min-height: 60vh;
    color: #6b7280; text-align: center;
    border: 2px dashed #e5e7eb; border-radius: 12px;
    padding: 56px 24px;
    background: #fafafa;
}
.bg-empty .bg-empty-icon { font-size: 56px; line-height: 1; }
.bg-empty .bg-empty-title { font-size: 17px; font-weight: 600; color: #374151; }
.bg-empty .bg-empty-hint { font-size: 14px; max-width: 580px; line-height: 1.6; }
.bg-empty .bg-empty-hint code { background: #f3f4f6; padding: 1px 6px; border-radius: 4px; font-size: 13px; }

/* Compact downloads section */
.bg-downloads { gap: 6px !important; }
.bg-downloads .gr-file { min-height: auto !important; }
.bg-downloads .bg-file-input > label > div {
    height: 52px !important;
    min-height: 52px !important;
    max-height: 52px !important;
}

/* Footer */
.bg-footer {
    text-align: center;
    margin-top: 18px;
    padding-top: 12px;
    border-top: 1px solid #f1f5f9;
    font-size: 11.5px;
    color: #9ca3af;
}
.bg-footer code { background: #f3f4f6; padding: 1px 5px; border-radius: 3px; font-size: 11px; }
.bg-footer a { color: #6b7280; text-decoration: none; }
.bg-footer a:hover { text-decoration: underline; }

/* Trim accordion chrome a bit */
.gr-accordion { border-radius: 10px !important; border: 1px solid #e5e7eb !important; }
.gr-accordion > .label-wrap { padding: 8px 12px !important; font-size: 13px !important; }

@media (prefers-color-scheme: dark) {
    .bg-empty { background: #161b22; border-color: #2a313c; color: #9ca3af; }
    .bg-empty .bg-empty-title { color: #e6edf3; }
    .bg-empty .bg-empty-hint code { background: #21262d; }
    .bg-report-iframe { background: #0d1117; border-color: #2a313c; box-shadow: none; }
    .bg-status { background: #0f172a; border-color: #1e293b; color: #cbd5e1; }
    .bg-status .bg-status-stage { color: #93c5fd; }
    .bg-status .bg-status-detail { color: #94a3b8; }
    .bg-status .bg-status-detail code { background: #1e293b; color: #93c5fd; }
    .bg-status .bg-status-meta { color: #64748b; }
    .bg-status.done { background: #052e1a; border-color: #14532d; }
    .bg-status.done .bg-status-stage { color: #86efac; }
    .bg-status.error { background: #2a0e0e; border-color: #7f1d1d; }
    .bg-preset label { background: #161b22 !important; border-color: #2a313c !important; color: #cbd5e1 !important; }
    .bg-preset label:hover { background: #1e293b !important; }
    .bg-preset .selected { background: #2563eb !important; border-color: #2563eb !important; }
    .bg-footer { border-color: #1e293b; }
}
"""


EMPTY_PANEL_HTML = """
<div class="bg-empty">
    <div class="bg-empty-icon">📄</div>
    <div class="bg-empty-title">Your interactive report appears here</div>
    <div class="bg-empty-hint">
        Upload a <code>.bib</code> file and a <code>.tex</code> file in the toolbar above,
        pick a preset, then press <strong>Run check</strong>. The report renders as a
        self-contained HTML page with per-section filters, full-text search,
        inline span highlighting, and dark-mode support.
    </div>
</div>
"""

EMPTY_STATUS_HTML = (
    '<div class="bg-status">'
    '<div class="bg-status-row">'
    '<span class="bg-status-stage">○ Idle</span>'
    '<span class="bg-status-detail">Upload <code>.bib</code> + <code>.tex</code> '
    'and press <strong>Run check</strong> to begin.</span>'
    '</div></div>'
)


def _placeholder(message: str, color: str = "#b91c1c") -> str:
    """Inline error/info card shown in place of the iframe."""
    return (
        f'<div class="bg-empty" style="color:{color};border-color:{color}33">'
        f'<div class="bg-empty-icon">⚠️</div>'
        f'<div class="bg-empty-title">{message}</div>'
        f'</div>'
    )


def _html_to_iframe(html: str) -> str:
    """
    Embed an HTML document inside ``<iframe srcdoc>``.

    We escape only ``&`` and ``"`` — these are the two characters that can
    break the attribute value or get re-decoded as entities. ``<`` and ``>``
    must stay raw, otherwise the inner document would be HTML-encoded.
    """
    escaped = html.replace("&", "&amp;").replace('"', "&quot;")
    return (
        f'<iframe class="bg-report-iframe" srcdoc="{escaped}" '
        f'sandbox="allow-scripts allow-same-origin allow-popups allow-popups-to-escape-sandbox" '
        f'loading="lazy"></iframe>'
    )


def _status_html(stage: str, detail: str = "", meta: list[str] | None = None,
                 state: str = "running") -> str:
    """Render the live-status strip shown above the report.

    Layout is a single horizontal row: [stage] [detail] [meta chips].
    Wraps cleanly on narrow screens.
    """
    if state == "running":
        stage_icon = '<span class="spin"></span>'
    elif state == "done":
        stage_icon = '<span>✓</span>'
    elif state == "error":
        stage_icon = '<span>⚠</span>'
    else:
        stage_icon = '<span>○</span>'
    detail_html = f'<span class="bg-status-detail">{detail}</span>' if detail else '<span class="bg-status-detail"></span>'
    meta_html = ""
    if meta:
        meta_html = (
            '<span class="bg-status-meta">'
            + " ".join(f"<span>{m}</span>" for m in meta)
            + "</span>"
        )
    return (
        f'<div class="bg-status {state}">'
        f'<div class="bg-status-row">'
        f'<span class="bg-status-stage">{stage_icon}<span>{stage}</span></span>'
        f'{detail_html}{meta_html}'
        f'</div></div>'
    )


# --------------------------------------------------------------- config glue

def create_config_from_ui(
    check_metadata, check_usage, check_duplicates, check_preprint_ratio,
    caption, reference, formatting, equation, ai_artifacts,
    sentence, consistency, acronym, number, citation_quality, anonymization,
) -> BibGuardConfig:
    config = BibGuardConfig()
    config.bibliography = BibliographyConfig(
        check_metadata=check_metadata,
        check_usage=check_usage,
        check_duplicates=check_duplicates,
        check_preprint_ratio=check_preprint_ratio,
        check_relevance=False,  # LLM disabled in web mode
    )
    config.submission = SubmissionConfig(
        caption=caption, reference=reference, formatting=formatting, equation=equation,
        ai_artifacts=ai_artifacts, sentence=sentence, consistency=consistency,
        acronym=acronym, number=number, citation_quality=citation_quality,
        anonymization=anonymization,
    )
    config.output = OutputConfig(quiet=True, minimal_verified=False)
    return config


def apply_preset(name: str):
    p = PRESETS.get(name, PRESETS["Standard"])
    sub = p["submission"]
    return (
        p["check_metadata"], p["check_usage"], p["check_duplicates"], p["check_preprint_ratio"],
        sub["caption"], sub["reference"], sub["formatting"], sub["equation"],
        sub["ai_artifacts"], sub["sentence"], sub["consistency"], sub["acronym"],
        sub["number"], sub["citation_quality"], sub["anonymization"],
        p["url_liveness"], p["retraction"],
    )


_PRESET_CAPTIONS = {
    "Quick":    "local checks only · no network · instant",
    "Standard": "local checks + retraction lookup (CrossRef)",
    "Strict":   "+ URL liveness + multi-source metadata (slow)",
}


def _preset_caption_html(name: str) -> str:
    text = _PRESET_CAPTIONS.get(name, "")
    return f'<div class="bg-fname" style="text-align:center">{text}</div>'


# ------------------------------------------------------------------ run_check
# Streaming generator. Each yield is a 7-tuple:
#   (iframe_html, status_html, html_path, md_path, json_path,
#    cleaned_bib_path, log_path)
# `capture_run` attaches a per-run DEBUG file handler so any exception or
# warning anywhere in the pipeline is recorded with full traceback at
# `<out_dir>/bibguard.log`, which is then downloadable. The status panel
# surfaces warning+error counts so problems aren't invisible.

def run_check(
    bib_file, tex_file,
    check_metadata, check_usage, check_duplicates, check_preprint_ratio,
    caption, reference, formatting, equation, ai_artifacts,
    sentence, consistency, acronym, number, citation_quality, anonymization,
    url_liveness=False, retraction=True,
):
    """Run the full check pipeline as a streaming generator with per-run logging.

    `bib_file` / `tex_file` are filesystem path strings (carried by gr.State),
    not gr.File objects. The status panel is the single source of progress
    feedback — no separate gr.Progress bar.
    """
    started = time.time()

    def _elapsed() -> str:
        return f"⏱ {int(time.time() - started)}s"

    # Initial state: keep current report (None means clear).
    if not bib_file or not tex_file:
        yield (
            _placeholder("Please choose both a .bib and a .tex file in the toolbar."),
            _status_html("Waiting for files",
                         "Pick a .bib and a .tex file from the toolbar to start.",
                         state="error"),
            None, None, None, None, None,
        )
        return

    # Allocate the artifact dir up-front so the per-run log lives next to
    # the report files.
    out_dir = Path(tempfile.mkdtemp(prefix="bibguard_"))
    log_path_target = out_dir / "bibguard.log"

    # Reset per-source circuit breakers so a previous run's flaky source
    # doesn't carry over and skip valid lookups in this run.
    http_layer.reset_breakers()

    with capture_run(target_path=log_path_target) as (log_path, log_stats):
        logger.info("=== run_check start: bib=%s tex=%s ===", bib_file, tex_file)
        try:
            yield from _run_check_impl(
                bib_file, tex_file, out_dir, log_path, log_stats,
                check_metadata, check_usage, check_duplicates, check_preprint_ratio,
                caption, reference, formatting, equation, ai_artifacts,
                sentence, consistency, acronym, number, citation_quality, anonymization,
                url_liveness, retraction, started, _elapsed,
            )
        except Exception as e:
            logger.exception("run_check crashed (entry-level guard)")
            yield (
                _placeholder(f"Unhandled error: {e}"),
                _status_html("Failed", f"{e} — see <code>bibguard.log</code> for the full traceback.",
                             state="error"),
                None, None, None, None, str(log_path),
            )
        finally:
            logger.info("=== run_check end: warnings=%d errors=%d ===",
                        log_stats.warnings, log_stats.errors)


def _run_check_impl(
    bib_file, tex_file, out_dir, log_path, log_stats,
    check_metadata, check_usage, check_duplicates, check_preprint_ratio,
    caption, reference, formatting, equation, ai_artifacts,
    sentence, consistency, acronym, number, citation_quality, anonymization,
    url_liveness, retraction, started, _elapsed,
):
    """Inner pipeline. Wrapped in `capture_run` by `run_check`.

    Every yield is a 7-tuple ending with the log path so the user can
    download `bibguard.log` even from intermediate updates.
    """
    log_path_str = str(log_path)

    bib_path = Path(bib_file)
    tex_path = Path(tex_file)
    logger.info("Inputs: bib=%s tex=%s out_dir=%s", bib_path, tex_path, out_dir)

    def _meta_with_logs(extra: list[str]) -> list[str]:
        out = list(extra)
        if log_stats.warnings or log_stats.errors:
            out.append(f"⚠ {log_stats.warnings}w / {log_stats.errors}e logged")
        return out

    yield (
        gr.update(),
        _status_html("Validating files",
                     f"Reading <code>{bib_path.name}</code> and <code>{tex_path.name}</code>",
                     meta=_meta_with_logs([_elapsed()])),
        None, None, None, None, log_path_str,
    )

    # Pre-flight content validation
    bib_rep = validate_bib(bib_path)
    tex_rep = validate_tex(tex_path)
    msg = "\n".join(filter(None, [
        format_report(bib_rep, bib_path.name),
        format_report(tex_rep, tex_path.name),
    ]))
    if not bib_rep.ok or not tex_rep.ok:
        logger.error("File validation failed:\n%s", msg)
        block = (
            f'<div class="bg-empty" style="color:#b91c1c;border-color:#b91c1c33">'
            f'<div class="bg-empty-icon">⚠️</div>'
            f'<div class="bg-empty-title">File validation failed</div>'
            f'<pre style="white-space:pre-wrap;font-size:13px;color:#7f1d1d;'
            f'background:#fef2f2;padding:12px;border-radius:6px;max-width:540px">{msg}</pre>'
            f'</div>'
        )
        yield (
            block,
            _status_html("File validation failed", msg.replace("\n", "<br>"),
                         state="error"),
            None, None, None, None, log_path_str,
        )
        return
    elif msg:
        logger.info("Validation warnings:\n%s", msg)

    config = create_config_from_ui(
        check_metadata, check_usage, check_duplicates, check_preprint_ratio,
        caption, reference, formatting, equation, ai_artifacts,
        sentence, consistency, acronym, number, citation_quality, anonymization,
    )

    yield (
        gr.update(),
        _status_html("Parsing", "Loading bibliography and LaTeX source",
                     meta=_meta_with_logs([_elapsed()])),
        None, None, None, None, log_path_str,
    )

    tex_content = tex_path.read_text(encoding='utf-8', errors='replace')
    bib_parser = BibParser()
    entries = bib_parser.parse_file(str(bib_path))
    tex_parser = TexParser()
    tex_parser.parse_file(str(tex_path))
    logger.info("Parsed %d bib entries from %s", len(entries), bib_path.name)

    bib_config = config.bibliography

    # Init components
    arxiv_fetcher = crossref_fetcher = ss_fetcher = oa_fetcher = dblp_fetcher = None
    comparator = usage_checker = duplicate_detector = None

    if bib_config.check_metadata:
        arxiv_fetcher = ArxivFetcher()
        ss_fetcher = SemanticScholarFetcher()
        oa_fetcher = OpenAlexFetcher()
        dblp_fetcher = DBLPFetcher()
        crossref_fetcher = CrossRefFetcher()
        comparator = MetadataComparator()
    if bib_config.check_usage:
        usage_checker = UsageChecker(tex_parser)
    if bib_config.check_duplicates:
        duplicate_detector = DuplicateDetector()

    report_gen = ReportGenerator(
        minimal_verified=False,
        check_preprint_ratio=bib_config.check_preprint_ratio,
        preprint_warning_threshold=bib_config.preprint_warning_threshold,
    )
    report_gen.set_metadata([str(bib_path)], [str(tex_path)])

    # Submission quality checks
    yield (
        gr.update(),
        _status_html("LaTeX quality checks",
                     f"Running {len(config.submission.get_enabled_checkers())} checkers on the LaTeX source",
                     meta=_meta_with_logs([f"📚 {len(entries)} bib entries", _elapsed()])),
        None, None, None, None, log_path_str,
    )
    submission_results = []
    for name in config.submission.get_enabled_checkers():
        if name in CHECKER_REGISTRY:
            try:
                checker = CHECKER_REGISTRY[name]()
                results = checker.check(tex_content, {})
                for r in results:
                    r.file_path = str(tex_path)
                submission_results.extend(results)
            except Exception:
                logger.exception("Checker %s crashed", name)
    report_gen.set_submission_results(submission_results, None)

    if bib_config.check_duplicates and duplicate_detector:
        try:
            report_gen.set_duplicate_groups(duplicate_detector.find_duplicates(entries))
        except Exception:
            logger.exception("Duplicate detection crashed")
    if bib_config.check_usage and usage_checker:
        try:
            report_gen.set_missing_citations(usage_checker.get_missing_entries(entries))
        except Exception:
            logger.exception("Missing-citation lookup crashed")

    # Per-entry workflow
    total = max(1, len(entries))
    workflow_config = get_default_workflow()
    verified_count = 0
    flagged_count = 0
    not_found_count = 0
    last_yield = time.time()

    def _identifier_chip(entry) -> str:
        """Tiny inline hint about which IDs we have for this entry."""
        bits = []
        if entry.doi: bits.append("DOI")
        if entry.has_arxiv: bits.append("arXiv")
        if entry.title and not bits: bits.append("title")
        elif entry.title: bits.append("title")
        return " + ".join(bits) if bits else "no identifiers"

    def _outcome_label(cmp) -> str:
        if cmp is None:
            return ""
        if cmp.source == "unable":
            return "<span style='color:#b45309'>? no metadata</span>"
        if cmp.is_match:
            return f"<span style='color:#166534'>✓ verified by {cmp.source}</span>"
        return f"<span style='color:#b45309'>⚠ flagged ({cmp.source})</span>"

    for i, entry in enumerate(entries):
        # ── Pre-fetch status: announce identifier set BEFORE the network roundtrip
        # so the user sees what's being attempted, not just the entry name.
        if bib_config.check_metadata and comparator:
            now = time.time()
            if now - last_yield > 0.4 or i == 0:
                ids = _identifier_chip(entry)
                detail = f"<code>{entry.key}</code> · querying via <strong>{ids}</strong>"
                if entry.title:
                    short = entry.title[:70] + ("…" if len(entry.title) > 70 else "")
                    detail += f" — <span style='color:#64748b'>{short}</span>"
                yield (
                    gr.update(),
                    _status_html(
                        f"Verifying entry {i + 1}/{total}",
                        detail,
                        meta=_meta_with_logs([
                            f"📚 {total} total",
                            f"✓ {verified_count}",
                            f"⚠ {flagged_count}",
                            f"? {not_found_count}",
                            _elapsed(),
                        ]),
                    ),
                    None, None, None, None, log_path_str,
                )
                last_yield = now

        usage_result = None
        comparison_result = None
        try:
            if usage_checker:
                usage_result = usage_checker.check_usage(entry)
        except Exception:
            logger.exception("Usage check crashed for entry=%s", entry.key)
        try:
            if bib_config.check_metadata and comparator:
                comparison_result = fetch_and_compare_with_workflow(
                    entry, workflow_config, arxiv_fetcher, crossref_fetcher,
                    ss_fetcher, oa_fetcher, dblp_fetcher, comparator,
                )
                if comparison_result is None or comparison_result.source == "unable":
                    not_found_count += 1
                elif comparison_result.is_match:
                    verified_count += 1
                else:
                    flagged_count += 1
        except Exception:
            logger.exception("Metadata fetch crashed for entry=%s", entry.key)
        report_gen.add_entry_report(EntryReport(
            entry=entry, comparison=comparison_result,
            usage=usage_result, evaluations=[],
        ))

        # ── Post-fetch status: show outcome inline so the user can watch
        # results stream in (verified / flagged / not found).
        now = time.time()
        if now - last_yield > 0.4 or i == total - 1:
            outcome = _outcome_label(comparison_result)
            detail_parts = [f"<code>{entry.key}</code>"]
            if outcome:
                detail_parts.append(outcome)
            if entry.title:
                short = entry.title[:70] + ("…" if len(entry.title) > 70 else "")
                detail_parts.append(f"<span style='color:#64748b'>{short}</span>")
            detail = " · ".join(detail_parts)
            meta = _meta_with_logs([
                f"📚 {i + 1}/{total}",
                f"✓ {verified_count}",
                f"⚠ {flagged_count}",
                f"? {not_found_count}",
                _elapsed(),
            ])
            yield (
                gr.update(),
                _status_html(f"Bibliography {i + 1}/{total}", detail, meta=meta),
                None, None, None, None, log_path_str,
            )
            last_yield = now

    if retraction:
        try:
            doi_count = sum(1 for e in entries if getattr(e, "doi", ""))
            yield (
                gr.update(),
                _status_html("Retraction lookups",
                             f"Querying CrossRef for {doi_count} DOI(s)",
                             meta=_meta_with_logs([_elapsed()])),
                None, None, None, None, log_path_str,
            )
            report_gen.set_retraction_findings(RetractionChecker().check_entries(entries))
        except Exception:
            logger.exception("Retraction lookup crashed")

    if url_liveness:
        try:
            url_count = sum(1 for e in entries if getattr(e, "url", ""))
            yield (
                gr.update(),
                _status_html("URL liveness",
                             f"HEAD-checking {url_count} URL(s) in parallel",
                             meta=_meta_with_logs([_elapsed()])),
                None, None, None, None, log_path_str,
            )
            report_gen.set_url_findings(URLChecker().check_entries(entries))
        except Exception:
            logger.exception("URL liveness crashed")

    # Save artifacts
    yield (
        gr.update(),
        _status_html("Building report",
                     "Rendering self-contained HTML, JSON, and Markdown",
                     meta=_meta_with_logs([_elapsed()])),
        None, None, None, None, log_path_str,
    )
    html_path = out_dir / "report.html"
    md_path = out_dir / "bibliography_report.md"
    json_path = out_dir / "report.json"
    cleaned_bib_path: Path | None = None

    try:
        report_gen.save_html(str(html_path))
        report_gen.save_bibliography_report(str(md_path))
        report_gen.save_json(str(json_path))
        if usage_checker:
            used_keys = {er.entry.key for er in report_gen.entries if er.usage and er.usage.is_used}
            if used_keys:
                cleaned_bib_path = out_dir / f"{bib_path.stem}_only_used.bib"
                bib_parser.filter_file(str(bib_path), str(cleaned_bib_path), used_keys)
    except Exception:
        logger.exception("Artifact generation failed")

    # Embed report.html as iframe srcdoc
    if html_path.exists():
        iframe_html = _html_to_iframe(html_path.read_text(encoding='utf-8'))
    else:
        iframe_html = _placeholder("Report generation failed — see bibguard.log.")

    meta = _meta_with_logs([
        f"📚 {len(entries)} entries",
        f"✓ {verified_count} verified",
        f"⚠ {flagged_count} flagged",
        _elapsed(),
    ])
    state = "done"
    summary = "Report ready. Use the right pane to filter, search, and copy fixes."
    if log_stats.errors > 0:
        state = "error"
        summary = (f"Done with {log_stats.errors} error(s) and {log_stats.warnings} warning(s) "
                   "logged — see <code>bibguard.log</code> for full tracebacks.")
    elif log_stats.warnings > 0:
        summary = (f"Report ready ({log_stats.warnings} warnings logged — see "
                   "<code>bibguard.log</code>).")

    yield (
        iframe_html,
        _status_html("Done", summary, meta=meta, state=state),
        str(html_path) if html_path.exists() else None,
        str(md_path) if md_path.exists() else None,
        str(json_path) if json_path.exists() else None,
        str(cleaned_bib_path) if (cleaned_bib_path and cleaned_bib_path.exists()) else None,
        log_path_str,
    )


# --------------------------------------------------------------------- layout

def create_app() -> gr.Blocks:
    # Inline app icon as a base64 data URL — works regardless of cwd.
    icon_html = '<span style="font-size:28px">🛡️</span>'
    try:
        icon_path = Path(__file__).parent / "assets" / "icon-192.png"
        if icon_path.exists():
            with open(icon_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            icon_html = (
                f'<img src="data:image/png;base64,{b64}" '
                f'style="width:32px;height:32px;border-radius:6px" alt="BibGuard">'
            )
    except Exception as e:
        logger.debug("Icon load failed; using emoji fallback: %s", e, exc_info=True)

    with gr.Blocks(
        title="BibGuard — Bibliography & LaTeX Quality Auditor",
    ) as app:

        gr.HTML(f"""
        <div class="bg-header" style="display:flex;align-items:center;gap:10px">
            {icon_html}
            <strong style="font-size:18px">BibGuard</strong>
            <span style="color:#6b7280;font-size:13px">— Bibliography & LaTeX quality auditor</span>
            <span style="flex:1"></span>
            <a href="https://github.com/thinkwee/BibGuard" target="_blank"
               style="color:#6b7280;text-decoration:none;font-size:13px">GitHub ↗</a>
        </div>
        """)

        # ───────────────────────── Top toolbar ─────────────────────────
        # All primary controls on a single horizontal row, every primary
        # widget pinned to 56px height. gr.UploadButton replaces gr.File
        # because the latter's drop-zone doesn't shrink to a toolbar.
        with gr.Row(elem_classes=["bg-toolbar"]):
            with gr.Column(scale=2, min_width=200):
                bib_btn = gr.UploadButton(
                    "📚 Choose .bib file",
                    file_types=[".bib"], file_count="single",
                    elem_classes=["bg-upload-btn"],
                )
                bib_status = gr.HTML('<div class="bg-fname">no file selected</div>')
            with gr.Column(scale=2, min_width=200):
                tex_btn = gr.UploadButton(
                    "📄 Choose .tex file",
                    file_types=[".tex"], file_count="single",
                    elem_classes=["bg-upload-btn"],
                )
                tex_status = gr.HTML('<div class="bg-fname">no file selected</div>')
            with gr.Column(scale=3, min_width=280):
                preset = gr.Radio(
                    choices=list(PRESETS.keys()),
                    value="Standard",
                    show_label=False,
                    elem_classes=["bg-preset"],
                )
                preset_caption = gr.HTML(
                    _preset_caption_html("Standard"),
                )
            with gr.Column(scale=1, min_width=140):
                run_btn = gr.Button("▶  Run check", variant="primary",
                                    elem_classes=["bg-run-btn"])
                stop_btn = gr.Button("◼  Stop", variant="stop",
                                     elem_classes=["bg-run-btn", "bg-stop-btn"],
                                     visible=False)
                gr.HTML('<div class="bg-fname" style="text-align:center">&nbsp;</div>')

        # Holds the selected file paths (strings). Updated by the UploadButton
        # callbacks below so run_check sees plain paths regardless of how the
        # user picked the files.
        bib_path_state = gr.State(value=None)
        tex_path_state = gr.State(value=None)

        # Advanced fine-grained toggles. Default closed — most users just
        # pick a preset and go. Each tab is composed of gr.Row blocks of
        # exactly 4 cells so columns line up vertically. Short rows are
        # padded with invisible spacer HTML.
        def _spacer():
            return gr.HTML('<div class="bg-row-spacer">&nbsp;</div>',
                           elem_classes=["bg-row-spacer"])

        with gr.Accordion("⚙️  Advanced settings", open=False):
            with gr.Tabs():
                with gr.TabItem("Bibliography"):
                    with gr.Row(elem_classes=["bg-row"]):
                        check_metadata = gr.Checkbox(label="Metadata verify", value=False)
                        check_usage = gr.Checkbox(label="Usage", value=True)
                        check_duplicates = gr.Checkbox(label="Duplicates", value=True)
                        check_preprint_ratio = gr.Checkbox(label="Preprints", value=True)
                    with gr.Row(elem_classes=["bg-row"]):
                        retraction = gr.Checkbox(label="Retractions", value=True)
                        url_liveness = gr.Checkbox(label="URL liveness", value=False)
                        _spacer()
                        _spacer()

                with gr.TabItem("LaTeX format"):
                    with gr.Row(elem_classes=["bg-row"]):
                        caption = gr.Checkbox(label="Captions", value=True)
                        reference = gr.Checkbox(label="References", value=True)
                        formatting = gr.Checkbox(label="Formatting", value=True)
                        equation = gr.Checkbox(label="Equations", value=True)

                with gr.TabItem("Writing"):
                    with gr.Row(elem_classes=["bg-row"]):
                        ai_artifacts = gr.Checkbox(label="AI artifacts", value=True)
                        sentence = gr.Checkbox(label="Sentences", value=True)
                        consistency = gr.Checkbox(label="Consistency", value=True)
                        acronym = gr.Checkbox(label="Acronyms", value=True)
                    with gr.Row(elem_classes=["bg-row"]):
                        number = gr.Checkbox(label="Numbers", value=True)
                        citation_quality = gr.Checkbox(label="Citations", value=True)
                        anonymization = gr.Checkbox(label="Anonymization", value=True)
                        _spacer()

        # ───────────────────────── Status strip ─────────────────────────
        status_panel = gr.HTML(value=EMPTY_STATUS_HTML, elem_id="bg-status-wrap")

        # ───────────────────────── Report (full width) ───────────────────
        with gr.Row(elem_classes=["bg-main"]):
            report_panel = gr.HTML(value=EMPTY_PANEL_HTML)

        # ───────────────────────── Downloads ────────────────────────────
        with gr.Accordion("📥 Downloads", open=False):
            with gr.Row(elem_classes=["bg-downloads"]):
                download_html = gr.File(label="report.html (offline)",
                                        interactive=False, elem_classes=["bg-file-input"])
                download_md = gr.File(label="bibliography_report.md",
                                      interactive=False, elem_classes=["bg-file-input"])
                download_json = gr.File(label="report.json",
                                        interactive=False, elem_classes=["bg-file-input"])
                download_bib = gr.File(label="cleaned .bib",
                                       interactive=False, elem_classes=["bg-file-input"])
                download_log = gr.File(label="bibguard.log",
                                       interactive=False, elem_classes=["bg-file-input"])

        gr.HTML(
            '<div class="bg-footer">'
            'Set <code>$BIBGUARD_CONTACT_EMAIL</code> for the polite-pool User-Agent · '
            f'persistent log at <code>{LOG_PATH}</code> · '
            'set <code>BIBGUARD_DEBUG=1</code> for verbose console output.'
            '</div>'
        )

        preset.change(
            fn=apply_preset,
            inputs=[preset],
            outputs=[
                check_metadata, check_usage, check_duplicates, check_preprint_ratio,
                caption, reference, formatting, equation,
                ai_artifacts, sentence, consistency, acronym,
                number, citation_quality, anonymization,
                url_liveness, retraction,
            ],
        )
        preset.change(
            fn=_preset_caption_html,
            inputs=[preset],
            outputs=[preset_caption],
        )

        # ---- Upload-button callbacks: store path in state + update chip ----

        def _on_bib_upload(f):
            if f is None:
                return None, '<div class="bg-fname">no file selected</div>'
            path = getattr(f, "name", str(f))
            return path, f'<div class="bg-fname ok">📚 {Path(path).name}</div>'

        def _on_tex_upload(f):
            if f is None:
                return None, '<div class="bg-fname">no file selected</div>'
            path = getattr(f, "name", str(f))
            return path, f'<div class="bg-fname ok">📄 {Path(path).name}</div>'

        bib_btn.upload(_on_bib_upload, inputs=[bib_btn], outputs=[bib_path_state, bib_status])
        tex_btn.upload(_on_tex_upload, inputs=[tex_btn], outputs=[tex_path_state, tex_status])

        # Run pipeline:
        #   1. Toggle visibility: hide Run, show Stop.
        #   2. Stream run_check yields into report + status + downloads.
        #   3. After completion, swap buttons back.
        # Stop button cancels the streaming task via Gradio's `cancels=`.
        def _show_stop():
            return gr.update(visible=False), gr.update(visible=True)

        def _show_run():
            return gr.update(visible=True), gr.update(visible=False)

        run_event = run_btn.click(
            fn=_show_stop, inputs=None, outputs=[run_btn, stop_btn],
        ).then(
            fn=run_check,
            inputs=[
                bib_path_state, tex_path_state,
                check_metadata, check_usage, check_duplicates, check_preprint_ratio,
                caption, reference, formatting, equation, ai_artifacts,
                sentence, consistency, acronym, number, citation_quality, anonymization,
                url_liveness, retraction,
            ],
            outputs=[report_panel, status_panel,
                     download_html, download_md, download_json, download_bib, download_log],
        ).then(
            fn=_show_run, inputs=None, outputs=[run_btn, stop_btn],
        )

        stop_btn.click(
            fn=lambda: (
                gr.update(visible=True),
                gr.update(visible=False),
                _status_html("Cancelled",
                             "Run interrupted by user. Partial results discarded.",
                             state="error"),
            ),
            inputs=None,
            outputs=[run_btn, stop_btn, status_panel],
            cancels=[run_event],
        )

    return app


app = create_app()


if __name__ == "__main__":
    _favicon = Path(__file__).parent / "assets" / "icon-192.png"
    app.launch(
        favicon_path=str(_favicon) if _favicon.exists() else None,
        show_error=True,
        css=CUSTOM_CSS,
        theme=gr.themes.Soft(),
    )
