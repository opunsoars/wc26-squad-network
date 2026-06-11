"""DuckDB-backed persistent store for players and match logs.

Single file, single responsibility: owns schema creation, upserts, and queries.
All other modules import from here — no other module touches DuckDB directly.
"""

from __future__ import annotations

import datetime
import pathlib

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
    player_tm_id   VARCHAR NOT NULL,
    match_id       VARCHAR NOT NULL,
    date           DATE    NOT NULL,
    competition    VARCHAR NOT NULL,
    team           VARCHAR NOT NULL,
    opponent       VARCHAR NOT NULL,
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
              Pass a tmp_path string for an isolated test store.
    """

    def __init__(self, path: str = "data/wc26.duckdb") -> None:
        if path != ":memory:":
            pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = duckdb.connect(path)
        self._init_schema()
        logger.debug("store_opened", path=path)

    def _init_schema(self) -> None:
        self._conn.execute(_PLAYERS_DDL)
        self._conn.execute(_MATCH_LOGS_DDL)

    def upsert_players(self, players: list[Player]) -> None:
        """Insert or replace players by tm_id (primary key).

        Args:
            players: List of Player objects to persist.
        """
        rows = [(p.tm_id, p.name, p.squad, p.position, p.club, p.market_value_eur) for p in players]
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
        """Return all match logs ordered by date then player.

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
        """Return tm_ids of players who already have match logs stored.

        Used by the matchlogs pipeline to skip already-processed players
        when resuming an interrupted run.

        Returns:
            Set of tm_id strings.
        """
        rows = self._conn.execute("SELECT DISTINCT player_tm_id FROM match_logs").fetchall()
        return {r[0] for r in rows}

    def close(self) -> None:
        """Close the DuckDB connection."""
        self._conn.close()
        logger.debug("store_closed")

    def __enter__(self) -> Store:
        """Support ``with Store(...) as store:`` for short-lived open/close."""
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
