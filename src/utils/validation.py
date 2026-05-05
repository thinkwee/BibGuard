"""
Pre-flight validation for user-supplied .bib / .tex inputs.

Catch obvious problems (giant files, files that don't actually contain bibs/cites)
*before* spending five minutes on metadata fetches.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)


@dataclass
class ValidationReport:
    ok: bool = True
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def add_error(self, msg: str) -> None:
        self.errors.append(msg)
        self.ok = False

    def add_warning(self, msg: str) -> None:
        self.warnings.append(msg)


# Sensible thresholds; tuned for typical CS/ML papers.
MAX_BIB_BYTES = 5 * 1024 * 1024      # 5 MB
MAX_BIB_ENTRIES = 5000
MAX_TEX_BYTES = 10 * 1024 * 1024     # 10 MB

_BIB_ENTRY = re.compile(r"^@\w+\s*\{", re.MULTILINE)
_TEX_HAS_CITES = re.compile(r"\\(?:cite|citep|citet|citeauthor|citeyear|nocite|parencite|textcite)\b")
_TEX_HAS_BIB = re.compile(r"\\(?:bibliography|addbibresource|printbibliography|bibitem)\b")


def validate_bib(path: Path) -> ValidationReport:
    """Pre-flight check on a .bib file."""
    rep = ValidationReport()
    if not path.exists():
        rep.add_error(f"Bib file does not exist: {path}")
        return rep
    if not path.is_file():
        rep.add_error(f"Not a file: {path}")
        return rep

    size = path.stat().st_size
    if size == 0:
        rep.add_error(f"Bib file is empty: {path}")
        return rep
    if size > MAX_BIB_BYTES:
        rep.add_warning(
            f".bib file is large ({size/1024/1024:.1f} MB). Metadata checks may be slow."
        )

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        rep.add_error(f"Cannot read bib file: {e}")
        return rep

    entries = _BIB_ENTRY.findall(text)
    n = len(entries)
    if n == 0:
        rep.add_error(f"No bibtex entries (`@type{{...}}`) found in {path.name}.")
    elif n > MAX_BIB_ENTRIES:
        rep.add_warning(
            f"{n} entries in {path.name}; metadata checks may take a long time."
        )
    return rep


def validate_tex(path: Path) -> ValidationReport:
    """Pre-flight check on a .tex file."""
    rep = ValidationReport()
    if not path.exists():
        rep.add_error(f"TeX file does not exist: {path}")
        return rep
    if not path.is_file():
        rep.add_error(f"Not a file: {path}")
        return rep

    size = path.stat().st_size
    if size == 0:
        rep.add_error(f"TeX file is empty: {path}")
        return rep
    if size > MAX_TEX_BYTES:
        rep.add_warning(
            f".tex file is large ({size/1024/1024:.1f} MB). Some checks scan whole content."
        )

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        rep.add_error(f"Cannot read tex file: {e}")
        return rep

    has_cite = bool(_TEX_HAS_CITES.search(text))
    has_bib_decl = bool(_TEX_HAS_BIB.search(text))
    if not (has_cite or has_bib_decl):
        rep.add_warning(
            f"{path.name} contains no \\cite{{...}} and no \\bibliography{{...}} — "
            "BibGuard's bibliography checks won't find anything to verify."
        )
    return rep


def format_report(rep: ValidationReport, label: str = "") -> str:
    """Pretty-print a ValidationReport for stdout."""
    parts = []
    prefix = f"[{label}] " if label else ""
    for e in rep.errors:
        parts.append(f"{prefix}ERROR: {e}")
    for w in rep.warnings:
        parts.append(f"{prefix}WARN:  {w}")
    return "\n".join(parts)
