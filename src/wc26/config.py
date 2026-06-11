from __future__ import annotations

import datetime

# Tournament start date — used as the "as of" date for freshness window
TOURNAMENT_DATE: datetime.date = datetime.date(2026, 6, 11)

# Rolling window for freshness analysis
FRESHNESS_DAYS: int = 365

# Window for familiarity / co-play analysis
FAMILIARITY_SEASONS: list[str] = ["2023/24", "2024/25", "2025/26"]

# Competition tier weights for edge-weight heuristic.
# Keys are Transfermarkt competition category strings (adjust after inspecting real pages).
COMP_TIER_WEIGHTS: dict[str, float] = {
    "UEFA Champions League": 1.0,
    "UEFA Europa League": 0.85,
    "UEFA Europa Conference League": 0.75,
    "FIFA World Cup": 1.0,
    "UEFA European Championship": 0.95,
    "Copa America": 0.90,
    "AFCON": 0.80,
    "Premier League": 0.90,
    "La Liga": 0.90,
    "Bundesliga": 0.88,
    "Serie A": 0.88,
    "Ligue 1": 0.85,
    "Eredivisie": 0.75,
    "Primeira Liga": 0.75,
    "default": 0.60,
}

# Half-life in days for recency decay: weight = 2^(-days_ago / DECAY_HALF_LIFE_DAYS)
DECAY_HALF_LIFE_DAYS: float = 365.0

# Throttle: seconds between HTTP requests
REQUEST_DELAY_SECONDS: float = 1.5

# Raw HTML cache directory (gitignored)
RAW_CACHE_DIR: str = "data/raw"

# Manual TM-ID override file
TM_ID_OVERRIDES_FILE: str = "data/overrides/tm_id_overrides.json"
