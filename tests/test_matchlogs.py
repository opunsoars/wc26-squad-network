"""Tests for the JSON API-based matchlogs pipeline."""

from __future__ import annotations

import datetime

from wc26.pipeline.matchlogs import _parse_games


def _game(
    game_id: str = "123",
    season_id: int = 2024,
    date_utc: str = "2025-01-15T20:00:00+00:00",
    played_minutes: int = 90,
    is_starting: bool = True,
    sub_out_minute: int | None = None,
    sub_in_minute: int | None = None,
    comp_id: str = "CL",
    club_id: str = "11",
    opponent_id: str = "22",
) -> dict:
    playing_time: dict = {
        "playedMinutes": played_minutes,
        "isStarting": is_starting,
    }
    if sub_out_minute is not None:
        playing_time["substitutedOut"] = {"minute": sub_out_minute}
    if sub_in_minute is not None:
        playing_time["substitutedIn"] = {"minute": sub_in_minute}

    return {
        "gameInformation": {
            "gameId": game_id,
            "seasonId": season_id,
            "competitionId": comp_id,
            "date": {"dateTimeUTC": date_utc},
        },
        "clubsInformation": {
            "club": {"clubId": club_id},
            "opponent": {"clubId": opponent_id},
        },
        "statistics": {
            "playingTimeStatistics": playing_time,
        },
    }


def test_matchlogs_parse_games_basic_appearance() -> None:
    logs = _parse_games([_game()], "tm_123")
    assert len(logs) == 1
    log = logs[0]
    assert log.date == datetime.date(2025, 1, 15)
    assert log.minutes_played == 90
    assert log.competition == "UEFA Champions League"
    assert log.match_id == "tm_2025-01-15_123"


def test_matchlogs_parse_games_filters_out_of_window_season() -> None:
    logs = _parse_games([_game(season_id=2020)], "tm_123")
    assert logs == []


def test_matchlogs_parse_games_filters_zero_minutes() -> None:
    logs = _parse_games([_game(played_minutes=0)], "tm_123")
    assert logs == []


def test_matchlogs_parse_games_sub_on_minute() -> None:
    logs = _parse_games([_game(is_starting=False, sub_in_minute=60, played_minutes=30)], "tm_123")
    assert len(logs) == 1
    assert logs[0].sub_on_minute == 60


def test_matchlogs_parse_games_sub_off_minute() -> None:
    logs = _parse_games([_game(sub_out_minute=72, played_minutes=72)], "tm_123")
    assert len(logs) == 1
    assert logs[0].sub_off_minute == 72


def test_matchlogs_parse_games_unknown_comp_id_passes_through() -> None:
    logs = _parse_games([_game(comp_id="XYZ99")], "tm_123")
    assert len(logs) == 1
    assert logs[0].competition == "XYZ99"


def test_matchlogs_parse_games_multiple_seasons() -> None:
    games = [_game(season_id=2023), _game(season_id=2024), _game(season_id=2025)]
    logs = _parse_games(games, "tm_123")
    assert len(logs) == 3


def test_matchlogs_parse_games_match_id_is_player_independent() -> None:
    game = _game(game_id="999", date_utc="2024-11-05T20:00:00+00:00")
    logs_a = _parse_games([game], "player_a")
    logs_b = _parse_games([game], "player_b")
    assert logs_a[0].match_id == logs_b[0].match_id
