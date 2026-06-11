from __future__ import annotations

import hashlib
import pathlib
from unittest.mock import MagicMock, patch

from wc26.scraper import Scraper


def test_cache_hit_does_not_call_httpx(tmp_path: pathlib.Path):
    url = "https://www.transfermarkt.com/player/418560"
    url_hash = hashlib.md5(url.encode()).hexdigest()
    cache_file = tmp_path / f"{url_hash}.html"
    cache_file.write_text("<html>cached</html>", encoding="utf-8")

    scraper = Scraper(cache_dir=str(tmp_path), delay_seconds=0.0)
    with patch("httpx.Client.get") as mock_get:
        html = scraper.fetch(url)
        mock_get.assert_not_called()

    assert html == "<html>cached</html>"


def test_cache_miss_fetches_and_writes(tmp_path: pathlib.Path):
    url = "https://www.transfermarkt.com/player/999"
    url_hash = hashlib.md5(url.encode()).hexdigest()

    mock_response = MagicMock()
    mock_response.text = "<html>live</html>"
    mock_response.raise_for_status = MagicMock()

    scraper = Scraper(cache_dir=str(tmp_path), delay_seconds=0.0)
    with patch("httpx.Client.get", return_value=mock_response):
        html = scraper.fetch(url)

    assert html == "<html>live</html>"
    assert (tmp_path / f"{url_hash}.html").read_text(encoding="utf-8") == "<html>live</html>"
