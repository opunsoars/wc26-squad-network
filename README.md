# WC26 Squad Freshness & Familiarity

Player fitness and on-pitch familiarity analysis for all 48 squads at the 2026 FIFA World Cup.

**Live site:** https://opunsoars.github.io/wc26-squad-network

Inspired by [Euro 2020 — How much do players know each other?](https://www.linkedin.com/pulse/how-much-do-euro-2020-players-know-each-other-network-vinay-warrier/)

## What it shows

- **Freshness** — professional minutes each player has played in the last 365 days (club + international), a proxy for match sharpness and fatigue going into the tournament.
- **Familiarity network** — a weighted co-play graph per squad: edge weight derived from actual shared on-pitch appearances over 3 seasons (2023/24–2025/26), decayed by recency and competition tier.

Network metrics per squad: density, clustering coefficient, weighted degree centrality — the same methodology as the Euro 2020 piece, updated for the Transfermarkt + Playwright data source.

## Data

Source: [Transfermarkt](https://www.transfermarkt.com) per-player performance pages (personal/educational use, throttled, raw HTML not republished).

Squad lists: Wikipedia "2026 FIFA World Cup squads" page.

Committed datasets (derived only, no raw HTML):
- `data/players.csv` / `data/players.parquet` — resolved squad lists with TM IDs
- `data/player_matches.csv` / `data/player_matches.parquet` — per-player match logs, 3 seasons

## Run the pipeline

```bash
uv sync
uv run wc26 --help

# Full run (scrapes + computes + writes site JSON):
uv run wc26 all

# Or step by step:
uv run wc26 squads       # scrape Wikipedia → data/players.parquet
uv run wc26 matchlogs    # render TM pages → data/player_matches.parquet
uv run wc26 metrics      # compute metrics → site/data/
```

Requires [Playwright](https://playwright.dev/python/) for the TM scrape step:

```bash
uv run playwright install chromium
```

## Development

```bash
uv run --python 3.12 ruff format .
uv run --python 3.12 ruff check --fix .
uv run --python 3.12 mypy --strict src/
uv run --python 3.12 pytest
```

## Methodology

**Edge weight** = shared appearances × competition-tier weight × recency decay × team-strength factor

- Competition tiers: Champions League = 1.0, Premier League/La Liga = 0.90, default = 0.60
- Recency decay: `2^(−days_ago / 365)` — a match from 3 years ago weighs ~12.5% of today's
- Team strength: ClubElo ratings (national team: FIFA Elo)
- Base unit: shared appearances (sub-minute data does not exist on any public source)

**Squad metrics:**
- *Density* — fraction of possible edges that exist (0–1)
- *Clustering coefficient* — triadic closure, weighted by co-play
- *Weighted degree* — total edge weight per node (squad "connector" players)
