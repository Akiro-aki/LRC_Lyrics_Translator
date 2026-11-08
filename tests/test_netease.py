"""NetEase Cloud Music provider tests."""

import pytest

from audio2lrc.models import LyricsNotFoundError, TrackMetadata
from audio2lrc.providers.netease import (
    NetEaseProvider,
    _candidate,
    _song_duration_ms,
)

META = TrackMetadata(title="Song", artist="Artist", album="Album", duration=120.0)

SYNCED_LRC = "[00:01.00]line one\n[00:02.00]line two"
PLAIN_TEXT = "line one\nline two"


def _song(id=12345, name="Song", artists=None, album="Album", duration_ms=120000):
    return {
        "id": id,
        "name": name,
        "artists": [{"name": a} for a in (artists or ["Artist"])],
        "album": {"name": album},
        "duration": duration_ms,
    }


def _lyrics_response(lrc=SYNCED_LRC, tlyric=None, yrc=None, romalrc=None):
    resp: dict = {"lrc": {"lyric": lrc or ""}}
    if tlyric is not None:
        resp["tlyric"] = {"lyric": tlyric}
    if yrc is not None:
        resp["yrc"] = {"lyric": yrc}
    if romalrc is not None:
        resp["romalrc"] = {"lyric": romalrc}
    return resp


@pytest.fixture
def provider(monkeypatch, tmp_path):
    """Return a helper that installs a stubbed _get on the netease module."""
    calls: list[tuple[str, dict | None]] = []
    cache_dir = tmp_path / "cache"

    def install(search_results=None, lyrics_map=None):
        """lyrics_map: {song_id: response_dict}"""
        search_resp = {"result": {"songs": search_results or []}}
        lyrics_map = lyrics_map or {}

        def fake_get(url, params=None, **kwargs):
            calls.append((url, params))
            if "search" in url:
                return search_resp
            if "lyric" in url:
                sid = int(params["id"])
                return lyrics_map.get(sid, {})
            return {}

        monkeypatch.setattr("audio2lrc.providers.netease._get", fake_get)
        return calls, str(cache_dir)

    return install


# -- basic flows -----------------------------------------------------------

def test_synced_lyrics_returned(provider):
    song = _song()
    calls, cache_dir = provider(
        search_results=[song],
        lyrics_map={12345: _lyrics_response()},
    )
    p = NetEaseProvider()
    r = p.fetch_lyrics(META, cache_dir=cache_dir)
    synced, plain, instrumental = r.synced, r.plain, r.instrumental

    assert not instrumental
    assert synced is not None
    assert len(synced) == 2
    assert synced[0].text == "line one"
    assert any("lyric" in u for u, _ in calls)


def test_no_search_results(provider):
    _, cache_dir = provider(search_results=[])
    p = NetEaseProvider()
    r = p.fetch_lyrics(META, cache_dir=cache_dir)
    synced, plain, instrumental = r.synced, r.plain, r.instrumental

    assert not instrumental
    assert synced is None
    assert plain is None


def test_instrumental_when_nolyric_flag(provider):
    song = _song(id=99)
    _, cache_dir = provider(
        search_results=[song],
        lyrics_map={99: {"nolyric": True}},
    )
    r = NetEaseProvider().fetch_lyrics(META, cache_dir=cache_dir)

    assert r.instrumental
    assert r.confidence is not None


def test_empty_lyrics_is_not_instrumental(provider):
    """No lyrics on NetEase does not mean the song has none."""
    _, cache_dir = provider(search_results=[_song(id=99)], lyrics_map={99: {}})
    r = NetEaseProvider().fetch_lyrics(META, cache_dir=cache_dir)

    assert not r.instrumental
    assert r.synced is None and r.plain is None
    assert "no lyrics available" in r.rejected


def test_instrumental_placeholder_text(provider):
    _, cache_dir = provider(
        search_results=[_song(id=5)],
        lyrics_map={5: _lyrics_response(lrc="[00:00.00]纯音乐，请欣赏")},
    )
    r = NetEaseProvider().fetch_lyrics(META, cache_dir=cache_dir)

    assert r.instrumental


def test_cache_hit_skips_network(provider):
    song = _song()
    calls, cache_dir = provider(
        search_results=[song],
        lyrics_map={12345: _lyrics_response()},
    )
    p = NetEaseProvider()
    p.fetch_lyrics(META, cache_dir=cache_dir)
    first_count = len(calls)
    assert first_count >= 2

    calls.clear()
    p.fetch_lyrics(META, cache_dir=cache_dir)
    assert len(calls) == 0


# -- multi-candidate fallback ----------------------------------------------

def test_tries_second_candidate_when_first_has_no_synced(provider):
    song1 = _song(id=1, name="Song", duration_ms=120000)
    song2 = _song(id=2, name="Song", duration_ms=121000)

    _, cache_dir = provider(
        search_results=[song1, song2],
        lyrics_map={
            1: {"lrc": {"lyric": PLAIN_TEXT}},          # no timestamps
            2: _lyrics_response(lrc=SYNCED_LRC),         # synced
        },
    )
    p = NetEaseProvider()
    r = p.fetch_lyrics(META, cache_dir=cache_dir)
    synced, plain, instrumental = r.synced, r.plain, r.instrumental

    assert not instrumental
    assert synced is not None
    assert len(synced) == 2


def test_falls_back_to_unsynced_when_no_candidate_has_synced(provider):
    song1 = _song(id=1)
    song2 = _song(id=2, album="Other Album")

    _, cache_dir = provider(
        search_results=[song1, song2],
        lyrics_map={
            1: {"lrc": {"lyric": PLAIN_TEXT}},
            2: {"lrc": {"lyric": PLAIN_TEXT}},
        },
    )
    p = NetEaseProvider()
    r = p.fetch_lyrics(META, cache_dir=cache_dir)
    synced, plain, instrumental = r.synced, r.plain, r.instrumental

    assert not instrumental
    assert synced is None
    assert plain is not None


# -- v1 endpoint preference ------------------------------------------------

def test_prefers_yrc_over_lrc(provider):
    song = _song()
    yrc_text = "[00:01.00,300,0]y line one\n[00:02.00,200,0]y line two"
    _, cache_dir = provider(
        search_results=[song],
        lyrics_map={12345: _lyrics_response(lrc=SYNCED_LRC, yrc=yrc_text)},
    )
    p = NetEaseProvider()
    synced = p.fetch_lyrics(META, cache_dir=cache_dir).synced

    assert synced is not None
    assert synced[0].text == "y line one"


def test_falls_back_to_lrc_when_yrc_not_synced(provider):
    song = _song()
    _, cache_dir = provider(
        search_results=[song],
        lyrics_map={12345: _lyrics_response(lrc=SYNCED_LRC, yrc="plain text")},
    )
    p = NetEaseProvider()
    synced = p.fetch_lyrics(META, cache_dir=cache_dir).synced

    assert synced is not None
    assert synced[0].text == "line one"


def test_translated_lyrics_never_used_as_lyrics(provider):
    """tlyric is a translation, not the song's words: fall back to plain lrc."""
    song = _song()
    _, cache_dir = provider(
        search_results=[song],
        lyrics_map={
            12345: _lyrics_response(lrc=PLAIN_TEXT, tlyric=SYNCED_LRC, romalrc=SYNCED_LRC),
        },
    )
    r = NetEaseProvider().fetch_lyrics(META, cache_dir=cache_dir)

    assert r.synced is None
    assert r.plain is not None
    assert r.plain[0].text == "line one"


# -- match verification ------------------------------------------------------

def test_live_version_skipped_for_studio_track(provider):
    live = _song(id=1, name="Song (Live)", duration_ms=121000)
    studio = _song(id=2, name="Song", duration_ms=120000)
    calls, cache_dir = provider(
        search_results=[live, studio],
        lyrics_map={
            1: _lyrics_response(lrc="[00:01.00]live one\n[00:02.00]live two"),
            2: _lyrics_response(),
        },
    )
    r = NetEaseProvider().fetch_lyrics(META, cache_dir=cache_dir)

    assert r.synced[0].text == "line one"
    assert not any(p and p.get("id") == "1" for _, p in calls)


def test_wrong_duration_rejected(provider):
    long_cut = _song(id=1, duration_ms=200000)
    _, cache_dir = provider(search_results=[long_cut], lyrics_map={1: _lyrics_response()})
    r = NetEaseProvider().fetch_lyrics(META, cache_dir=cache_dir)

    assert r.synced is None
    assert "duration differs" in r.rejected


def test_different_artist_rejected(provider):
    cover = _song(id=1, artists=["Somebody Else"])
    _, cache_dir = provider(search_results=[cover], lyrics_map={1: _lyrics_response()})
    r = NetEaseProvider().fetch_lyrics(META, cache_dir=cache_dir)

    assert r.synced is None
    assert "artist mismatch" in r.rejected


def test_lyrics_longer_than_track_rejected(provider):
    _, cache_dir = provider(
        search_results=[_song(id=1)],
        lyrics_map={1: _lyrics_response(lrc="[00:01.00]a\n[04:00.00]b")},
    )
    r = NetEaseProvider().fetch_lyrics(META, cache_dir=cache_dir)

    assert r.synced is None
    assert "lyrics run to 4:00" in r.rejected


def test_credit_lines_stripped(provider):
    lrc = ('[00:00.00]作词 : Someone\n[00:00.50]作曲 : Someone\n'
           '[00:00.60]{"t":0,"c":[{"tx":"制作人: "},{"tx":"Someone"}]}\n' + SYNCED_LRC)
    _, cache_dir = provider(search_results=[_song()], lyrics_map={12345: _lyrics_response(lrc=lrc)})
    r = NetEaseProvider().fetch_lyrics(META, cache_dir=cache_dir)

    assert [l.text for l in r.synced] == ["line one", "line two"]


def test_alias_title_matches():
    c = _candidate({"id": 1, "name": "夜に駆ける", "alias": ["Into the Night"],
                    "artists": [{"name": "YOASOBI"}], "duration": 261000})
    assert c.alt_titles == ["Into the Night"]
    assert c.duration == 261.0


def test_result_reports_match_details(provider):
    _, cache_dir = provider(search_results=[_song()], lyrics_map={12345: _lyrics_response()})
    r = NetEaseProvider().fetch_lyrics(META, cache_dir=cache_dir)

    assert r.confidence > 0.9
    assert '"Song" by Artist (2:00)' == r.matched


def test_song_duration_ms():
    assert _song_duration_ms({"duration": 120000}) == 120.0
    assert _song_duration_ms({"duration": 0}) is None
    assert _song_duration_ms({}) is None


# -- edge cases ------------------------------------------------------------

def test_no_title_raises_error():
    meta = TrackMetadata()
    p = NetEaseProvider()
    with pytest.raises(LyricsNotFoundError, match="no title"):
        p.fetch_lyrics(meta, cache_dir="/tmp/fake")


def test_network_error_raises_lyrics_not_found(monkeypatch, tmp_path):
    def fail(url, params=None, **kwargs):
        raise ConnectionError("no network")

    monkeypatch.setattr("audio2lrc.providers.netease._get", fail)
    p = NetEaseProvider()
    with pytest.raises(LyricsNotFoundError, match="NetEase request failed"):
        p.fetch_lyrics(META, cache_dir=str(tmp_path / "cache"))
