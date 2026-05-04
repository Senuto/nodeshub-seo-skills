#!/usr/bin/env python3
"""
PAA Miner — Extract People Also Ask questions from Google SERPs via NodesHub API.

Usage:
    python3 mine.py "keyword" --gl us --hl en
    python3 mine.py "kw1" "kw2" --gl us --hl en
    python3 mine.py --file keywords.txt --gl us --hl en --cluster
"""

import argparse
import json
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'nod-nodeshub-api' / 'scripts'))
from client import NodeshubClient, NodeshubError
from report import render_section_wrapper, make_section_id, html_table, summary_card, badge
import serp_cache

_PROJECT_ROOT = Path(__file__).resolve().parents[4]


def _slug(text):
    return re.sub(r"[^\w\s-]", "", text.lower().strip()).replace(" ", "-")[:100]


def _output_path(keywords, file_arg):
    if file_arg:
        stem = _slug(Path(file_arg).stem)
    elif len(keywords) == 1:
        stem = _slug(keywords[0])
    else:
        stem = _slug(keywords[0]) + f"_and_{len(keywords) - 1}_more"
    date = datetime.now().strftime("%Y%m%d")
    out_dir = _PROJECT_ROOT / "output" / "data" / "paa"
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / f"{stem}_{date}.json"

MAX_WORKERS = 5


def extract_paa(serp_data):
    """Extract PAA questions from SERP response. Returns list of question strings."""
    questions = []
    data = serp_data.get("data", {})
    results = data.get("results", {})
    snippets = results.get("snippets", {})

    # People Also Ask
    paa = snippets.get("people_also_ask")
    if paa:
        if isinstance(paa, list):
            for item in paa:
                if isinstance(item, dict):
                    q = item.get("question") or item.get("title") or item.get("text", "")
                    if q:
                        questions.append(q.strip())
                elif isinstance(item, str):
                    questions.append(item.strip())
        elif isinstance(paa, dict):
            items = paa.get("items") or paa.get("questions") or []
            for item in items:
                if isinstance(item, dict):
                    q = item.get("question") or item.get("title") or item.get("text", "")
                    if q:
                        questions.append(q.strip())
                elif isinstance(item, str):
                    questions.append(item.strip())

    # Answer box — may contain a question too
    ab = snippets.get("answer_box")
    if ab and isinstance(ab, dict):
        ab_q = ab.get("question") or ab.get("title", "")
        if ab_q and ab_q.strip().endswith("?"):
            questions.append(ab_q.strip())

    return questions


def deduplicate(questions_by_keyword):
    """Deduplicate questions across keywords. Returns list of {question, sources}."""
    seen = {}  # lowercase question -> {question: original, sources: set}
    for kw, questions in questions_by_keyword.items():
        for q in questions:
            key = q.lower().strip().rstrip("?").strip()
            if key not in seen:
                seen[key] = {"question": q, "sources": set()}
            seen[key]["sources"].add(kw)

    result = []
    for item in seen.values():
        result.append({
            "question": item["question"],
            "sources": sorted(item["sources"]),
        })
    # Sort by number of sources (most common first), then alphabetically
    result.sort(key=lambda x: (-len(x["sources"]), x["question"].lower()))
    return result


def cluster_questions(questions, hl="en"):
    """Cluster questions by topic using OpenRouter LLM."""
    try:
        from openrouter_client import OpenRouterClient
    except ImportError:
        print("[WARN] OpenRouter client not available, skipping clustering", file=sys.stderr)
        return None

    q_list = [item["question"] for item in questions]
    if len(q_list) < 3:
        return None

    lang_hint = "Polish" if hl == "pl" else "the same language as the questions"

    prompt = f"""Group these questions into 3-8 topic clusters. Return ONLY valid JSON.

Questions:
{json.dumps(q_list, ensure_ascii=False)}

Return JSON format:
{{"clusters": [{{"name": "Cluster Name", "questions": ["question1", "question2"]}}]}}

Rules:
- Cluster names should be short (2-4 words), in {lang_hint}
- Every question must appear in exactly one cluster
- Minimum 2 questions per cluster; merge tiny clusters
"""

    try:
        client = OpenRouterClient()
        response = client.chat(prompt, temperature=0.2, max_tokens=3000)
        # Extract JSON from response
        match = re.search(r'\{[\s\S]*\}', response)
        if match:
            return json.loads(match.group())
    except Exception as e:
        print(f"[WARN] Clustering failed: {e}", file=sys.stderr)

    return None


def render_report_section(data):
    """Convert PAA miner data into an HTML report section.

    Args:
        data: Dict with keywords_analyzed, total_raw_questions, unique_questions,
              questions (list of {question, sources}), clusters (optional).
    """
    from html import escape as e
    parts = []

    parts.append(summary_card([
        (str(data.get("keywords_analyzed", 0)), "Keywords Mined"),
        (str(data.get("unique_questions", 0)), "Unique Questions"),
        (str(data.get("total_raw_questions", 0)), "Raw Total"),
    ]))

    questions = data.get("questions", [])
    clusters = data.get("clusters")

    if clusters and isinstance(clusters, dict) and clusters.get("clusters"):
        for cluster in clusters["clusters"]:
            name = e(cluster.get("name", ""))
            items = "".join(f"<li>{e(q)}</li>" for q in cluster.get("questions", []))
            parts.append(f'<div class="brand-card" style="margin:10px 0">'
                         f'<h4>{name}</h4><ul>{items}</ul></div>')
    elif questions:
        rows = [[str(i), e(q.get("question", "")), e(", ".join(q.get("sources", [])))]
                for i, q in enumerate(questions, 1)]
        parts.append(html_table(["#", "Question", "Found For"], rows))

    sid = make_section_id("paa-miner")
    return render_section_wrapper(sid, "PAA Miner",
                                  "PAA Questions Mined", "\n".join(parts))


def main():
    parser = argparse.ArgumentParser(description="Mine PAA questions from Google SERPs")
    parser.add_argument("keywords", nargs="*", help="Keywords to mine")
    parser.add_argument("--file", help="File with keywords (one per line)")
    parser.add_argument("--gl", default="us", help="Country code (default: us)")
    parser.add_argument("--hl", default="en", help="Language code (default: en)")
    parser.add_argument("--cluster", action="store_true", help="Cluster questions by topic (requires OPENROUTER_API_KEY)")
    parser.add_argument("--raw", action="store_true", help="Output raw JSON to stdout (also saves to disk)")
    args = parser.parse_args()

    # Collect keywords
    keywords = list(args.keywords) if args.keywords else []
    if args.file:
        try:
            with open(args.file) as f:
                keywords.extend(line.strip() for line in f if line.strip())
        except FileNotFoundError:
            print(f"Error: File not found: {args.file}", file=sys.stderr)
            sys.exit(1)

    if not keywords:
        print("Error: No keywords provided.", file=sys.stderr)
        sys.exit(1)

    print(f"Mining PAA questions for {len(keywords)} keywords (cost: {len(keywords)} tokens)")

    try:
        client = NodeshubClient()
        questions_by_keyword = {}
        total_raw = 0

        lock = threading.Lock()
        counter = [0]

        def _fetch(kw):
            serp, from_cache = serp_cache.search_cached(client, kw, args.gl, args.hl)
            return extract_paa(serp), from_cache

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {executor.submit(_fetch, kw): kw for kw in keywords}
            for future in as_completed(futures):
                kw = futures[future]
                with lock:
                    counter[0] += 1
                    n = counter[0]
                paa, from_cache = future.result()
                questions_by_keyword[kw] = paa
                tag = "[cache]" if from_cache else "[api]"
                print(f"  [{n}/{len(keywords)}] {kw}... {len(paa)} questions {tag}")

        total_raw = sum(len(v) for v in questions_by_keyword.values())

        # Deduplicate
        unique = deduplicate(questions_by_keyword)

        output = {
            "keywords_analyzed": len(keywords),
            "total_raw_questions": total_raw,
            "unique_questions": len(unique),
            "questions": unique,
            "by_keyword": {kw: qs for kw, qs in questions_by_keyword.items()},
        }

        if args.raw:
            if args.cluster:
                clusters = cluster_questions(unique, hl=args.hl)
                if clusters:
                    output["clusters"] = clusters
            save_path = _output_path(keywords, args.file)
            save_path.write_text(json.dumps(output, indent=2, ensure_ascii=False))
            print(f"Saved to: {save_path}", file=sys.stderr)
            print(json.dumps(output, indent=2, ensure_ascii=False))
            return

        print()

        if not unique:
            print("No PAA questions found for the given keywords.")
            return

        # Clustering
        clusters = None
        if args.cluster and len(unique) >= 3:
            print("Clustering questions...", end=" ", flush=True)
            clusters = cluster_questions(unique, hl=args.hl)
            if clusters:
                print(f"{len(clusters.get('clusters', []))} clusters")
            else:
                print("failed, showing flat list")

        if clusters and clusters.get("clusters"):
            # Clustered output
            print(f"## PAA Questions Mined (Clustered)")
            print()
            print(f"**Keywords:** {len(keywords)} | **Tokens:** {len(keywords)} | **Questions:** {len(unique)} | **Clusters:** {len(clusters['clusters'])}")
            print()

            for cluster in clusters["clusters"]:
                print(f"### {cluster['name']}")
                for q in cluster.get("questions", []):
                    print(f"- {q}")
                print()
        else:
            # Flat output
            print(f"## PAA Questions Mined")
            print()
            print(f"**Keywords analyzed:** {len(keywords)} | **Tokens used:** {len(keywords)} | **Unique questions:** {len(unique)}")
            print()

            print("| # | Question | Found for |")
            print("|---|----------|-----------|")
            for i, item in enumerate(unique, 1):
                sources = ", ".join(item["sources"])
                print(f"| {i} | {item['question']} | {sources} |")
            print()

        # Source distribution
        print("### Source Distribution")
        kw_counts = {kw: len(qs) for kw, qs in questions_by_keyword.items()}
        for kw, count in sorted(kw_counts.items(), key=lambda x: -x[1]):
            print(f"- {kw}: {count} questions")

        # Save JSON output
        if clusters:
            output["clusters"] = clusters
        save_path = _output_path(keywords, args.file)
        save_path.write_text(json.dumps(output, indent=2, ensure_ascii=False))
        print(f"\nSaved to: {save_path}")

    except NodeshubError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
