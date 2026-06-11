"""Match-log orchestration: render + parse across the familiarity seasons.

Ties together the Playwright rendering layer (:mod:`wc26.pipeline.browser`) and
the pure parser (:mod:`wc26.pipeline.transform`) to produce a player's complete
match log over the configured familiarity window.
"""

from __future__ import annotations

import structlog

from wc26.config import FAMILIARITY_SEASONS, RAW_CACHE_DIR
from wc26.models import MatchLog, Player
from wc26.pipeline.browser import render_tm_performance
from wc26.pipeline.transform import parse_tm_performance_page

logger = structlog.get_logger()


def fetch_player_matchlogs(
    player: Player,
    cache_dir: str = RAW_CACHE_DIR,
    *,
    headless: bool = True,
) -> list[MatchLog]:
    """Fetch and parse all match logs for a player across familiarity seasons.

    For each season in :data:`wc26.config.FAMILIARITY_SEASONS`, renders the
    player's detailed-performance page (cached) and parses the rendered HTML
    into :class:`~wc26.models.MatchLog` objects. Players without a resolved
    Transfermarkt id are skipped with a warning.

    Args:
        player: The player to fetch logs for; must have a non-empty ``tm_id``.
        cache_dir: Directory for cached rendered HTML.
        headless: Whether to run Chromium headless.

    Returns:
        A flat list of match logs across all familiarity seasons. Empty if the
        player has no ``tm_id``.
    """
    if not player.tm_id:
        logger.warning("skip_player_no_tm_id", name=player.name, squad=player.squad)
        return []

    logs: list[MatchLog] = []
    for season in FAMILIARITY_SEASONS:
        season_code = season[:4]
        html = render_tm_performance(
            tm_id=player.tm_id,
            player_name=player.name,
            season_code=season_code,
            cache_dir=cache_dir,
            headless=headless,
        )
        season_logs = parse_tm_performance_page(
            rendered_html=html,
            player_tm_id=player.tm_id,
            season=season,
        )
        logs.extend(season_logs)
        logger.info(
            "fetched_season_matchlogs",
            name=player.name,
            tm_id=player.tm_id,
            season=season,
            match_count=len(season_logs),
        )

    logger.info(
        "fetched_player_matchlogs",
        name=player.name,
        tm_id=player.tm_id,
        total=len(logs),
    )
    return logs
