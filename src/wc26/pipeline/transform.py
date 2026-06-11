"""Pure parsing of rendered Transfermarkt detailed-performance pages.

This module is browser-free and fully unit-testable. It consumes the HTML
produced *after* a headless browser has rendered the
``<tm-player-performance-table-new data-type="matchPerformanceByCompetition">``
web component and dismissed the cookie-consent banner, and turns it into a list
of :class:`~wc26.models.MatchLog` objects.

The rendered component groups matches into one ``div.box`` per competition. Each
box has a ``.content-box-headline`` (the competition name) followed by a grid of
``div.grid-row`` elements. Each data row's direct-child ``<div>`` cells are, in
order::

    [0]  date            e.g. "19/09/24"
    [1]  venue           "H" or "A"
    [2]  home team       e.g. "Arsenal"
    [3]  away team       e.g. "Atalanta"
    [4]  position        e.g. "RW"  (empty when the player did not play)
    [5..11] per-match stat columns (goals, assists, cards, ...) — ignored here
    [-2] minutes played  e.g. "90'", "73'"  ("-" when the player did not play)
    [-1] note            e.g. "Thigh problems" (empty when the player played)

Sub-on/sub-off minutes are not exposed anywhere on the page, so they are always
recorded as ``None``.
"""

from __future__ import annotations

import datetime
import re

import structlog
from bs4 import BeautifulSoup, Tag

from wc26.models import MatchLog

logger = structlog.get_logger()

# Date formats seen on Transfermarkt across locales, tried in order.
#
# The rendered detailed-performance grid uses day-first two-digit-year dates
# (e.g. "19/09/24" = 19 Sep 2024), so the day-first slash formats are tried
# before the US month-first one to avoid misreading ambiguous dates such as
# "01/10/24" (1 Oct, not 10 Jan).
_DATE_FORMATS: tuple[str, ...] = (
    "%b %d, %Y",
    "%d/%m/%y",
    "%d/%m/%Y",
    "%d.%m.%Y",
    "%m/%d/%y",
    "%Y-%m-%d",
)

# Minimum direct-child cell count for a row to be considered a data row.
_MIN_CELLS = 14

# Non-alphanumeric run, used by the slug helper.
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")

# Strip everything except digits from a minutes token (handles "90 + 2'", "73'").
_DIGITS_RE = re.compile(r"\d+")


def _slug(text: str) -> str:
    """Return a lowercase, hyphen-separated slug of ``text``.

    Used to build deterministic, player-independent match IDs from team names.

    Args:
        text: Arbitrary input text (e.g. a club name).

    Returns:
        A slug with non-alphanumeric runs collapsed to single hyphens and
        leading/trailing hyphens stripped. Empty input yields "unknown".
    """
    slug = _NON_ALNUM_RE.sub("-", text.strip().lower()).strip("-")
    return slug or "unknown"


def _parse_date(raw: str) -> datetime.date | None:
    """Parse a date string against the known Transfermarkt formats.

    Args:
        raw: The raw date cell text (e.g. "19/09/24").

    Returns:
        A :class:`datetime.date`, or ``None`` if no known format matched.
    """
    raw = raw.strip()
    if not raw:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _parse_minutes(raw: str) -> int | None:
    """Parse the minutes-played cell into an integer.

    Args:
        raw: The raw minutes cell text (e.g. "90'", "90 + 2'", "-").

    Returns:
        The total minutes as an int, or ``None`` if the cell holds no digits
        (e.g. a "-" placeholder for a match the player did not feature in).
    """
    digits = _DIGITS_RE.findall(raw)
    if not digits:
        return None
    # "90 + 2'" -> sum the parts so stoppage time is included.
    return sum(int(d) for d in digits)


def _row_cells(row: Tag) -> list[str]:
    """Return the stripped text of a grid row's direct-child cells.

    Args:
        row: A ``div.grid-row`` Tag.

    Returns:
        List of cell texts in document order.
    """
    return [cell.get_text(" ", strip=True) for cell in row.find_all("div", recursive=False)]


def _build_match_log(
    cells: list[str],
    competition: str,
    player_tm_id: str,
) -> MatchLog | None:
    """Build a :class:`MatchLog` from one parsed grid row.

    Args:
        cells: Direct-child cell texts for the row.
        competition: Competition name from the enclosing box headline.
        player_tm_id: Transfermarkt id of the player this log belongs to.

    Returns:
        A :class:`MatchLog`, or ``None`` if the row is not a played match
        (header row, did-not-play, zero/blank minutes, or unparseable date).
    """
    if len(cells) < _MIN_CELLS:
        return None

    date = _parse_date(cells[0])
    if date is None:
        return None

    minutes = _parse_minutes(cells[-2])
    if minutes is None or minutes <= 0:
        # Did-not-play / bench / 0-minute rows are skipped.
        return None

    venue = cells[1].strip().upper()
    home_team = cells[2].strip()
    away_team = cells[3].strip()
    if not home_team or not away_team:
        return None

    if venue == "A":
        team, opponent = away_team, home_team
    else:
        # Default to home perspective when venue is "H" or unrecognised.
        team, opponent = home_team, away_team

    # Player-independent so squad-mates in the same fixture share a match_id.
    match_id = f"tm_{date.isoformat()}_{_slug(team)}_{_slug(opponent)}"

    return MatchLog(
        player_tm_id=player_tm_id,
        match_id=match_id,
        date=date,
        competition=competition or "Unknown",
        team=team,
        opponent=opponent,
        minutes_played=minutes,
        sub_on_minute=None,
        sub_off_minute=None,
    )


def parse_tm_performance_page(
    rendered_html: str,
    player_tm_id: str,
    season: str,
) -> list[MatchLog]:
    """Parse a rendered TM detailed-performance page into match logs.

    Args:
        rendered_html: HTML captured after the performance web component has
            rendered (i.e. post-consent, post-hydration).
        player_tm_id: Transfermarkt id of the player the page belongs to.
        season: Season label (e.g. "2024/25"); currently informational and used
            only for logging.

    Returns:
        A list of :class:`MatchLog` objects, one per match the player featured
        in. Rows that are headers, did-not-play, or otherwise unparseable are
        silently skipped.
    """
    soup = BeautifulSoup(rendered_html, "lxml")
    logs: list[MatchLog] = []

    for box in soup.select("div.box"):
        headline = box.select_one(".content-box-headline")
        competition = headline.get_text(" ", strip=True) if headline else ""

        for row in box.select("div.grid-row"):
            cells = _row_cells(row)
            match_log = _build_match_log(cells, competition, player_tm_id)
            if match_log is not None:
                logs.append(match_log)

    logger.info(
        "parsed_tm_performance_page",
        player_tm_id=player_tm_id,
        season=season,
        match_count=len(logs),
    )
    return logs
