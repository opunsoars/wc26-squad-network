"""Tests for the squad pipeline: Wikipedia parse + TM ID resolution."""

from __future__ import annotations

import pathlib

from wc26.pipeline.squads import parse_wiki_squads, resolve_tm_id


def _wiki_html() -> str:
    return pathlib.Path("tests/fixtures/wiki_squads_page.html").read_text(encoding="utf-8")


def test_parse_wiki_squads_returns_players() -> None:
    players = parse_wiki_squads(_wiki_html())
    assert len(players) >= 11
    first = players[0]
    assert first.name
    assert first.squad
    assert first.position in {"GK", "DF", "MF", "FW"}
    assert first.club


def test_parse_wiki_squads_count_matches_squads() -> None:
    """Fixture has 2 squads of 26 players each = 52 total."""
    players = parse_wiki_squads(_wiki_html())
    assert len(players) == 52


def test_parse_wiki_squads_squad_names() -> None:
    players = parse_wiki_squads(_wiki_html())
    squads = {p.squad for p in players}
    assert "Czech Republic" in squads
    assert "Mexico" in squads


def test_parse_wiki_squads_all_positions_valid() -> None:
    players = parse_wiki_squads(_wiki_html())
    assert all(p.position in {"GK", "DF", "MF", "FW"} for p in players)


def test_parse_wiki_squads_has_gk() -> None:
    players = parse_wiki_squads(_wiki_html())
    assert any(p.position == "GK" for p in players)


def test_resolve_tm_id_uses_override_first(tmp_path: pathlib.Path) -> None:
    overrides = tmp_path / "overrides.json"
    overrides.write_text('{"Bukayo Saka": "418560"}', encoding="utf-8")
    tm_id = resolve_tm_id("Bukayo Saka", overrides_file=str(overrides), scraper=None)
    assert tm_id == "418560"


def test_resolve_tm_id_fuzzy_match(tmp_path: pathlib.Path) -> None:
    overrides = tmp_path / "overrides.json"
    overrides.write_text('{"Bukayo Saka": "418560"}', encoding="utf-8")
    # Slight name variation — should still match via fuzzy at score ≥ 90
    tm_id = resolve_tm_id("Bukayo  Saka", overrides_file=str(overrides), scraper=None)
    assert tm_id == "418560"


def test_resolve_tm_id_no_match_no_scraper(tmp_path: pathlib.Path) -> None:
    overrides = tmp_path / "overrides.json"
    overrides.write_text("{}", encoding="utf-8")
    tm_id = resolve_tm_id("Unknown Player XYZ", overrides_file=str(overrides), scraper=None)
    assert tm_id == ""


def test_resolve_tm_id_missing_overrides_file(tmp_path: pathlib.Path) -> None:
    """Should not raise even if overrides file does not exist."""
    tm_id = resolve_tm_id(
        "Some Player",
        overrides_file=str(tmp_path / "nonexistent.json"),
        scraper=None,
    )
    assert tm_id == ""
