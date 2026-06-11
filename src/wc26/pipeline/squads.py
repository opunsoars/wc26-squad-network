"""Squad pipeline: Wikipedia squad scrape and Transfermarkt ID resolution.

Scrapes the Wikipedia WC squads page, parses each country's squad table into
Player objects, then resolves a Transfermarkt player ID for each player via an
overrides file or a live TM search.
"""

from __future__ import annotations

import json
import pathlib
import re

import structlog
from bs4 import BeautifulSoup, Tag
from rapidfuzz import process as fuzz_process

from wc26.config import TM_ID_OVERRIDES_FILE
from wc26.models import Player
from wc26.scraper import Scraper

logger = structlog.get_logger()

_WIKI_SQUADS_URL = "https://en.wikipedia.org/wiki/2026_FIFA_World_Cup_squads"

# Transfermarkt quick-search URL — returns HTML with player links containing /spieler/<id>
_TM_SEARCH_URL = (
    "https://www.transfermarkt.com/schnellsuche/ergebnis/schnellsuche?query={name}&Spieler_page=1"
)

# Wikipedia squad tables encode position as e.g. "1GK", "2DF", "3MF", "4FW"
# The anchor text inside the cell is the canonical abbreviation; we normalise both.
_POSITION_MAP: dict[str, str] = {
    "GK": "GK",
    "DF": "DF",
    "MF": "MF",
    "FW": "FW",
    "Goalkeeper": "GK",
    "Defender": "DF",
    "Midfielder": "MF",
    "Forward": "FW",
    "Attacker": "FW",
}

# Regex to strip leading digit from "1GK", "2DF", etc.
_POS_STRIP_RE = re.compile(r"^\d+")

# Regex to extract /spieler/<id> from a Transfermarkt href
_TM_SPIELER_RE = re.compile(r"/spieler/(\d+)")


def _extract_country(heading: Tag) -> str:
    """Return the plain-text country name from an h3 heading tag.

    Args:
        heading: A BeautifulSoup Tag representing an h2 or h3 heading.

    Returns:
        The country name string with edit-section spans stripped.
    """
    # Remove the [edit] span if present
    for span in heading.find_all("span", class_="mw-editsection"):
        span.decompose()
    return heading.get_text(strip=True)


def _parse_position(cell: Tag) -> str:
    """Derive a normalised position code (GK/DF/MF/FW) from the position cell.

    Wikipedia encodes the position as a hidden sort-key digit followed by an
    anchor with the abbreviation, e.g. ``<span style="display:none">1</span>
    <a ...>GK</a>``.  We try to read the anchor text first; fall back to the
    raw cell text with the leading digit stripped.

    Args:
        cell: The BeautifulSoup td/th cell for the Pos. column.

    Returns:
        One of "GK", "DF", "MF", "FW", or "?" if unrecognised.
    """
    link = cell.find("a")
    raw = (
        link.get_text(strip=True)
        if link
        else _POS_STRIP_RE.sub("", cell.get_text(strip=True))
    )
    return _POSITION_MAP.get(raw, "?")


def _parse_player_row(row: Tag, squad: str) -> Player | None:
    """Parse one player row from a Wikipedia squad wikitable.

    Args:
        row: A ``<tr>`` Tag from the table body (not the header row).
        squad: The country/squad name to assign.

    Returns:
        A Player instance, or None if the row cannot be parsed (e.g. colspan
        rows or rows with fewer than 7 cells).
    """
    cells = row.find_all(["td", "th"])
    # Expect at least 7 columns: No. | Pos. | Player | DOB | Caps | Goals | Club
    if len(cells) < 7:
        return None

    position = _parse_position(cells[1])
    if position == "?":
        return None

    # Player name: the th cell may have a link or plain text
    name_cell = cells[2]
    name_link = name_cell.find("a")
    name = name_link.get_text(strip=True) if name_link else name_cell.get_text(strip=True)
    if not name:
        return None

    # Club: last cell.  The cell typically contains a flag icon link (image-only)
    # followed by the club name link.  Find the first <a> whose text is non-empty.
    club_cell = cells[6]
    club = ""
    for a in club_cell.find_all("a"):
        text = a.get_text(strip=True)
        if text:
            club = text
            break
    if not club:
        # Fall back: strip flag spans and take plain text
        for span in club_cell.find_all("span", class_="flagicon"):
            span.decompose()
        club = club_cell.get_text(strip=True)

    return Player(
        name=name,
        squad=squad,
        position=position,
        club=club,
        tm_id="",
    )


def parse_wiki_squads(html: str) -> list[Player]:
    """Parse the Wikipedia WC squads page into a flat list of Players (tm_id="").

    The page structure is:
    - ``<h2>`` for each group (e.g. "Group A")
    - ``<h3>`` for each country within the group
    - ``<table class="wikitable">`` immediately following each h3 with the
      squad roster (columns: No., Pos., Player, Date of birth, Caps, Goals, Club)

    Args:
        html: Raw HTML of the Wikipedia World Cup squads page.

    Returns:
        Flat list of Player objects with tm_id="" for every player parsed.
    """
    soup = BeautifulSoup(html, "lxml")
    players: list[Player] = []

    current_country: str = ""

    # Walk every element at the content level; track h3 → country, table → players
    for element in soup.find_all(["h2", "h3", "table"]):
        if not isinstance(element, Tag):
            continue

        tag = element.name

        if tag == "h2":
            # Group heading — reset country; will be set by the next h3
            current_country = ""

        elif tag == "h3":
            current_country = _extract_country(element)
            logger.debug("found_squad_heading", country=current_country)

        elif tag == "table" and "wikitable" in (element.get("class") or []):
            if not current_country:
                continue

            rows = element.find_all("tr")
            # Skip the header row (index 0) and parse each subsequent row
            squad_count = 0
            for row in rows[1:]:
                player = _parse_player_row(row, current_country)
                if player is not None:
                    players.append(player)
                    squad_count += 1

            logger.info(
                "parsed_squad",
                squad=current_country,
                player_count=squad_count,
            )
            # Reset country so we don't accidentally attach the next table to
            # this country if the markup structure is unusual.
            current_country = ""

    logger.info("parse_complete", total_players=len(players))
    return players


def resolve_tm_id(
    name: str,
    overrides_file: str = TM_ID_OVERRIDES_FILE,
    scraper: Scraper | None = None,
) -> str:
    """Return the Transfermarkt player ID for a given player name.

    Lookup order:
    1. Exact match in the JSON overrides file.
    2. Fuzzy match (rapidfuzz, score ≥ 90) in the overrides file.
    3. If a ``scraper`` is provided, search Transfermarkt and extract the best
       fuzzy-matched player ID from the result links.
    4. Return "" if nothing is found.

    Args:
        name: The player's display name (as parsed from Wikipedia).
        overrides_file: Path to a JSON file mapping ``name → tm_id``.
        scraper: Optional Scraper instance for live TM lookups.

    Returns:
        Transfermarkt player ID string, or "" if not found.
    """
    # --- overrides file ---
    overrides_path = pathlib.Path(overrides_file)
    overrides: dict[str, str] = {}
    if overrides_path.exists():
        try:
            raw = json.loads(overrides_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                overrides = {str(k): str(v) for k, v in raw.items()}
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("overrides_load_failed", path=str(overrides_path), error=str(exc))

    # Exact match
    if name in overrides:
        logger.debug("tm_id_override_exact", name=name, tm_id=overrides[name])
        return overrides[name]

    # Fuzzy match
    if overrides:
        result = fuzz_process.extractOne(name, list(overrides.keys()), score_cutoff=90)
        if result is not None:
            matched_name: str = result[0]
            logger.debug(
                "tm_id_override_fuzzy",
                name=name,
                matched=matched_name,
                score=result[1],
                tm_id=overrides[matched_name],
            )
            return overrides[matched_name]

    # --- live TM search ---
    if scraper is None:
        return ""

    search_url = _TM_SEARCH_URL.format(name=name.replace(" ", "+"))
    try:
        search_html = scraper.fetch(search_url)
    except Exception as exc:  # noqa: BLE001
        logger.warning("tm_search_failed", name=name, error=str(exc))
        return ""

    # Extract candidate player links and their names
    search_soup = BeautifulSoup(search_html, "lxml")
    candidates: dict[str, str] = {}  # display_name → tm_id

    for link in search_soup.find_all("a", href=_TM_SPIELER_RE):
        href: str = link.get("href", "")
        m = _TM_SPIELER_RE.search(href)
        if not m:
            continue
        tm_id = m.group(1)
        candidate_name = link.get_text(strip=True)
        if candidate_name:
            candidates[candidate_name] = tm_id

    if not candidates:
        logger.debug("tm_search_no_candidates", name=name)
        return ""

    best = fuzz_process.extractOne(name, list(candidates.keys()), score_cutoff=70)
    if best is None:
        logger.debug("tm_search_no_match", name=name)
        return ""

    matched: str = best[0]
    found_id = candidates[matched]
    logger.info("tm_id_resolved", name=name, matched=matched, score=best[1], tm_id=found_id)
    return found_id


def build_players_dataset(scraper: Scraper) -> list[Player]:
    """Scrape Wikipedia, parse squads, and resolve each player's TM ID.

    Args:
        scraper: Scraper instance used for all HTTP fetches (Wikipedia + TM).

    Returns:
        List of Player objects with tm_id resolved (or "" where resolution
        failed).
    """
    logger.info("building_players_dataset", url=_WIKI_SQUADS_URL)
    html = scraper.fetch(_WIKI_SQUADS_URL)
    players = parse_wiki_squads(html)

    resolved: list[Player] = []
    for player in players:
        tm_id = resolve_tm_id(name=player.name, scraper=scraper)
        resolved.append(player.model_copy(update={"tm_id": tm_id}))
        logger.debug("player_resolved", name=player.name, squad=player.squad, tm_id=tm_id)

    logger.info("dataset_complete", total=len(resolved))
    return resolved
