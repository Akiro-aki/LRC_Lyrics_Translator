"""Tests for the TUI orchestration (non-interactive parts)."""

import pytest

from conftest import SYNCED_LRC, tag_mp3

from audio2lrc.tui import TUIOptions, _opts_to_args, run_pipeline


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


def test_opts_to_args_maps_fields():
    opts = TUIOptions(
        mode="file", path="/tmp/x.mp3", provider="auto",
        translate=True, target_lang="en", source_lang="fr",
        translator="gemini", api_key="k", romanize=True, out="/tmp/o.lrc",
        prefer_external=True,
    )
    a = _opts_to_args(opts)
    assert a.provider == "auto"
    assert a.translate is True
    assert a.target_lang == "en"
    assert a.source_lang == "fr"
    assert a.translator == "gemini"
    assert a.api_key == "k"
    assert a.romanize is True
    assert a.out == "/tmp/o.lrc"
    assert a.prefer_external is True
    assert a.prefer_embedded is False
    assert a.audio == "/tmp/x.mp3"


def test_run_pipeline_link_mode(fake_lrclib, tmp_path, monkeypatch):
    fake_lrclib({"trackName": "Linked", "artistName": "A", "syncedLyrics": SYNCED_LRC})
    monkeypatch.chdir(tmp_path)
    opts = TUIOptions(mode="link", path="https://lrclib.net/song/123")
    assert run_pipeline(opts) == 0
    assert (tmp_path / "Linked.lrc").exists()


def test_run_pipeline_link_mode_failure(fake_lrclib, tmp_path, monkeypatch):
    fake_lrclib({"trackName": "Empty", "syncedLyrics": None, "plainLyrics": None})
    monkeypatch.chdir(tmp_path)
    opts = TUIOptions(mode="link", path="https://lrclib.net/song/999")
    assert run_pipeline(opts) == 1
    assert not (tmp_path / "Empty.lrc").exists()


def test_run_pipeline_single_file_embedded(mp3_path):
    tag_mp3(mp3_path, synced_text=SYNCED_LRC)
    opts = TUIOptions(mode="file", path=str(mp3_path), provider="lrclib")
    assert run_pipeline(opts) == 0
    assert mp3_path.with_suffix(".lrc").exists()


def test_run_pipeline_missing_path(tmp_path):
    opts = TUIOptions(mode="file", path=str(tmp_path / "nope.mp3"))
    assert run_pipeline(opts) == 1


def test_run_pipeline_directory_batch(tmp_path):
    d = tmp_path / "music"
    d.mkdir()
    good = d / "Artist - Song.mp3"
    good.write_bytes(__import__("conftest")._minimal_mp3_bytes())
    tag_mp3(good, title="Song", artist="Artist", synced_text=SYNCED_LRC)
    opts = TUIOptions(mode="dir", path=str(d), provider="lrclib")
    assert run_pipeline(opts) == 0
    assert (d / "Artist - Song.lrc").exists()


def test_run_pipeline_directory_batch_reports_failure(tmp_path, monkeypatch):
    import conftest

    d = tmp_path / "music"
    d.mkdir()
    bad = d / "Bad - NoLyrics.mp3"
    bad.write_bytes(conftest._minimal_mp3_bytes())

    def no_match(url):
        return None

    monkeypatch.setattr("audio2lrc.providers.lrclib._request", no_match)
    opts = TUIOptions(mode="dir", path=str(d), provider="lrclib")
    assert run_pipeline(opts) == 1
