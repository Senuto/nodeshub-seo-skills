#!/usr/bin/env python3
"""
Content Humanizer Pipeline — text → AI score → rewrite flagged sections → loop until human.

Orchestrates iterative humanization:
  1. Run Genuino AI score (with guidelines)
  2. Identify flagged sections
  3. Rewrite via LLM (OpenRouter)
  4. Re-check score
  5. Loop until threshold or max iterations

Each iteration saves a versioned file: article_humanized_v1.md, v2.md, etc.

Usage:
  python3 pipeline.py --file article.md
  python3 pipeline.py --file article.md --threshold 30 --max-iter 3
  python3 pipeline.py --file article.md --lang Polish
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
AI_SCORE_SCRIPT = SKILLS_DIR / "ai-score" / "scripts" / "analyze.py"
NODESHUB_SCRIPTS = SKILLS_DIR / "nod-nodeshub-api" / "scripts"

sys.path.insert(0, str(NODESHUB_SCRIPTS))


def run_genuino(file_path, guidelines=True, humanize=False):
    """Run Genuino AI score analysis and return parsed JSON."""
    cmd = [
        sys.executable, str(AI_SCORE_SCRIPT),
        "--file", str(file_path),
        "--json",
    ]
    if guidelines:
        cmd.append("--guidelines")
    if humanize:
        cmd.append("--humanize")

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  Genuino error: {result.stderr}", file=sys.stderr)
        return None

    # Parse JSON from stdout (may have non-JSON lines before it)
    for line in result.stdout.strip().split("\n"):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue

    # Try parsing the whole output
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        print(f"  Could not parse Genuino output", file=sys.stderr)
        return None


def rewrite_with_llm(text, guidelines_data, lang="English"):
    """Rewrite flagged sections using OpenRouter LLM."""
    from openrouter_client import OpenRouterClient
    llm = OpenRouterClient()

    # Build guidelines context
    guidelines_text = ""
    if guidelines_data:
        for g in guidelines_data:
            name = g.get("name", "")
            priority = g.get("priority", "")
            instructions = g.get("instructions", [])
            if instructions:
                guidelines_text += f"\n- {name} (priority: {priority}):\n"
                for inst in instructions:
                    guidelines_text += f"  * {inst}\n"

    prompt = f"""You are a professional editor. Your job is to rewrite the text below so it sounds
naturally human-written while preserving the exact meaning, structure, and information.

GUIDELINES FROM AI DETECTOR — fix these specific issues:
{guidelines_text if guidelines_text else "No specific guidelines — just make it sound more natural."}

RULES:
1. Only change phrasing and sentence structure — do NOT add or remove information
2. Vary sentence length (mix short and long)
3. Use natural transitions instead of formulaic connectors
4. Remove AI patterns: "It's important to note," "Furthermore," "In conclusion,"
   "In today's world," perfectly parallel structures, lists of exactly 3 items
5. Keep the original heading structure (H1, H2, H3)
6. Write in {lang}
7. Preserve all markdown formatting
8. Do NOT add commentary — output ONLY the rewritten text

TEXT TO HUMANIZE:

{text}"""

    try:
        rewritten = llm.chat(
            prompt,
            model="google/gemini-2.5-flash-lite",
            temperature=0.4,
            max_tokens=8000,
        )
        return rewritten
    except Exception as e:
        print(f"  LLM error: {e}", file=sys.stderr)
        return None


def main():
    parser = argparse.ArgumentParser(description="Content Humanizer: iterative AI score reduction")
    parser.add_argument("--file", required=True, help="Path to text file to humanize")
    parser.add_argument("--threshold", type=float, default=30.0,
                        help="Target AI probability threshold (default: 30%%)")
    parser.add_argument("--max-iter", type=int, default=3,
                        help="Max humanization iterations (default: 3)")
    parser.add_argument("--lang", default="English",
                        help="Language of the text (default: English)")
    parser.add_argument("--output-dir", help="Output directory (default: same as input file)")
    args = parser.parse_args()

    input_path = Path(args.file)
    if not input_path.exists():
        print(f"ERROR: File not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    output_dir = Path(args.output_dir) if args.output_dir else input_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    stem = input_path.stem
    suffix = input_path.suffix or ".md"

    print(f"{'='*60}", file=sys.stderr)
    print(f"  CONTENT HUMANIZER", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)
    print(f"  File: {input_path}", file=sys.stderr)
    print(f"  Threshold: {args.threshold}%", file=sys.stderr)
    print(f"  Max iterations: {args.max_iter}", file=sys.stderr)
    print(f"  Language: {args.lang}", file=sys.stderr)
    print(f"{'='*60}\n", file=sys.stderr)

    current_file = input_path
    original_score = None
    history = []

    for iteration in range(1, args.max_iter + 1):
        print(f"\n--- Iteration {iteration}/{args.max_iter} ---", file=sys.stderr)

        # Step 1: Check AI score
        print(f"  Checking AI score...", file=sys.stderr)
        result = run_genuino(current_file, guidelines=True, humanize=(iteration == 1))

        if not result:
            print(f"  Failed to get AI score. Stopping.", file=sys.stderr)
            break

        score = result.get("ai_probability", result.get("score", 100))
        classification = result.get("classification", "unknown")
        style = result.get("style", "")
        guidelines = result.get("guidelines", [])
        humanize_prompt = result.get("humanize_prompt", "")

        if original_score is None:
            original_score = score

        history.append({
            "iteration": iteration,
            "score": score,
            "classification": classification,
            "file": str(current_file),
        })

        print(f"  AI Probability: {score}%", file=sys.stderr)
        print(f"  Classification: {classification}", file=sys.stderr)
        if style:
            print(f"  Style: {style}", file=sys.stderr)
        if guidelines:
            print(f"  Guidelines ({len(guidelines)}):", file=sys.stderr)
            for g in guidelines[:5]:
                print(f"    - {g.get('name', '')}: {g.get('priority', '')}", file=sys.stderr)

        # Check if we're below threshold
        if score < args.threshold:
            print(f"\n  Score {score}% is below threshold {args.threshold}%. Done!", file=sys.stderr)
            break

        # Step 2: Rewrite
        print(f"  Rewriting flagged sections...", file=sys.stderr)
        text = current_file.read_text(encoding="utf-8")

        rewritten = rewrite_with_llm(text, guidelines, args.lang)
        if not rewritten:
            print(f"  Rewrite failed. Stopping.", file=sys.stderr)
            break

        # Save versioned file
        version_file = output_dir / f"{stem}_humanized_v{iteration}{suffix}"
        version_file.write_text(rewritten, encoding="utf-8")
        print(f"  Saved: {version_file}", file=sys.stderr)

        current_file = version_file
        time.sleep(1)  # Small delay between Genuino calls

    # Final check if last iteration was a rewrite
    if current_file != input_path and (not history or history[-1].get("score", 100) >= args.threshold):
        print(f"\n  Final score check...", file=sys.stderr)
        result = run_genuino(current_file, guidelines=False)
        if result:
            final_score = result.get("ai_probability", result.get("score", 100))
            history.append({
                "iteration": "final",
                "score": final_score,
                "classification": result.get("classification", "unknown"),
                "file": str(current_file),
            })
        else:
            final_score = history[-1]["score"] if history else None
    else:
        final_score = history[-1]["score"] if history else None

    # Summary
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"  HUMANIZER COMPLETE", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)
    print(f"  Original score:  {original_score}%", file=sys.stderr)
    print(f"  Final score:     {final_score}%", file=sys.stderr)
    print(f"  Iterations:      {len([h for h in history if isinstance(h['iteration'], int)])}", file=sys.stderr)
    print(f"  Original file:   {input_path}", file=sys.stderr)
    print(f"  Final file:      {current_file}", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)

    # Output JSON summary
    summary = {
        "original_file": str(input_path),
        "final_file": str(current_file),
        "original_score": original_score,
        "final_score": final_score,
        "threshold": args.threshold,
        "iterations": history,
        "success": final_score is not None and final_score < args.threshold,
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
