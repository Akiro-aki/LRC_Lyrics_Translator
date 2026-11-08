"""QQ Music provider tests (HTTP layer stubbed)."""

import base64

import pytest

from audio2lrc.models import LyricsNotFoundError, TrackMetadata
from audio2lrc.providers.qqmusic import QQMusicProvider, _candidate, _decode_lyric

META = TrackMetadata(title="Song", artist="Artist", album="Album", duration=120.0)
SYNCED = "[00:01.00]line one\n[00:02.00]line two"


def _song(mid="m1", name="Song", singer="Artist", interval=120):
    return {"mid": mid, "name": name, "singer": [{"name": singer}],
            "album": {"name": "Album"}, "interval": interval}


def _legacy_song(mid="m1", name="Song", singer="Artist", interval=120):
    return {"songmid": mid, "songname": name, "singer": [{"name": singer}],
            "albumname": "Album", "interval": interval}


@pytest.fixture
def qq(monkeypatch, tmp_path):
    calls = []

    def install(songs=None, legacy=None, lyrics=None, musicu_fails=False):
        lyrics = lyrics or {}

        def fake_post(url, payload):
            calls.append(("post", url))
            if musicu_fails:
                raise ValueError("bad json")
            return {"req_1": {"data": {"body": {"song": {"list": songs or []}}}}}

        def fake_get(url, params=None):
            calls.append(("get", url))
            if "client_search_cp" in url:
                return {"data": {"song": {"list": legacy or []}}}
            if "lyric" in url:
                return lyrics.get(params["songmid"], {})
            return {}

        monkeypatch.setattr("audio2lrc.providers.qqmusic._post", fake_post)
        monkeypatch.setattr("audio2lrc.providers.qqmusic._get", fake_get)
        return calls, str(tmp_path / "cache")

    return install


def test_musicu_search_and_synced_lyrics(qq):
    calls, cache = qq(songs=[_song()], lyrics={"m1": {"lyric": SYNCED}})
    r = QQMusicProvider().fetch_lyrics(META, cache_dir=cache)
    assert [l.text for l in r.synced] == ["line one", "line two"]
    assert r.confidence > 0.9
    assert not any("client_search_cp" in u for _, u in calls)


def test_falls_back_to_legacy_search(qq):
    calls, cache = qq(musicu_fails=True, legacy=[_legacy_song()],
                      lyrics={"m1": {"lyric": SYNCED}})
    r = QQMusicProvider().fetch_lyrics(META, cache_dir=cache)
    assert r.synced is not None
    assert any("client_search_cp" in u for _, u in calls)


def test_html_entities_unescaped(qq):
    escaped = "[00&#58;01&#46;00]it&apos;s one&#10;[00&#58;02&#46;00]two"
    _, cache = qq(songs=[_song()], lyrics={"m1": {"lyric": escaped}})
    r = QQMusicProvider().fetch_lyrics(META, cache_dir=cache)
    assert [l.text for l in r.synced] == ["it's one", "two"]


def test_base64_lyrics_decoded():
    encoded = base64.b64encode(SYNCED.encode()).decode()
    assert _decode_lyric(encoded) == SYNCED


def test_translation_field_ignored(qq):
    _, cache = qq(songs=[_song()], lyrics={"m1": {"lyric": "", "trans": SYNCED}})
    r = QQMusicProvider().fetch_lyrics(META, cache_dir=cache)
    assert r.synced is None and r.plain is None


def test_live_version_rejected(qq):
    _, cache = qq(songs=[_song(name="Song (Live)")], lyrics={"m1": {"lyric": SYNCED}})
    r = QQMusicProvider().fetch_lyrics(META, cache_dir=cache)
    assert r.synced is None
    assert "version mismatch (live)" in r.rejected


def test_cache_hit_skips_network(qq):
    calls, cache = qq(songs=[_song()], lyrics={"m1": {"lyric": SYNCED}})
    p = QQMusicProvider()
    p.fetch_lyrics(META, cache_dir=cache)
    calls.clear()
    assert p.fetch_lyrics(META, cache_dir=cache).synced is not None
    assert calls == []


def test_candidate_mapping_legacy_and_new():
    new, old = _candidate(_song()), _candidate(_legacy_song())
    for c in (new, old):
        assert (c.id, c.title, c.artists, c.album, c.duration) == (
            "m1", "Song", ["Artist"], "Album", 120.0)


def test_no_title_raises():
    with pytest.raises(LyricsNotFoundError, match="no title"):
        QQMusicProvider().fetch_lyrics(TrackMetadata(), cache_dir="/tmp/unused")


def test_legacy_search_used_when_desktop_results_do_not_match(qq):
    calls, cache = qq(
        songs=[_song(mid="live", name="Song (Live)")],
        legacy=[_legacy_song(mid="studio")],
        lyrics={"live": {"lyric": SYNCED}, "studio": {"lyric": SYNCED}},
    )
    r = QQMusicProvider().fetch_lyrics(META, cache_dir=cache)
    assert r.synced is not None
    assert any("client_search_cp" in u for _, u in calls)


def test_header_and_credit_lines_stripped(qq):
    lrc = ("[ti:Song]\n[00:00.00]Song - Artist (Band)\n[00:00.90]词：Someone\n"
           "[00:01.20]混音工程师：Someone\n" + SYNCED)
    _, cache = qq(songs=[_song()], lyrics={"m1": {"lyric": lrc}})
    r = QQMusicProvider().fetch_lyrics(META, cache_dir=cache)
    assert [l.text for l in r.synced] == ["line one", "line two"]
