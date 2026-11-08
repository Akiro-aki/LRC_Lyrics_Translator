"""QQ Music (y.qq.com) lyrics provider with a local on-disk cache."""

from __future__ import annotations

import base64
import binascii
import html
import json
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

API_BASE = os.environ.get("QQMUSIC_URL", "https://c.y.qq.com")
SEARCH_URL = os.environ.get("QQMUSIC_SEARCH_URL", "https://u.y.qq.com/cgi-bin/musicu.fcg")
_TIMEOUT = 20

_HEADERS = {
    "User-Agent": "audio2lrc/0.1",
    "Referer": "https://y.qq.com/",
}

_JSONP_RE = re.compile(r"^\s*[\w$.]+\((.*)\)\s*;?\s*$", re.S)


def _decode(resp: requests.Response) -> Any:
    if resp.status_code == 429:
        raise requests.HTTPError("429 Too Many Requests from QQ Music", response=resp)
    resp.raise_for_status()
    text = resp.text
    m = _JSONP_RE.match(text)
    return json.loads(m.group(1) if m else text)


def _get(url: str, params: dict | None = None) -> Any:
    return _decode(requests.get(url, params=params, headers=_HEADERS, timeout=_TIMEOUT))


def _post(url: str, payload: dict) -> Any:
    return _decode(requests.post(url, json=payload, headers=_HEADERS, timeout=_TIMEOUT))


def _candidate(song: dict) -> Candidate:
    """Map a QQ Music search result (new or legacy format) to a Candidate."""
    album = song.get("album")
    album_name = album.get("name") if isinstance(album, dict) else song.get("albumname")
    singers = song.get("singer") or []
    interval = song.get("interval")
    return Candidate(
        provider=QQMusicProvider.name,
        id=song.get("mid") or song.get("songmid"),
        title=song.get("name") or song.get("title") or song.get("songname") or "",
        artists=[s["name"] for s in singers if isinstance(s, dict) and s.get("name")],
        album=album_name or None,
        duration=float(interval) if interval else None,
        raw=song,
    )


def _search_musicu(query: str) -> list[dict]:
    payload = {
        "comm": {"ct": "19", "cv": "1859", "uin": "0"},
        "req_1": {
            "module": "music.search.SearchCgiService",
            "method": "DoSearchForQQMusicDesktop",
            "param": {"query": query, "num_per_page": 20, "page_num": 1, "search_type": 0},
        },
    }
    resp = _post(SEARCH_URL, payload) or {}
    body = ((resp.get("req_1") or {}).get("data") or {}).get("body") or {}
    return (body.get("song") or {}).get("list") or []


def _search_legacy(query: str) -> list[dict]:
    params = {"w": query, "format": "json", "p": "1", "n": "20", "cr": "1", "t": "0"}
    resp = _get(f"{API_BASE}/soso/fcgi-bin/client_search_cp", params=params) or {}
    return (((resp.get("data") or {}).get("song") or {}).get("list")) or []


def _searches(query: str):
    """Yield result lists from each search endpoint, best-first.

    The desktop API is tried first; the legacy endpoint ranks differently
    and is used when the desktop results hold no verified match (or the
    desktop API refuses the request).
    """
    try:
        yield _search_musicu(query)
    except (requests.RequestException, ValueError):
        pass
    yield _search_legacy(query)


def _decode_lyric(raw: str | None) -> str:
    """QQ lyrics come HTML-entity escaped, or base64 when nobase64 is ignored."""
    if not raw:
        return ""
    text = html.unescape(raw)
    if looks_synced(text) or "\n" in text:
        return text
    try:
        decoded = base64.b64decode(raw, validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return text
    return html.unescape(decoded)


def _fetch_candidate(c: Candidate) -> tuple[str | None, str | None, bool]:
    params = {
        "songmid": str(c.id),
        "format": "json",
        "nobase64": "1",
        "g_tk": "5381",
        "platform": "yqq",
    }
    try:
        resp = _get(f"{API_BASE}/lyric/fcgi-bin/fcg_query_lyric_new.fcg", params=params)
    except (requests.RequestException, ValueError):
        return None, None, False
    if not isinstance(resp, dict):
        return None, None, False
    # Only the original lyrics; "trans" holds a translation, not the song.
    text = _decode_lyric(resp.get("lyric"))
    if not text.strip():
        return None, None, False
    if looks_synced(text):
        return text, None, False
    return None, text, False


def _usefulness(result: dict) -> int:
    """Rank non-synced outcomes from different search endpoints."""
    if result.get("plain") or result.get("instrumental"):
        return 3
    rejected = result.get("rejected") or ""
    if rejected and not rejected.startswith("closest"):
        return 2  # a match was found but its lyrics failed the checks
    return 1 if rejected else 0


class QQMusicProvider:
    """Fetch lyrics from QQ Music (y.qq.com).

    Strong catalogue for Chinese, Japanese and Korean releases.  Searches,
    ranks results with the shared matcher and tries up to five accepted
    candidates, preferring synced lyrics.
    """

    name = "y.qq.com"

    def fetch_lyrics(
        self,
        meta: TrackMetadata,
        cache_dir: str | None = None,
        min_confidence: float | None = None,
    ) -> ProviderResult:
        query = meta.search_query()
        if not query:
            raise LyricsNotFoundError(
                "cannot query QQ Music: no title available "
                "(tags missing and filename not parseable)"
            )
        min_conf = default_min_confidence() if min_confidence is None else min_confidence
        path = cache_path(cache_dir or default_cache_dir(), "qqmusic", meta)

        def compute() -> dict:
            seen: set = set()
            best: dict = {}
            for songs in _searches(query):
                candidates = [c for c in map(_candidate, songs) if c.id and c.id not in seen]
                seen.update(c.id for c in candidates)
                if not candidates:
                    continue
                matches, closest = rank(candidates, meta, min_conf)
                result = select_lyrics(matches, _fetch_candidate, meta, closest)
                if result.get("lrc"):
                    return result
                if _usefulness(result) > _usefulness(best):
                    best = result
            return best

        try:
            data = cached_lookup(path, min_conf, compute, "QQ Music")
        except (requests.RequestException, OSError, ValueError) as exc:
            raise LyricsNotFoundError(
                f"QQ Music request failed ({exc}); "
                "check your network connection or the QQMUSIC_URL setting"
            ) from exc
        return to_result(data, meta)


qqmusic = QQMusicProvider()
