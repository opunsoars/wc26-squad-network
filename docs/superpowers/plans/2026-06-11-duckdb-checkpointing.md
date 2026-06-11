# DuckDB Checkpointing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the all-or-nothing parquet writes with a DuckDB-backed store that appends per-player rows immediately and allows `wc26 matchlogs --resume` to skip already-processed players.

**Architecture:** A new `src/wc26/store.py` module owns all DuckDB reads/writes and is the single place that knows the schema. The CLI commands (`squads`, `matchlogs`, `metrics`) are updated to call the store instead of writing parquet at the end. Parquet export is kept as an opt-in `wc26 export` command for the committed datasets. The DuckDB file (`data/wc26.duckdb`) is gitignored during active runs; the final clean export (parquet + CSV) is what gets committed.

**Tech Stack:** `duckdb>=1.0`, existing `pydantic`, `typer`, `structlog`, `pandas` (kept for metrics step), `pytest`.

---

## File Map

```
src/wc26/
├── store.py          # NEW — DuckDB open/init/upsert/query; all schema knowledge lives here
└── cli.py            # MODIFY — squads/matchlogs/metrics/all commands use store; add export cmd

tests/
└── test_store.py     # NEW — unit tests for store layer
```

`.gitignore` — add `data/wc26.duckdb`

`pyproject.toml` — add `duckdb>=1.0`

---

## Task 1: Add duckdb dependency

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add duckdb to project dependencies**

Edit `pyproject.toml` — add `"duckdb>=1.0"` to the `dependencies` list:

```toml
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
    "playwright>=1.60.0",
    "duckdb>=1.0",
]
```

- [ ] **Step 2: Sync the environment**

```bash
uv sync
```

Expected: duckdb downloaded and installed, no errors.

- [ ] **Step 3: Add duckdb to gitignore**

Add to `.gitignore`:

```
data/wc26.duckdb
data/wc26.duckdb.wal
```

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock .gitignore
git commit -m "chore: add duckdb dependency and gitignore db file"
```

---

## Task 2: Store module — schema + upsert + query

**Files:**
- Create: `src/wc26/store.py`
- Create: `tests/test_store.py`

### Step 1: Write failing tests first

- [ ] **Step 1: Create `tests/test_store.py`**

```python
from __future__ import annotations

import datetime
import pathlib

import pytest

from wc26.models import MatchLog, Player
from wc26.store import Store


@pytest.fixture()
def db(tmp_path: pathlib.Path) -> Store:
    return Store(str(tmp_path / "test.duckdb"))


def test_upsert_players_and_read_back(db: Store) -> None:
    players = [
        Player(name="Bukayo Saka", squad="England", position="MF", club="Arsenal", tm_id="433177"),
        Player(name="Harry Kane", squad="England", position="FW", club="Bayern Munich", tm_id="132098"),
    ]
    db.upsert_players(players)
    result = db.all_players()
    assert len(result) == 2
    assert {p.tm_id for p in result} == {"433177", "132098"}


def test_upsert_players_is_idempotent(db: Store) -> None:
    player = Player(name="Bukayo Saka", squad="England", position="MF", club="Arsenal", tm_id="433177")
    db.upsert_players([player])
    db.upsert_players([player])  # second upsert — must not duplicate
    assert len(db.all_players()) == 1


def test_append_match_logs_and_read_back(db: Store) -> None:
    logs = [
        MatchLog(
            player_tm_id="433177",
            match_id="tm_2025-10-01_arsenal_wolves",
            date=datetime.date(2025, 10, 1),
            competition="Premier League",
            team="Arsenal",
            opponent="Wolves",
            minutes_played=90,
            sub_on_minute=None,
            sub_off_minute=None,
        )
    ]
    db.append_match_logs(logs)
    result = db.all_match_logs()
    assert len(result) == 1
    assert result[0].player_tm_id == "433177"
    assert result[0].minutes_played == 90


def test_processed_tm_ids_empty_when_no_logs(db: Store) -> None:
    assert db.processed_tm_ids() == set()


def test_processed_tm_ids_after_append(db: Store) -> None:
    logs = [
        MatchLog(
            player_tm_id="433177",
            match_id="tm_2025-10-01_arsenal_wolves",
            date=datetime.date(2025, 10, 1),
            competition="Premier League",
            team="Arsenal",
            opponent="Wolves",
            minutes_played=90,
            sub_on_minute=None,
            sub_off_minute=None,
        )
    ]
    db.append_match_logs(logs)
    assert db.processed_tm_ids() == {"433177"}


def test_append_match_logs_deduplicates_by_player_match(db: Store) -> None:
    log = MatchLog(
        player_tm_id="433177",
        match_id="tm_2025-10-01_arsenal_wolves",
        date=datetime.date(2025, 10, 1),
        competition="Premier League",
        team="Arsenal",
        opponent="Wolves",
        minutes_played=90,
        sub_on_minute=None,
        sub_off_minute=None,
    )
    db.append_match_logs([log])
    db.append_match_logs([log])  # duplicate — must not double-insert
    assert len(db.all_match_logs()) == 1
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
uv run pytest tests/test_store.py -v
```

Expected: `ModuleNotFoundError: No module named 'wc26.store'`

### Step 3: Implement `src/wc26/store.py`

- [ ] **Step 3: Create `src/wc26/store.py`**

```python
"""DuckDB-backed persistent store for players and match logs.

Single file, single responsibility: owns schema creation, upserts, and queries.
All other modules import from here — no other module touches DuckDB directly.
"""

from __future__ import annotations

import datetime

import duckdb
import structlog

from wc26.models import MatchLog, Player

logger = structlog.get_logger()

_PLAYERS_DDL = """
CREATE TABLE IF NOT EXISTS players (
    tm_id            VARCHAR PRIMARY KEY,
    name             VARCHAR NOT NULL,
    squad            VARCHAR NOT NULL,
    position         VARCHAR NOT NULL,
    club             VARCHAR NOT NULL,
    market_value_eur BIGINT
)
"""

_MATCH_LOGS_DDL = """
CREATE TABLE IF NOT EXISTS match_logs (
    player_tm_id  VARCHAR NOT NULL,
    match_id      VARCHAR NOT NULL,
    date          DATE    NOT NULL,
    competition   VARCHAR NOT NULL,
    team          VARCHAR NOT NULL,
    opponent      VARCHAR NOT NULL,
    minutes_played INTEGER NOT NULL,
    sub_on_minute  INTEGER,
    sub_off_minute INTEGER,
    PRIMARY KEY (player_tm_id, match_id)
)
"""


class Store:
    """Persistent DuckDB store for the WC26 pipeline.

    All read/write access to players and match_logs goes through this class.
    The underlying DuckDB file is created on first open; subsequent opens
    reuse the existing schema and data.

    Args:
        path: Filesystem path to the DuckDB file (e.g. ``"data/wc26.duckdb"``).
              Pass ``":memory:"`` for an in-process, non-persistent store
              (useful in tests).
    """

    def __init__(self, path: str = "data/wc26.duckdb") -> None:
        import pathlib

        if path != ":memory:":
            pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = duckdb.connect(path)
        self._init_schema()
        logger.debug("store_opened", path=path)

    def _init_schema(self) -> None:
        self._conn.execute(_PLAYERS_DDL)
        self._conn.execute(_MATCH_LOGS_DDL)

    # ------------------------------------------------------------------
    # Players
    # ------------------------------------------------------------------

    def upsert_players(self, players: list[Player]) -> None:
        """Insert or replace players by tm_id (primary key).

        Args:
            players: List of Player objects to persist.
        """
        rows = [
            (
                p.tm_id,
                p.name,
                p.squad,
                p.position,
                p.club,
                p.market_value_eur,
            )
            for p in players
        ]
        self._conn.executemany(
            """
            INSERT OR REPLACE INTO players
                (tm_id, name, squad, position, club, market_value_eur)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        logger.info("players_upserted", count=len(rows))

    def all_players(self) -> list[Player]:
        """Return all players in insertion order.

        Returns:
            List of Player objects.
        """
        rows = self._conn.execute(
            "SELECT tm_id, name, squad, position, club, market_value_eur FROM players"
        ).fetchall()
        return [
            Player(
                tm_id=r[0],
                name=r[1],
                squad=r[2],
                position=r[3],
                club=r[4],
                market_value_eur=r[5],
            )
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Match logs
    # ------------------------------------------------------------------

    def append_match_logs(self, logs: list[MatchLog]) -> None:
        """Append match logs, ignoring duplicates (same player_tm_id + match_id).

        Args:
            logs: Match log records to persist.
        """
        rows = [
            (
                log.player_tm_id,
                log.match_id,
                log.date.isoformat(),
                log.competition,
                log.team,
                log.opponent,
                log.minutes_played,
                log.sub_on_minute,
                log.sub_off_minute,
            )
            for log in logs
        ]
        self._conn.executemany(
            """
            INSERT OR IGNORE INTO match_logs
                (player_tm_id, match_id, date, competition, team, opponent,
                 minutes_played, sub_on_minute, sub_off_minute)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        logger.info("match_logs_appended", count=len(rows))

    def all_match_logs(self) -> list[MatchLog]:
        """Return all match logs.

        Returns:
            List of MatchLog objects.
        """
        rows = self._conn.execute(
            """
            SELECT player_tm_id, match_id, date, competition, team, opponent,
                   minutes_played, sub_on_minute, sub_off_minute
            FROM match_logs
            ORDER BY date, player_tm_id
            """
        ).fetchall()
        return [
            MatchLog(
                player_tm_id=r[0],
                match_id=r[1],
                date=datetime.date.fromisoformat(str(r[2])),
                competition=r[3],
                team=r[4],
                opponent=r[5],
                minutes_played=r[6],
                sub_on_minute=r[7],
                sub_off_minute=r[8],
            )
            for r in rows
        ]

    def processed_tm_ids(self) -> set[str]:
        """Return the set of player tm_ids that already have match logs stored.

        Used by the matchlogs pipeline to skip already-processed players
        when resuming an interrupted run.

        Returns:
            Set of tm_id strings.
        """
        rows = self._conn.execute(
            "SELECT DISTINCT player_tm_id FROM match_logs"
        ).fetchall()
        return {r[0] for r in rows}

    def close(self) -> None:
        """Close the DuckDB connection."""
        self._conn.close()
        logger.debug("store_closed")
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
uv run pytest tests/test_store.py -v
```

Expected: 6 PASSED.

- [ ] **Step 5: Run full suite to check nothing broke**

```bash
uv run pytest --tb=short -q
```

Expected: all existing tests still pass + 6 new ones.

- [ ] **Step 6: Run quality gate**

```bash
uv run ruff format src/wc26/store.py tests/test_store.py
uv run ruff check --fix src/wc26/store.py tests/test_store.py
uv run mypy --strict src/wc26/
```

Fix any issues before committing. Common mypy note: duckdb stubs may be absent — if mypy reports `import-untyped` for duckdb, add `"types-duckdb"` to dev deps in pyproject.toml and `uv sync`, OR add `# type: ignore[import-untyped]` on the duckdb import line.

- [ ] **Step 7: Commit**

```bash
git add src/wc26/store.py tests/test_store.py pyproject.toml uv.lock
git commit -m "feat: DuckDB store with upsert, append, and processed-id checkpoint"
```

---

## Task 3: Wire CLI commands to the store

**Files:**
- Modify: `src/wc26/cli.py`

The three changes:
1. `squads` command: call `store.upsert_players()` instead of writing parquet.
2. `matchlogs` command: add `--resume` flag; read players from store; append per-player immediately; skip `processed_tm_ids()` when `--resume`.
3. `metrics` command: read from `store.all_players()` / `store.all_match_logs()` instead of parquet.
4. New `export` command: write `data/players.parquet`, `data/players.csv`, `data/player_matches.parquet`, `data/player_matches.csv` from the store (for committing clean datasets).

- [ ] **Step 1: Rewrite `src/wc26/cli.py`**

Replace the entire file with:

```python
"""CLI entry-point for the WC26 squad freshness & familiarity pipeline."""

from __future__ import annotations

import json
import pathlib
from typing import Any

import pandas as pd
import structlog
import typer

from wc26.config import RAW_CACHE_DIR, TOURNAMENT_DATE
from wc26.pipeline.matchlogs import fetch_player_matchlogs
from wc26.pipeline.metrics import build_squad_graph, compute_freshness, compute_squad_metrics
from wc26.pipeline.squads import build_players_dataset
from wc26.scraper import Scraper
from wc26.store import Store

app = typer.Typer(help="WC26 squad freshness & familiarity pipeline")
logger = structlog.get_logger()

_DEFAULT_DB = "data/wc26.duckdb"


@app.command()
def squads(
    cache_dir: str = typer.Option(RAW_CACHE_DIR, help="Raw HTML cache dir"),
    db: str = typer.Option(_DEFAULT_DB, help="DuckDB file path"),
) -> None:
    """Scrape squad lists, resolve Transfermarkt IDs, and save to DuckDB."""
    scraper = Scraper(cache_dir=cache_dir)
    players = build_players_dataset(scraper)
    store = Store(db)
    store.upsert_players(players)
    store.close()
    typer.echo(f"Saved {len(players)} players to {db}")


@app.command()
def matchlogs(
    cache_dir: str = typer.Option(RAW_CACHE_DIR, help="Raw HTML cache dir"),
    db: str = typer.Option(_DEFAULT_DB, help="DuckDB file path"),
    headless: bool = typer.Option(True, help="Run Chromium headless"),
    resume: bool = typer.Option(False, "--resume", help="Skip players already in DB"),
) -> None:
    """Render TM performance pages and append match logs to DuckDB.

    Use --resume to continue an interrupted run without re-scraping
    players whose logs are already stored.
    """
    store = Store(db)
    all_players = store.all_players()

    if resume:
        done = store.processed_tm_ids()
        players = [p for p in all_players if p.tm_id not in done]
        typer.echo(f"Resuming: {len(done)} already done, {len(players)} remaining")
    else:
        players = all_players

    total_new = 0
    for i, player in enumerate(players, 1):
        logs = fetch_player_matchlogs(player, cache_dir=cache_dir, headless=headless)
        if logs:
            store.append_match_logs(logs)
            total_new += len(logs)
        typer.echo(f"[{i}/{len(players)}] {player.name} ({player.squad}): {len(logs)} rows")

    store.close()
    typer.echo(f"Done. {total_new} new match-log rows written to {db}")


@app.command()
def metrics(
    db: str = typer.Option(_DEFAULT_DB, help="DuckDB file path"),
    out_dir: str = typer.Option("site/data", help="JSON output directory"),
) -> None:
    """Compute freshness + network metrics and write site JSON."""
    store = Store(db)
    all_players = store.all_players()
    all_logs = store.all_match_logs()
    store.close()

    players_by_squad: dict[str, list] = {}
    for p in all_players:
        players_by_squad.setdefault(p.squad, []).append(p)

    logs_by_player: dict[str, list] = {}
    for log in all_logs:
        logs_by_player.setdefault(log.player_tm_id, []).append(log)

    out_path = pathlib.Path(out_dir)
    (out_path / "teams").mkdir(parents=True, exist_ok=True)

    summary_squads: list[dict[str, Any]] = []

    for squad, players in players_by_squad.items():
        squad_logs = [log for p in players for log in logs_by_player.get(p.tm_id, [])]
        sq_metrics = compute_squad_metrics(squad, players, squad_logs)
        G = build_squad_graph(players, squad_logs)

        player_freshness: list[dict[str, Any]] = [
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

        edges: list[dict[str, Any]] = [
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

    summary_json: dict[str, Any] = {
        "as_of": TOURNAMENT_DATE.isoformat(),
        "squads": summary_squads,
    }
    (out_path / "summary.json").write_text(
        json.dumps(summary_json, default=str), encoding="utf-8"
    )
    typer.echo(f"JSON written to {out_dir}: {len(summary_squads)} squads")


@app.command()
def export(
    db: str = typer.Option(_DEFAULT_DB, help="DuckDB file path"),
    out_dir: str = typer.Option("data", help="Output directory for parquet/CSV files"),
) -> None:
    """Export DuckDB contents to parquet + CSV for committing to the repo."""
    store = Store(db)
    players = store.all_players()
    logs = store.all_match_logs()
    store.close()

    out = pathlib.Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    df_players = pd.DataFrame([p.model_dump() for p in players])
    df_players.to_parquet(out / "players.parquet", index=False)
    df_players.to_csv(out / "players.csv", index=False)

    df_logs = pd.DataFrame([m.model_dump() for m in logs])
    df_logs.to_parquet(out / "player_matches.parquet", index=False)
    df_logs.to_csv(out / "player_matches.csv", index=False)

    typer.echo(
        f"Exported {len(players)} players and {len(logs)} match logs to {out_dir}/"
    )


@app.command(name="all")
def run_all(
    cache_dir: str = typer.Option(RAW_CACHE_DIR),
    db: str = typer.Option(_DEFAULT_DB),
    resume: bool = typer.Option(False, "--resume"),
) -> None:
    """Run all pipeline stages in order (squads → matchlogs → metrics → export)."""
    typer.echo("Running: squads")
    squads(cache_dir=cache_dir, db=db)
    typer.echo("Running: matchlogs")
    matchlogs(cache_dir=cache_dir, db=db, headless=True, resume=resume)
    typer.echo("Running: metrics")
    metrics(db=db, out_dir="site/data")
    typer.echo("Running: export")
    export(db=db, out_dir="data")
```

- [ ] **Step 2: Verify CLI help**

```bash
uv run wc26 --help
```

Expected output — five commands listed:

```
Commands:
  squads     Scrape squad lists, resolve TM IDs, and save to DuckDB.
  matchlogs  Render TM performance pages and append match logs to DuckDB.
  metrics    Compute freshness + network metrics and write site JSON.
  export     Export DuckDB contents to parquet + CSV for committing.
  all        Run all pipeline stages in order.
```

- [ ] **Step 3: Verify each subcommand help**

```bash
uv run wc26 matchlogs --help
```

Expected: `--resume` flag visible in the options list.

- [ ] **Step 4: Run quality gate**

```bash
uv run ruff format src/wc26/cli.py
uv run ruff check --fix src/wc26/cli.py
uv run mypy --strict src/wc26/
uv run pytest --tb=short -q
```

All 33 tests should pass (27 existing + 6 store tests). Fix any issues.

- [ ] **Step 5: Commit**

```bash
git add src/wc26/cli.py
git commit -m "feat: wire CLI to DuckDB store — squads/matchlogs/metrics/export/all with --resume"
```

---

## Self-Review

**Spec coverage:**
- ✅ DuckDB replaces all-or-nothing parquet write
- ✅ Per-player append immediately after parsing
- ✅ `--resume` skips already-processed TM IDs via `processed_tm_ids()`
- ✅ Parquet/CSV export kept as opt-in `wc26 export` for committing datasets
- ✅ `wc26 all --resume` threads the flag through
- ✅ DuckDB file gitignored

**Placeholder scan:** none found — all steps contain actual code.

**Type consistency:**
- `Store.upsert_players(players: list[Player])` — called as `store.upsert_players(players)` in cli.py ✅
- `Store.append_match_logs(logs: list[MatchLog])` — called as `store.append_match_logs(logs)` ✅
- `Store.processed_tm_ids() -> set[str]` — used in set comprehension filter ✅
- `Store.all_players() -> list[Player]` and `Store.all_match_logs() -> list[MatchLog]` — used directly in metrics ✅
