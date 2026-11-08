"""Utilities for parsing lyrics-source links (e.g. an LRCLIB song URL)."""

from __future__ import annotations

import re
from urllib.parse import urlparse

LRCLIB_HOSTS = ("lrclib.net",)


def parse_lrclib_url(url: str) -> int | None:
    """Extract a numeric LRCLIB track ID from any LRCLIB URL form.

    LRCLIB links can look like:
      https://lrclib.net/song/12345
      https://lrclib.net/tracks/12345
      https://lrclib.net/lyrics/12345
      https://lrclib.net/api/get/12345
      https://lrclib.net/api/get?id=12345

    Returns the track ID, or None when the URL is not an LRCLIB link or has
    no parseable ID.
    """
    if not url:
        return None

    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https") or parsed.netloc not in LRCLIB_HOSTS:
        return None

    if "id" in parsed.query:
        match = re.search(r"(?:^|&)id=(\d+)", parsed.query)
        if match:
            return int(match.group(1))

    path = parsed.path.rstrip("/")
    match = re.search(r"/(?:song|tracks|lyrics|api/get)/(\d+)$", path)
    if match:
        return int(match.group(1))

    return None
