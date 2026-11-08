"""NetEase Cloud Music lyrics provider with a local on-disk cache."""

from __future__ import annotations

import os
import re
from typing import Any

import requests

from audio2lrc.lrc.parser import looks_synced
from audio2lrc.models import LyricsNotFoundError, ProviderResult, TrackMetadata
from audio2lrc.providers.cache import cache_path, cached_lookup, default_cache_dir
from audio2lrc.providers.matching import (
    Candidate,
    default_min_confidence,
    rank,
    select_lyrics,
    to_result,
)

API_BASE = os.environ.get("NETEASE_URL", "https://music.163.com")
_TIMEOUT = 20

_HEADERS = {
    "User-Agent": "audio2lrc/0.1",
    "Referer": "https://music.163.com/",
}


def _get(url: str, params: dict | None = None) -> Any:
    resp = requests.get(url, params=params, headers=_HEADERS, timeout=_TIMEOUT)
    if resp.status_code == 429:
        raise requests.HTTPError("429 Too Many Requests from NetEase", response=resp)
    resp.raise_for_status()
    return resp.json()


# Word-by-word YRC timing, e.g. "[00:01.00,300,0]..." — strip the ",ms,ms"
# so the base LRC parser can handle it like a normal timestamp line.
_YRC_TIMESTAMP_RE = re.compile(r"\[(\d{1,3}):(\d{1,2})(?:[.:](\d{1,3}))?(?:,\d+,\d+)?\]")


def _strip_yrc(text: str) -> str:
    """Convert NetEase YRC (word-level timing) text to plain LRC."""
    out: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        times = _YRC_TIMESTAMP_RE.findall(line)
        rest = _YRC_TIMESTAMP_RE.sub("", line).strip()
        if times and rest:
            prefix = ",".join(
                f"[{m}:{s}{('.' + f) if f else ''}]" for m, s, f in times
            )
            out.append(prefix + rest)
        else:
            out.append(rest)
    return "\n".join(out)


def _song_duration_ms(song: dict) -> float | None:
    """Extract duration in seconds from a NetEase search result (API returns ms)."""
    ms = song.get("duration") or song.get("dt")
    if ms and ms > 0:
        return ms / 1000.0
    return None


def _candidate(song: dict) -> Candidate:
    """Map a NetEase search result to a Candidate."""
    artists = song.get("artists") or song.get("ar") or []
    album = song.get("album") or song.get("al") or {}
    alt = [*(song.get("alias") or []), *(song.get("transNames") or [])]
    return Candidate(
        provider=NetEaseProvider.name,
        id=song.get("id"),
        title=song.get("name") or "",
        artists=[a["name"] for a in artists if a.get("name")],
        album=album.get("name") if isinstance(album, dict) else None,
        duration=_song_duration_ms(song),
        alt_titles=[t for t in alt if isinstance(t, str) and t],
        raw=song,
    )


def _extract_best_lyrics(resp: dict) -> tuple[str | None, str | None, bool]:
    """Extract (synced_lrc_text, plain_text, instrumental) from a lyrics response.

    Only the original-language lyrics are used: YRC (word-by-word) first,
    then LRC.  Translated (``tlyric``) and romanised (``romalrc``) tracks
    are never returned as the song's lyrics.
    """
    if resp.get("nolyric"):
        return None, None, True
    lrc = (resp.get("lrc") or {}).get("lyric") or ""
    yrc = (resp.get("yrc") or {}).get("lyric") or ""

    for candidate in (_strip_yrc(yrc) if yrc else "", lrc):
        if candidate and looks_synced(candidate):
            return candidate, None, False
    if lrc.strip():
        return None, lrc, False
    return None, None, False


def _lyrics_endpoints(song_id: Any) -> list[tuple[str, dict[str, str]]]:
    """Return (url, params) pairs to try, best-first."""
    sid = str(song_id)
    return [
        (
            f"{API_BASE}/api/song/lyric/v1",
            {"id": sid, "cp": "false", "lv": "1", "tv": "1", "rv": "1", "kv": "1", "yv": "1"},
        ),
        (f"{API_BASE}/api/song/lyric", {"id": sid, "lv": "1", "kv": "1", "tv": "-1"}),
    ]


def _fetch_candidate(c: Candidate) -> tuple[str | None, str | None, bool]:
    """Fetch lyrics for one song, trying both lyric endpoints."""
    plain: str | None = None
    instrumental = False
    for endpoint, params in _lyrics_endpoints(c.id):
        try:
            resp = _get(endpoint, params=params)
        except requests.RequestException:
            continue
        if not isinstance(resp, dict) or not resp:
            continue
        synced, text, inst = _extract_best_lyrics(resp)
        if synced:
            return synced, None, False
        plain = plain or text
        instrumental = instrumental or inst
    return None, plain, instrumental and not plain


def _search(query: str) -> list[dict]:
    url = f"{API_BASE}/api/search/get"
    params = {"type": "1", "s": query, "limit": "20", "offset": "0"}
    resp = _get(url, params=params)
    return ((resp or {}).get("result") or {}).get("songs") or []


class NetEaseProvider:
    """Fetch lyrics from NetEase Cloud Music (music.163.com).

    Searches for the track, ranks the results with the shared matcher and
    tries up to five accepted candidates, preferring one with synced
    (timestamped) lyrics.
    """

    name = "music.163.com"

    def fetch_lyrics(
        self,
        meta: TrackMetadata,
        cache_dir: str | None = None,
        min_confidence: float | None = None,
    ) -> ProviderResult:
        query = meta.search_query()
        if not query:
            raise LyricsNotFoundError(
                "cannot query NetEase: no title available "
                "(tags missing and filename not parseable)"
            )
        min_conf = default_min_confidence() if min_confidence is None else min_confidence
        path = cache_path(cache_dir or default_cache_dir(), "netease", meta)

        def compute() -> dict:
            candidates = [_candidate(s) for s in _search(query) if s.get("id") is not None]
            matches, closest = rank(candidates, meta, min_conf)
            return select_lyrics(matches, _fetch_candidate, meta, closest)

        try:
            data = cached_lookup(path, min_conf, compute, "NetEase")
        except (requests.RequestException, OSError, ValueError) as exc:
            raise LyricsNotFoundError(
                f"NetEase request failed ({exc}); "
                "check your network connection or the NETEASE_URL setting"
            ) from exc
        return to_result(data, meta)


netease = NetEaseProvider()
