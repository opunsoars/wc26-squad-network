from __future__ import annotations

import datetime

from wc26.models import MatchLog, Player
from wc26.pipeline.metrics import (
    build_squad_graph,
    compute_coplay_minutes,
    compute_freshness,
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


def test_compute_freshness_sums_last_365_days() -> None:
    cutoff = datetime.date(2026, 6, 11)
    logs = [
        _make_log("p1", "m1", datetime.date(2026, 5, 1), 90),  # in window
        _make_log("p1", "m2", datetime.date(2025, 7, 1), 90),  # in window (just)
        _make_log("p1", "m3", datetime.date(2025, 6, 1), 60),  # outside window
    ]
    total = compute_freshness(logs, player_tm_id="p1", as_of=cutoff)
    assert total == 180


def test_compute_coplay_minutes_full_overlap() -> None:
    logs = [
        _make_log("p1", "m1", datetime.date(2025, 10, 1), 90),
        _make_log("p2", "m1", datetime.date(2025, 10, 1), 90),
    ]
    shared = compute_coplay_minutes("p1", "p2", logs)
    assert shared == 90


def test_compute_coplay_minutes_partial_overlap() -> None:
    # p1 plays 0-90, p2 plays 60-90 (sub on at 60)
    logs = [
        _make_log("p1", "m1", datetime.date(2025, 10, 1), 90),
        _make_log("p2", "m1", datetime.date(2025, 10, 1), 30, sub_on=60),
    ]
    shared = compute_coplay_minutes("p1", "p2", logs)
    assert shared == 30


def test_compute_coplay_minutes_no_shared_match() -> None:
    logs = [
        _make_log("p1", "m1", datetime.date(2025, 10, 1), 90),
        _make_log("p2", "m2", datetime.date(2025, 10, 2), 90),  # different match
    ]
    shared = compute_coplay_minutes("p1", "p2", logs)
    assert shared == 0


def test_edge_weight_decays_with_time() -> None:
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


def test_build_squad_graph_nodes_and_edges() -> None:
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


def test_compute_squad_metrics_density() -> None:
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
