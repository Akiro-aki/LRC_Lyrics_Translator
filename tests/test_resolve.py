"""Resolution logic tests: embedded vs LRCLIB priority + cache."""

import json

import pytest

from audio2lrc.models import EmbeddedLyrics, LyricsNotFoundError, TrackMetadata
from audio2lrc.resolve import resolve

SYNCED = "[00:01.00]line one\n[00:02.00]line two"
PLAIN = "line one\nline two"

META = TrackMetadata(title="Song", artist="Artist", album="Album", duration=120.0)


@pytest.fixture
def fake_lrclib(monkeypatch, tmp_path):
    """Stub the LRCLIB HTTP layer; record requests for cache assertions."""
    hits = []
    cache_dir = tmp_path / "cache"

    def install(synced=None, plain=None, instrumental=False):
        data = {"instrumental": instrumental, "syncedLyrics": synced, "plainLyrics": plain}

        def fake_request(url):
            hits.append(url)
            return data

        monkeypatch.setattr("audio2lrc.providers.lrclib._request", fake_request)
        return hits, str(cache_dir)

    return install


def test_embedded_synced_wins_no_lrclib_call(fake_lrclib):
    hits, cache_dir = fake_lrclib(synced="[00:01.00]x")
    result = resolve(
        META, EmbeddedLyrics(text=SYNCED, synced=True), cache_dir=cache_dir
    )
    assert result.source == "embedded"
    assert not result.unsynced
    assert hits == []


def test_embedded_unsynced_falls_through_to_lrclib_synced(fake_lrclib):
    hits, cache_dir = fake_lrclib(synced=SYNCED)
    result = resolve(
        META, EmbeddedLyrics(text=PLAIN, synced=False), cache_dir=cache_dir
    )
    assert result.source == "lrclib.net"
    assert not result.unsynced
    assert len(hits) == 1


def test_lrclib_plain_only(fake_lrclib):
    _, cache_dir = fake_lrclib(plain=PLAIN)
    result = resolve(META, None, cache_dir=cache_dir)
    assert result.source == "lrclib.net"
    assert result.unsynced is True


def test_embedded_unsynced_fallback_when_lrclib_empty(fake_lrclib):
    _, cache_dir = fake_lrclib()
    result = resolve(
        META, EmbeddedLyrics(text=PLAIN, synced=False), cache_dir=cache_dir
    )
    assert result.source == "embedded"
    assert result.unsynced is True


def test_no_lyrics_anywhere_errors(fake_lrclib):
    _, cache_dir = fake_lrclib()
    with pytest.raises(LyricsNotFoundError):
        resolve(META, None, cache_dir=cache_dir)


def test_instrumental_errors(fake_lrclib):
    _, cache_dir = fake_lrclib(instrumental=True)
    with pytest.raises(LyricsNotFoundError):
        resolve(META, None, cache_dir=cache_dir)


def test_prefer_embedded_overrides_lrclib_synced(fake_lrclib):
    hits, cache_dir = fake_lrclib(synced=SYNCED)
    result = resolve(
        META,
        EmbeddedLyrics(text=PLAIN, synced=False),
        prefer_embedded=True,
        cache_dir=cache_dir,
    )
    assert result.source == "embedded"
    assert result.unsynced is True
    assert hits == []


def test_prefer_lrclib_overrides_embedded_synced(fake_lrclib):
    hits, cache_dir = fake_lrclib(synced=SYNCED)
    result = resolve(
        META,
        EmbeddedLyrics(text=SYNCED, synced=True),
        prefer_external=True,
        cache_dir=cache_dir,
    )
    assert result.source == "lrclib.net"
    assert len(hits) == 1


def test_cache_prevents_second_network_call(fake_lrclib):
    hits, cache_dir = fake_lrclib(synced=SYNCED)
    resolve(META, None, cache_dir=cache_dir)
    assert len(hits) == 1
    hits.clear()
    resolve(META, None, cache_dir=cache_dir)
    assert hits == []


def test_cache_file_written(tmp_path):
    cache_dir = tmp_path / "cache"
    result = resolve(META, EmbeddedLyrics(text=SYNCED, synced=True), cache_dir=cache_dir)
    assert result.source == "embedded"  # no cache write for embedded path
    files = list((tmp_path / "cache").glob("*.json"))
    assert files == []  # embedded path never touches the cache


def test_embedded_with_timestamps_in_plain_field_is_synced():
    result = resolve(
        META,
        EmbeddedLyrics(text="[00:01.00]x", synced=True),
    )
    assert result.source == "embedded"
    assert not result.unsynced


@pytest.fixture
def fake_netease(monkeypatch, tmp_path):
    """Stub the NetEase HTTP layer."""
    hits = []
    cache_dir = tmp_path / "cache"

    def install(search_results=None, lyrics_map=None):
        search_resp = {"result": {"songs": search_results or []}}
        lyrics_map = lyrics_map or {}

        def fake_get(url, params=None, **kwargs):
            hits.append(url)
            if "search" in url:
                return search_resp
            if "lyric" in url:
                return lyrics_map.get(int(params["id"]), {})
            return {}

        monkeypatch.setattr("audio2lrc.providers.netease._get", fake_get)
        return hits, str(cache_dir)

    return install


def test_provider_auto_prefers_lrclib_when_match(fake_lrclib, fake_netease, tmp_path):
    """auto tries lrclib first; if it has synced lyrics, netease is never hit."""
    lrclib_hits, lrclib_cache = fake_lrclib(synced=SYNCED)
    netease_hits, _ = fake_netease()
    result = resolve(META, None, provider="auto", cache_dir=lrclib_cache)
    assert result.source == "lrclib.net"
    assert not result.unsynced
    assert len(lrclib_hits) == 1


def test_provider_auto_falls_back_to_netease(fake_lrclib, fake_netease, tmp_path):
    """When lrclib has nothing, auto falls back to netease."""
    lrclib_hits, lrclib_cache = fake_lrclib()  # no results
    netease_hits, _ = fake_netease(
        search_results=[{"id": 7, "name": "Song", "artists": [{"name": "Artist"}], "album": {}, "duration": 120000}],
        lyrics_map={7: {"lrc": {"lyric": SYNCED}}},
    )
    result = resolve(META, None, provider="auto", cache_dir=lrclib_cache)
    assert result.source == "music.163.com"
    assert not result.unsynced
    assert len(lrclib_hits) == 1  # lrclib was attempted


def test_provider_netease_only(fake_netease, tmp_path):
    netease_hits, _ = fake_netease(
        search_results=[{"id": 7, "name": "Song", "artists": [{"name": "Artist"}], "album": {}, "duration": 120000}],
        lyrics_map={7: {"lrc": {"lyric": SYNCED}}},
    )
    result = resolve(META, None, provider="netease", cache_dir=str(tmp_path / "c"))
    assert result.source == "music.163.com"
    assert not result.unsynced


def test_unknown_provider_errors():
    with pytest.raises(LyricsNotFoundError, match="unknown lyrics provider"):
        resolve(META, None, provider="bogus", cache_dir="/tmp/x")

# -- best-match selection across providers --------------------------------------

NETEASE_SONG = {"id": 7, "name": "Song", "artists": [{"name": "Artist"}], "album": {}, "duration": 120000}


@pytest.fixture
def fake_qqmusic(monkeypatch):
    hits = []

    def install(songs=None, lyrics=None):
        def fake_post(url, payload):
            hits.append(url)
            return {"req_1": {"data": {"body": {"song": {"list": songs or []}}}}}

        def fake_get(url, params=None):
            hits.append(url)
            if "lyric" in url:
                return (lyrics or {}).get(params["songmid"], {})
            return {}

        monkeypatch.setattr("audio2lrc.providers.qqmusic._post", fake_post)
        monkeypatch.setattr("audio2lrc.providers.qqmusic._get", fake_get)
        return hits

    return install


def test_auto_prefers_synced_netease_over_plain_lrclib(fake_lrclib, fake_netease, fake_qqmusic):
    _, cache_dir = fake_lrclib(plain=PLAIN)
    fake_netease(search_results=[NETEASE_SONG], lyrics_map={7: {"lrc": {"lyric": SYNCED}}})
    fake_qqmusic()
    result = resolve(META, None, provider="auto", cache_dir=cache_dir)
    assert result.source == "music.163.com"
    assert not result.unsynced
    assert result.confidence > 0.9
    assert result.matched


def test_auto_stops_after_strong_synced_match(fake_lrclib, fake_netease, fake_qqmusic):
    _, cache_dir = fake_lrclib(synced=SYNCED)
    netease_hits, _ = fake_netease()
    qq_hits = fake_qqmusic()
    result = resolve(META, None, provider="auto", cache_dir=cache_dir)
    assert result.source == "lrclib.net"
    assert netease_hits == [] and qq_hits == []


def test_auto_reaches_qqmusic(fake_lrclib, fake_netease, fake_qqmusic):
    _, cache_dir = fake_lrclib()
    fake_netease()
    fake_qqmusic(
        songs=[{"mid": "q", "name": "Song", "singer": [{"name": "Artist"}], "interval": 120}],
        lyrics={"q": {"lyric": SYNCED}},
    )
    result = resolve(META, None, provider="auto", cache_dir=cache_dir)
    assert result.source == "y.qq.com"


def test_error_explains_rejected_candidates(fake_netease, tmp_path):
    fake_netease(
        search_results=[{**NETEASE_SONG, "name": "Song (Live)"}],
        lyrics_map={7: {"lrc": {"lyric": SYNCED}}},
    )
    with pytest.raises(LyricsNotFoundError, match=r"version mismatch \(live\)"):
        resolve(META, None, provider="netease", cache_dir=str(tmp_path / "c"))


def test_min_confidence_rejects_weak_match(fake_netease, tmp_path):
    meta = TrackMetadata(title="Song")  # title-only match is capped at 0.7
    fake_netease(search_results=[NETEASE_SONG], lyrics_map={7: {"lrc": {"lyric": SYNCED}}})
    cache = str(tmp_path / "c")
    assert resolve(meta, None, provider="netease", cache_dir=cache).source == "music.163.com"
    with pytest.raises(LyricsNotFoundError, match="low confidence"):
        resolve(meta, None, provider="netease", cache_dir=cache, min_confidence=0.8)


def test_embedded_fallback_explains_rejection(fake_netease, tmp_path):
    fake_netease(
        search_results=[{**NETEASE_SONG, "name": "Song (Remix)"}],
        lyrics_map={7: {"lrc": {"lyric": SYNCED}}},
    )
    result = resolve(META, EmbeddedLyrics(text=PLAIN, synced=False),
                     provider="netease", cache_dir=str(tmp_path / "c"))
    assert result.source == "embedded"
    assert any("version mismatch (remix)" in n for n in result.notes)
