#!/usr/bin/env python3
"""Branding helper — loads brand-config.json for HTML report generation.

Usage:
    from branding import load_brand, render_header, render_footer, brand_css

    brand = load_brand()
    html = f'''
    <html><head><style>{brand_css(brand)}</style></head>
    <body>
    {render_header(brand, "SERP Cluster Report")}
    ... report content ...
    {render_footer(brand)}
    </body></html>
    '''
"""

import json
import os
from datetime import date
from pathlib import Path
from typing import Optional

# ── Defaults ─────────────────────────────────────────────────────────

DEFAULTS = {
    "company": {"name": "Nodeshub SEO Skills", "url": "", "tagline": ""},
    "logo": {"light": "", "dark": "", "fallback_text": True},
    "colors": {
        "primary": "#3B82F6",
        "primary_light": "#60A5FA",
        "secondary": "#10B981",
        "background": "#FFFFFF",
        "background_dark": "#0F172A",
        "background_card": "#F8FAFC",
        "text_primary": "#1E293B",
        "text_secondary": "#64748B",
        "text_muted": "#94A3B8",
        "border": "#E2E8F0",
        "success": "#22C55E",
        "warning": "#F59E0B",
        "error": "#EF4444",
    },
    "gradients": {
        "primary": "linear-gradient(135deg, #3B82F6 0%, #60A5FA 100%)",
        "header": "linear-gradient(90deg, #0F172A 0%, #1E293B 100%)",
    },
    "typography": {
        "font_family": "Inter, system-ui, -apple-system, sans-serif",
        "font_family_mono": "JetBrains Mono, monospace",
        "heading_weight": "700",
        "body_weight": "400",
    },
    "report": {
        "show_logo": True,
        "show_footer": True,
        "footer_text": "Generated with Nodeshub SEO Skills",
        "date_format": "YYYY-MM-DD",
    },
}


def _find_brand_config() -> Optional[Path]:
    """Walk up from CWD looking for assets/branding/brand-config.json."""
    current = Path.cwd()
    for _ in range(6):  # max 6 levels up
        candidate = current / "assets" / "branding" / "brand-config.json"
        if candidate.exists():
            return candidate
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None


def _deep_merge(base: dict, override: dict) -> dict:
    """Merge override into base, preserving nested keys."""
    result = base.copy()
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def load_brand() -> dict:
    """Load brand config, falling back to defaults for missing keys."""
    config_path = _find_brand_config()
    if config_path is None:
        return DEFAULTS.copy()
    try:
        with open(config_path) as f:
            user_config = json.load(f)
        return _deep_merge(DEFAULTS, user_config)
    except (json.JSONDecodeError, IOError):
        return DEFAULTS.copy()


def _resolve_logo(brand: dict, variant: str = "dark") -> str:
    """Return logo <img> tag (base64-embedded) or company name text."""
    import base64
    logo_path = brand.get("logo", {}).get(variant, "")
    if logo_path and os.path.exists(logo_path):
        try:
            with open(logo_path, "rb") as f:
                data = f.read()
            ext = Path(logo_path).suffix.lstrip(".")
            mime = "image/svg+xml" if ext == "svg" else f"image/{ext}"
            b64 = base64.b64encode(data).decode()
            return f'<img src="data:{mime};base64,{b64}" alt="{brand["company"]["name"]}" style="height:32px;">'
        except IOError:
            pass
    if brand.get("logo", {}).get("fallback_text", True):
        return f'<span class="brand-logo-text">{brand["company"]["name"]}</span>'
    return ""


def brand_css(brand: dict) -> str:
    """Generate CSS variables and base styles from brand config."""
    c = brand["colors"]
    t = brand["typography"]
    g = brand.get("gradients", DEFAULTS["gradients"])

    return f"""
:root {{
  --brand-primary: {c['primary']};
  --brand-primary-light: {c['primary_light']};
  --brand-secondary: {c['secondary']};
  --brand-bg: {c['background']};
  --brand-bg-dark: {c['background_dark']};
  --brand-bg-card: {c['background_card']};
  --brand-text: {c['text_primary']};
  --brand-text-secondary: {c['text_secondary']};
  --brand-text-muted: {c['text_muted']};
  --brand-border: {c['border']};
  --brand-success: {c['success']};
  --brand-warning: {c['warning']};
  --brand-error: {c['error']};
  --brand-gradient-primary: {g['primary']};
  --brand-gradient-header: {g['header']};
  --brand-font: {t['font_family']};
  --brand-font-mono: {t['font_family_mono']};
}}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
  font-family: var(--brand-font);
  font-weight: {t['body_weight']};
  color: var(--brand-text);
  background: var(--brand-bg);
  line-height: 1.6;
}}
h1, h2, h3, h4 {{ font-weight: {t['heading_weight']}; line-height: 1.3; }}
.report-section h3, .report-section h4 {{ margin-top: 28px; margin-bottom: 12px; }}
.report-section h3:first-child, .report-section h4:first-child {{ margin-top: 0; }}
.report-section ul, .report-section ol {{ padding-left: 24px; margin: 8px 0; }}
.report-section li {{ padding: 2px 0; }}
.brand-header {{
  background: var(--brand-gradient-header);
  color: #fff;
  padding: 20px 32px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}}
.brand-header .brand-logo-text {{
  font-size: 18px;
  font-weight: 700;
  letter-spacing: -0.02em;
}}
.brand-header .brand-title {{
  font-size: 22px;
  font-weight: 600;
}}
.brand-header .brand-date {{
  font-size: 13px;
  opacity: 0.7;
}}
.brand-footer {{
  border-top: 1px solid var(--brand-border);
  padding: 16px 32px;
  font-size: 12px;
  color: var(--brand-text-muted);
  display: flex;
  justify-content: space-between;
}}
.brand-card {{
  background: var(--brand-bg-card);
  border: 1px solid var(--brand-border);
  border-radius: 8px;
  padding: 20px;
}}
.brand-table {{
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
}}
.brand-table th {{
  background: var(--brand-bg-card);
  border-bottom: 2px solid var(--brand-border);
  padding: 10px 12px;
  text-align: left;
  font-weight: 600;
}}
.brand-table td {{
  border-bottom: 1px solid var(--brand-border);
  padding: 8px 12px;
}}
.brand-table tr:hover {{ background: var(--brand-bg-card); }}
.brand-badge {{
  display: inline-block;
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
}}
.brand-badge-success {{ background: {c['success']}22; color: {c['success']}; }}
.brand-badge-warning {{ background: {c['warning']}22; color: {c['warning']}; }}
.brand-badge-error {{ background: {c['error']}22; color: {c['error']}; }}
.brand-badge-info {{ background: {c['primary']}22; color: {c['primary']}; }}
/* ── Report layout ────────────────────────────────── */
.report-container {{
  max-width: 1200px;
  margin: 0 auto;
  padding: 24px 32px;
}}
.report-toc {{
  background: var(--brand-bg-card);
  border: 1px solid var(--brand-border);
  border-radius: 8px;
  padding: 16px 24px;
  margin: 24px 0;
}}
.report-toc h3 {{
  font-size: 14px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--brand-text-secondary);
  margin-bottom: 8px;
}}
.report-toc ol {{
  list-style: decimal;
  padding-left: 20px;
  margin: 0;
}}
.report-toc li {{
  padding: 4px 0;
  font-size: 14px;
}}
.report-toc a {{
  color: var(--brand-primary);
  text-decoration: none;
}}
.report-toc a:hover {{
  text-decoration: underline;
}}
.report-section {{
  margin: 32px 0;
  padding: 24px 0;
  border-top: 1px solid var(--brand-border);
}}
.report-section:first-of-type {{
  border-top: none;
}}
.section-header {{
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}}
.section-header h2 {{
  font-size: 20px;
  color: var(--brand-text);
}}
.section-header .section-skill {{
  font-size: 12px;
  color: var(--brand-text-muted);
  background: var(--brand-bg-card);
  border: 1px solid var(--brand-border);
  border-radius: 4px;
  padding: 2px 8px;
}}
.summary-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 16px;
  margin-bottom: 24px;
}}
.summary-stat {{
  background: var(--brand-bg-card);
  border: 1px solid var(--brand-border);
  border-radius: 8px;
  padding: 16px;
  text-align: center;
}}
.summary-stat .stat-value {{
  font-size: 28px;
  font-weight: 700;
  color: var(--brand-primary);
  line-height: 1.2;
}}
.summary-stat .stat-label {{
  font-size: 12px;
  color: var(--brand-text-secondary);
  margin-top: 4px;
}}
.bar-chart {{
  margin: 16px 0;
}}
.bar-chart .bar-row {{
  display: flex;
  align-items: center;
  margin: 6px 0;
  font-size: 13px;
}}
.bar-chart .bar-label {{
  width: 140px;
  text-align: right;
  padding-right: 12px;
  color: var(--brand-text-secondary);
  flex-shrink: 0;
}}
.bar-chart .bar-track {{
  flex: 1;
  height: 20px;
  background: var(--brand-bg-card);
  border-radius: 4px;
  overflow: hidden;
}}
.bar-chart .bar-fill {{
  height: 100%;
  background: var(--brand-gradient-primary);
  border-radius: 4px;
  min-width: 2px;
}}
.bar-chart .bar-value {{
  width: 50px;
  padding-left: 8px;
  font-weight: 600;
  font-size: 12px;
  color: var(--brand-text);
}}
/* ── Score gauge ──────────────────────────────────── */
.score-gauge {{
  display: inline-flex;
  align-items: center;
  gap: 12px;
  padding: 12px 20px;
  border-radius: 8px;
  font-size: 24px;
  font-weight: 700;
}}
.score-gauge.score-low {{ background: {c['error']}15; color: {c['error']}; }}
.score-gauge.score-mid {{ background: {c['warning']}15; color: {c['warning']}; }}
.score-gauge.score-high {{ background: {c['success']}15; color: {c['success']}; }}
/* ── Change indicators ────────────────────────────── */
.change-up {{ color: {c['success']}; font-weight: 600; }}
.change-down {{ color: {c['error']}; font-weight: 600; }}
.change-stable {{ color: var(--brand-text-muted); }}
/* ── Responsive ──────────────────────────────────── */
@media (max-width: 768px) {{
  .report-container {{ padding: 16px; }}
  .brand-header {{ padding: 16px; flex-wrap: wrap; gap: 8px; }}
  .brand-header .brand-title {{ font-size: 18px; }}
  .brand-footer {{ padding: 12px 16px; flex-wrap: wrap; gap: 4px; }}
  .section-header {{ flex-wrap: wrap; gap: 8px; }}
  .section-header h2 {{ font-size: 18px; }}
  .summary-grid {{ grid-template-columns: repeat(2, 1fr); gap: 10px; }}
  .summary-stat {{ padding: 12px; }}
  .summary-stat .stat-value {{ font-size: 22px; }}
  .brand-table {{ font-size: 13px; }}
  .brand-table th, .brand-table td {{ padding: 6px 8px; }}
  .bar-chart .bar-label {{ width: 100px; font-size: 12px; }}
}}
@media (max-width: 480px) {{
  .report-container {{ padding: 12px; }}
  .summary-grid {{ grid-template-columns: 1fr 1fr; gap: 8px; }}
  .summary-stat .stat-value {{ font-size: 18px; }}
  .brand-table {{ display: block; overflow-x: auto; -webkit-overflow-scrolling: touch; }}
  .bar-chart .bar-label {{ width: 80px; }}
}}
"""


def render_header(brand: dict, title: str) -> str:
    """Render branded HTML header with logo, title, and date."""
    logo_html = _resolve_logo(brand, "light")
    today = date.today().isoformat()
    return f"""<header class="brand-header">
  <div style="display:flex;align-items:center;gap:16px;">
    {logo_html}
    <span class="brand-title">{title}</span>
  </div>
  <span class="brand-date">{today}</span>
</header>"""


def render_footer(brand: dict) -> str:
    """Render branded HTML footer."""
    r = brand.get("report", DEFAULTS["report"])
    if not r.get("show_footer", True):
        return ""
    footer_text = r.get("footer_text", DEFAULTS["report"]["footer_text"])
    today = date.today().isoformat()
    company = brand["company"]["name"]
    url = brand["company"].get("url", "")
    company_html = f'<a href="{url}" style="color:inherit;">{company}</a>' if url else company
    return f"""<footer class="brand-footer">
  <span>{company_html}</span>
  <span>{footer_text} &middot; {today}</span>
</footer>"""


if __name__ == "__main__":
    brand = load_brand()
    print(f"Company: {brand['company']['name']}")
    print(f"Primary color: {brand['colors']['primary']}")
    print(f"Font: {brand['typography']['font_family']}")
    config_path = _find_brand_config()
    print(f"Config: {config_path or 'using defaults'}")
