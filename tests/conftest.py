from __future__ import annotations

import datetime

import pytest

from wc26.models import MatchLog, Player


@pytest.fixture()
def sample_player() -> Player:
    """Return a sample Player for use in tests."""
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
    """Return a sample MatchLog for use in tests."""
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
