"""Tests for the LRCLIB link parsing and link-driven resolution."""

import pytest

from audio2lrc.cli import main as cli_main
from audio2lrc.links import parse_lrclib_url
from audio2lrc.models import LyricsNotFoundError
from audio2lrc.resolve import resolve_from_url

SYNCED = "[00:01.00]line one\n[00:02.00]line two"


@pytest.fixture
def fake_lrclib(monkeypatch):
    """Stub the LRCLIB `_request` HTTP layer, keyed on the URL."""
    store = {}

    def set_record(data, path=None):
        store[path or "/api/get/123"] = data

    def fake_request(url):
        for path, data in store.items():
            if url.endswith(path):
                return data
        return None

    monkeypatch.setattr("audio2lrc.providers.lrclib._request", fake_request)
    return set_record


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://lrclib.net/song/12345", 12345),
        ("https://lrclib.net/tracks/10194812", 10194812),
        ("https://lrclib.net/lyrics/12345", 12345),
        ("https://lrclib.net/api/get/12345", 12345),
        ("https://lrclib.net/api/get?id=99", 99),
        ("https://lrclib.net/song/12345/", 12345),
        ("https://lrclib.net/api/get?id=7&foo=bar", 7),
    ],
)
def test_parse_valid_lrclib_urls(url, expected):
    assert parse_lrclib_url(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "",
        "not a url",
        "https://example.com/song/12345",
        "https://lrclib.net/",
        "https://lrclib.net/search?q=hello",
        "ftp://lrclib.net/song/1",
    ],
)
def test_parse_invalid_lrclib_urls(url):
    assert parse_lrclib_url(url) is None


def test_resolve_from_url_synced(fake_lrclib):
    fake_lrclib(
        {"trackName": "Song", "artistName": "Artist", "albumName": "Album",
         "duration": 120, "syncedLyrics": SYNCED}
    )
    resolved, meta = resolve_from_url("https://lrclib.net/song/123")
    assert resolved.source == "lrclib.net:link"
    assert not resolved.unsynced
    assert len(resolved.lines) == 2
    assert meta.title == "Song"
    assert meta.artist == "Artist"
    assert meta.album == "Album"
    assert meta.duration == 120


def test_resolve_from_url_tracks_path(fake_lrclib):
    fake_lrclib(
        {"trackName": "Song", "artistName": "Artist", "syncedLyrics": SYNCED}
    )
    resolved, meta = resolve_from_url("https://lrclib.net/tracks/123")
    assert resolved.source == "lrclib.net:link"
    assert len(resolved.lines) == 2
    assert meta.title == "Song"


def test_resolve_from_url_plain(fake_lrclib):
    fake_lrclib(
        {"trackName": "Song", "artistName": "Artist", "syncedLyrics": None,
         "plainLyrics": "line one\nline two"}
    )
    resolved, _ = resolve_from_url("https://lrclib.net/song/123")
    assert resolved.unsynced is True
    assert len(resolved.lines) == 2


@pytest.mark.parametrize(
    "url",
    ["https://lrclib.net/song/", "https://example.com/song/123", ""],
)
def test_resolve_from_url_invalid_link_errors(url):
    with pytest.raises(LyricsNotFoundError, match="not a valid LRCLIB link"):
        resolve_from_url(url)


def test_resolve_from_url_instrumental_errors(fake_lrclib):
    fake_lrclib({"trackName": "Song", "instrumental": True})
    with pytest.raises(LyricsNotFoundError, match="instrumental"):
        resolve_from_url("https://lrclib.net/song/123")


def test_resolve_from_url_missing_record_errors(fake_lrclib):
    fake_lrclib({"trackName": "Song", "syncedLyrics": None, "plainLyrics": None},
                path="/api/get/999")
    with pytest.raises(LyricsNotFoundError, match="no lyrics found"):
        resolve_from_url("https://lrclib.net/song/999")


def test_cli_lrclib_link_writes_file(fake_lrclib, tmp_path, monkeypatch):
    fake_lrclib(
        {"trackName": "My Song", "artistName": "Artist", "syncedLyrics": SYNCED}
    )
    monkeypatch.chdir(tmp_path)
    assert cli_main(["--lrclib-link", "https://lrclib.net/song/123"]) == 0
    out = tmp_path / "My Song.lrc"
    assert out.exists()
    text = out.read_text(encoding="utf-8")
    assert "#X-SOURCE: lrclib.net:link" in text
    assert "[00:01.00]line one" in text


def test_cli_rejects_both_audio_and_link():
    assert cli_main(["--lrclib-link", "https://lrclib.net/song/1", "track.mp3"]) == 2


def test_cli_requires_either_audio_or_link():
    assert cli_main([]) == 2
