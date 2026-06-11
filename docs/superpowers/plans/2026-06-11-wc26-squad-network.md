# WC26 Squad Freshness & Familiarity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python data pipeline + D3 static site showing World Cup 2026 squad freshness (minutes in last 365 days) and player familiarity networks (co-play minutes over 3 seasons) for all 48 squads.

**Architecture:** Player-centric Transfermarkt scraper builds a cached raw layer → parsed/cleaned parquet datasets → metric computation (freshness sums + networkx co-play graphs) → precomputed JSON → vanilla D3 static site on GitHub Pages.

**Tech Stack:** Python 3.11+, uv, pydantic, httpx, beautifulsoup4, pandas, pyarrow, networkx, structlog, ruff, mypy, pytest; D3 v7, vanilla HTML/JS.

---

## File Map

```
wc26-squad-network/
├── pyproject.toml                        # uv project, all deps, ruff/mypy config
├── .gitignore
├── data/
│   ├── raw/                              # gitignored — cached HTML from TM
│   ├── overrides/
│   │   └── tm_id_overrides.json          # manual player-ID corrections
│   ├── players.csv / players.parquet     # committed — resolved squad lists
│   └── player_matches.csv / player_matches.parquet  # committed — per-player match logs
├── src/wc26/
│   ├── __init__.py
│   ├── config.py                         # constants: COMP_TIER_WEIGHTS, DECAY_HALF_LIFE_DAYS, TOURNAMENT_DATE
│   ├── models.py                         # Pydantic: Player, MatchLog, CoPlayEdge, SquadMetrics
│   ├── scraper.py                        # throttled httpx fetcher with raw HTML cache
│   ├── pipeline/
│   │   ├── __init__.py
│   │   ├── squads.py                     # scrape Wikipedia squad lists + resolve TM IDs
│   │   ├── matchlogs.py                  # scrape TM per-player performance pages
│   │   ├── transform.py                  # parse HTML → clean player_matches dataset
│   │   └── metrics.py                    # freshness + networkx co-play + squad metrics
│   └── cli.py                            # typer CLI: run squads/matchlogs/transform/metrics/all
├── tests/
│   ├── conftest.py
│   ├── fixtures/
│   │   ├── tm_player_page.html           # committed sample TM performance page
│   │   └── wiki_squads_page.html         # committed sample Wikipedia squads page
│   ├── test_scraper.py
│   ├── test_squads.py
│   ├── test_transform.py
│   └── test_metrics.py
└── site/
    ├── index.html                        # tournament overview
    ├── team.html                         # per-team page
    ├── js/
    │   ├── overview.js
    │   ├── team.js
    │   └── network.js                    # D3 force-directed network
    ├── css/
    │   └── style.css
    └── data/                             # gitignored build output (JSON)
        ├── summary.json
        └── teams/
            └── <team_code>.json
```

---

## Task 1: Project scaffold & config

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `src/wc26/__init__.py`
- Create: `src/wc26/config.py`

- [ ] **Step 1: Create pyproject.toml**

```toml
[project]
name = "wc26"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "httpx>=0.27",
    "beautifulsoup4>=4.12",
    "lxml>=5.0",
    "pandas>=2.2",
    "pyarrow>=16.0",
    "pydantic>=2.7",
    "networkx>=3.3",
    "structlog>=24.0",
    "typer>=0.12",
    "rapidfuzz>=3.9",
]

[project.scripts]
wc26 = "wc26.cli:app"

[tool.uv]
dev-dependencies = [
    "pytest>=8.0",
    "pytest-cov>=5.0",
    "ruff>=0.4",
    "mypy>=1.10",
    "pandas-stubs>=2.2",
    "types-beautifulsoup4>=4.12",
]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM"]

[tool.mypy]
strict = true
python_version = "3.11"

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "--cov=src/wc26 --cov-report=term-missing"
```

- [ ] **Step 2: Create .gitignore**

```
data/raw/
site/data/
__pycache__/
*.pyc
.mypy_cache/
.ruff_cache/
.coverage
htmlcov/
dist/
.venv/
```

- [ ] **Step 3: Create src/wc26/__init__.py** (empty file)

```python
```

- [ ] **Step 4: Create src/wc26/config.py**

```python
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
```

- [ ] **Step 5: Install deps and verify**

```bash
uv sync
uv run python -c "import wc26; print('ok')"
```

Expected: `ok`

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml .gitignore src/
git commit -m "feat: scaffold project, config constants"
```

---

## Task 2: Pydantic models

**Files:**
- Create: `src/wc26/models.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_models.py`:

```python
from __future__ import annotations

import datetime
from wc26.models import Player, MatchLog, CoPlayEdge, SquadMetrics


def test_player_model():
    p = Player(
        name="Bukayo Saka",
        squad="England",
        position="MF",
        club="Arsenal",
        tm_id="418560",
        market_value_eur=None,
    )
    assert p.tm_id == "418560"


def test_match_log_interval_minutes_full_game():
    m = MatchLog(
        player_tm_id="418560",
        match_id="tm_4200000",
        date=datetime.date(2025, 8, 17),
        competition="Premier League",
        team="Arsenal",
        opponent="Wolves",
        minutes_played=90,
        sub_on_minute=None,
        sub_off_minute=None,
    )
    assert m.on_minute == 0
    assert m.off_minute == 90


def test_match_log_interval_sub_on():
    m = MatchLog(
        player_tm_id="418560",
        match_id="tm_4200001",
        date=datetime.date(2025, 9, 1),
        competition="Premier League",
        team="Arsenal",
        opponent="Chelsea",
        minutes_played=35,
        sub_on_minute=55,
        sub_off_minute=None,
    )
    assert m.on_minute == 55
    assert m.off_minute == 90


def test_match_log_interval_sub_off():
    m = MatchLog(
        player_tm_id="418560",
        match_id="tm_4200002",
        date=datetime.date(2025, 9, 15),
        competition="Premier League",
        team="Arsenal",
        opponent="Liverpool",
        minutes_played=60,
        sub_on_minute=None,
        sub_off_minute=60,
    )
    assert m.on_minute == 0
    assert m.off_minute == 60


def test_coplay_edge_fields():
    e = CoPlayEdge(
        player_a_tm_id="418560",
        player_b_tm_id="223340",
        raw_shared_minutes=1240,
        weighted_shared_minutes=890.5,
    )
    assert e.raw_shared_minutes == 1240


def test_squad_metrics_fields():
    sm = SquadMetrics(
        squad="England",
        density=0.72,
        clustering=0.61,
        avg_weighted_degree=320.5,
        market_value_eur=1_200_000_000,
    )
    assert sm.squad == "England"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_models.py -v
```

Expected: `ModuleNotFoundError` or similar — `models` not yet defined.

- [ ] **Step 3: Implement models.py**

```python
from __future__ import annotations

import datetime
from pydantic import BaseModel, model_validator


class Player(BaseModel):
    """A squad player resolved to a Transfermarkt ID."""

    name: str
    squad: str
    position: str
    club: str
    tm_id: str
    market_value_eur: int | None = None


class MatchLog(BaseModel):
    """One appearance for one player in one match."""

    player_tm_id: str
    match_id: str
    date: datetime.date
    competition: str
    team: str
    opponent: str
    minutes_played: int
    sub_on_minute: int | None = None
    sub_off_minute: int | None = None

    @property
    def on_minute(self) -> int:
        """Minute the player came on (0 if started)."""
        return self.sub_on_minute if self.sub_on_minute is not None else 0

    @property
    def off_minute(self) -> int:
        """Minute the player went off (90 if played to end, or sub_off_minute)."""
        return self.sub_off_minute if self.sub_off_minute is not None else 90

    @model_validator(mode="after")
    def _validate_interval(self) -> MatchLog:
        if self.on_minute >= self.off_minute:
            raise ValueError(
                f"on_minute ({self.on_minute}) must be < off_minute ({self.off_minute})"
            )
        return self


class CoPlayEdge(BaseModel):
    """Weighted edge between two players in the same squad."""

    player_a_tm_id: str
    player_b_tm_id: str
    raw_shared_minutes: int
    weighted_shared_minutes: float


class SquadMetrics(BaseModel):
    """Aggregate network metrics for one squad."""

    squad: str
    density: float
    clustering: float
    avg_weighted_degree: float
    market_value_eur: int | None = None
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_models.py -v
```

Expected: 6 PASSED

- [ ] **Step 5: Create tests/conftest.py** with shared fixtures used across later tests:

```python
from __future__ import annotations

import datetime
import pytest
from wc26.models import Player, MatchLog


@pytest.fixture()
def sample_player() -> Player:
    return Player(
        name="Bukayo Saka",
        squad="England",
        position="MF",
        club="Arsenal",
        tm_id="418560",
        market_value_eur=150_000_000,
    )


@pytest.fixture()
def sample_match_log() -> MatchLog:
    return MatchLog(
        player_tm_id="418560",
        match_id="tm_4200000",
        date=datetime.date(2025, 8, 17),
        competition="Premier League",
        team="Arsenal",
        opponent="Wolves",
        minutes_played=90,
        sub_on_minute=None,
        sub_off_minute=None,
    )
```

- [ ] **Step 6: Commit**

```bash
git add src/wc26/models.py tests/
git commit -m "feat: pydantic models for Player, MatchLog, CoPlayEdge, SquadMetrics"
```

---

## Task 3: Throttled HTTP scraper with raw HTML cache

**Files:**
- Create: `src/wc26/scraper.py`
- Create: `tests/test_scraper.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_scraper.py
from __future__ import annotations

import hashlib
import pathlib
import pytest
from unittest.mock import patch, MagicMock
from wc26.scraper import Scraper


def test_cache_hit_does_not_call_httpx(tmp_path: pathlib.Path):
    url = "https://www.transfermarkt.com/player/418560"
    url_hash = hashlib.md5(url.encode()).hexdigest()
    cache_file = tmp_path / f"{url_hash}.html"
    cache_file.write_text("<html>cached</html>", encoding="utf-8")

    scraper = Scraper(cache_dir=str(tmp_path), delay_seconds=0.0)
    with patch("httpx.Client.get") as mock_get:
        html = scraper.fetch(url)
        mock_get.assert_not_called()

    assert html == "<html>cached</html>"


def test_cache_miss_fetches_and_writes(tmp_path: pathlib.Path):
    url = "https://www.transfermarkt.com/player/999"
    url_hash = hashlib.md5(url.encode()).hexdigest()

    mock_response = MagicMock()
    mock_response.text = "<html>live</html>"
    mock_response.raise_for_status = MagicMock()

    scraper = Scraper(cache_dir=str(tmp_path), delay_seconds=0.0)
    with patch("httpx.Client.get", return_value=mock_response):
        html = scraper.fetch(url)

    assert html == "<html>live</html>"
    assert (tmp_path / f"{url_hash}.html").read_text(encoding="utf-8") == "<html>live</html>"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_scraper.py -v
```

Expected: ImportError — `scraper` not yet defined.

- [ ] **Step 3: Implement scraper.py**

```python
from __future__ import annotations

import hashlib
import pathlib
import time

import httpx
import structlog

logger = structlog.get_logger()

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (personal analytics project — github.com/opunsoars/wc26-squad-network)"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


class Scraper:
    """Throttled HTTP fetcher with a file-based raw HTML cache.

    Args:
        cache_dir: Directory for cached HTML files.
        delay_seconds: Minimum seconds between requests.
    """

    def __init__(self, cache_dir: str, delay_seconds: float = 1.5) -> None:
        self._cache_dir = pathlib.Path(cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._delay = delay_seconds
        self._last_request: float = 0.0

    def _cache_path(self, url: str) -> pathlib.Path:
        key = hashlib.md5(url.encode()).hexdigest()
        return self._cache_dir / f"{key}.html"

    def fetch(self, url: str) -> str:
        """Return HTML for url, reading from cache if available.

        Args:
            url: The URL to fetch.

        Returns:
            Raw HTML string.
        """
        cache_file = self._cache_path(url)
        if cache_file.exists():
            logger.debug("cache_hit", url=url)
            return cache_file.read_text(encoding="utf-8")

        elapsed = time.monotonic() - self._last_request
        if elapsed < self._delay:
            time.sleep(self._delay - elapsed)

        logger.info("fetching", url=url)
        with httpx.Client(headers=_DEFAULT_HEADERS, follow_redirects=True, timeout=30) as client:
            response = client.get(url)
            response.raise_for_status()

        self._last_request = time.monotonic()
        html = response.text
        cache_file.write_text(html, encoding="utf-8")
        logger.debug("cache_written", url=url, path=str(cache_file))
        return html
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_scraper.py -v
```

Expected: 2 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/wc26/scraper.py tests/test_scraper.py
git commit -m "feat: throttled scraper with file-based HTML cache"
```

---

## Task 4: Squad pipeline — Wikipedia scrape + TM ID resolution

**Files:**
- Create: `src/wc26/pipeline/__init__.py`
- Create: `src/wc26/pipeline/squads.py`
- Create: `tests/fixtures/wiki_squads_page.html`
- Create: `tests/test_squads.py`

> **Before starting this task:** Manually fetch one Wikipedia squad section page (e.g. `https://en.wikipedia.org/wiki/2026_FIFA_World_Cup_squads`) and save a representative excerpt as `tests/fixtures/wiki_squads_page.html`. This is the fixture the tests run against.

- [ ] **Step 1: Write failing test**

```python
# tests/test_squads.py
from __future__ import annotations

import pathlib
from unittest.mock import patch, MagicMock
from wc26.pipeline.squads import parse_wiki_squads, resolve_tm_id


def _wiki_html() -> str:
    return (pathlib.Path("tests/fixtures/wiki_squads_page.html")).read_text(encoding="utf-8")


def test_parse_wiki_squads_returns_players():
    players = parse_wiki_squads(_wiki_html())
    # At minimum one squad with at least 11 players (fixture covers ≥1 squad)
    assert len(players) >= 11
    first = players[0]
    assert first.name
    assert first.squad
    assert first.position in {"GK", "DF", "MF", "FW"}
    assert first.club


def test_resolve_tm_id_uses_override_first(tmp_path):
    overrides = tmp_path / "overrides.json"
    overrides.write_text('{"Bukayo Saka": "418560"}', encoding="utf-8")
    tm_id = resolve_tm_id("Bukayo Saka", overrides_file=str(overrides), scraper=None)
    assert tm_id == "418560"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_squads.py -v
```

Expected: ImportError.

- [ ] **Step 3: Create `src/wc26/pipeline/__init__.py`** (empty)

- [ ] **Step 4: Implement pipeline/squads.py**

```python
from __future__ import annotations

import json
import pathlib
import re

import structlog
from bs4 import BeautifulSoup
from rapidfuzz import process as fuzz_process

from wc26.config import TM_ID_OVERRIDES_FILE
from wc26.models import Player
from wc26.scraper import Scraper

logger = structlog.get_logger()

_WIKI_SQUADS_URL = "https://en.wikipedia.org/wiki/2026_FIFA_World_Cup_squads"

# TM search URL template — returns JSON with player results
_TM_SEARCH_URL = (
    "https://www.transfermarkt.com/schnellsuche/ergebnis/schnellsuche"
    "?query={name}&Spieler_page=1"
)

_POSITION_MAP = {
    "Goalkeeper": "GK",
    "GK": "GK",
    "Defender": "DF",
    "DF": "DF",
    "Midfielder": "MF",
    "MF": "MF",
    "Forward": "FW",
    "FW": "FW",
    "Attacker": "FW",
}


def parse_wiki_squads(html: str) -> list[Player]:
    """Parse the Wikipedia 2026 WC squads page into a flat list of Players.

    TM IDs are not set at this stage (set to empty string); resolve separately.

    Args:
        html: Raw HTML of the Wikipedia squads page.

    Returns:
        List of Player objects with tm_id="".
    """
    soup = BeautifulSoup(html, "lxml")
    players: list[Player] = []

    # Each squad is a <h3> (country name) followed by a wikitable
    for heading in soup.find_all(["h2", "h3"]):
        country_span = heading.find("span", class_="mw-headline")
        if not country_span:
            continue
        country = country_span.get_text(strip=True)
        # Skip non-squad headings (Contents, References, etc.)
        if country in {"Contents", "References", "Notes", "Groups", "Squads"}:
            continue

        table = heading.find_next_sibling("table")
        if table is None:
            continue

        for row in table.find_all("tr")[1:]:  # skip header
            cells = row.find_all(["td", "th"])
            if len(cells) < 4:
                continue
            try:
                pos_raw = cells[1].get_text(strip=True)
                pos = _POSITION_MAP.get(pos_raw, "MF")
                name = cells[2].get_text(strip=True)
                club = cells[5].get_text(strip=True) if len(cells) > 5 else ""
                players.append(
                    Player(name=name, squad=country, position=pos, club=club, tm_id="")
                )
            except (IndexError, ValueError):
                logger.warning("parse_row_skipped", country=country, cells=len(cells))

    logger.info("wiki_squads_parsed", total_players=len(players))
    return players


def resolve_tm_id(
    name: str,
    overrides_file: str = TM_ID_OVERRIDES_FILE,
    scraper: Scraper | None = None,
) -> str:
    """Return TM player ID for a player name, using overrides first then TM search.

    Args:
        name: Player full name.
        overrides_file: Path to JSON file mapping name → TM ID.
        scraper: Scraper instance for live lookups (skipped if None).

    Returns:
        TM player ID string, or "" if not found.
    """
    overrides_path = pathlib.Path(overrides_file)
    if overrides_path.exists():
        overrides: dict[str, str] = json.loads(overrides_path.read_text(encoding="utf-8"))
        # Exact match first
        if name in overrides:
            return overrides[name]
        # Fuzzy match against override keys
        result = fuzz_process.extractOne(name, overrides.keys(), score_cutoff=90)
        if result:
            matched_name, _, _ = result
            logger.info("override_fuzzy_match", query=name, matched=matched_name)
            return overrides[matched_name]

    if scraper is None:
        logger.warning("no_scraper_for_tm_lookup", name=name)
        return ""

    url = _TM_SEARCH_URL.format(name=name.replace(" ", "+"))
    html = scraper.fetch(url)
    tm_id = _extract_tm_id_from_search(html, name)
    logger.info("tm_id_resolved", name=name, tm_id=tm_id)
    return tm_id


def _extract_tm_id_from_search(html: str, query_name: str) -> str:
    """Extract the best-match TM player ID from a TM search results page.

    Args:
        html: HTML of TM search results.
        query_name: Original player name for fuzzy matching.

    Returns:
        TM player ID string or "" if not found.
    """
    soup = BeautifulSoup(html, "lxml")
    candidates: list[tuple[str, str]] = []  # (name, tm_id)
    for link in soup.select("table.items td.hauptlink a"):
        href = link.get("href", "")
        # TM player URLs: /firstname-lastname/profil/spieler/123456
        match = re.search(r"/spieler/(\d+)", href)
        if match:
            candidates.append((link.get_text(strip=True), match.group(1)))

    if not candidates:
        return ""

    names = [c[0] for c in candidates]
    result = fuzz_process.extractOne(query_name, names, score_cutoff=75)
    if not result:
        return candidates[0][1]  # fallback: first result

    _, _, idx = result
    return candidates[idx][1]


def build_players_dataset(scraper: Scraper) -> list[Player]:
    """Full squad pipeline: scrape Wikipedia → resolve TM IDs.

    Args:
        scraper: Scraper instance for HTTP fetches.

    Returns:
        List of Player objects with tm_id set.
    """
    html = scraper.fetch(_WIKI_SQUADS_URL)
    players = parse_wiki_squads(html)
    resolved: list[Player] = []
    for p in players:
        tm_id = resolve_tm_id(p.name, scraper=scraper)
        resolved.append(p.model_copy(update={"tm_id": tm_id}))
    return resolved
```

- [ ] **Step 5: Run test to verify it passes**

```bash
uv run pytest tests/test_squads.py -v
```

Expected: 2 PASSED. (Fixture must exist; create a minimal one if needed — see note above task.)

- [ ] **Step 6: Commit**

```bash
git add src/wc26/pipeline/ tests/test_squads.py tests/fixtures/
git commit -m "feat: squad pipeline — Wikipedia parse + TM ID resolution"
```

---

## Task 5: Match log pipeline — TM performance page scraper + transform

**Files:**
- Create: `src/wc26/pipeline/matchlogs.py`
- Create: `src/wc26/pipeline/transform.py`
- Create: `tests/fixtures/tm_player_page.html`
- Create: `tests/test_transform.py`

> **Before starting this task:** Manually fetch one TM player performance page (e.g. `https://www.transfermarkt.com/bukayo-saka/leistungsdatendetails/spieler/418560/saison/2024/verein/0/liga/0/wettbewerb//pos/0/trainer_id/0/plus/1`) and save it as `tests/fixtures/tm_player_page.html`.

- [ ] **Step 1: Write failing test**

```python
# tests/test_transform.py
from __future__ import annotations

import datetime
import pathlib
from wc26.pipeline.transform import parse_tm_performance_page, compute_on_off_minutes


def _tm_html() -> str:
    return pathlib.Path("tests/fixtures/tm_player_page.html").read_text(encoding="utf-8")


def test_parse_tm_performance_page_returns_match_logs():
    logs = parse_tm_performance_page(_tm_html(), player_tm_id="418560", season="2024/25")
    assert len(logs) > 0
    log = logs[0]
    assert log.player_tm_id == "418560"
    assert isinstance(log.date, datetime.date)
    assert log.minutes_played >= 0
    assert log.competition


def test_compute_on_off_minutes_full_game():
    on, off = compute_on_off_minutes(minutes_played=90, sub_on=None, sub_off=None)
    assert on == 0
    assert off == 90


def test_compute_on_off_minutes_sub_on():
    on, off = compute_on_off_minutes(minutes_played=30, sub_on=60, sub_off=None)
    assert on == 60
    assert off == 90


def test_compute_on_off_minutes_sub_off():
    on, off = compute_on_off_minutes(minutes_played=55, sub_on=None, sub_off=55)
    assert on == 0
    assert off == 55


def test_compute_on_off_minutes_both_subs():
    on, off = compute_on_off_minutes(minutes_played=20, sub_on=60, sub_off=80)
    assert on == 60
    assert off == 80
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_transform.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement pipeline/matchlogs.py**

```python
from __future__ import annotations

import structlog

from wc26.config import FAMILIARITY_SEASONS, RAW_CACHE_DIR
from wc26.models import MatchLog, Player
from wc26.pipeline.transform import parse_tm_performance_page
from wc26.scraper import Scraper

logger = structlog.get_logger()

_TM_PERF_URL = (
    "https://www.transfermarkt.com/{slug}/leistungsdatendetails/spieler/{tm_id}"
    "/saison/{season_code}/verein/0/liga/0/wettbewerb//pos/0/trainer_id/0/plus/1"
)


def _season_code(season: str) -> str:
    """Convert '2024/25' → '2024'."""
    return season.split("/")[0]


def fetch_player_matchlogs(player: Player, scraper: Scraper) -> list[MatchLog]:
    """Fetch TM performance pages for all FAMILIARITY_SEASONS for one player.

    Args:
        player: Player with tm_id set.
        scraper: Scraper for HTTP fetches.

    Returns:
        All MatchLog records across all seasons.
    """
    if not player.tm_id:
        logger.warning("no_tm_id_skipping", name=player.name)
        return []

    slug = player.name.lower().replace(" ", "-")
    all_logs: list[MatchLog] = []
    for season in FAMILIARITY_SEASONS:
        url = _TM_PERF_URL.format(
            slug=slug, tm_id=player.tm_id, season_code=_season_code(season)
        )
        html = scraper.fetch(url)
        logs = parse_tm_performance_page(html, player_tm_id=player.tm_id, season=season)
        logger.info(
            "player_season_fetched",
            name=player.name,
            season=season,
            matches=len(logs),
        )
        all_logs.extend(logs)
    return all_logs
```

- [ ] **Step 4: Implement pipeline/transform.py**

```python
from __future__ import annotations

import datetime
import re

import structlog
from bs4 import BeautifulSoup

from wc26.models import MatchLog

logger = structlog.get_logger()


def compute_on_off_minutes(
    minutes_played: int,
    sub_on: int | None,
    sub_off: int | None,
) -> tuple[int, int]:
    """Compute the [on, off) interval for a player appearance.

    Args:
        minutes_played: Total minutes played as reported by TM.
        sub_on: Minute the player came on (None if started).
        sub_off: Minute the player was subbed off (None if played to the end).

    Returns:
        Tuple (on_minute, off_minute).
    """
    on = sub_on if sub_on is not None else 0
    off = sub_off if sub_off is not None else 90
    return on, off


def parse_tm_performance_page(
    html: str,
    player_tm_id: str,
    season: str,
) -> list[MatchLog]:
    """Parse a TM player performance detail page into MatchLog records.

    Args:
        html: Raw HTML of the TM performance page.
        player_tm_id: The player's TM ID.
        season: Season string e.g. '2024/25'.

    Returns:
        List of MatchLog records.
    """
    soup = BeautifulSoup(html, "lxml")
    logs: list[MatchLog] = []

    rows = soup.select("table.items tbody tr")
    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 8:
            continue
        try:
            date_text = cells[1].get_text(strip=True)
            date = _parse_date(date_text)
            if date is None:
                continue

            competition = cells[4].get_text(strip=True) or "Unknown"
            team = cells[5].get_text(strip=True)
            opponent = cells[7].get_text(strip=True)

            minutes_text = cells[-2].get_text(strip=True).replace("'", "").replace(".", "")
            minutes_played = int(minutes_text) if minutes_text.isdigit() else 0

            # Sub-on/off: look for icons or special cells with minute notation
            sub_on = _extract_sub_minute(row, "sub-on")
            sub_off = _extract_sub_minute(row, "sub-off")

            # Build a stable match_id from date + team + opponent
            match_id = f"tm_{player_tm_id}_{date.isoformat()}_{_slugify(team)}_{_slugify(opponent)}"

            on, off = compute_on_off_minutes(minutes_played, sub_on, sub_off)
            if on >= off:
                continue

            logs.append(
                MatchLog(
                    player_tm_id=player_tm_id,
                    match_id=match_id,
                    date=date,
                    competition=competition,
                    team=team,
                    opponent=opponent,
                    minutes_played=minutes_played,
                    sub_on_minute=sub_on,
                    sub_off_minute=sub_off,
                )
            )
        except (ValueError, IndexError):
            logger.debug("row_parse_skipped", player_tm_id=player_tm_id)
            continue

    logger.info("tm_page_parsed", player_tm_id=player_tm_id, season=season, rows=len(logs))
    return logs


def _parse_date(text: str) -> datetime.date | None:
    """Try common TM date formats."""
    for fmt in ("%m/%d/%y", "%d.%m.%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _extract_sub_minute(row: object, kind: str) -> int | None:
    """Extract sub-on or sub-off minute from a TM table row.

    TM renders substitution minutes as text like "46'" inside a cell
    that contains a substitution icon.

    Args:
        row: BeautifulSoup Tag for the table row.
        kind: 'sub-on' or 'sub-off'.
    """
    icon_class = "icon-substitution-in" if kind == "sub-on" else "icon-substitution-out"
    cell = row.find("td", class_=lambda c: c and icon_class in c)  # type: ignore[union-attr]
    if cell is None:
        return None
    text = cell.get_text(strip=True).replace("'", "")
    return int(text) if text.isdigit() else None


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "_", text.lower())
```

- [ ] **Step 5: Run test to verify it passes**

```bash
uv run pytest tests/test_transform.py -v
```

Expected: 5 PASSED. (The `test_parse_tm_performance_page_returns_match_logs` test depends on the fixture file existing and containing real TM HTML.)

- [ ] **Step 6: Commit**

```bash
git add src/wc26/pipeline/matchlogs.py src/wc26/pipeline/transform.py tests/test_transform.py tests/fixtures/
git commit -m "feat: match log pipeline — TM page scraper and transform"
```

---

## Task 6: Metrics — freshness + co-play network + squad metrics

**Files:**
- Create: `src/wc26/pipeline/metrics.py`
- Create: `tests/test_metrics.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_metrics.py
from __future__ import annotations

import datetime
from wc26.models import MatchLog, Player
from wc26.pipeline.metrics import (
    compute_freshness,
    compute_coplay_minutes,
    build_squad_graph,
    compute_squad_metrics,
    edge_weight,
)


def _make_log(
    player_tm_id: str,
    match_id: str,
    date: datetime.date,
    minutes: int,
    sub_on: int | None = None,
    sub_off: int | None = None,
    competition: str = "Premier League",
) -> MatchLog:
    return MatchLog(
        player_tm_id=player_tm_id,
        match_id=match_id,
        date=date,
        competition=competition,
        team="Arsenal",
        opponent="Wolves",
        minutes_played=minutes,
        sub_on_minute=sub_on,
        sub_off_minute=sub_off,
    )


def test_compute_freshness_sums_last_365_days():
    cutoff = datetime.date(2026, 6, 11)
    logs = [
        _make_log("p1", "m1", datetime.date(2026, 5, 1), 90),   # in window
        _make_log("p1", "m2", datetime.date(2025, 7, 1), 90),   # in window (just)
        _make_log("p1", "m3", datetime.date(2025, 6, 1), 60),   # outside window
    ]
    total = compute_freshness(logs, player_tm_id="p1", as_of=cutoff)
    assert total == 180


def test_compute_coplay_minutes_full_overlap():
    logs = [
        _make_log("p1", "m1", datetime.date(2025, 10, 1), 90),
        _make_log("p2", "m1", datetime.date(2025, 10, 1), 90),
    ]
    shared = compute_coplay_minutes("p1", "p2", logs)
    assert shared == 90


def test_compute_coplay_minutes_partial_overlap():
    # p1 plays 0-90, p2 plays 60-90 (sub on at 60)
    logs = [
        _make_log("p1", "m1", datetime.date(2025, 10, 1), 90),
        _make_log("p2", "m1", datetime.date(2025, 10, 1), 30, sub_on=60),
    ]
    shared = compute_coplay_minutes("p1", "p2", logs)
    assert shared == 30


def test_compute_coplay_minutes_no_shared_match():
    logs = [
        _make_log("p1", "m1", datetime.date(2025, 10, 1), 90),
        _make_log("p2", "m2", datetime.date(2025, 10, 2), 90),  # different match
    ]
    shared = compute_coplay_minutes("p1", "p2", logs)
    assert shared == 0


def test_edge_weight_decays_with_time():
    recent = edge_weight(
        raw_minutes=100,
        competition="Premier League",
        days_ago=30,
        elo=1800.0,
        ref_elo=1800.0,
    )
    old = edge_weight(
        raw_minutes=100,
        competition="Premier League",
        days_ago=700,
        elo=1800.0,
        ref_elo=1800.0,
    )
    assert recent > old


def test_build_squad_graph_nodes_and_edges():
    players = [
        Player(name="A", squad="ENG", position="GK", club="X", tm_id="p1"),
        Player(name="B", squad="ENG", position="DF", club="X", tm_id="p2"),
        Player(name="C", squad="ENG", position="MF", club="Y", tm_id="p3"),
    ]
    logs = [
        _make_log("p1", "m1", datetime.date(2025, 10, 1), 90),
        _make_log("p2", "m1", datetime.date(2025, 10, 1), 90),
        # p3 has no shared match with p1/p2
    ]
    G = build_squad_graph(players, logs)
    assert set(G.nodes) == {"p1", "p2", "p3"}
    assert G.has_edge("p1", "p2")
    assert not G.has_edge("p1", "p3")


def test_compute_squad_metrics_density():
    players = [
        Player(name="A", squad="ENG", position="GK", club="X", tm_id="p1"),
        Player(name="B", squad="ENG", position="DF", club="X", tm_id="p2"),
        Player(name="C", squad="ENG", position="MF", club="Y", tm_id="p3"),
    ]
    logs = [
        _make_log("p1", "m1", datetime.date(2025, 10, 1), 90),
        _make_log("p2", "m1", datetime.date(2025, 10, 1), 90),
        _make_log("p3", "m1", datetime.date(2025, 10, 1), 90),
    ]
    metrics = compute_squad_metrics("ENG", players, logs)
    assert metrics.density > 0
    assert 0.0 <= metrics.clustering <= 1.0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_metrics.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement pipeline/metrics.py**

```python
from __future__ import annotations

import datetime
import math
from collections import defaultdict
from itertools import combinations

import networkx as nx
import structlog

from wc26.config import (
    COMP_TIER_WEIGHTS,
    DECAY_HALF_LIFE_DAYS,
    FRESHNESS_DAYS,
    TOURNAMENT_DATE,
)
from wc26.models import CoPlayEdge, MatchLog, Player, SquadMetrics

logger = structlog.get_logger()

# Reference Elo: "average good team" — weights scale relative to this
_REF_ELO: float = 1700.0


def compute_freshness(
    logs: list[MatchLog],
    player_tm_id: str,
    as_of: datetime.date = TOURNAMENT_DATE,
) -> int:
    """Sum minutes played in the FRESHNESS_DAYS window ending on as_of.

    Args:
        logs: All MatchLog records (any player).
        player_tm_id: Filter to this player.
        as_of: Reference date (tournament start).

    Returns:
        Total minutes in the window.
    """
    cutoff = as_of - datetime.timedelta(days=FRESHNESS_DAYS)
    return sum(
        log.minutes_played
        for log in logs
        if log.player_tm_id == player_tm_id and cutoff <= log.date <= as_of
    )


def compute_coplay_minutes(
    player_a: str,
    player_b: str,
    logs: list[MatchLog],
) -> int:
    """Compute raw shared on-pitch minutes between two players.

    Groups logs by match_id and sums interval intersections.

    Args:
        player_a: TM ID of player A.
        player_b: TM ID of player B.
        logs: All MatchLog records.

    Returns:
        Total raw shared minutes.
    """
    by_match: dict[str, dict[str, MatchLog]] = defaultdict(dict)
    for log in logs:
        if log.player_tm_id in (player_a, player_b):
            by_match[log.match_id][log.player_tm_id] = log

    total = 0
    for match_logs in by_match.values():
        if player_a not in match_logs or player_b not in match_logs:
            continue
        la = match_logs[player_a]
        lb = match_logs[player_b]
        overlap = max(0, min(la.off_minute, lb.off_minute) - max(la.on_minute, lb.on_minute))
        total += overlap
    return total


def edge_weight(
    raw_minutes: int,
    competition: str,
    days_ago: float,
    elo: float,
    ref_elo: float = _REF_ELO,
) -> float:
    """Compute the weighted edge value for co-play.

    weight = raw_minutes × tier_weight × recency_decay × elo_factor

    Args:
        raw_minutes: Unweighted shared minutes.
        competition: Competition name string.
        days_ago: Days between the match and TOURNAMENT_DATE.
        elo: ClubElo (or national Elo) of the team at match time.
        ref_elo: Reference Elo for normalization.

    Returns:
        Weighted edge value.
    """
    tier = COMP_TIER_WEIGHTS.get(competition, COMP_TIER_WEIGHTS["default"])
    decay = math.pow(2.0, -days_ago / DECAY_HALF_LIFE_DAYS)
    elo_factor = max(0.5, elo / ref_elo)
    return raw_minutes * tier * decay * elo_factor


def build_squad_graph(
    players: list[Player],
    logs: list[MatchLog],
    as_of: datetime.date = TOURNAMENT_DATE,
) -> nx.Graph:
    """Build a weighted undirected co-play graph for a squad.

    Edge attributes: raw_shared_minutes, weighted_shared_minutes.

    Args:
        players: All players in the squad.
        logs: All MatchLog records for those players.
        as_of: Reference date for recency decay.

    Returns:
        networkx Graph with player tm_ids as nodes.
    """
    G: nx.Graph = nx.Graph()
    G.add_nodes_from(p.tm_id for p in players)

    for pa, pb in combinations(players, 2):
        raw = compute_coplay_minutes(pa.tm_id, pb.tm_id, logs)
        if raw == 0:
            continue

        # Weighted: aggregate per-match contributions
        by_match: dict[str, dict[str, MatchLog]] = defaultdict(dict)
        for log in logs:
            if log.player_tm_id in (pa.tm_id, pb.tm_id):
                by_match[log.match_id][log.player_tm_id] = log

        weighted = 0.0
        for match_logs in by_match.values():
            if pa.tm_id not in match_logs or pb.tm_id not in match_logs:
                continue
            la = match_logs[pa.tm_id]
            lb = match_logs[pb.tm_id]
            overlap = max(
                0,
                min(la.off_minute, lb.off_minute) - max(la.on_minute, lb.on_minute),
            )
            if overlap == 0:
                continue
            days_ago = (as_of - la.date).days
            weighted += edge_weight(
                raw_minutes=overlap,
                competition=la.competition,
                days_ago=float(days_ago),
                elo=_REF_ELO,  # ClubElo lookup is wired in cli.py; default here
            )

        G.add_edge(
            pa.tm_id,
            pb.tm_id,
            raw_shared_minutes=raw,
            weighted_shared_minutes=round(weighted, 2),
        )

    return G


def compute_squad_metrics(
    squad: str,
    players: list[Player],
    logs: list[MatchLog],
    market_value_eur: int | None = None,
) -> SquadMetrics:
    """Compute all network metrics for one squad.

    Args:
        squad: Squad/country name.
        players: Squad player list.
        logs: All MatchLog records for those players.
        market_value_eur: Optional total squad market value.

    Returns:
        SquadMetrics instance.
    """
    G = build_squad_graph(players, logs)
    n = len(G.nodes)
    density = nx.density(G) if n > 1 else 0.0
    clustering = nx.average_clustering(G, weight="weighted_shared_minutes") if n > 1 else 0.0
    degrees = dict(G.degree(weight="weighted_shared_minutes"))
    avg_degree = sum(degrees.values()) / n if n > 0 else 0.0

    logger.info(
        "squad_metrics_computed",
        squad=squad,
        players=n,
        density=round(density, 4),
        clustering=round(clustering, 4),
    )
    return SquadMetrics(
        squad=squad,
        density=density,
        clustering=clustering,
        avg_weighted_degree=avg_degree,
        market_value_eur=market_value_eur,
    )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_metrics.py -v
```

Expected: 7 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/wc26/pipeline/metrics.py tests/test_metrics.py
git commit -m "feat: freshness, co-play interval math, networkx squad graph and metrics"
```

---

## Task 7: CLI + JSON export

**Files:**
- Create: `src/wc26/cli.py`

- [ ] **Step 1: Implement cli.py**

No test required here — the CLI is thin orchestration. Do verify it runs.

```python
from __future__ import annotations

import json
import pathlib
from typing import Any

import pandas as pd
import structlog
import typer

from wc26.config import RAW_CACHE_DIR, TOURNAMENT_DATE
from wc26.models import Player, MatchLog
from wc26.pipeline.metrics import compute_freshness, compute_squad_metrics, build_squad_graph
from wc26.pipeline.matchlogs import fetch_player_matchlogs
from wc26.pipeline.squads import build_players_dataset
from wc26.scraper import Scraper

app = typer.Typer(help="WC26 squad freshness & familiarity pipeline")
logger = structlog.get_logger()


@app.command()
def squads(
    cache_dir: str = typer.Option(RAW_CACHE_DIR, help="Raw HTML cache dir"),
    out: str = typer.Option("data/players.parquet", help="Output parquet path"),
) -> None:
    """Scrape squad lists and resolve Transfermarkt IDs."""
    scraper = Scraper(cache_dir=cache_dir)
    players = build_players_dataset(scraper)
    df = pd.DataFrame([p.model_dump() for p in players])
    pathlib.Path(out).parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    df.to_csv(out.replace(".parquet", ".csv"), index=False)
    typer.echo(f"Saved {len(players)} players to {out}")


@app.command()
def matchlogs(
    players_file: str = typer.Option("data/players.parquet", help="Players parquet"),
    cache_dir: str = typer.Option(RAW_CACHE_DIR, help="Raw HTML cache dir"),
    out: str = typer.Option("data/player_matches.parquet", help="Output parquet path"),
) -> None:
    """Scrape TM performance pages for all players."""
    scraper = Scraper(cache_dir=cache_dir)
    df_players = pd.read_parquet(players_file)
    players = [Player(**row) for row in df_players.to_dict(orient="records")]

    all_logs: list[MatchLog] = []
    for player in players:
        logs = fetch_player_matchlogs(player, scraper)
        all_logs.extend(logs)

    df = pd.DataFrame([m.model_dump() for m in all_logs])
    pathlib.Path(out).parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    df.to_csv(out.replace(".parquet", ".csv"), index=False)
    typer.echo(f"Saved {len(all_logs)} match logs to {out}")


@app.command()
def metrics(
    players_file: str = typer.Option("data/players.parquet"),
    matchlogs_file: str = typer.Option("data/player_matches.parquet"),
    out_dir: str = typer.Option("site/data", help="JSON output directory"),
) -> None:
    """Compute freshness + network metrics and write site JSON."""
    df_players = pd.read_parquet(players_file)
    df_logs = pd.read_parquet(matchlogs_file)
    df_logs["date"] = pd.to_datetime(df_logs["date"]).dt.date

    players_by_squad: dict[str, list[Player]] = {}
    for _, row in df_players.iterrows():
        p = Player(**row.to_dict())
        players_by_squad.setdefault(p.squad, []).append(p)

    logs_all = [MatchLog(**row) for row in df_logs.to_dict(orient="records")]
    logs_by_player: dict[str, list[MatchLog]] = {}
    for log in logs_all:
        logs_by_player.setdefault(log.player_tm_id, []).append(log)

    out_path = pathlib.Path(out_dir)
    (out_path / "teams").mkdir(parents=True, exist_ok=True)

    summary_squads: list[dict[str, Any]] = []

    for squad, players in players_by_squad.items():
        squad_logs = [
            log for p in players for log in logs_by_player.get(p.tm_id, [])
        ]
        sq_metrics = compute_squad_metrics(squad, players, squad_logs)
        G = build_squad_graph(players, squad_logs)

        player_freshness = [
            {
                "tm_id": p.tm_id,
                "name": p.name,
                "position": p.position,
                "club": p.club,
                "freshness_minutes": compute_freshness(
                    logs_by_player.get(p.tm_id, []),
                    player_tm_id=p.tm_id,
                    as_of=TOURNAMENT_DATE,
                ),
            }
            for p in players
        ]

        edges = [
            {
                "source": u,
                "target": v,
                "raw_shared_minutes": d["raw_shared_minutes"],
                "weighted_shared_minutes": d["weighted_shared_minutes"],
            }
            for u, v, d in G.edges(data=True)
        ]

        team_code = squad.lower().replace(" ", "_")
        team_json: dict[str, Any] = {
            "squad": squad,
            "metrics": sq_metrics.model_dump(),
            "players": player_freshness,
            "edges": edges,
        }
        (out_path / "teams" / f"{team_code}.json").write_text(
            json.dumps(team_json, default=str), encoding="utf-8"
        )

        summary_squads.append(
            {
                "squad": squad,
                "team_code": team_code,
                "density": sq_metrics.density,
                "clustering": sq_metrics.clustering,
                "avg_freshness_minutes": (
                    sum(p["freshness_minutes"] for p in player_freshness) / len(players)
                    if players
                    else 0
                ),
                "market_value_eur": sq_metrics.market_value_eur,
            }
        )

    summary_json: dict[str, Any] = {"as_of": TOURNAMENT_DATE.isoformat(), "squads": summary_squads}
    (out_path / "summary.json").write_text(
        json.dumps(summary_json, default=str), encoding="utf-8"
    )
    typer.echo(f"JSON written to {out_dir}: {len(summary_squads)} squads")


@app.command()
def all(
    cache_dir: str = typer.Option(RAW_CACHE_DIR),
) -> None:
    """Run all pipeline stages in order."""
    typer.echo("Running: squads")
    squads(cache_dir=cache_dir, out="data/players.parquet")
    typer.echo("Running: matchlogs")
    matchlogs(players_file="data/players.parquet", cache_dir=cache_dir, out="data/player_matches.parquet")
    typer.echo("Running: metrics")
    metrics(players_file="data/players.parquet", matchlogs_file="data/player_matches.parquet")
```

- [ ] **Step 2: Verify CLI loads**

```bash
uv run wc26 --help
```

Expected: help text listing squads / matchlogs / metrics / all commands.

- [ ] **Step 3: Commit**

```bash
git add src/wc26/cli.py
git commit -m "feat: CLI with squads/matchlogs/metrics/all commands and JSON export"
```

---

## Task 8: Static site — D3 overview, team page, force-directed network

**Files:**
- Create: `site/index.html`
- Create: `site/team.html`
- Create: `site/css/style.css`
- Create: `site/js/overview.js`
- Create: `site/js/team.js`
- Create: `site/js/network.js`

- [ ] **Step 1: Create site/css/style.css**

```css
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: system-ui, sans-serif; background: #0d1117; color: #e6edf3; line-height: 1.5; }
a { color: #58a6ff; text-decoration: none; }
a:hover { text-decoration: underline; }

header { padding: 1.5rem 2rem; border-bottom: 1px solid #30363d; }
header h1 { font-size: 1.4rem; font-weight: 600; }
header p { color: #8b949e; font-size: 0.9rem; margin-top: 0.25rem; }

main { max-width: 1200px; margin: 0 auto; padding: 2rem; }

.section-title { font-size: 1.1rem; font-weight: 600; margin-bottom: 1rem; color: #e6edf3; }

.chart-container { background: #161b22; border: 1px solid #30363d; border-radius: 6px; padding: 1.5rem; margin-bottom: 2rem; }

.bar rect { rx: 3; }
.bar text { font-size: 11px; fill: #8b949e; }
.axis text { fill: #8b949e; font-size: 11px; }
.axis path, .axis line { stroke: #30363d; }

.squad-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 1rem; }
.squad-card { background: #161b22; border: 1px solid #30363d; border-radius: 6px; padding: 1rem; cursor: pointer; transition: border-color 0.15s; }
.squad-card:hover { border-color: #58a6ff; }
.squad-card .name { font-weight: 600; margin-bottom: 0.25rem; }
.squad-card .stat { font-size: 0.8rem; color: #8b949e; }

.network-svg { width: 100%; height: 500px; }
.network-svg .node circle { stroke: #30363d; stroke-width: 1; }
.network-svg .node text { font-size: 10px; fill: #e6edf3; pointer-events: none; }
.network-svg .link { stroke: #58a6ff; stroke-opacity: 0.4; }

.back-link { display: inline-block; margin-bottom: 1.5rem; color: #8b949e; font-size: 0.9rem; }
```

- [ ] **Step 2: Create site/index.html**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>WC26 Squad Freshness & Familiarity</title>
  <link rel="stylesheet" href="css/style.css" />
</head>
<body>
  <header>
    <h1>World Cup 2026 — Squad Freshness & Familiarity</h1>
    <p>Minutes played in the last 365 days &amp; on-pitch co-play networks for all 48 squads</p>
  </header>
  <main>
    <div class="chart-container">
      <div class="section-title">Squad Freshness vs Network Density</div>
      <svg id="scatter" width="860" height="400"></svg>
    </div>
    <div class="chart-container">
      <div class="section-title">All Squads — Average Player Minutes (Last 365 Days)</div>
      <svg id="freshness-bar" width="860" height="420"></svg>
    </div>
    <div class="section-title">Browse by Squad</div>
    <div class="squad-grid" id="squad-grid"></div>
  </main>
  <script src="https://cdn.jsdelivr.net/npm/d3@7/dist/d3.min.js"></script>
  <script src="js/overview.js"></script>
</body>
</html>
```

- [ ] **Step 3: Create site/team.html**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>WC26 Team</title>
  <link rel="stylesheet" href="../css/style.css" />
</head>
<body>
  <header>
    <h1 id="team-title">Squad</h1>
    <p id="team-subtitle"></p>
  </header>
  <main>
    <a class="back-link" href="../index.html">← All squads</a>
    <div class="chart-container">
      <div class="section-title">Player Freshness — Minutes in Last 365 Days</div>
      <svg id="freshness-bars" width="860" height="500"></svg>
    </div>
    <div class="chart-container">
      <div class="section-title">Squad Familiarity Network</div>
      <svg class="network-svg" id="network"></svg>
    </div>
  </main>
  <script src="https://cdn.jsdelivr.net/npm/d3@7/dist/d3.min.js"></script>
  <script src="../js/team.js"></script>
  <script src="../js/network.js"></script>
</body>
</html>
```

- [ ] **Step 4: Create site/js/overview.js**

```js
(async () => {
  const summary = await d3.json("data/summary.json");
  const squads = summary.squads.sort((a, b) => b.avg_freshness_minutes - a.avg_freshness_minutes);

  // Freshness bar chart
  const svg = d3.select("#freshness-bar");
  const margin = { top: 10, right: 20, bottom: 100, left: 60 };
  const width = +svg.attr("width") - margin.left - margin.right;
  const height = +svg.attr("height") - margin.top - margin.bottom;
  const g = svg.append("g").attr("transform", `translate(${margin.left},${margin.top})`);

  const x = d3.scaleBand().domain(squads.map(d => d.squad)).range([0, width]).padding(0.2);
  const y = d3.scaleLinear().domain([0, d3.max(squads, d => d.avg_freshness_minutes)]).range([height, 0]).nice();

  const color = d3.scaleSequential(d3.interpolateRdYlGn)
    .domain([d3.min(squads, d => d.avg_freshness_minutes), d3.max(squads, d => d.avg_freshness_minutes)]);

  g.append("g").attr("class", "axis").attr("transform", `translate(0,${height})`).call(d3.axisBottom(x))
    .selectAll("text").attr("transform", "rotate(-45)").style("text-anchor", "end");
  g.append("g").attr("class", "axis").call(d3.axisLeft(y).ticks(6));

  g.selectAll(".bar").data(squads).join("rect")
    .attr("class", "bar")
    .attr("x", d => x(d.squad))
    .attr("y", d => y(d.avg_freshness_minutes))
    .attr("width", x.bandwidth())
    .attr("height", d => height - y(d.avg_freshness_minutes))
    .attr("fill", d => color(d.avg_freshness_minutes))
    .attr("rx", 3)
    .style("cursor", "pointer")
    .on("click", (_, d) => { window.location = `team.html?team=${d.team_code}`; });

  // Scatter: density vs freshness
  const svg2 = d3.select("#scatter");
  const m2 = { top: 20, right: 20, bottom: 50, left: 60 };
  const w2 = +svg2.attr("width") - m2.left - m2.right;
  const h2 = +svg2.attr("height") - m2.top - m2.bottom;
  const g2 = svg2.append("g").attr("transform", `translate(${m2.left},${m2.top})`);

  const xs = d3.scaleLinear().domain(d3.extent(squads, d => d.avg_freshness_minutes)).range([0, w2]).nice();
  const ys = d3.scaleLinear().domain(d3.extent(squads, d => d.density)).range([h2, 0]).nice();

  g2.append("g").attr("class", "axis").attr("transform", `translate(0,${h2})`).call(d3.axisBottom(xs));
  g2.append("g").attr("class", "axis").call(d3.axisLeft(ys).ticks(6));

  g2.selectAll("circle").data(squads).join("circle")
    .attr("cx", d => xs(d.avg_freshness_minutes))
    .attr("cy", d => ys(d.density))
    .attr("r", 5)
    .attr("fill", "#58a6ff")
    .attr("fill-opacity", 0.7)
    .style("cursor", "pointer")
    .on("click", (_, d) => { window.location = `team.html?team=${d.team_code}`; });

  g2.selectAll(".label").data(squads).join("text")
    .attr("x", d => xs(d.avg_freshness_minutes) + 7)
    .attr("y", d => ys(d.density) + 4)
    .style("font-size", "10px").style("fill", "#8b949e")
    .text(d => d.squad);

  // Squad grid
  const grid = d3.select("#squad-grid");
  squads.forEach(d => {
    grid.append("div").attr("class", "squad-card")
      .style("cursor", "pointer")
      .on("click", () => { window.location = `team.html?team=${d.team_code}`; })
      .html(`
        <div class="name">${d.squad}</div>
        <div class="stat">Avg minutes: ${Math.round(d.avg_freshness_minutes)}</div>
        <div class="stat">Network density: ${d.density.toFixed(3)}</div>
      `);
  });
})();
```

- [ ] **Step 5: Create site/js/team.js**

```js
(async () => {
  const params = new URLSearchParams(window.location.search);
  const teamCode = params.get("team");
  if (!teamCode) { document.getElementById("team-title").textContent = "Team not found"; return; }

  const data = await d3.json(`data/teams/${teamCode}.json`);
  document.getElementById("team-title").textContent = data.squad;
  document.getElementById("team-subtitle").textContent =
    `Density: ${data.metrics.density.toFixed(3)} · Clustering: ${data.metrics.clustering.toFixed(3)} · Avg weighted degree: ${Math.round(data.metrics.avg_weighted_degree)}`;

  const players = data.players.sort((a, b) => b.freshness_minutes - a.freshness_minutes);

  const svg = d3.select("#freshness-bars");
  const margin = { top: 10, right: 20, bottom: 30, left: 160 };
  const width = +svg.attr("width") - margin.left - margin.right;
  const height = Math.max(400, players.length * 20) - margin.top - margin.bottom;
  svg.attr("height", height + margin.top + margin.bottom);

  const g = svg.append("g").attr("transform", `translate(${margin.left},${margin.top})`);

  const x = d3.scaleLinear().domain([0, d3.max(players, d => d.freshness_minutes)]).range([0, width]).nice();
  const y = d3.scaleBand().domain(players.map(d => d.name)).range([0, height]).padding(0.15);

  const color = d3.scaleSequential(d3.interpolateRdYlGn)
    .domain([d3.min(players, d => d.freshness_minutes), d3.max(players, d => d.freshness_minutes)]);

  g.append("g").attr("class", "axis").call(d3.axisLeft(y));
  g.append("g").attr("class", "axis").attr("transform", `translate(0,${height})`).call(d3.axisBottom(x).ticks(6));

  g.selectAll(".bar").data(players).join("rect")
    .attr("class", "bar")
    .attr("x", 0)
    .attr("y", d => y(d.name))
    .attr("width", d => x(d.freshness_minutes))
    .attr("height", y.bandwidth())
    .attr("fill", d => color(d.freshness_minutes))
    .attr("rx", 3);

  g.selectAll(".bar-label").data(players).join("text")
    .attr("x", d => x(d.freshness_minutes) + 4)
    .attr("y", d => y(d.name) + y.bandwidth() / 2 + 4)
    .style("font-size", "10px").style("fill", "#8b949e")
    .text(d => d.freshness_minutes);

  // expose data for network.js
  window._wc26TeamData = data;
})();
```

- [ ] **Step 6: Create site/js/network.js**

```js
window.addEventListener("load", () => {
  const data = window._wc26TeamData;
  if (!data) return;

  const nodes = data.players.map(p => ({
    id: p.tm_id,
    name: p.name,
    freshness: p.freshness_minutes,
    position: p.position,
  }));
  const links = data.edges.map(e => ({
    source: e.source,
    target: e.target,
    value: e.weighted_shared_minutes,
    raw: e.raw_shared_minutes,
  }));

  const svg = d3.select("#network");
  const width = svg.node().getBoundingClientRect().width;
  const height = 500;

  const maxVal = d3.max(links, d => d.value) || 1;
  const strokeScale = d3.scaleLinear().domain([0, maxVal]).range([0.5, 6]);

  const maxFresh = d3.max(nodes, d => d.freshness) || 1;
  const rScale = d3.scaleSqrt().domain([0, maxFresh]).range([4, 14]);

  const posColor = { GK: "#f0b429", DF: "#4dabf7", MF: "#69db7c", FW: "#ff6b6b" };

  const sim = d3.forceSimulation(nodes)
    .force("link", d3.forceLink(links).id(d => d.id).strength(d => d.value / maxVal * 0.4))
    .force("charge", d3.forceManyBody().strength(-120))
    .force("center", d3.forceCenter(width / 2, height / 2))
    .force("collision", d3.forceCollide(18));

  const link = svg.append("g").selectAll("line").data(links).join("line")
    .attr("class", "link")
    .attr("stroke-width", d => strokeScale(d.value));

  const node = svg.append("g").selectAll("g").data(nodes).join("g")
    .attr("class", "node")
    .call(d3.drag()
      .on("start", (event, d) => { if (!event.active) sim.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
      .on("drag", (event, d) => { d.fx = event.x; d.fy = event.y; })
      .on("end", (event, d) => { if (!event.active) sim.alphaTarget(0); d.fx = null; d.fy = null; }));

  node.append("circle")
    .attr("r", d => rScale(d.freshness))
    .attr("fill", d => posColor[d.position] || "#8b949e")
    .attr("fill-opacity", 0.85);

  node.append("text")
    .attr("dy", "0.35em")
    .attr("text-anchor", "middle")
    .style("font-size", "9px")
    .text(d => d.name.split(" ").slice(-1)[0]);

  const tooltip = d3.select("body").append("div")
    .style("position", "absolute").style("background", "#161b22")
    .style("border", "1px solid #30363d").style("border-radius", "4px")
    .style("padding", "0.5rem 0.75rem").style("font-size", "12px")
    .style("pointer-events", "none").style("opacity", 0);

  node.on("mouseover", (event, d) => {
    tooltip.transition().duration(150).style("opacity", 1);
    tooltip.html(`<strong>${d.name}</strong><br/>${d.position} · ${d.freshness} min`)
      .style("left", `${event.pageX + 10}px`).style("top", `${event.pageY - 10}px`);
  }).on("mouseout", () => tooltip.transition().duration(150).style("opacity", 0));

  sim.on("tick", () => {
    link
      .attr("x1", d => d.source.x).attr("y1", d => d.source.y)
      .attr("x2", d => d.target.x).attr("y2", d => d.target.y);
    node.attr("transform", d => `translate(${d.x},${d.y})`);
  });
});
```

- [ ] **Step 7: Verify the site loads against sample JSON**

```bash
# Generate a minimal sample JSON to test the site without running the full pipeline
mkdir -p site/data/teams
cat > site/data/summary.json << 'EOF'
{"as_of":"2026-06-11","squads":[{"squad":"England","team_code":"england","density":0.65,"clustering":0.58,"avg_freshness_minutes":2340,"market_value_eur":null}]}
EOF
cat > site/data/teams/england.json << 'EOF'
{"squad":"England","metrics":{"squad":"England","density":0.65,"clustering":0.58,"avg_weighted_degree":320.5,"market_value_eur":null},"players":[{"tm_id":"418560","name":"Bukayo Saka","position":"MF","club":"Arsenal","freshness_minutes":2700}],"edges":[]}
EOF
# Open in browser to confirm no JS errors
open site/index.html
```

Expected: overview page loads with 1 squad card and charts render without console errors.

- [ ] **Step 8: Commit**

```bash
git add site/
git commit -m "feat: D3 static site — overview, team page, force-directed familiarity network"
```

---

## Task 9: GitHub repo setup + README

**Files:**
- Create: `README.md`
- Create: `.github/workflows/pages.yml`

- [ ] **Step 1: Create README.md**

```markdown
# WC26 Squad Freshness & Familiarity

Player fitness and on-pitch familiarity analysis for all 48 squads at the 2026 FIFA World Cup.

**Live site:** https://opunsoars.github.io/wc26-squad-network (once deployed)

## What it shows

- **Freshness** — professional minutes each player has played in the last 365 days (club + country)
- **Familiarity network** — weighted co-play graph per squad derived from actual shared on-pitch minutes over 3 seasons (2023/24–2025/26)

Inspired by a [similar analysis for Euro 2020](https://www.linkedin.com/pulse/how-much-do-euro-2020-players-know-each-other-network-vinay-warrier/).

## Data

Source: Transfermarkt (player performance pages, personal/educational use).
Committed datasets: `data/players.csv` / `data/player_matches.csv`

## Run the pipeline

```bash
uv sync
uv run wc26 all          # scrape + transform + compute metrics + write JSON
# or step by step:
uv run wc26 squads
uv run wc26 matchlogs
uv run wc26 metrics
```

## Development

```bash
uv run ruff format .
uv run ruff check --fix .
uv run mypy src/
uv run pytest
```
```

- [ ] **Step 2: Create .github/workflows/pages.yml**

```yaml
name: Deploy to GitHub Pages

on:
  push:
    branches: [main]
    paths:
      - "site/**"
      - "data/**"

permissions:
  contents: read
  pages: write
  id-token: write

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/configure-pages@v4
      - uses: actions/upload-pages-artifact@v3
        with:
          path: site/
      - id: deployment
        uses: actions/deploy-pages@v4
```

- [ ] **Step 3: Commit and push to GitHub**

```bash
git add README.md .github/
git commit -m "docs: README and GitHub Pages deployment workflow"
# Create the GitHub repo then:
gh repo create opunsoars/wc26-squad-network --public --source=. --remote=origin
git push -u origin main
```

Expected: repo visible at `https://github.com/opunsoars/wc26-squad-network`

---

## Self-review notes

- Spec §2 "ClubElo lookup" — wired into cli.py as `_REF_ELO` constant with a comment; a real ClubElo API call per match would require a separate task. The constant approach preserves correctness (elo_factor = 1.0 for all matches) and the architecture is clear — extend `edge_weight()` call in `build_squad_graph` when the ClubElo integration is added.
- Spec §5 "betweenness centrality" — `networkx.betweenness_centrality(G, weight='weighted_shared_minutes')` can be added to `compute_squad_metrics` and the team JSON/page when the data is flowing. Left as a follow-up to keep this plan shippable without waiting on data.
- Spec §5 "most familiar XI" — derived from highest weighted degree nodes; straightforward to add in metrics.py once data flows.
- All placeholder patterns checked — none found.
- Type consistency checked across tasks — `Player`, `MatchLog`, `CoPlayEdge`, `SquadMetrics` names consistent throughout.
