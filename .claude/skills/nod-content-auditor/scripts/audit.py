#!/usr/bin/env python3
"""
Content Auditor — Audit content vs SERP reality via NodesHub + Jina Reader.

Crawls competitor pages and optionally your page to produce a real content gap analysis.

Usage:
    python3 audit.py "target keyword" --gl us --hl en
    python3 audit.py "target keyword" --gl us --hl en --url https://example.com/page
    python3 audit.py "target keyword" --gl us --hl en --top 5
    python3 audit.py "target keyword" --gl us --hl en --no-crawl  (SERP-only, no Jina)
"""

import argparse
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'nod-nodeshub-api' / 'scripts'))
from client import NodeshubClient, NodeshubError
from jina_reader import JinaReader, JinaReaderError
from report import render_section_wrapper, make_section_id, html_table, summary_card, badge


# ── Helpers ──────────────────────────────────────────────

def detect_serp_features(snippets):
    """Detect SERP features from snippets data."""
    features = []
    if not snippets:
        return features
    checks = {
        "ai_overview": "AI Overview",
        "ads": "Ads",
        "answer_box": "Answer Box",
        "people_also_ask": "People Also Ask",
        "videos_pack": "Videos",
        "related_searches": "Related Searches",
        "knowledge_panel_right": "Knowledge Panel",
        "local_pack": "Local Pack",
        "top_stories": "Top Stories",
        "shopping_results": "Shopping",
        "image_pack": "Images",
    }
    for key, name in checks.items():
        val = snippets.get(key)
        if val and val != [] and val != {}:
            features.append(name)
    return features


def classify_content_type(title):
    """Guess content type from title patterns."""
    t = title.lower()
    if any(w in t for w in ["how to", "jak ", "guide", "tutorial", "poradnik"]):
        return "how-to"
    if any(w in t for w in ["best", "top", "najlepsze", "ranking"]):
        return "listicle"
    if any(w in t for w in ["vs", "vs.", "comparison", "porównanie"]):
        return "comparison"
    if any(w in t for w in ["review", "recenzja", "opinia"]):
        return "review"
    if any(w in t for w in ["what is", "co to", "definition", "definicja"]):
        return "explainer"
    return "article"


def extract_keywords_from_text(text, min_len=3):
    """Extract meaningful words from text for comparison."""
    words = re.findall(r'\b[a-zA-ZąćęłńóśźżĄĆĘŁŃÓŚŹŻ]{' + str(min_len) + r',}\b',
                       text.lower())
    # Filter common stop words
    stop_en = {"the", "and", "for", "are", "but", "not", "you", "all", "can",
               "had", "her", "was", "one", "our", "out", "has", "have", "from",
               "they", "been", "said", "each", "which", "their", "will", "other",
               "about", "many", "then", "them", "these", "some", "would", "make",
               "like", "into", "time", "very", "when", "come", "could", "more",
               "with", "that", "this", "what", "your", "than", "also", "just",
               "most", "only", "such"}
    stop_pl = {"jest", "nie", "się", "ale", "lub", "jak", "dla", "czy", "oraz",
               "ten", "jego", "jej", "ich", "tego", "tej", "tym", "tych",
               "które", "który", "która", "może", "tak", "już", "tylko",
               "przez", "więc", "bardzo", "tego", "być", "będzie", "został",
               "jako", "przy", "nawet", "gdzie", "kiedy", "przed", "między"}
    stop = stop_en | stop_pl
    return [w for w in words if w not in stop]


def extract_headings(text):
    """Extract markdown headings from text."""
    headings = []
    for line in text.split("\n"):
        match = re.match(r'^(#{1,4})\s+(.+)', line)
        if match:
            level = len(match.group(1))
            headings.append({"level": level, "text": match.group(2).strip()})
    return headings


def keyword_presence(keyword_list, text):
    """Check which keywords from a list appear in the text."""
    text_lower = text.lower()
    found = []
    missing = []
    for kw in keyword_list:
        if kw.lower() in text_lower:
            found.append(kw)
        else:
            missing.append(kw)
    return found, missing


def keyword_frequency_in_competitors(keyword, competitor_texts):
    """Count how many competitor texts contain a keyword."""
    count = 0
    kw_lower = keyword.lower()
    for text in competitor_texts:
        if kw_lower in text.lower():
            count += 1
    return count


def render_report_section(data):
    """Convert content auditor data into an HTML report section.

    Args:
        data: Dict with keyword, url, serp_features, dominant_type,
              competitors_crawled, keyword_coverage, question_coverage,
              content_gaps, important_topics.
    """
    from html import escape as e
    parts = []
    keyword = data.get("keyword", "")
    gaps = data.get("content_gaps", [])

    parts.append(summary_card([
        (e(keyword), "Keyword"),
        (str(data.get("competitors_crawled", 0)), "Competitors Crawled"),
        (str(len(gaps)), "Content Gaps"),
        (e(str(data.get("dominant_type", ""))), "Dominant Type"),
    ]))

    # SERP features
    features = data.get("serp_features", [])
    if features:
        badges_html = " ".join(badge(e(f), "info") for f in features)
        parts.append(f"<h3>SERP Features</h3>\n<p>{badges_html}</p>")

    # Keyword coverage table
    kw_coverage = data.get("keyword_coverage", [])
    if kw_coverage:
        rows = []
        for kc in kw_coverage:
            row = [e(kc.get("keyword", "")), kc.get("in_competitors", "")]
            if "in_your_page" in kc:
                row.append(badge("Yes", "success") if kc["in_your_page"] == "Yes"
                           else badge("No", "error"))
            row.append(badge(kc.get("priority", ""), "warning"
                             if kc.get("priority") == "Must have" else "info"))
            rows.append(row)
        headers = ["Keyword", "In Competitors"]
        if any("in_your_page" in kc for kc in kw_coverage):
            headers.append("In Your Page")
        headers.append("Priority")
        parts.append("<h3>Keyword Coverage</h3>")
        parts.append(html_table(headers, rows))

    # Content gaps
    if gaps:
        gap_rows = [[e(g.get("term", "")), f"{g.get('competitors', 0)}/{g.get('total', 0)}"]
                    for g in gaps[:15]]
        parts.append("<h3>Content Gaps</h3>")
        parts.append(html_table(["Term", "Competitors Using It"], gap_rows))

    # Questions
    q_coverage = data.get("question_coverage", [])
    if q_coverage:
        q_rows = [[e(qc.get("question", "")[:60]), qc.get("in_competitors", "")]
                  for qc in q_coverage]
        parts.append("<h3>Questions to Answer</h3>")
        parts.append(html_table(["Question", "In Competitors"], q_rows))

    sid = make_section_id("content-auditor")
    return render_section_wrapper(sid, "Content Auditor",
                                  f"Content Audit: {e(keyword)}", "\n".join(parts))


# ── Main ─────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Audit content against SERP reality")
    parser.add_argument("keyword", help="Target keyword to audit against")
    parser.add_argument("--gl", default="us", help="Country code (default: us)")
    parser.add_argument("--hl", default="en", help="Language code (default: en)")
    parser.add_argument("--mode", choices=["standard", "reasoning"], default="standard",
                        help="Fan-out mode: standard (8.5 tokens) or reasoning (31 tokens)")
    parser.add_argument("--url", help="URL of your page to audit")
    parser.add_argument("--top", type=int, default=5,
                        help="Number of top SERP results to crawl (default: 5)")
    parser.add_argument("--no-crawl", action="store_true",
                        help="Skip Jina crawling (SERP-only mode)")
    parser.add_argument("--raw", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    mode_cost = 8.5 if args.mode == "standard" else 31
    print(f"Auditing: \"{args.keyword}\" | country: {args.gl} | top: {args.top} | "
          f"crawl: {'off' if args.no_crawl else 'on'}", file=sys.stderr)

    try:
        client = NodeshubClient()

        # ── Step 1: SERP data ──
        print("  [1/4] Fetching SERP data...", flush=True, file=sys.stderr)
        serp = client.search(args.keyword, gl=args.gl, hl=args.hl)

        # ── Step 2: Keyword expansion ──
        print("  [2/4] Expanding keywords...", flush=True, file=sys.stderr)
        fanout = client.query_fanout(args.keyword, hl=args.hl, mode=args.mode,
                                     add_questions=True, add_topic_leaders=False)

        # Parse SERP
        data = serp.get("data", {})
        results = data.get("results", {})
        organic = results.get("organic_results", [])
        snippets = results.get("snippets", {})
        features = detect_serp_features(snippets)

        # Parse PAA
        paa = snippets.get("people_also_ask", {})
        paa_questions = []
        if isinstance(paa, dict):
            for item in paa.get("questions", paa.get("items", [])):
                if isinstance(item, dict):
                    paa_questions.append(item.get("question", item.get("text", "")))
                elif isinstance(item, str):
                    paa_questions.append(item)
        elif isinstance(paa, list):
            for item in paa:
                if isinstance(item, dict):
                    paa_questions.append(item.get("question", item.get("text", "")))

        # Parse fanout
        fanout_data = fanout if isinstance(fanout, dict) else {}
        related_queries = []
        fanout_questions = []
        for key, value in fanout_data.items():
            if key in ("success", "totalResponseTime"):
                continue
            if isinstance(value, list):
                for item in value:
                    q = item.get("query", item.get("keyword", str(item))) if isinstance(item, dict) else str(item)
                    if "?" in q or any(q.lower().startswith(w) for w in
                                       ["how", "what", "why", "when", "where", "which",
                                        "jak", "co", "dlaczego", "kiedy", "gdzie"]):
                        fanout_questions.append(q)
                    else:
                        related_queries.append(q)
            elif isinstance(value, dict):
                for k, v in value.items():
                    if isinstance(v, list):
                        for item in v:
                            q = item.get("query", item.get("keyword", str(item))) if isinstance(item, dict) else str(item)
                            related_queries.append(q)

        all_questions = list(dict.fromkeys(paa_questions + fanout_questions))
        all_keywords = list(dict.fromkeys(related_queries))

        # Content type analysis
        content_types = [classify_content_type(r.get("title", "")) for r in organic[:10]]
        dominant_type = max(set(content_types), key=content_types.count) if content_types else "unknown"

        # ── Step 3: Crawl competitor pages via Jina ──
        competitor_contents = []
        user_content = None

        if not args.no_crawl:
            reader = JinaReader()
            competitor_urls = [r.get("url", r.get("link", "")) for r in organic[:args.top]
                               if r.get("url") or r.get("link")]

            print(f"  [3/4] Crawling {len(competitor_urls)} competitor pages via Jina Reader...",
                  flush=True, file=sys.stderr)

            def _on_progress(done, total, url, ok):
                status = "OK" if ok else "SKIP"
                domain = url.split("/")[2] if "/" in url else url
                print(f"    [{done}/{total}] {status} {domain}", flush=True, file=sys.stderr)

            competitor_contents = reader.fetch_batch(
                competitor_urls, max_workers=3, max_words=1500,
                min_words=200, on_progress=_on_progress
            )

            # Crawl user's URL if provided
            if args.url:
                print(f"  [3/4] Crawling your page: {args.url}...", flush=True, file=sys.stderr)
                user_content = reader.fetch(args.url, max_words=2000)
                if user_content["ok"]:
                    print(f"    OK ({user_content['word_count']} words)", flush=True, file=sys.stderr)
                else:
                    print(f"    FAILED: {user_content.get('error', 'too short')}", flush=True, file=sys.stderr)
                    user_content = None
        else:
            print("  [3/4] Skipping crawl (--no-crawl mode)", flush=True, file=sys.stderr)

        # ── Step 4: Content gap analysis ──
        print("  [4/4] Analyzing content gaps...", flush=True, file=sys.stderr)

        competitor_texts = [c["content"] for c in competitor_contents]

        # Extract top keywords from competitor content
        all_competitor_words = []
        for text in competitor_texts:
            all_competitor_words.extend(extract_keywords_from_text(text))
        competitor_word_freq = Counter(all_competitor_words)

        # Keywords that appear in multiple competitors (likely important)
        n_competitors = max(len(competitor_texts), 1)
        important_topics = []
        for word, count in competitor_word_freq.most_common(100):
            # How many competitors use this word?
            pages_with_word = keyword_frequency_in_competitors(word, competitor_texts)
            if pages_with_word >= max(2, n_competitors * 0.4):
                important_topics.append({
                    "term": word,
                    "competitors": pages_with_word,
                    "total": n_competitors,
                })

        # Extract competitor headings for structure analysis
        competitor_headings = []
        for c in competitor_contents:
            competitor_headings.extend(extract_headings(c["content"]))

        heading_texts = [h["text"].lower() for h in competitor_headings]
        heading_freq = Counter(heading_texts)

        # Keyword coverage analysis
        keyword_coverage = []
        for kw in all_keywords[:20]:
            pages_with = keyword_frequency_in_competitors(kw, competitor_texts)
            priority = "Must have" if pages_with >= max(2, n_competitors * 0.6) else \
                       "Should have" if pages_with >= max(1, n_competitors * 0.3) else \
                       "Nice to have"
            entry = {
                "keyword": kw,
                "in_competitors": f"{pages_with}/{n_competitors}",
                "priority": priority,
            }
            # Check if user's page has it
            if user_content and user_content.get("ok"):
                entry["in_your_page"] = "Yes" if kw.lower() in user_content["content"].lower() else "No"
            keyword_coverage.append(entry)

        # Question coverage
        question_coverage = []
        for q in all_questions[:15]:
            pages_with = keyword_frequency_in_competitors(q, competitor_texts)
            entry = {
                "question": q,
                "in_competitors": f"{pages_with}/{n_competitors}",
            }
            if user_content and user_content.get("ok"):
                # Check if question topic is addressed (fuzzy — check key words)
                q_words = [w for w in q.lower().split() if len(w) > 3]
                matches = sum(1 for w in q_words if w in user_content["content"].lower())
                entry["addressed"] = "Likely" if matches >= len(q_words) * 0.5 else "No"
            question_coverage.append(entry)

        # Content gaps (user vs competitors)
        content_gaps = []
        if user_content and user_content.get("ok"):
            user_words = set(extract_keywords_from_text(user_content["content"]))
            for topic in important_topics[:30]:
                if topic["term"] not in user_words and topic["competitors"] >= 2:
                    content_gaps.append(topic)

        # ── Output ──
        if args.raw:
            result = {
                "keyword": args.keyword,
                "url": args.url,
                "serp_features": features,
                "dominant_type": dominant_type,
                "competitors_crawled": len(competitor_contents),
                "keyword_coverage": keyword_coverage,
                "question_coverage": question_coverage,
                "content_gaps": content_gaps[:15],
                "important_topics": important_topics[:20],
            }
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return

        # Pretty output
        print()
        print(f"## Content Audit: {args.keyword}")
        if args.url:
            print(f"**Your URL:** {args.url}")
        print(f"**NodesHub tokens:** ~{mode_cost} | "
              f"**Pages crawled:** {len(competitor_contents)}"
              f"{' + your page' if user_content and user_content.get('ok') else ''}")
        print()

        # SERP Reality
        print("### SERP Reality")
        print(f"- **Dominant content type:** {dominant_type}")
        if features:
            print(f"- **SERP features:** {', '.join(features)}")
        print(f"- **Top domains:** {', '.join(r.get('domain', '') for r in organic[:5])}")
        print()

        # Top Results
        print("### Top 10 Results")
        print("| # | Title | Domain | Type | Crawled |")
        print("|---|-------|--------|------|---------|")
        crawled_urls = {c["url"] for c in competitor_contents}
        for r in organic[:10]:
            pos = r.get("pos", r.get("global_pos", "?"))
            title = r.get("title", "")[:50]
            domain = r.get("domain", "")
            ctype = classify_content_type(r.get("title", ""))
            url = r.get("url", r.get("link", ""))
            crawled = "Yes" if url in crawled_urls else "-"
            print(f"| {pos} | {title} | {domain} | {ctype} | {crawled} |")
        print()

        # Keyword Coverage
        if keyword_coverage:
            print(f"### Keyword Coverage ({len(keyword_coverage)})")
            if user_content and user_content.get("ok"):
                print("| Keyword | In competitors | In your page | Priority |")
                print("|---------|---------------|-------------|----------|")
                for kc in keyword_coverage:
                    print(f"| {kc['keyword']} | {kc['in_competitors']} | "
                          f"{kc.get('in_your_page', '?')} | {kc['priority']} |")
            else:
                print("| Keyword | In competitors | Priority |")
                print("|---------|---------------|----------|")
                for kc in keyword_coverage:
                    print(f"| {kc['keyword']} | {kc['in_competitors']} | {kc['priority']} |")
            print()

        # Questions
        if question_coverage:
            print(f"### Questions to Answer ({len(question_coverage)})")
            if user_content and user_content.get("ok"):
                print("| Question | In competitors | Addressed? |")
                print("|----------|---------------|-----------|")
                for qc in question_coverage:
                    print(f"| {qc['question'][:60]} | {qc['in_competitors']} | "
                          f"{qc.get('addressed', '?')} |")
            else:
                print("| Question | In competitors |")
                print("|----------|---------------|")
                for qc in question_coverage:
                    print(f"| {qc['question'][:60]} | {qc['in_competitors']} |")
            print()

        # Content Gaps (only when user URL provided)
        if content_gaps:
            print(f"### Content Gaps — Missing from Your Page ({len(content_gaps[:15])})")
            print("Topics that competitors cover but your page doesn't:")
            print("| Term | Competitors using it |")
            print("|------|---------------------|")
            for gap in content_gaps[:15]:
                print(f"| {gap['term']} | {gap['competitors']}/{gap['total']} |")
            print()

        # Competitor heading patterns
        if competitor_headings:
            common_headings = heading_freq.most_common(10)
            common_headings = [(h, c) for h, c in common_headings if c >= 2]
            if common_headings:
                print("### Common Heading Patterns")
                print("Headings used by multiple competitors:")
                for heading, count in common_headings:
                    print(f"- **{heading}** ({count} competitors)")
                print()

        # Important topics from competitor content
        if important_topics and not content_gaps:
            print(f"### Key Topics from Competitors ({len(important_topics[:15])})")
            print("| Term | Used by |")
            print("|------|---------|")
            for t in important_topics[:15]:
                print(f"| {t['term']} | {t['competitors']}/{t['total']} competitors |")
            print()

        # Summary
        print("### Audit Summary")
        print(f"- Dominant format: **{dominant_type}** — match this or improve on it")
        if paa_questions:
            print(f"- **{len(paa_questions)} PAA questions** — address for featured snippet opportunity")
        if "AI Overview" in features:
            print("- **AI Overview present** — structure content for AI citation (BLUF)")
        if "Ads" in features:
            print("- **Ads present** — commercial intent confirmed")
        if competitor_contents:
            avg_words = sum(c["word_count"] for c in competitor_contents) // len(competitor_contents)
            print(f"- **Avg competitor length:** ~{avg_words} words (from crawled content)")
        if content_gaps:
            must_haves = [g for g in content_gaps if g["competitors"] >= max(2, n_competitors * 0.6)]
            print(f"- **{len(content_gaps)} content gaps found** "
                  f"({len(must_haves)} critical)")
        if user_content and user_content.get("ok"):
            missing_kw = [kc for kc in keyword_coverage if kc.get("in_your_page") == "No"
                          and kc["priority"] == "Must have"]
            if missing_kw:
                print(f"- **{len(missing_kw)} must-have keywords missing** from your page")

    except NodeshubError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
