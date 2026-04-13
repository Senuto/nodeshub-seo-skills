#!/usr/bin/env python3
"""
Keyword to Publish Pipeline — keyword → research → brief → article → AI check → audit.

Orchestrates 6 steps:
  1. Keyword Research (iterative SERP mining)
  2. SERP Analysis (top 10 competitors)
  3. Content Brief (data-driven brief)
  4. Write Article (LLM via OpenRouter)
  5. AI Score Check + Humanization loop
  6. Content Audit vs Competition

Each step saves output to data/articles/[slug]/ — resumable from any step.

Usage:
  python3 pipeline.py "pozycjonowanie stron" --gl pl --hl pl
  python3 pipeline.py "SEO tools" --gl us --hl en --skip-to 4
  python3 pipeline.py "content marketing" --gl pl --hl pl --lang Polish
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

SKILLS_DIR = Path(__file__).resolve().parents[2]
NODESHUB_SCRIPTS = SKILLS_DIR / "nod-nodeshub-api" / "scripts"
KW_RESEARCH_SCRIPT = SKILLS_DIR / "nod-keyword-research" / "scripts" / "iterative_research.py"
SERP_ANALYSIS_SCRIPT = SKILLS_DIR / "nod-serp-analysis" / "scripts" / "analyze_serp.py"
CONTENT_BRIEF_SCRIPT = SKILLS_DIR / "nod-content-brief" / "scripts" / "research.py"
AI_SCORE_SCRIPT = SKILLS_DIR / "ai-score" / "scripts" / "analyze.py"
CONTENT_AUDIT_SCRIPT = SKILLS_DIR / "nod-content-auditor" / "scripts" / "audit.py"
HUMANIZER_SCRIPT = Path(__file__).resolve().parents[1] / ".." / "content-humanizer" / "scripts" / "pipeline.py"

sys.path.insert(0, str(NODESHUB_SCRIPTS))


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower().strip()).strip("-")[:50]


def run_step(cmd, step_name, capture=False):
    """Run a subprocess and stream or capture output."""
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"  STEP: {step_name}", file=sys.stderr)
    print(f"{'='*60}\n", file=sys.stderr)

    if capture:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"  WARNING: {step_name} exited with code {result.returncode}", file=sys.stderr)
            if result.stderr:
                print(f"  {result.stderr[:500]}", file=sys.stderr)
        return result
    else:
        result = subprocess.run(cmd, capture_output=False, text=True)
        if result.returncode != 0:
            print(f"  WARNING: {step_name} exited with code {result.returncode}", file=sys.stderr)
            return None
        return True


def parse_json_output(text):
    """Extract JSON from command output (may have non-JSON lines)."""
    for line in text.strip().split("\n"):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def write_article_with_llm(brief_text, keyword, lang, serp_data=None):
    """Write a full article using OpenRouter LLM based on the content brief."""
    from openrouter_client import OpenRouterClient
    llm = OpenRouterClient()

    serp_context = ""
    if serp_data:
        top_titles = [r.get("title", "") for r in serp_data.get("organic_results", [])[:5]]
        features = serp_data.get("serp_features", [])
        paa = serp_data.get("paa_questions", [])[:5]
        serp_context = f"""
Top ranking titles: {', '.join(top_titles)}
SERP features: {', '.join(features)}
People Also Ask: {', '.join(paa)}
"""

    prompt = f"""Write a comprehensive, publish-ready article based on the content brief below.

RULES:
1. Follow the brief structure exactly (headings, sections)
2. Write naturally — vary sentence length, use conversational transitions
3. Avoid AI patterns: "It's important to note," "Furthermore," "In conclusion,"
   "In today's world," perfectly parallel structures
4. Include keywords naturally — never force them
5. Answer any PAA questions within the content
6. Write in {lang}
7. Use markdown formatting (# H1, ## H2, ### H3, bullet points, bold)
8. Target the word count suggested in the brief
9. Be specific and practical — use examples, data, comparisons
10. Do NOT add meta-commentary — output ONLY the article

{f"SERP CONTEXT:{serp_context}" if serp_context else ""}

CONTENT BRIEF:

{brief_text}"""

    try:
        article = llm.chat(
            prompt,
            model="google/gemini-2.5-flash-lite",
            temperature=0.5,
            max_tokens=8000,
        )
        return article
    except Exception as e:
        print(f"  LLM error: {e}", file=sys.stderr)
        return None


def main():
    parser = argparse.ArgumentParser(description="Keyword to Publish Pipeline")
    parser.add_argument("keyword", help="Seed keyword / topic")
    parser.add_argument("--gl", default="pl", help="Country code (default: pl)")
    parser.add_argument("--hl", default="pl", help="Language code (default: pl)")
    parser.add_argument("--lang", default=None,
                        help="Article language (default: auto from --hl)")
    parser.add_argument("--output-dir", help="Output directory (default: data/articles/[slug]/)")
    parser.add_argument("--skip-to", type=int, default=1, choices=[1, 2, 3, 4, 5, 6],
                        help="Skip to step N (requires previous step outputs)")
    # Step 1 params
    parser.add_argument("--kw-loops", type=int, default=2, help="Keyword research loops (default: 2)")
    parser.add_argument("--kw-serp-per-loop", type=int, default=3, help="SERPs per loop (default: 3)")
    # Step 5 params
    parser.add_argument("--ai-threshold", type=float, default=30.0,
                        help="Max acceptable AI score (default: 30%%)")
    parser.add_argument("--ai-max-iter", type=int, default=3,
                        help="Max humanization iterations (default: 3)")
    args = parser.parse_args()

    # Auto-detect language from hl
    lang_map = {"pl": "Polish", "en": "English", "de": "German", "fr": "French",
                "es": "Spanish", "it": "Italian", "pt": "Portuguese", "nl": "Dutch"}
    lang = args.lang or lang_map.get(args.hl, "English")

    slug = slugify(args.keyword)
    output_dir = Path(args.output_dir) if args.output_dir else Path(f"data/articles/{slug}")
    output_dir.mkdir(parents=True, exist_ok=True)

    # File paths
    kw_csv = output_dir / "01_keywords.csv"
    serp_json = output_dir / "02_serp_analysis.json"
    brief_md = output_dir / "03_brief.md"
    article_md = output_dir / "04_article.md"
    article_final = output_dir / "05_article_final.md"
    audit_json = output_dir / "06_audit.json"

    print(f"{'='*60}", file=sys.stderr)
    print(f"  KEYWORD TO PUBLISH PIPELINE", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)
    print(f"  Keyword: {args.keyword}", file=sys.stderr)
    print(f"  Market: gl={args.gl}, hl={args.hl}", file=sys.stderr)
    print(f"  Language: {lang}", file=sys.stderr)
    print(f"  Output: {output_dir}/", file=sys.stderr)
    print(f"  Skip to step: {args.skip_to}", file=sys.stderr)
    print(f"{'='*60}\n", file=sys.stderr)

    # ── STEP 1: Keyword Research ──
    if args.skip_to <= 1:
        cmd = [
            sys.executable, str(KW_RESEARCH_SCRIPT),
            args.keyword,
            "--gl", args.gl, "--hl", args.hl,
            "--loops", str(args.kw_loops),
            "--serp-per-loop", str(args.kw_serp_per_loop),
            "--expand-popular", "2",
            "--output", str(kw_csv),
            "--json",
        ]
        if not run_step(cmd, "Keyword Research"):
            print("Step 1 failed. Fix and rerun, or --skip-to 2.", file=sys.stderr)
            sys.exit(1)
    else:
        if not kw_csv.exists():
            print(f"  Skipping step 1 — {kw_csv} not found (non-critical)", file=sys.stderr)

    if kw_csv.exists():
        with open(kw_csv) as f:
            kw_count = sum(1 for _ in f) - 1
        print(f"\n  Keywords: {kw_count}", file=sys.stderr)

    # ── STEP 2: SERP Analysis ──
    if args.skip_to <= 2:
        cmd = [
            sys.executable, str(SERP_ANALYSIS_SCRIPT),
            args.keyword,
            "--gl", args.gl, "--hl", args.hl,
        ]
        result = run_step(cmd, "SERP Analysis", capture=True)
        if result and result.stdout:
            serp_data = parse_json_output(result.stdout)
            if serp_data:
                serp_json.write_text(json.dumps(serp_data, indent=2, ensure_ascii=False))
                print(f"  Saved: {serp_json}", file=sys.stderr)
                organic = serp_data.get("organic_results", [])
                print(f"  Top 10: {len(organic)} results", file=sys.stderr)
                features = serp_data.get("serp_features", [])
                print(f"  SERP features: {', '.join(features) if features else 'none'}", file=sys.stderr)
    else:
        if not serp_json.exists():
            print(f"  Skipping step 2 — {serp_json} not found (non-critical)", file=sys.stderr)

    # Load SERP data for later steps
    serp_data = None
    if serp_json.exists():
        serp_data = json.loads(serp_json.read_text())

    # ── STEP 3: Content Brief ──
    if args.skip_to <= 3:
        cmd = [
            sys.executable, str(CONTENT_BRIEF_SCRIPT),
            args.keyword,
            "--gl", args.gl, "--hl", args.hl,
            "--json",
        ]
        result = run_step(cmd, "Content Brief", capture=True)
        if result and result.stdout:
            brief_data = parse_json_output(result.stdout)
            if brief_data:
                # Build markdown brief from the data
                brief_parts = [f"# Content Brief: {args.keyword}\n"]

                if brief_data.get("dominant_intent"):
                    brief_parts.append(f"**Intent:** {brief_data['dominant_intent']}\n")

                # Related keywords
                related = brief_data.get("related_queries", [])
                if related:
                    brief_parts.append("## Target Keywords")
                    brief_parts.append(", ".join(related[:20]) + "\n")

                # PAA questions
                paa = brief_data.get("paa_questions", [])
                if paa:
                    brief_parts.append("## Questions to Answer")
                    for q in paa:
                        brief_parts.append(f"- {q}")
                    brief_parts.append("")

                # Top results for context
                organic = brief_data.get("organic_results", [])
                if organic:
                    brief_parts.append("## Competitor Analysis")
                    for r in organic[:5]:
                        brief_parts.append(f"- #{r.get('pos', '?')}: {r.get('title', '')} ({r.get('domain', '')})")
                    brief_parts.append("")

                brief_parts.append("## Suggested Structure")
                brief_parts.append("- H1: [Based on keyword and intent]")
                brief_parts.append("- H2 sections covering main subtopics")
                brief_parts.append("- Answer PAA questions as H2/H3 sections")
                brief_parts.append(f"- Target word count: 1500-2500 words")
                brief_parts.append(f"- Language: {lang}\n")

                brief_md.write_text("\n".join(brief_parts), encoding="utf-8")
                print(f"  Saved: {brief_md}", file=sys.stderr)
    else:
        if not brief_md.exists():
            print(f"ERROR: {brief_md} not found. Run step 3 first.", file=sys.stderr)
            sys.exit(1)

    # ── STEP 4: Write Article ──
    if args.skip_to <= 4:
        print(f"\n{'='*60}", file=sys.stderr)
        print(f"  STEP: Write Article", file=sys.stderr)
        print(f"{'='*60}\n", file=sys.stderr)

        if not brief_md.exists():
            print(f"ERROR: No brief found at {brief_md}. Run step 3 first.", file=sys.stderr)
            sys.exit(1)

        brief_text = brief_md.read_text(encoding="utf-8")
        print(f"  Generating article via LLM...", file=sys.stderr)

        article = write_article_with_llm(brief_text, args.keyword, lang, serp_data)
        if not article:
            print(f"  Article generation failed.", file=sys.stderr)
            sys.exit(1)

        article_md.write_text(article, encoding="utf-8")
        word_count = len(article.split())
        print(f"  Saved: {article_md} ({word_count} words)", file=sys.stderr)
    else:
        if not article_md.exists():
            print(f"ERROR: {article_md} not found. Run step 4 first.", file=sys.stderr)
            sys.exit(1)

    # ── STEP 5: AI Score + Humanization ──
    if args.skip_to <= 5:
        print(f"\n{'='*60}", file=sys.stderr)
        print(f"  STEP: AI Score Check + Humanization", file=sys.stderr)
        print(f"{'='*60}\n", file=sys.stderr)

        humanizer_script = SKILLS_DIR.parent / "agents" / "content-humanizer" / "scripts" / "pipeline.py"

        cmd = [
            sys.executable, str(humanizer_script),
            "--file", str(article_md),
            "--threshold", str(args.ai_threshold),
            "--max-iter", str(args.ai_max_iter),
            "--lang", lang,
            "--output-dir", str(output_dir),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.stdout:
            humanizer_result = parse_json_output(result.stdout)
            if humanizer_result and humanizer_result.get("final_file"):
                final_path = Path(humanizer_result["final_file"])
                if final_path.exists() and final_path != article_md:
                    # Copy final humanized version
                    article_final.write_text(final_path.read_text(encoding="utf-8"), encoding="utf-8")
                    print(f"  Final article: {article_final}", file=sys.stderr)
                    print(f"  AI score: {humanizer_result.get('original_score')}% → "
                          f"{humanizer_result.get('final_score')}%", file=sys.stderr)
                else:
                    # Score was already below threshold
                    article_final.write_text(article_md.read_text(encoding="utf-8"), encoding="utf-8")
                    print(f"  Article passed AI check without changes.", file=sys.stderr)
            else:
                article_final.write_text(article_md.read_text(encoding="utf-8"), encoding="utf-8")
                print(f"  Humanizer returned no result. Using original article.", file=sys.stderr)
        else:
            article_final.write_text(article_md.read_text(encoding="utf-8"), encoding="utf-8")
            print(f"  Humanizer failed. Using original article.", file=sys.stderr)
            if result.stderr:
                print(f"  {result.stderr[:500]}", file=sys.stderr)
    else:
        if not article_final.exists():
            print(f"  Skipping step 5 — using {article_md}", file=sys.stderr)
            article_final.write_text(article_md.read_text(encoding="utf-8"), encoding="utf-8")

    # ── STEP 6: Content Audit ──
    if args.skip_to <= 6:
        audit_file = article_final if article_final.exists() else article_md
        cmd = [
            sys.executable, str(CONTENT_AUDIT_SCRIPT),
            args.keyword,
            "--gl", args.gl, "--hl", args.hl,
            "--no-crawl",
            "--raw",
        ]
        result = run_step(cmd, "Content Audit", capture=True)
        if result and result.stdout:
            audit_data = parse_json_output(result.stdout)
            if audit_data:
                audit_json.write_text(json.dumps(audit_data, indent=2, ensure_ascii=False))
                print(f"  Saved: {audit_json}", file=sys.stderr)

    # ── Summary ──
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"  PIPELINE COMPLETE", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)
    print(f"  Keyword: {args.keyword}", file=sys.stderr)
    print(f"  Market: gl={args.gl}, hl={args.hl}", file=sys.stderr)
    print(f"  Language: {lang}", file=sys.stderr)
    print(f"  Output: {output_dir}/", file=sys.stderr)
    print(f"  Files:", file=sys.stderr)
    for f in sorted(output_dir.rglob("*")):
        if f.is_file():
            size = f.stat().st_size
            print(f"    {f.relative_to(output_dir)} ({size:,} bytes)", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)


if __name__ == "__main__":
    main()
