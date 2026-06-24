# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Concurrent SERP fetching with `ThreadPoolExecutor(max_workers=5)` in `nod-rank-tracker`, `nod-competitor-tracker`, `nod-visibility-monitor`, and `nod-paa-miner` — roughly 2x faster (150s → 70s on 51 keywords).
- Shared disk cache for SERP responses with 24h TTL (`.claude/skills/nod-nodeshub-api/scripts/serp_cache.py`) — eliminates redundant API calls across skills.
- `/nod-content-brief` auto-saves the generated brief as Markdown under `output/data/briefs/{slug}.md`.
- `/nod-paa-miner` auto-saves results to `output/data/paa/{slug}_{date}.json`.
- `/nod-serp-analysis` asks for device (desktop/mobile) before running.
- `/guide` option D shows GSC and GA4 connection status.
- `.claude/settings.local.json.example` shipped with the repo and copied by `bin/install.mjs` during install.

### Changed
- All runtime artifacts moved under `output/` — rank history, reports, cache, briefs, keywords, PAA, topics, articles. `.gitignore` simplified to a single `output/` entry.
- `/nod-content-auditor` progress logs moved to stderr so `--raw` JSON output is clean and parseable.
- `/nod-keyword-research` default save path aligned with the `output/data/` convention.
- Documented `create_report()` / `append_section()` signatures in five `SKILL.md` files to prevent hallucinated kwargs at runtime.

### Fixed
- Hardcoded `data/` paths in agents and `nod-nodeshub-api/scripts/report.py` updated to `output/data/`.
- `bin/install.mjs` now adds `output/` to the user project's `.gitignore` so SERP cache, snapshots, reports, and other runtime artifacts are not accidentally committed (replaces the now-stale `data/gsc/*.json` entry).
- `nod-competitor-tracker` no longer crashes when a SERP organic result lacks a position (`r.get("pos", r.get("global_pos"))` returns `None`). `None` positions are excluded from the average; domains with zero positions render as `—`.
- `nod-rank-tracker`, `nod-competitor-tracker`, `nod-visibility-monitor`, and `nod-paa-miner` now catch any worker exception (network timeout, connection error, malformed response), not just `NodeshubError`. Previously a non-NodesHub exception would either crash the whole run or leave a missing key in `serp_results` causing a downstream `KeyError` in visibility-monitor.

## [0.1.0] - 2026-04-13

Initial release.
