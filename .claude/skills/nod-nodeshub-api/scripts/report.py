#!/usr/bin/env python3
from __future__ import annotations
"""Unified HTML Report Builder for SEO Skills.

Creates branded HTML reports with multiple sections. Each skill can render
its data as a report section and append it to new or existing reports.

Usage as module:
    from report import create_report, append_section, render_section_wrapper

Usage as CLI:
    python3 report.py create --title "SEO Audit"
    python3 report.py create --title "SEO Audit" --section-file /tmp/section.html
    python3 report.py append --report reports/seo-audit_20260320.html --section-file /tmp/section.html
    python3 report.py list
"""

import argparse
import os
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from branding import load_brand, brand_css, render_header, render_footer


# ── Paths ─────────────────────────────────────────────────────────

def _find_repo_root() -> Path:
    """Walk up from CWD to find the repo root (has .git or CLAUDE.md)."""
    current = Path.cwd()
    for _ in range(8):
        if (current / ".git").exists() or (current / "CLAUDE.md").exists():
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent
    return Path.cwd()


def _reports_dir() -> Path:
    """Return the reports/ directory, creating it if needed."""
    d = _find_repo_root() / "output" / "reports"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ── Section wrapper ───────────────────────────────────────────────

def render_section_wrapper(section_id: str, skill_name: str, title: str,
                           content_html: str) -> str:
    """Wrap content in a section with comment markers for reliable append/replace.

    Args:
        section_id: Unique ID like "serp-analysis-20260320-143022"
        skill_name: Display name like "SERP Analysis"
        title: Section heading like "SERP Analysis: best seo tools"
        content_html: Inner HTML content (tables, cards, etc.)

    Returns:
        HTML string with marker comments.
    """
    return f"""<!-- BEGIN_SECTION:{section_id} -->
<section class="report-section" id="{section_id}">
  <div class="section-header">
    <h2>{title}</h2>
    <span class="section-skill">{skill_name}</span>
  </div>
  {content_html}
</section>
<!-- END_SECTION:{section_id} -->"""


# ── Report creation ───────────────────────────────────────────────

def _build_toc(html: str) -> str:
    """Build table of contents from section markers in HTML."""
    pattern = r'<!-- BEGIN_SECTION:(\S+) -->.*?<h2>(.*?)</h2>'
    matches = re.findall(pattern, html, re.DOTALL)
    if not matches:
        return ""
    items = "\n".join(
        f'    <li><a href="#{sid}">{title}</a></li>'
        for sid, title in matches
    )
    return f"""<nav class="report-toc">
  <h3>Contents</h3>
  <ol>
{items}
  </ol>
</nav>"""


def create_report(title: str, sections: list[str] | None = None,
                  extra_head: str = "") -> str:
    """Create a new HTML report file in reports/.

    Args:
        title: Report title (used in header and filename).
        sections: Optional list of section HTML strings.
        extra_head: Extra HTML to include in <head> (e.g., D3.js script tag).

    Returns:
        Path to the created HTML file.
    """
    brand = load_brand()
    now = datetime.now()
    safe_title = re.sub(r'[^a-zA-Z0-9]+', '-', title.lower()).strip('-')
    filename = f"{safe_title}_{now.strftime('%Y%m%d-%H%M%S')}.html"
    report_path = _reports_dir() / filename

    sections_html = "\n".join(sections) if sections else ""
    toc = _build_toc(sections_html) if sections else ""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>{brand_css(brand)}</style>
{extra_head}
</head>
<body>
{render_header(brand, title)}
<main class="report-container">
{toc}
{sections_html}
</main>
{render_footer(brand)}
</body>
</html>"""

    report_path.write_text(html, encoding="utf-8")
    return str(report_path)


# ── Append section ────────────────────────────────────────────────

def append_section(report_path: str, section_html: str,
                   extra_head: str = "") -> str:
    """Append a section to an existing report before </main>.

    Also regenerates the table of contents. If a section with the same ID
    already exists, it is replaced.

    Args:
        report_path: Path to existing HTML report.
        section_html: Section HTML (from render_section_wrapper).
        extra_head: Extra HTML to inject into <head> if not already present.

    Returns:
        Path to the updated report.
    """
    path = Path(report_path)
    if not path.exists():
        raise FileNotFoundError(f"Report not found: {report_path}")

    html = path.read_text(encoding="utf-8")

    # Extract section ID from new section
    id_match = re.search(r'<!-- BEGIN_SECTION:(\S+) -->', section_html)
    if id_match:
        sid = id_match.group(1)
        # Remove existing section with same ID (replace mode)
        pattern = rf'<!-- BEGIN_SECTION:{re.escape(sid)} -->.*?<!-- END_SECTION:{re.escape(sid)} -->\n?'
        html = re.sub(pattern, '', html, flags=re.DOTALL)

    # Insert before </main>
    html = html.replace('</main>', f'{section_html}\n</main>')

    # Inject extra_head into <head> if not already present
    if extra_head and extra_head.strip():
        # Check if already present (e.g., D3 script)
        check_str = extra_head.strip()[:60]
        if check_str not in html:
            html = html.replace('</head>', f'{extra_head}\n</head>')

    # Regenerate TOC
    toc = _build_toc(html)
    toc_pattern = r'<nav class="report-toc">.*?</nav>'
    if re.search(toc_pattern, html, re.DOTALL):
        html = re.sub(toc_pattern, toc, html, flags=re.DOTALL)
    elif toc:
        # Insert TOC after report-container opening
        html = html.replace(
            '<main class="report-container">\n',
            f'<main class="report-container">\n{toc}\n'
        )

    path.write_text(html, encoding="utf-8")
    return str(path)


# ── List reports ──────────────────────────────────────────────────

def list_reports() -> list[dict]:
    """Scan reports/ directory and return metadata for each report.

    Returns:
        List of dicts with keys: path, title, date, sections.
    """
    reports_dir = _reports_dir()
    results = []

    for f in sorted(reports_dir.glob("*.html"), reverse=True):
        html = f.read_text(encoding="utf-8")

        # Extract title
        title_match = re.search(r'<title>(.*?)</title>', html)
        title = title_match.group(1) if title_match else f.stem

        # Extract date from header
        date_match = re.search(r'class="brand-date">([\d-]+)</span>', html)
        report_date = date_match.group(1) if date_match else ""

        # Count sections
        section_ids = re.findall(r'<!-- BEGIN_SECTION:(\S+) -->', html)

        results.append({
            "path": str(f),
            "filename": f.name,
            "title": title,
            "date": report_date,
            "sections": section_ids,
            "section_count": len(section_ids),
        })

    return results


# ── Helpers for skill renderers ───────────────────────────────────

def make_section_id(skill_slug: str) -> str:
    """Generate a unique section ID with timestamp."""
    now = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{skill_slug}-{now}"


def html_table(headers: list[str], rows: list[list[str]],
               class_name: str = "brand-table") -> str:
    """Build an HTML table string from headers and rows."""
    ths = "".join(f"<th>{h}</th>" for h in headers)
    trs = ""
    for row in rows:
        tds = "".join(f"<td>{c}</td>" for c in row)
        trs += f"<tr>{tds}</tr>\n"
    return f"""<table class="{class_name}">
<thead><tr>{ths}</tr></thead>
<tbody>
{trs}</tbody>
</table>"""


def summary_card(items: list[tuple[str, str]]) -> str:
    """Build a summary grid with stat cards.

    Args:
        items: List of (value, label) tuples.
    """
    cards = ""
    for value, label in items:
        cards += f"""<div class="summary-stat">
  <div class="stat-value">{value}</div>
  <div class="stat-label">{label}</div>
</div>\n"""
    return f'<div class="summary-grid">\n{cards}</div>'


def bar_chart(items: list[tuple[str, float, str]], max_val: float = 0) -> str:
    """Build a horizontal bar chart.

    Args:
        items: List of (label, value, display_text) tuples.
        max_val: Maximum value for scaling. 0 = auto from data.
    """
    if not items:
        return ""
    if max_val <= 0:
        max_val = max(v for _, v, _ in items) or 1
    rows = ""
    for label, value, display in items:
        pct = min(value / max_val * 100, 100)
        rows += f"""<div class="bar-row">
  <span class="bar-label">{label}</span>
  <div class="bar-track"><div class="bar-fill" style="width:{pct:.1f}%"></div></div>
  <span class="bar-value">{display}</span>
</div>\n"""
    return f'<div class="bar-chart">\n{rows}</div>'


def badge(text: str, variant: str = "info") -> str:
    """Render an inline badge. Variants: success, warning, error, info."""
    return f'<span class="brand-badge brand-badge-{variant}">{text}</span>'


# ── CLI ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="SEO Skills HTML Report Builder")
    sub = parser.add_subparsers(dest="command", required=True)

    # create
    p_create = sub.add_parser("create", help="Create a new report")
    p_create.add_argument("--title", required=True, help="Report title")
    p_create.add_argument("--section-file", help="HTML file with initial section")

    # append
    p_append = sub.add_parser("append", help="Append a section to an existing report")
    p_append.add_argument("--report", required=True, help="Path to existing report HTML")
    p_append.add_argument("--section-file", required=True, help="HTML file with section to append")

    # list
    sub.add_parser("list", help="List all reports in reports/")

    args = parser.parse_args()

    if args.command == "create":
        sections = []
        if args.section_file:
            sections.append(Path(args.section_file).read_text(encoding="utf-8"))
        path = create_report(args.title, sections=sections)
        print(f"Created: {path}")

    elif args.command == "append":
        section_html = Path(args.section_file).read_text(encoding="utf-8")
        path = append_section(args.report, section_html)
        print(f"Updated: {path}")

    elif args.command == "list":
        reports = list_reports()
        if not reports:
            print("No reports found in reports/")
            return
        print(f"{'File':<45} {'Title':<30} {'Date':<12} {'Sections':>8}")
        print("-" * 100)
        for r in reports:
            print(f"{r['filename']:<45} {r['title'][:30]:<30} {r['date']:<12} {r['section_count']:>8}")


if __name__ == "__main__":
    main()
