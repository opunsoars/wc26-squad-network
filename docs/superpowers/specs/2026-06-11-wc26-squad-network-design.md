# World Cup 2026 — Squad Freshness & Familiarity

**Date:** 2026-06-11
**Author:** Vinay Warrier (opunsoars)
**Status:** Approved design
**Predecessor:** [Euro 2020 player familiarity network analysis (LinkedIn)](https://www.linkedin.com/pulse/how-much-do-euro-2020-players-know-each-other-network-vinay-warrier/)

## 1. Concept

A personal, open-source analytics project covering all 48 squads (~1,250 players)
of the 2026 FIFA World Cup. One data pipeline feeds two analyses:

- **Freshness** — professional minutes played in the 365 days before the
  tournament, per player, split club vs country and by competition. An
  indicator of fatigue / match sharpness going into the tournament.
- **Familiarity** — a co-play network per squad: edge weight derived from the
  minutes two squad-mates actually spent on the pitch together over the last
  3 seasons (2023/24–2025/26).

Deliverables: an interactive static site (GitHub Pages) and reusable cleaned
datasets committed to this public GitHub repo.

## 2. Data sourcing

FBref (the Euro 2020 source) lost its advanced Opta data feed in January 2026,
so this project is built player-centric on **Transfermarkt**:

- **Squads:** Wikipedia "2026 FIFA World Cup squads" page → 48 final squad
  lists. Each player resolved to a Transfermarkt player ID via TM search +
  fuzzy name matching, with a manual override file for mismatches (expect ~5%).
- **Match logs:** each player's TM detailed performance pages for seasons
  2023/24, 2024/25, 2025/26 → one row per player-match: match ID, date,
  competition, team, opponent, minutes played. **Rendered with Playwright** —
  TM migrated these pages to JS web components
  (`<tm-player-performance-table-new>`), so there is no server-side `<table>`
  and `httpx` alone cannot reach per-match rows (verified 2026-06-11). The
  headless browser accepts the consent banner, waits for the table to populate,
  then we parse the rendered `table.items`.
- **No sub-minute data exists** on any source (TM, FBref, ceapi) — only total
  minutes per match. Co-play therefore uses **shared appearances**, not interval
  overlap: two players co-played a match iff both have an appearance row for it.
- **Key insight:** no match-sheet crawling needed. Two players co-played iff
  they share a match ID (deterministic & player-independent: date+team+opponent).
  Freshness = sum of minutes in the trailing 365-day window. One scrape serves
  both analyses.
- **Team strength:** [ClubElo](http://clubelo.com/API) free API for club Elo
  ratings (replaces the defunct FiveThirtyEight SPI used in 2021); Elo/FIFA
  national-team ratings for internationals.
- **FBref is unusable** — returns 403 since the Jan 2026 shutdown. The TM
  `ceapi/player/<id>/performance` JSON endpoint exists but gives only
  per-competition season aggregates, not per-match rows.

Scraping etiquette: throttled requests, retry with backoff, identifying UA,
raw HTML cached to `data/raw/` (gitignored, never re-fetched, never
republished). Only derived datasets are committed. Personal / educational use.

## 3. Pipeline architecture (Python 3.11+, uv)

Stages, each runnable independently via a CLI entry point:

1. `squads` — scrape squad lists, resolve TM IDs → `players` dataset.
2. `matchlogs` — scrape TM performance pages per player → raw cache.
3. `transform` — parse + clean → `player_matches` dataset (parquet + CSV,
   committed). Pydantic models for all records.
4. `metrics` — compute freshness metrics and per-squad co-play graphs +
   network metrics → compact JSON per team + one tournament summary JSON
   written to `site/data/`.

Standards: ruff format/check, mypy strict, structlog, pytest, Google
docstrings, type hints everywhere — per the Data/AI team guidelines.

## 4. Committed datasets

- `players` — player, squad, position, club, TM ID, market value.
- `player_matches` — one row per player per match (3 seasons).

These are the reusable public artifacts (parquet + CSV in `data/`).

## 5. Network analysis (networkx)

Per squad, weighted undirected graph over the 26 players:

- **Edge weight** = shared appearances × competition-tier weight ×
  recency decay × team-strength weight (ClubElo / national Elo) — same
  heuristic family as the Euro 2020 piece (which used SPI), but the base unit
  is shared appearances rather than shared minutes (sub-minute data no longer
  exists). Tier weights and the decay half-life are named constants in one
  config module, and the raw unweighted shared-appearance count is always
  retained alongside the weighted edge so the heuristic can be tuned without
  re-deriving data.
- **Squad metrics:** density and triadic closure / clustering coefficient
  (for direct continuity with Euro 2020), plus the previously-deferred
  centrality work: weighted degree (squad "connector") and betweenness
  (bridges between club cliques).
- **Cross-squad outputs:** metric table for all 48 squads; density vs squad
  market value scatter (echoing the 2021 budget-vs-cohesion finding);
  "most familiar XI" per squad.

## 6. Interactive site

Static, no build step: `site/` with vanilla HTML/JS + D3, all data from
precomputed JSON.

- **Tournament overview** — squads ranked by recent-minutes load (freshest vs
  most-leggy), density-vs-market-value scatter.
- **Team page** — per-player 365-day minutes bars (club/country split),
  minutes timeline, squad network metrics.
- **Familiarity network** — force-directed graph per squad, edge thickness =
  weighted co-play, node size = minutes.

Hosting: GitHub Pages from `site/` in this repo; designed to be re-mountable
under `opunsoars.github.io` / `opunsoars.dev` later.

## 7. Testing & quality

- pytest on: HTML parsers (fixture pages committed under `tests/fixtures/`),
  interval-overlap logic, freshness window math, network metric calculations.
- Spot-check pipeline totals against known players' public season stats.
- ≥80% coverage on new code; ruff + mypy strict in pre-commit checklist.

## 8. Risks & mitigations

| Risk | Mitigation |
|---|---|
| TM ToS prohibits scraping | Throttled, cached, personal/educational, raw data not republished |
| Player-ID resolution errors | Fuzzy match + manual override file + count assertions per squad |
| TM sub-minute detail patchy in some leagues | Fallback to Sofascore/FotMob for affected matches |
| Squad lists change (injuries/replacements) | Pipeline is squad-file-driven; re-run is cheap (cache) |
| TM HTML changes mid-project | Parsers tested on committed fixtures; raw cache preserves history |
