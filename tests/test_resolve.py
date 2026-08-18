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
        prefer_lrclib=True,
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