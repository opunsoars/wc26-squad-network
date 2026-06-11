from __future__ import annotations

import datetime
import pathlib

from wc26.pipeline.transform import parse_tm_performance_page


def _tm_html() -> str:
    return pathlib.Path("tests/fixtures/tm_player_page.html").read_text(encoding="utf-8")


def test_parse_returns_match_logs():
    logs = parse_tm_performance_page(_tm_html(), player_tm_id="433177", season="2024/25")
    assert len(logs) > 0
    assert logs[0].player_tm_id == "433177"
    assert isinstance(logs[0].date, datetime.date)
    assert logs[0].minutes_played >= 0
    assert logs[0].competition


def test_match_id_is_player_independent():
    a = parse_tm_performance_page(_tm_html(), player_tm_id="433177", season="2024/25")
    b = parse_tm_performance_page(_tm_html(), player_tm_id="999999", season="2024/25")
    assert a[0].match_id == b[0].match_id
    # match_id must NOT contain the player id
    assert "433177" not in a[0].match_id


def test_no_sub_minutes_recorded():
    logs = parse_tm_performance_page(_tm_html(), player_tm_id="433177", season="2024/25")
    assert all(m.sub_on_minute is None and m.sub_off_minute is None for m in logs)
