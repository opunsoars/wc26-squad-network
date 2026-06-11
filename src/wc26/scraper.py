from __future__ import annotations

import hashlib
import pathlib
import time

import httpx
import structlog

logger = structlog.get_logger()

# Transfermarkt blocks non-browser UAs; Wikipedia blocks fake-browser UAs and
# prefers honest bots with contact info. Use domain-appropriate headers.
_CHROME_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
}

_WIKI_HEADERS = {
    "User-Agent": (
        "wc26-squad-network/0.1 (https://github.com/opunsoars/wc26-squad-network; "
        "personal analytics project)"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
}


def _headers_for(url: str) -> dict[str, str]:
    if "wikipedia.org" in url:
        return _WIKI_HEADERS
    return _CHROME_HEADERS


class Scraper:
    """Throttled HTTP fetcher with a file-based raw HTML cache.

    Args:
        cache_dir: Directory for cached HTML files.
        delay_seconds: Minimum seconds between requests.
    """

    def __init__(self, cache_dir: str, delay_seconds: float = 1.5) -> None:
        self._cache_dir = pathlib.Path(cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._delay = delay_seconds
        self._last_request: float = 0.0

    def _cache_path(self, url: str) -> pathlib.Path:
        key = hashlib.md5(url.encode(), usedforsecurity=False).hexdigest()  # noqa: S324
        return self._cache_dir / f"{key}.html"

    def fetch(self, url: str) -> str:
        """Return HTML for url, reading from cache if available.

        Args:
            url: The URL to fetch.

        Returns:
            Raw HTML string.
        """
        cache_file = self._cache_path(url)
        if cache_file.exists():
            logger.debug("cache_hit", url=url)
            return cache_file.read_text(encoding="utf-8")

        elapsed = time.monotonic() - self._last_request
        if elapsed < self._delay:
            time.sleep(self._delay - elapsed)

        logger.info("fetching", url=url)
        with httpx.Client(headers=_headers_for(url), follow_redirects=True, timeout=30) as client:
            response = client.get(url)
            response.raise_for_status()

        self._last_request = time.monotonic()
        html = response.text
        cache_file.write_text(html, encoding="utf-8")
        logger.debug("cache_written", url=url, path=str(cache_file))
        return html
