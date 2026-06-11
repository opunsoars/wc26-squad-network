"""Match-log fetching via the Transfermarkt internal JSON API.

The ``<tm-player-performance-proxy>`` web component calls
``https://tmapi.transfermarkt.technology/player/{id}/performance-game``
on page load. This module hits that endpoint directly with httpx —
no browser rendering needed.

Returns the player's full career history in one request; we then filter
to the familiarity window (``FAMILIARITY_SEASONS``) locally.
"""

from __future__ import annotations

import datetime
import json

import httpx
import structlog

from wc26.config import FAMILIARITY_SEASONS, RAW_CACHE_DIR, REQUEST_DELAY_SECONDS
from wc26.models import MatchLog, Player
from wc26.scraper import Scraper

logger = structlog.get_logger()

_TMAPI_URL = "https://tmapi.transfermarkt.technology/player/{tm_id}/performance-game"

# Seasons we care about, as integer starting years e.g. 2023, 2024, 2025.
_SEASON_YEARS: frozenset[int] = frozenset(int(s.split("/")[0]) for s in FAMILIARITY_SEASONS)

# Competition-ID → display name for the tier-weight lookup.
_COMP_ID_TO_NAME: dict[str, str] = {
    "CL": "UEFA Champions League",
    "EL": "UEFA Europa League",
    "UECL": "UEFA Europa Conference League",
    "WMQ6": "FIFA World Cup",
    "WCUP": "FIFA World Cup",
    "EM": "UEFA European Championship",
    "COPA": "Copa America",
    "AFCON": "AFCON",
    "GB1": "Premier League",
    "L1": "La Liga",
    "L2": "Ligue 1",
    "A1": "Serie A",
    "L3": "Bundesliga",
    "NL1": "Eredivisie",
    "PO1": "Primeira Liga",
}


def _competition_name(comp_id: str) -> str:
    """Return a display name for a TM competition ID, falling back to the raw ID."""
    return _COMP_ID_TO_NAME.get(comp_id, comp_id)


def _parse_games(raw_games: list[dict[str, object]], player_tm_id: str) -> list[MatchLog]:
    """Convert raw API game dicts to MatchLog objects, filtering to our window.

    Args:
        raw_games: List of game dicts from the ``data.performance`` field.
        player_tm_id: Transfermarkt id of the player.

    Returns:
        Filtered list of :class:`~wc26.models.MatchLog` objects.
    """
    logs: list[MatchLog] = []

    for game in raw_games:
        game_info = game.get("gameInformation") or {}
        season_id = game_info.get("seasonId")
        if season_id not in _SEASON_YEARS:
            continue

        stats = game.get("statistics") or {}
        playing_time = stats.get("playingTimeStatistics") or {}
        played_minutes = playing_time.get("playedMinutes")
        if not played_minutes or int(played_minutes) <= 0:
            continue

        date_raw = (game_info.get("date") or {}).get("dateTimeUTC", "")
        if not date_raw:
            continue
        try:
            date = datetime.date.fromisoformat(str(date_raw)[:10])
        except ValueError:
            continue

        comp_id = str(game_info.get("competitionId") or "")
        competition = _competition_name(comp_id)

        game_id = str(game_info.get("gameId") or "")
        match_id = f"tm_{date.isoformat()}_{game_id}"

        clubs = game.get("clubsInformation") or {}
        team_id = str((clubs.get("club") or {}).get("clubId") or "")
        opponent_id = str((clubs.get("opponent") or {}).get("clubId") or "")

        is_starting: bool = bool(playing_time.get("isStarting", True))
        sub_on: int | None = None
        sub_off: int | None = None

        if not is_starting:
            sub_in = playing_time.get("substitutedIn") or {}
            minute_in = sub_in.get("minute")
            if minute_in is not None:
                sub_on = int(minute_in)

        sub_out_data = playing_time.get("substitutedOut") or {}
        minute_out = sub_out_data.get("minute")
        if minute_out is not None:
            sub_off = int(minute_out)

        # Ensure on_minute < off_minute to satisfy the model validator.
        on = sub_on if sub_on is not None else 0
        off = sub_off if sub_off is not None else min(int(played_minutes), 90)
        if on >= off:
            off = on + 1

        try:
            log = MatchLog(
                player_tm_id=player_tm_id,
                match_id=match_id,
                date=date,
                competition=competition,
                team=team_id,
                opponent=opponent_id,
                minutes_played=int(played_minutes),
                sub_on_minute=sub_on,
                sub_off_minute=sub_off,
            )
        except ValueError as exc:
            logger.debug("skip_invalid_match_log", player_tm_id=player_tm_id, error=str(exc))
            continue

        logs.append(log)

    return logs


def fetch_player_matchlogs(
    player: Player,
    cache_dir: str = RAW_CACHE_DIR,
    *,
    headless: bool = True,  # unused; kept for CLI backward compat
) -> list[MatchLog]:
    """Fetch all match logs for a player via the TM internal JSON API.

    One HTTP request per player returns the full career history; we filter
    locally to :data:`~wc26.config.FAMILIARITY_SEASONS`.

    Args:
        player: The player to fetch; must have a non-empty ``tm_id``.
        cache_dir: Directory for the HTTP cache (shared with the scraper).
        headless: Unused; kept for backward compatibility with the CLI.

    Returns:
        A flat list of :class:`~wc26.models.MatchLog` objects filtered to
        the familiarity seasons. Empty if the player has no ``tm_id``.
    """
    if not player.tm_id:
        logger.warning("skip_player_no_tm_id", name=player.name, squad=player.squad)
        return []

    url = _TMAPI_URL.format(tm_id=player.tm_id)
    scraper = Scraper(cache_dir=cache_dir, delay_seconds=REQUEST_DELAY_SECONDS)

    try:
        raw = scraper.fetch(url)
    except httpx.HTTPStatusError as exc:
        logger.warning("tmapi_http_error", tm_id=player.tm_id, status=exc.response.status_code)
        return []
    except httpx.RequestError as exc:
        logger.warning("tmapi_request_error", tm_id=player.tm_id, error=str(exc))
        return []

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("tmapi_bad_json", tm_id=player.tm_id)
        return []

    games: list[dict[str, object]] = (payload.get("data") or {}).get("performance") or []
    logs = _parse_games(games, player.tm_id)

    logger.info(
        "fetched_player_matchlogs",
        name=player.name,
        tm_id=player.tm_id,
        total_games=len(games),
        filtered_logs=len(logs),
    )
    return logs
