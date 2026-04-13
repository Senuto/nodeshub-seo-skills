#!/usr/bin/env python3
"""
Genuino AI Detection — analyze text for AI-generated content.

Usage:
    python3 analyze.py --text "Your text here (min 200 words)"
    python3 analyze.py --file article.txt
    python3 analyze.py --file article.txt --guidelines --humanize
    python3 analyze.py --url "https://example.com/article" (requires Jina)
"""

import argparse
import json
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'nod-nodeshub-api' / 'scripts'))
from report import render_section_wrapper, make_section_id, summary_card, badge

API_URL = "https://api.genuino.ai/v1/analyze"

_SETTINGS_CANDIDATES = [
    Path(".claude/settings.local.json"),
    Path(__file__).resolve().parents[4] / ".claude" / "settings.local.json",
    Path.home() / ".claude" / "settings.local.json",
]


def load_api_key():
    """Load GENUINO_API_KEY from environment or settings files."""
    key = os.environ.get("GENUINO_API_KEY")
    if key:
        return key

    for path in _SETTINGS_CANDIDATES:
        if path.is_file():
            try:
                data = json.loads(path.read_text())
                key = data.get("env", {}).get("GENUINO_API_KEY")
                if key:
                    return key
            except (json.JSONDecodeError, OSError):
                continue

    return None


def analyze(text, api_key, include_guidelines=False, include_humanization=False):
    """Send text to Genuino API for AI detection analysis."""
    payload = {
        "text": text,
        "include_guidelines": include_guidelines,
        "include_humanization_prompt": include_humanization,
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(API_URL, data=data)
    req.add_header("X-API-Key", api_key)
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "genuino-claude-skill/0.1")

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8") if e.fp else ""
        print(f"[ERROR] HTTP {e.code}: {body}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"[ERROR] Connection failed: {e.reason}", file=sys.stderr)
        sys.exit(1)


def read_text_from_url(url):
    """Fetch article text via Jina Reader API (if available)."""
    jina_key = None
    for path in _SETTINGS_CANDIDATES:
        if path.is_file():
            try:
                data = json.loads(path.read_text())
                jina_key = data.get("env", {}).get("JINA_API_KEY")
                if jina_key:
                    break
            except (json.JSONDecodeError, OSError):
                continue

    jina_url = f"https://r.jina.ai/{url}"
    req = urllib.request.Request(jina_url)
    req.add_header("X-Return-Format", "text")
    req.add_header("User-Agent", "genuino-claude-skill/0.1")
    if jina_key:
        req.add_header("Authorization", f"Bearer {jina_key}")

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8")
    except (urllib.error.HTTPError, urllib.error.URLError) as e:
        print(f"[ERROR] Failed to fetch URL via Jina: {e}", file=sys.stderr)
        sys.exit(1)


def format_result(result):
    """Format analysis result for terminal output."""
    r = result.get("analysis_result", {})

    classification = r.get("classification", "UNKNOWN")
    probability = r.get("probability_ai_percent", 0)
    style = r.get("style_name", "Unknown")
    style_confidence = r.get("style_confidence", 0)
    style_desc = r.get("style_description", "")

    # Score bar
    bar_len = 30
    filled = int(probability / 100 * bar_len)
    bar = "█" * filled + "░" * (bar_len - filled)

    lines = [
        "",
        f"  Classification:  {classification}",
        f"  AI Probability:  {probability:.1f}% [{bar}]",
        f"  Writing Style:   {style} (confidence: {style_confidence:.0%})",
    ]

    if style_desc:
        lines.append(f"  Style Detail:    {style_desc}")

    threshold = r.get("decision_threshold")
    margin = r.get("decision_margin")
    if threshold is not None:
        lines.append(f"  Threshold:       {threshold:.3f} (margin: {margin:.3f})")

    lines.append(f"  Analysis ID:     {result.get('analysis_id', 'N/A')}")

    # Guidelines
    guidelines = r.get("guidelines", [])
    if guidelines:
        lines.append("")
        lines.append("  Guidelines to humanize:")
        for g in sorted(guidelines, key=lambda x: x.get("priority", 99)):
            name = g.get("friendly_name", g.get("name", ""))
            weight = g.get("weight", 0)
            lines.append(f"    • {name} (weight: {weight})")
            for instr in g.get("instructions", []):
                lines.append(f"      → {instr}")

    # Humanization prompt
    humanization = r.get("humanization_prompt")
    if humanization:
        lines.append("")
        lines.append("  Humanization prompt:")
        lines.append(f"    {humanization}")

    # Copywriter rules
    rules = r.get("copywriter_rules_block")
    if rules:
        lines.append("")
        lines.append("  Copywriter rules:")
        for line in rules.strip().split("\n"):
            lines.append(f"    {line}")

    lines.append("")
    return "\n".join(lines)


def render_report_section(data):
    """Convert AI score analysis data into an HTML report section.

    Args:
        data: Genuino API response dict with analysis_result.
    """
    from html import escape as e
    parts = []
    r = data.get("analysis_result", {})

    probability = r.get("probability_ai_percent", 0)
    classification = r.get("classification", "UNKNOWN")
    style = r.get("style_name", "Unknown")
    style_desc = r.get("style_description", "")

    # Score gauge (low AI = good for human content)
    if probability < 30:
        gauge_class = "score-high"
    elif probability < 70:
        gauge_class = "score-mid"
    else:
        gauge_class = "score-low"

    parts.append(f'<div class="score-gauge {gauge_class}">'
                 f'{probability:.1f}% AI Probability</div>')
    parts.append(f'<p style="margin-top:8px"><strong>Classification:</strong> {e(classification)}</p>')

    parts.append(summary_card([
        (f"{probability:.1f}%", "AI Probability"),
        (e(classification), "Classification"),
        (e(style), "Writing Style"),
    ]))

    if style_desc:
        parts.append(f"<p><strong>Style Detail:</strong> {e(style_desc)}</p>")

    # Guidelines
    guidelines = r.get("guidelines", [])
    if guidelines:
        items = ""
        for g in sorted(guidelines, key=lambda x: x.get("priority", 99)):
            name = e(g.get("friendly_name", g.get("name", "")))
            weight = g.get("weight", 0)
            instrs = "".join(f"<li>{e(i)}</li>" for i in g.get("instructions", []))
            items += f"<li><strong>{name}</strong> (weight: {weight})"
            if instrs:
                items += f"<ul>{instrs}</ul>"
            items += "</li>"
        parts.append(f"<h3>Humanization Guidelines</h3>\n<ul>{items}</ul>")

    # Humanization prompt
    humanization = r.get("humanization_prompt")
    if humanization:
        parts.append(f'<h3>Humanization Prompt</h3>\n'
                     f'<div class="brand-card"><pre style="white-space:pre-wrap;font-size:13px">'
                     f'{e(humanization)}</pre></div>')

    sid = make_section_id("ai-score")
    return render_section_wrapper(sid, "AI Score",
                                  "AI Content Detection", "\n".join(parts))


def main():
    parser = argparse.ArgumentParser(description="Genuino AI Detection — analyze text")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--text", help="Text to analyze (min 200 words)")
    group.add_argument("--file", help="Path to text file to analyze")
    group.add_argument("--url", help="URL to fetch and analyze (uses Jina Reader)")

    parser.add_argument("--guidelines", action="store_true", help="Include humanization guidelines (2 extra credits)")
    parser.add_argument("--humanize", action="store_true", help="Include humanization prompt (2 extra credits)")
    parser.add_argument("--json", action="store_true", help="Output raw JSON response")

    args = parser.parse_args()

    api_key = load_api_key()
    if not api_key:
        print("[ERROR] GENUINO_API_KEY not found.", file=sys.stderr)
        print("Run /connect-genuino to set up the API key.", file=sys.stderr)
        sys.exit(1)

    # Get text
    if args.text:
        text = args.text
    elif args.file:
        path = Path(args.file)
        if not path.is_file():
            print(f"[ERROR] File not found: {args.file}", file=sys.stderr)
            sys.exit(1)
        text = path.read_text(encoding="utf-8")
    elif args.url:
        text = read_text_from_url(args.url)

    # Word count check
    word_count = len(text.split())
    if word_count < 200:
        print(f"[ERROR] Text too short: {word_count} words (minimum 200).", file=sys.stderr)
        sys.exit(1)

    print(f"Analyzing {word_count} words...")

    result = analyze(
        text=text,
        api_key=api_key,
        include_guidelines=args.guidelines,
        include_humanization=args.humanize,
    )

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(format_result(result))


if __name__ == "__main__":
    main()
