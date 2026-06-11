from __future__ import annotations

import datetime

from wc26.models import CoPlayEdge, MatchLog, Player, SquadMetrics


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
