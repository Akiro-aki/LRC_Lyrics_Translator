"""LRCLIB lyrics provider with a local on-disk cache."""

from __future__ import annotations

import os
from typing import Any

import requests

from audio2lrc.models import LyricLine, LyricsNotFoundError, ProviderResult, TrackMetadata
from audio2lrc.providers.cache import cache_path, cached_lookup, default_cache_dir
from audio2lrc.providers.matching import (
    Candidate,
    default_min_confidence,
    rank,
    score_candidate,
    select_lyrics,
    to_result,
)

API_BASE = os.environ.get("LRCLIB_URL", "https://lrclib.net")
_TIMEOUT = 20


def _request(url: str) -> Any:
    resp = requests.get(url, timeout=_TIMEOUT, headers={"User-Agent": "audio2lrc/0.1"})
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


def _parse_lyrics(text: str | None) -> list[LyricLine] | None:
    if not text or not text.strip():
        return None
    from audio2lrc.lrc.parser import parse_lrc

    return parse_lrc(text)


def _candidate(record: dict, meta: TrackMetadata | None = None) -> Candidate:
    """Map an LRCLIB record to a Candidate.

    For /api/get hits the server already matched on our tags, so missing
    fields fall back to the track's own metadata.
    """
    fallback = meta or TrackMetadata()
    artist = record.get("artistName") or fallback.artist
    return Candidate(
        provider=LRCLIBProvider.name,
        id=record.get("id"),
        title=record.get("trackName") or record.get("name") or fallback.title or "",
        artists=[artist] if artist else [],
        album=record.get("albumName") or fallback.album,
        duration=record.get("duration") or None,
        raw=record,
    )


def _fetch_record(c: Candidate) -> tuple[str | None, str | None, bool]:
    r = c.raw
    return r.get("syncedLyrics"), r.get("plainLyrics"), bool(r.get("instrumental"))


class LRCLIBProvider:
    """Fetch lyrics from LRCLIB (lrclib.net)."""

    name = "lrclib.net"

    def fetch_lyrics(
        self,
        meta: TrackMetadata,
        cache_dir: str | None = None,
        min_confidence: float | None = None,
    ) -> ProviderResult:
        """Fetch lyrics for a track from LRCLIB.

        Tries the exact-match /api/get endpoint first, then /api/search.
        Every record goes through the shared matcher.  Results are cached on
        disk keyed by title+artist+album+duration so re-runs never hit the
        network again.
        """
        params = meta.lrclib_query()
        if not params or "track_name" not in params:
            raise LyricsNotFoundError(
                "cannot query LRCLIB: no title available (tags missing and filename not parseable)"
            )
        min_conf = default_min_confidence() if min_confidence is None else min_confidence
        path = cache_path(cache_dir or default_cache_dir(), "lrclib", meta)
        query = "&".join(f"{k}={requests.utils.quote(str(v))}" for k, v in params.items())

        def compute() -> dict:
            hit = _request(f"{API_BASE}/api/get?{query}")
            if isinstance(hit, dict):
                match = score_candidate(_candidate(hit, meta), meta)
                if match.rejected is None and match.confidence >= min_conf:
                    return select_lyrics([match], _fetch_record, meta)
            results = _request(f"{API_BASE}/api/search?{query}")
            if not isinstance(results, list):
                results = []
            matches, closest = rank([_candidate(r) for r in results], meta, min_conf)
            return select_lyrics(matches, _fetch_record, meta, closest)

        try:
            data = cached_lookup(path, min_conf, compute, "LRCLIB")
        except (requests.RequestException, OSError, ValueError) as exc:
            raise LyricsNotFoundError(
                f"LRCLIB request failed ({exc}); "
                "check your network connection or the LRCLIB_URL setting"
            ) from exc
        return to_result(data, meta)

    def fetch_by_id(self, track_id: int) -> dict:
        """Fetch a lyrics record directly by its LRCLIB track ID.

        Returns the raw LRCLIB record dict (``trackName``, ``artistName``,
        ``albumName``, ``syncedLyrics``, ``plainLyrics``, ``instrumental``, ...).
        Raises LyricsNotFoundError when the ID does not exist or the request
        fails.
        """
        data = _request(f"{API_BASE}/api/get/{track_id}")
        if data is None:
            raise LyricsNotFoundError(f"LRCLIB: no lyrics record for track id {track_id}")
        return data


lrclib = LRCLIBProvider()
