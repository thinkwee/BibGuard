"""
Self-contained, single-file HTML report.

The output is a single .html with all CSS and JS inlined: no external network
requests, opens cleanly with `open report.html` on any OS, supports light/dark
theme via prefers-color-scheme + manual toggle, and offers per-section
filtering (Verified/Unverified/Unused for bib; Errors/Warnings/Info for
LaTeX), full-text search, and inline highlighting of the offending substring
on each LaTeX-quality issue.

The page is driven from a JSON blob embedded into the HTML, so re-rendering or
re-filtering is cheap. We deliberately avoid external libraries.

The embedded JSON deliberately omits all source file paths — only counts
(`bib_files_count`, `tex_files_count`) reach the page so reports can be
shared without leaking local paths.
"""
from __future__ import annotations

import html
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------

def render_standalone_html(payload: Dict[str, Any]) -> str:
    """
    Render a complete self-contained HTML report.

    `payload` shape (see ReportGenerator.build_payload):
        {
          "meta": { "generated_at": str, "bib_files_count": int,
                    "tex_files_count": int, "template": str },
          "summary": { ... bib + latex counts ... },
          "entries": [ { ... per-bib-entry ... } ],
          "submission_results": [ { ... per-line LaTeX issues ... } ],
          "retractions": [ { entry_key, doi, type, notice_url, label } ],
          "url_findings": [ { entry_key, url, status, status_code, detail } ],
          "duplicates": [ [keys...], ... ],
          "missing_citations": [ "key1", "key2" ]
        }
    """
    blob = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    title = "BibGuard Report — " + payload.get("meta", {}).get("generated_at", "")
    return _PAGE.replace("__TITLE__", html.escape(title)).replace("__DATA_JSON__", blob)


# ---------------------------------------------------------------------------
# Static page template (single string for easy diff review)
# ---------------------------------------------------------------------------

_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title>
<style>
:root {
  --bg: #f7f8fb;
  --panel: #ffffff;
  --panel-border: #e6e8ee;
  --text: #1f2330;
  --text-muted: #5b6473;
  --accent: #5b6cff;
  --accent-2: #8d6bff;
  --ok: #16a34a;
  --warn: #d97706;
  --err: #dc2626;
  --info: #2563eb;
  --code-bg: #f3f4f6;
  --shadow: 0 1px 3px rgba(0,0,0,.06), 0 8px 24px rgba(15,23,42,.04);
  --radius: 12px;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0e1117;
    --panel: #161b22;
    --panel-border: #2a313c;
    --text: #e6edf3;
    --text-muted: #98a2b3;
    --accent: #7c8dff;
    --accent-2: #b48aff;
    --ok: #4ade80;
    --warn: #fbbf24;
    --err: #f87171;
    --info: #60a5fa;
    --code-bg: #0b0f15;
    --shadow: 0 1px 3px rgba(0,0,0,.4), 0 8px 24px rgba(0,0,0,.4);
  }
}
html[data-theme="light"] {
  --bg: #f7f8fb; --panel: #ffffff; --panel-border: #e6e8ee;
  --text: #1f2330; --text-muted: #5b6473;
  --accent: #5b6cff; --accent-2: #8d6bff;
  --ok: #16a34a; --warn: #d97706; --err: #dc2626; --info: #2563eb;
  --code-bg: #f3f4f6;
}
html[data-theme="dark"] {
  --bg: #0e1117; --panel: #161b22; --panel-border: #2a313c;
  --text: #e6edf3; --text-muted: #98a2b3;
  --accent: #7c8dff; --accent-2: #b48aff;
  --ok: #4ade80; --warn: #fbbf24; --err: #f87171; --info: #60a5fa;
  --code-bg: #0b0f15;
}
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Inter", "Helvetica Neue", Arial, sans-serif;
  background: var(--bg);
  color: var(--text);
  line-height: 1.55;
}
header.bg-hero {
  background: linear-gradient(135deg, var(--accent) 0%, var(--accent-2) 100%);
  color: white;
  padding: 28px 32px 20px;
}
header.bg-hero h1 {
  margin: 0; font-size: 26px; letter-spacing: .2px;
}
header.bg-hero p { margin: 4px 0 0; opacity: .9; font-size: 14px; }
.container { max-width: 1180px; margin: 0 auto; padding: 24px 24px 80px; }
.toolbar {
  display: flex; gap: 8px; flex-wrap: wrap; align-items: center;
  position: sticky; top: 0; padding: 12px 0; background: var(--bg); z-index: 5;
  border-bottom: 1px solid var(--panel-border);
}
.toolbar input[type="search"] {
  flex: 1 1 240px; min-width: 240px;
  padding: 8px 12px; border-radius: 9999px; border: 1px solid var(--panel-border);
  background: var(--panel); color: var(--text); font-size: 14px;
}
.section-filters {
  display: flex; gap: 6px; flex-wrap: wrap; align-items: center;
  margin: 12px 0 4px;
}
.section-filters .label {
  font-size: 12px; color: var(--text-muted); margin-right: 4px;
}
.chip {
  display: inline-flex; align-items: center; gap: 6px; padding: 5px 11px;
  border-radius: 9999px; font-size: 12.5px; font-weight: 500;
  background: var(--panel); border: 1px solid var(--panel-border);
  color: var(--text); cursor: pointer; user-select: none;
}
.chip[data-active="true"] {
  background: var(--accent); color: #fff; border-color: var(--accent);
}
.chip .badge-count {
  background: rgba(0,0,0,.08); border-radius: 9999px; padding: 1px 7px; font-size: 11px;
}
.chip[data-active="true"] .badge-count { background: rgba(255,255,255,.2); }
.tabs { display: flex; gap: 4px; margin: 24px 0 12px; border-bottom: 1px solid var(--panel-border); }
.tab {
  padding: 10px 16px; cursor: pointer; border: none; background: transparent;
  color: var(--text-muted); font-size: 14px; font-weight: 500;
  border-bottom: 2px solid transparent;
}
.tab.active { color: var(--accent); border-bottom-color: var(--accent); }
.tab .count { color: var(--text-muted); font-weight: 400; margin-left: 4px; font-size: 12px; }
.section { display: none; }
.section.active { display: block; }
.stat-grid {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 12px; margin: 16px 0 8px;
}
.stat {
  background: var(--panel); border: 1px solid var(--panel-border);
  border-radius: var(--radius); padding: 14px 16px; box-shadow: var(--shadow);
}
.stat .v { font-size: 26px; font-weight: 700; }
.stat .l { font-size: 12px; color: var(--text-muted); text-transform: uppercase; letter-spacing: .04em; }
.card {
  background: var(--panel); border: 1px solid var(--panel-border);
  border-radius: var(--radius); padding: 14px 16px; margin: 10px 0;
  box-shadow: var(--shadow);
}
.card h3 { margin: 0 0 4px; font-size: 16px; }
.card .meta { color: var(--text-muted); font-size: 12px; }
.kvs { display: flex; flex-wrap: wrap; gap: 6px 14px; margin-top: 8px; font-size: 13px; }
.kv .k { color: var(--text-muted); margin-right: 4px; }
.badge {
  display: inline-flex; align-items: center; padding: 2px 9px; border-radius: 9999px;
  font-size: 12px; font-weight: 500; margin-left: 6px;
}
.badge.ok   { background: color-mix(in srgb, var(--ok) 20%, transparent);   color: var(--ok); }
.badge.warn { background: color-mix(in srgb, var(--warn) 22%, transparent); color: var(--warn); }
.badge.err  { background: color-mix(in srgb, var(--err) 22%, transparent);  color: var(--err); }
.badge.info { background: color-mix(in srgb, var(--info) 22%, transparent); color: var(--info); }
.badge.muted{ background: var(--code-bg); color: var(--text-muted); }
.code {
  display: block; font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12.5px; background: var(--code-bg); padding: 8px 10px;
  border-radius: 6px; overflow-x: auto; white-space: pre-wrap; word-break: break-word;
  margin-top: 8px;
}
.code mark {
  background: color-mix(in srgb, var(--warn) 35%, transparent);
  color: inherit;
  padding: 0 2px; border-radius: 3px;
  outline: 1px solid color-mix(in srgb, var(--warn) 60%, transparent);
}
.suggestion { color: var(--ok); margin-top: 8px; font-size: 13px; }
details summary { cursor: pointer; padding: 4px 0; font-size: 13px; color: var(--text-muted); }
.empty { text-align: center; color: var(--text-muted); padding: 40px 20px; font-style: italic; }
.theme-toggle {
  margin-left: auto; cursor: pointer; padding: 6px 10px; border-radius: 8px;
  border: 1px solid var(--panel-border); background: var(--panel); color: var(--text);
  font-size: 13px;
}
footer { color: var(--text-muted); text-align: center; padding: 30px 12px; font-size: 12px; }
@media print {
  .toolbar, .theme-toggle, .tabs, .section-filters { display: none !important; }
  .section { display: block !important; }
  .card { break-inside: avoid; box-shadow: none; }
}
</style>
</head>
<body>

<header class="bg-hero">
  <h1>🛡️ BibGuard Report</h1>
  <p id="hero-meta">Loading…</p>
</header>

<div class="container">

  <div class="toolbar">
    <input id="q" type="search" placeholder="Search title, author, key, message…">
    <button class="theme-toggle" id="themeBtn">🌓 Theme</button>
  </div>

  <div class="tabs">
    <button class="tab active" data-tab="bib">Bibliography <span class="count" id="ct-bib">0</span></button>
    <button class="tab" data-tab="tex">LaTeX Quality <span class="count" id="ct-tex">0</span></button>
    <button class="tab" data-tab="extra">Retractions / URLs <span class="count" id="ct-extra">0</span></button>
  </div>

  <section id="sec-bib" class="section active">
    <div class="stat-grid" id="bib-stats"></div>
    <div class="section-filters" id="bib-filters">
      <span class="label">Show:</span>
      <span class="chip" data-bibfilter="all" data-active="true">All <span class="badge-count" id="bf-all">0</span></span>
      <span class="chip" data-bibfilter="verified">✓ Verified <span class="badge-count" id="bf-ver">0</span></span>
      <span class="chip" data-bibfilter="unverified">⚠ Unverified <span class="badge-count" id="bf-unv">0</span></span>
      <span class="chip" data-bibfilter="unused">🗑 Unused <span class="badge-count" id="bf-uns">0</span></span>
    </div>
    <div id="bib-list"></div>
  </section>

  <section id="sec-tex" class="section">
    <div class="stat-grid" id="tex-stats"></div>
    <div class="section-filters" id="tex-filters">
      <span class="label">Severity:</span>
      <span class="chip" data-texfilter="all" data-active="true">All <span class="badge-count" id="tf-all">0</span></span>
      <span class="chip" data-texfilter="error">🔴 Errors <span class="badge-count" id="tf-err">0</span></span>
      <span class="chip" data-texfilter="warning">🟡 Warnings <span class="badge-count" id="tf-warn">0</span></span>
      <span class="chip" data-texfilter="info">🔵 Info <span class="badge-count" id="tf-info">0</span></span>
    </div>
    <div id="tex-list"></div>
  </section>

  <section id="sec-extra" class="section">
    <h2>🚫 Retractions</h2>
    <div id="retraction-list"></div>
    <h2 style="margin-top:24px">🔗 URL Liveness</h2>
    <div id="url-list"></div>
  </section>

  <footer>BibGuard — single-file HTML report. Works offline.</footer>
</div>

<script id="payload" type="application/json">__DATA_JSON__</script>
<script>
(function () {
  const data = JSON.parse(document.getElementById("payload").textContent);
  const meta = data.meta || {};
  document.getElementById("hero-meta").textContent =
    "Generated " + (meta.generated_at || "") +
    (meta.template ? " · template: " + meta.template : "") +
    " · " + (meta.bib_files_count || 0) + " bib · " + (meta.tex_files_count || 0) + " tex";

  // ---------- Filtering state ----------
  const state = { tab: "bib", bibFilter: "all", texFilter: "all", q: "" };

  // ---------- Data ----------
  const entries = data.entries || [];
  const subResults = data.submission_results || [];
  const retractions = data.retractions || [];
  const urlFindings = data.url_findings || [];

  // Tab counts
  document.getElementById("ct-bib").textContent = entries.length;
  document.getElementById("ct-tex").textContent = subResults.length;
  document.getElementById("ct-extra").textContent = retractions.length + urlFindings.length;

  // Bib filter counts
  const bibCounts = {
    all: entries.length,
    verified: entries.filter(e => e.comparison && e.comparison.is_match).length,
    unverified: entries.filter(e => !(e.comparison && e.comparison.is_match)).length,
    unused: entries.filter(e => e.usage && !e.usage.is_used).length,
  };
  document.getElementById("bf-all").textContent = bibCounts.all;
  document.getElementById("bf-ver").textContent = bibCounts.verified;
  document.getElementById("bf-unv").textContent = bibCounts.unverified;
  document.getElementById("bf-uns").textContent = bibCounts.unused;

  // Tex filter counts
  const texCounts = {
    all: subResults.length,
    error: subResults.filter(r => r.severity === "error").length,
    warning: subResults.filter(r => r.severity === "warning").length,
    info: subResults.filter(r => r.severity === "info").length,
  };
  document.getElementById("tf-all").textContent = texCounts.all;
  document.getElementById("tf-err").textContent = texCounts.error;
  document.getElementById("tf-warn").textContent = texCounts.warning;
  document.getElementById("tf-info").textContent = texCounts.info;

  // ---------- Render bib entries ----------
  function escapeHtml(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
  function badge(text, kind) { return `<span class="badge ${kind}">${escapeHtml(text)}</span>`; }
  // Render line_content with the offending substring wrapped in <mark>.
  // Returns escaped HTML; if match_text is missing or not found, returns
  // plain escaped line_content. Only highlights the first occurrence.
  function renderLineWithMark(line, match) {
    if (!line) return "";
    if (!match) return escapeHtml(line);
    const idx = line.indexOf(match);
    if (idx < 0) return escapeHtml(line);
    return escapeHtml(line.slice(0, idx))
      + "<mark>" + escapeHtml(match) + "</mark>"
      + escapeHtml(line.slice(idx + match.length));
  }

  function renderBibStats() {
    const total = entries.length;
    const verified = entries.filter(e => e.comparison && e.comparison.is_match).length;
    const used = entries.filter(e => e.usage && e.usage.is_used).length;
    const dups = (data.duplicates || []).length;
    const miss = (data.missing_citations || []).length;
    document.getElementById("bib-stats").innerHTML = [
      ["Total", total], ["Verified", verified], ["Used in TeX", used],
      ["Duplicate groups", dups], ["Missing entries", miss], ["Retractions", retractions.filter(r=>r.is_retracted).length],
    ].map(([l, v]) => `<div class="stat"><div class="v">${v}</div><div class="l">${escapeHtml(l)}</div></div>`).join("");
  }

  function entryMatches(e) {
    const q = state.q.toLowerCase();
    if (q) {
      const hay = (e.entry.title + " " + e.entry.author + " " + e.entry.key + " " +
        (e.comparison ? (e.comparison.fetched_title || "") : "")).toLowerCase();
      if (!hay.includes(q)) return false;
    }
    if (state.bibFilter === "all") return true;
    if (state.bibFilter === "verified") return e.comparison && e.comparison.is_match;
    if (state.bibFilter === "unverified") return !(e.comparison && e.comparison.is_match);
    if (state.bibFilter === "unused") return e.usage && !e.usage.is_used;
    return true;
  }

  function renderBibList() {
    const filtered = entries.filter(entryMatches);
    const container = document.getElementById("bib-list");
    if (!filtered.length) {
      container.innerHTML = `<div class="empty">No entries match.</div>`;
      return;
    }
    container.innerHTML = filtered.map(e => {
      const ent = e.entry, cmp = e.comparison, use = e.usage;
      const badges = [];
      if (cmp) {
        if (cmp.is_match) badges.push(badge("✓ Verified", "ok"));
        else badges.push(badge("⚠ Mismatch", "err"));
        if (cmp.source) badges.push(badge(cmp.source.toUpperCase(), "info"));
      } else {
        badges.push(badge("No metadata check", "muted"));
      }
      if (use) badges.push(use.is_used ? badge(`Used ${use.usage_count}×`, "ok") : badge("Unused", "warn"));
      const issues = (cmp && cmp.issues) ? cmp.issues : [];
      const notes = (cmp && cmp.notes) ? cmp.notes : [];
      const pubHint = cmp && cmp.published_version_hint ? cmp.published_version_hint : "";
      const eval_ = (e.evaluations && e.evaluations.length) ? e.evaluations[0] : null;
      return `<div class="card">
        <h3>${escapeHtml(ent.title || "(no title)")} ${badges.join("")}</h3>
        <div class="meta"><code>${escapeHtml(ent.key)}</code> · ${escapeHtml(ent.year || "")} · ${escapeHtml(ent.entry_type || "")}</div>
        <div class="kvs">
          ${ent.author ? `<div class="kv"><span class="k">Authors</span>${escapeHtml(ent.author)}</div>` : ""}
          ${(ent.journal || ent.booktitle) ? `<div class="kv"><span class="k">Venue</span>${escapeHtml(ent.journal || ent.booktitle)}</div>` : ""}
          ${ent.doi ? `<div class="kv"><span class="k">DOI</span><a href="https://doi.org/${escapeHtml(ent.doi)}" target="_blank" rel="noopener">${escapeHtml(ent.doi)}</a></div>` : ""}
          ${ent.arxiv_id ? `<div class="kv"><span class="k">arXiv</span><a href="https://arxiv.org/abs/${escapeHtml(ent.arxiv_id)}" target="_blank" rel="noopener">${escapeHtml(ent.arxiv_id)}</a></div>` : ""}
        </div>
        ${pubHint ? `<div class="suggestion">📚 ${escapeHtml(pubHint)}</div>` : ""}
        ${issues.length ? `<details open><summary>${issues.length} issue(s)</summary>${
          issues.map(i => `<div class="suggestion" style="color:var(--err)">• ${escapeHtml(i)}</div>`).join("")
        }</details>` : ""}
        ${notes.length ? `<details><summary style="color:var(--ok)">${notes.length} corroboration / note(s)</summary>${
          notes.map(n => `<div class="suggestion" style="color:var(--ok)">• ${escapeHtml(n)}</div>`).join("")
        }</details>` : ""}
        ${eval_ ? `<details><summary>LLM relevance: ${eval_.relevance_score}/5${eval_.citation_role ? " · role=" + escapeHtml(eval_.citation_role) : ""}</summary>
          <div class="suggestion">${escapeHtml(eval_.explanation || "")}</div></details>` : ""}
      </div>`;
    }).join("");
  }

  // ---------- LaTeX quality ----------
  function texMatches(r) {
    if (state.q && !((r.message + " " + (r.line_content||"") + " " + (r.checker||"")).toLowerCase().includes(state.q.toLowerCase()))) return false;
    if (state.texFilter === "all") return true;
    return r.severity === state.texFilter;
  }
  function renderTex() {
    const filtered = subResults.filter(texMatches);
    document.getElementById("tex-stats").innerHTML = [
      ["Errors", texCounts.error], ["Warnings", texCounts.warning], ["Info", texCounts.info]
    ].map(([l, v]) => `<div class="stat"><div class="v">${v}</div><div class="l">${escapeHtml(l)}</div></div>`).join("");
    const container = document.getElementById("tex-list");
    if (!filtered.length) { container.innerHTML = `<div class="empty">Clean.</div>`; return; }
    container.innerHTML = filtered.map(r => {
      const sev = r.severity || "info";
      const kind = sev === "error" ? "err" : sev === "warning" ? "warn" : "info";
      return `<div class="card">
        <h3>${escapeHtml(r.checker || "check")} ${badge(sev.toUpperCase(), kind)}</h3>
        ${r.line_number ? `<div class="meta">Line ${r.line_number}</div>` : ""}
        <div>${escapeHtml(r.message || "")}</div>
        ${r.line_content ? `<code class="code">${renderLineWithMark(r.line_content, r.match_text)}</code>` : ""}
        ${r.suggestion ? `<div class="suggestion">💡 ${escapeHtml(r.suggestion)}</div>` : ""}
      </div>`;
    }).join("");
  }

  // ---------- Extras ----------
  function renderExtras() {
    const doiCount = entries.filter(e => e.entry && e.entry.doi).length;
    const urlCount = entries.filter(e => e.entry && e.entry.url).length;

    document.getElementById("retraction-list").innerHTML = retractions.length
      ? retractions.map(r => {
        const isHard = r.is_retracted;
        return `<div class="card">
          <h3>${escapeHtml(r.entry_key)} ${badge(isHard ? "RETRACTED" : (r.update_type || "notice"), isHard ? "err" : "warn")}</h3>
          <div class="meta">DOI: ${escapeHtml(r.doi)}</div>
          ${r.notice_url ? `<div class="suggestion">Notice: <a href="${escapeHtml(r.notice_url)}" target="_blank" rel="noopener">${escapeHtml(r.notice_url)}</a></div>` : ""}
          ${r.notice_label ? `<div class="meta">${escapeHtml(r.notice_label)}</div>` : ""}
        </div>`;
      }).join("")
      : (doiCount === 0
          ? `<div class="empty">No DOI fields in any of ${entries.length} entries — nothing to look up. Add <code>doi=</code> to entries you want checked against the CrossRef retraction registry.</div>`
          : `<div class="empty">✓ Checked ${doiCount} DOI(s) against the CrossRef retraction registry — none flagged.</div>`);

    document.getElementById("url-list").innerHTML = urlFindings.length
      ? urlFindings.map(u => {
        const kind = u.status === "ok" ? "ok" : (u.status === "broken" ? "err" : "warn");
        return `<div class="card">
          <h3>${escapeHtml(u.entry_key)} ${badge(u.status, kind)}${u.status_code ? badge("HTTP "+u.status_code, "muted") : ""}</h3>
          <div class="meta"><a href="${escapeHtml(u.url)}" target="_blank" rel="noopener">${escapeHtml(u.url)}</a></div>
          ${u.detail ? `<div class="suggestion">${escapeHtml(u.detail)}</div>` : ""}
        </div>`;
      }).join("")
      : (urlCount === 0
          ? `<div class="empty">No <code>url=</code> fields in any of ${entries.length} entries — nothing to ping. Strict preset enables this check, but it only runs on entries that actually carry a URL.</div>`
          : `<div class="empty">URL liveness check did not run, or all ${urlCount} URLs were skipped (non-http schemes).</div>`);
  }

  // ---------- Wiring ----------
  function rerender() {
    if (state.tab === "bib") { renderBibStats(); renderBibList(); }
    if (state.tab === "tex") renderTex();
    if (state.tab === "extra") renderExtras();
  }
  document.querySelectorAll(".tab").forEach(b => b.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach(x => x.classList.remove("active"));
    document.querySelectorAll(".section").forEach(s => s.classList.remove("active"));
    b.classList.add("active");
    state.tab = b.dataset.tab;
    document.getElementById("sec-" + state.tab).classList.add("active");
    rerender();
  }));
  document.querySelectorAll("#bib-filters .chip").forEach(c => c.addEventListener("click", () => {
    document.querySelectorAll("#bib-filters .chip").forEach(x => x.dataset.active = "false");
    c.dataset.active = "true";
    state.bibFilter = c.dataset.bibfilter;
    renderBibList();
  }));
  document.querySelectorAll("#tex-filters .chip").forEach(c => c.addEventListener("click", () => {
    document.querySelectorAll("#tex-filters .chip").forEach(x => x.dataset.active = "false");
    c.dataset.active = "true";
    state.texFilter = c.dataset.texfilter;
    renderTex();
  }));
  document.getElementById("q").addEventListener("input", e => { state.q = e.target.value; rerender(); });
  document.getElementById("themeBtn").addEventListener("click", () => {
    const cur = document.documentElement.getAttribute("data-theme");
    const next = cur === "dark" ? "light" : (cur === "light" ? "" : "dark");
    if (next) document.documentElement.setAttribute("data-theme", next);
    else document.documentElement.removeAttribute("data-theme");
  });

  // Initial render — make sure bib stats appear immediately
  renderBibStats(); renderBibList();
})();
</script>
</body>
</html>
"""
