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
        Player(
            name="Harry Kane", squad="England", position="FW", club="Bayern Munich", tm_id="132098"
        ),
    ]
    db.upsert_players(players)
    result = db.all_players()
    assert len(result) == 2
    assert {p.tm_id for p in result} == {"433177", "132098"}


def test_upsert_players_is_idempotent(db: Store) -> None:
    player = Player(
        name="Bukayo Saka", squad="England", position="MF", club="Arsenal", tm_id="433177"
    )
    db.upsert_players([player])
    db.upsert_players([player])
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
    db.append_match_logs([log])
    assert len(db.all_match_logs()) == 1
