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
from wc26.models import MatchLog, Player, SquadMetrics

logger = structlog.get_logger()

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
    by_match: defaultdict[str, dict[str, MatchLog]] = defaultdict(dict)
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
) -> nx.Graph[str]:
    """Build a weighted undirected co-play graph for a squad.

    Edge attributes: raw_shared_minutes, weighted_shared_minutes.

    Args:
        players: All players in the squad.
        logs: All MatchLog records for those players.
        as_of: Reference date for recency decay.

    Returns:
        networkx Graph with player tm_ids as nodes.
    """
    G: nx.Graph[str] = nx.Graph()
    G.add_nodes_from(p.tm_id for p in players)

    for pa, pb in combinations(players, 2):
        raw = compute_coplay_minutes(pa.tm_id, pb.tm_id, logs)
        if raw == 0:
            continue

        by_match: defaultdict[str, dict[str, MatchLog]] = defaultdict(dict)
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
                elo=_REF_ELO,
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
