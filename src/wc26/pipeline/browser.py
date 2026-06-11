"""Playwright rendering layer for Transfermarkt detailed-performance pages.

Transfermarkt serves the per-match performance data through a client-side
``<tm-player-performance-table-new>`` web component, so the static HTML contains
no match rows. This module drives a headless Chromium instance to render the
page, dismiss the Sourcepoint cookie-consent banner (served inside an iframe),
wait for the component to hydrate, and return the resulting HTML.

Rendered HTML is cached to disk keyed by URL. Because the full dataset spans
~1,250 players x 3 seasons, a cache hit must never launch a browser.
"""

from __future__ import annotations

import hashlib
import pathlib
import time

import structlog
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page, sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from wc26.config import RAW_CACHE_DIR, REQUEST_DELAY_SECONDS

logger = structlog.get_logger()

# Detailed per-match view. ``season_code`` is the starting year, e.g. "2024"
# for the 2024/25 season. The slug segment is cosmetic; TM resolves by id.
_DETAIL_URL = (
    "https://www.transfermarkt.com/{slug}/leistungsdatendetails/"
    "spieler/{tm_id}/saison/{season_code}/plus/1"
)

# Realistic desktop Chrome UA — TM blocks obvious automation/non-browser UAs.
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# The Sourcepoint consent banner renders inside an iframe from this host.
_CONSENT_IFRAME_SELECTOR = 'iframe[src*="privacy-mgmt.com"]'
_CONSENT_ACCEPT_NAME = "Accept & continue"

# The hydrated component that holds the per-match grid.
_PERFORMANCE_SELECTOR = (
    'tm-player-performance-table-new[data-type="matchPerformanceByCompetition"] div.grid-row'
)

# Timeouts (milliseconds).
_NAV_TIMEOUT_MS = 30_000
_CONSENT_TIMEOUT_MS = 8_000
_TABLE_TIMEOUT_MS = 20_000


class RenderError(RuntimeError):
    """Raised when the page cannot be rendered at all (e.g. browser launch)."""


def _slugify_name(player_name: str) -> str:
    """Return a URL-safe slug for the player-name path segment.

    The segment is purely cosmetic — Transfermarkt resolves the page by id — so
    a missing or odd name degrades gracefully to a placeholder.

    Args:
        player_name: The player's display name.

    Returns:
        A lowercase hyphen-separated slug, or "x" when empty.
    """
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in player_name)
    slug = "-".join(part for part in cleaned.split("-") if part)
    return slug or "x"


def _cache_path(cache_dir: str, url: str) -> pathlib.Path:
    """Return the on-disk cache path for a rendered URL.

    Args:
        cache_dir: Directory holding cached rendered HTML.
        url: The rendered detail URL.

    Returns:
        Path to the ``.html`` cache file for ``url``.
    """
    key = hashlib.md5(url.encode(), usedforsecurity=False).hexdigest()  # noqa: S324
    return pathlib.Path(cache_dir) / f"{key}.html"


def _accept_consent(page: Page) -> None:
    """Dismiss the Sourcepoint consent banner if it is present.

    The banner lives in an iframe. If it is absent or cannot be dismissed within
    the timeout we log and return — the caller will still try to read whatever
    rendered.

    Args:
        page: The active Playwright ``Page`` instance.
    """
    try:
        frame = page.frame_locator(_CONSENT_IFRAME_SELECTOR)
        frame.get_by_role("button", name=_CONSENT_ACCEPT_NAME).click(timeout=_CONSENT_TIMEOUT_MS)
        logger.debug("consent_accepted")
    except (PlaywrightTimeoutError, PlaywrightError) as exc:
        # No banner, or it changed shape: not fatal, the table may still load.
        logger.debug("consent_skip", error=str(exc))


def render_tm_performance(
    tm_id: str,
    player_name: str,
    season_code: str,
    cache_dir: str = RAW_CACHE_DIR,
    *,
    headless: bool = True,
) -> str:
    """Render a player's detailed-performance page for one season.

    Reads from the on-disk cache first; a cache hit returns immediately without
    launching a browser. On a miss, launches headless Chromium, navigates to the
    detail URL, accepts cookie consent, waits for the performance grid to
    hydrate, caches the rendered HTML, and returns it.

    Consent or table-wait failures are logged and the current page HTML is
    returned regardless (the parser yields an empty list for empty pages).

    Args:
        tm_id: Transfermarkt player id.
        player_name: Player display name (used only for the cosmetic URL slug).
        season_code: Season starting year, e.g. "2024" for 2024/25.
        cache_dir: Directory for cached rendered HTML.
        headless: Whether to run Chromium headless.

    Returns:
        The rendered page HTML.

    Raises:
        RenderError: If the browser cannot be launched or navigation fails
            outright.
    """
    url = _DETAIL_URL.format(
        slug=_slugify_name(player_name),
        tm_id=tm_id,
        season_code=season_code,
    )

    cache_file = _cache_path(cache_dir, url)
    if cache_file.exists():
        logger.debug("render_cache_hit", url=url)
        return cache_file.read_text(encoding="utf-8")

    pathlib.Path(cache_dir).mkdir(parents=True, exist_ok=True)
    logger.info("rendering", url=url, tm_id=tm_id, season_code=season_code)

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=headless)
            try:
                context = browser.new_context(user_agent=_USER_AGENT, locale="en-US")
                page = context.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=_NAV_TIMEOUT_MS)
                _accept_consent(page)
                try:
                    page.wait_for_selector(_PERFORMANCE_SELECTOR, timeout=_TABLE_TIMEOUT_MS)
                except PlaywrightTimeoutError as exc:
                    logger.warning("table_not_rendered", url=url, error=str(exc))
                html = page.content()
            finally:
                browser.close()
    except PlaywrightError as exc:
        raise RenderError(f"Playwright failed to render {url}: {exc}") from exc

    cache_file.write_text(html, encoding="utf-8")
    logger.debug("render_cache_written", url=url, path=str(cache_file))

    # Polite throttle between live renders.
    time.sleep(REQUEST_DELAY_SECONDS)
    return html
