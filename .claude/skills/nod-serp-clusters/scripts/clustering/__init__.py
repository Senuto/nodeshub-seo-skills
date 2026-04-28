"""SERP clustering subpackage.

Splits the algorithm into focused modules:
  serp_parse  — extract organic results / snippet types from raw SERP
  similarity  — weighted Jaccard + dynamic domain weighting
  louvain     — community detection
  naming      — LLM cluster naming
  hierarchy   — multi-level tree builder for dendrogram
  dendrogram  — D3.js dendrogram JS template
  report_html — standalone HTML report
  report_md   — standalone Markdown report
  section     — branded report section (shared report system)
  pipeline    — fetch + similarity + Louvain orchestration
"""
