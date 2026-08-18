"""LRCLIB lyrics provider with a local on-disk cache."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from typing import Any

import requests

from audio2lrc.models import LyricLine, LyricsNotFoundError, TrackMetadata

API_BASE = os.environ.get("LRCLIB_URL", "https://lrclib.net")
_TIMEOUT = 20
_MAX_DURATION_DIFF = 15.0


def _request(url: str) -> Any:
    resp = requests.get(url, timeout=_TIMEOUT, headers={"User-Agent": "audio2lrc/0.1"})
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


def _cache_path(cache_dir: str, meta: TrackMetadata) -> str:
    key = hashlib.sha1(
        f"{meta.title or ''}|{meta.artist or ''}|{meta.album or ''}|{meta.duration or ''}".encode("utf-8")
    ).hexdigest()
    return os.path.join(cache_dir, f"{key}.json")


def _parse_lyrics(text: str | None) -> list[LyricLine] | None:
    if not text or not text.strip():
        return None
    from audio2lrc.lrc.parser import parse_lrc

    return parse_lrc(text)


def _pick_best(results: list[dict], duration: float | None) -> dict | None:
    """Pick the best search result: prefer synced lyrics, then closest duration."""
    if not results:
        return None

    def score(r: dict) -> tuple[int, float]:
        synced = 0 if r.get("syncedLyrics") else 1
        diff = abs((r.get("duration") or 0) - (duration or 0)) if duration else 0.0
        return synced, diff

    ranked = sorted(results, key=score)
    best = ranked[0]
    if duration and abs((best.get("duration") or 0) - duration) > _MAX_DURATION_DIFF:
        return None
    return best


def fetch_lyrics(
    meta: TrackMetadata,
    cache_dir: str | None = None,
) -> tuple[list[LyricLine] | None, list[LyricLine] | None, bool]:
    """Fetch lyrics for a track from LRCLIB.

    Returns (synced_lines, plain_lines, instrumental). plain_lines holds
    unsynced lyrics when the server has no synced match. Results are cached
    on disk keyed by title+artist+album+duration so re-runs never hit the
    network again.
    """
    params = meta.lrclib_query()
    if not params or "track_name" not in params:
        raise LyricsNotFoundError(
            "cannot query LRCLIB: no title available (tags missing and filename not parseable)"
        )

    cache_dir = cache_dir or os.path.join(
        os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")), "audio2lrc"
    )
    cache_file = _cache_path(cache_dir, meta)

    data: dict | None = None
    if os.path.exists(cache_file):
        try:
            with open(cache_file, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError):
            data = None

    if data is None:
        query = "&".join(f"{k}={requests.utils.quote(str(v))}" for k, v in params.items())
        try:
            hit = _request(f"{API_BASE}/api/get?{query}")
            if hit is None:
                results = _request(f"{API_BASE}/api/search?{query}") or []
                hit = _pick_best(results, meta.duration)
        except requests.RequestException as exc:
            raise LyricsNotFoundError(
                f"LRCLIB request failed ({exc}); "
                "check your network connection or the LRCLIB_URL setting"
            ) from exc
        data = hit or {"instrumental": False}
        try:
            os.makedirs(cache_dir, exist_ok=True)
            tmp = cache_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False)
            os.replace(tmp, cache_file)
        except OSError as exc:
            sys.stderr.write(f"warning: could not write LRCLIB cache: {exc}\n")

    if data.get("instrumental"):
        return None, None, True

    synced = _parse_lyrics(data.get("syncedLyrics"))
    plain = _parse_lyrics(data.get("plainLyrics"))
    return synced, plain, False