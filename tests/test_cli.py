"""CLI smoke test: end-to-end with an embedded-lyrics mp3, fully offline."""

import os
import subprocess
import sys

from conftest import SYNCED_LRC, tag_mp3

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run(*args, env=None):
    full_env = dict(os.environ)
    full_env["PYTHONPATH"] = os.path.join(ROOT, "src")
    full_env.pop("CACHE_DIR", None)
    if env:
        full_env.update(env)
    return subprocess.run(
        [sys.executable, "-m", "audio2lrc", *args],
        capture_output=True,
        text=True,
        cwd=ROOT,
        env=full_env,
    )


def test_cli_plain_from_embedded_sylt(mp3_path):
    tag_mp3(mp3_path, synced_text=SYNCED_LRC)
    proc = _run(str(mp3_path))
    assert proc.returncode == 0, proc.stderr
    out = mp3_path.with_suffix(".lrc")
    assert out.exists()
    text = out.read_text(encoding="utf-8")
    assert "#X-SOURCE: embedded" in text
    assert "[00:01.00]First line" in text
    assert "#X-UNSYNCED" not in text


def test_cli_translate_requires_target_lang(mp3_path):
    tag_mp3(mp3_path, synced_text=SYNCED_LRC)
    proc = _run(str(mp3_path), "--translate")
    assert proc.returncode == 2
    assert "--target-lang" in proc.stderr


def test_cli_output_name_for_translated(mp3_path):
    tag_mp3(mp3_path, synced_text=SYNCED_LRC)
    proc = _run(
        str(mp3_path),
        "--translate",
        "--target-lang",
        "en",
        env={"TRANSLATOR_BACKEND": "google"},
    )
    if proc.returncode != 0 and "network" in proc.stderr.lower():
        pass  # offline environment: skip network-dependent assertions
    else:
        assert proc.returncode == 0, proc.stderr
        out = mp3_path.with_name("track.lrc")
        assert out.exists()


def test_cli_no_lyrics_errors(tmp_path):
    import conftest

    empty = tmp_path / "Silent - Instrumental.mp3"
    empty.write_bytes(conftest._minimal_mp3_bytes())
    proc = _run(str(empty), env={"LRCLIB_URL": "http://127.0.0.1:1"})
    assert proc.returncode == 1
    assert "lrclib" in proc.stderr.lower() or "no lyrics" in proc.stderr.lower()


def test_cli_batch_directory(tmp_path):
    import conftest

    d = tmp_path / "music"
    d.mkdir()
    good = d / "Artist One - First Song.mp3"
    good.write_bytes(conftest._minimal_mp3_bytes())
    tag_mp3(good, title="First Song", artist="Artist One", synced_text=SYNCED_LRC)
    other = d / "Artist Two - Second Song.mp3"
    other.write_bytes(conftest._minimal_mp3_bytes())
    tag_mp3(other, title="Second Song", artist="Artist Two", synced_text=SYNCED_LRC)
    nested = d / "sub"
    nested.mkdir()
    deep = nested / "Artist Three - Third.mp3"
    deep.write_bytes(conftest._minimal_mp3_bytes())
    tag_mp3(deep, title="Third", artist="Artist Three", synced_text=SYNCED_LRC)

    proc = _run(str(d))
    assert proc.returncode == 0, proc.stderr
    assert (d / "Artist One - First Song.lrc").exists()
    assert (d / "Artist Two - Second Song.lrc").exists()
    assert not (nested / "Artist Three - Third.lrc").exists()  # non-recursive skips subdirs
    assert "2 ok, 0 failed" in proc.stderr

    proc = _run(str(d), "--recursive")
    assert proc.returncode == 0, proc.stderr
    assert (nested / "Artist Three - Third.lrc").exists()
    assert "3 ok, 0 failed" in proc.stderr


def test_cli_batch_continues_on_error(tmp_path):
    import conftest

    d = tmp_path / "mixed"
    d.mkdir()
    good = d / "Good - Track.mp3"
    good.write_bytes(conftest._minimal_mp3_bytes())
    tag_mp3(good, title="Track", artist="Good", synced_text=SYNCED_LRC)
    bad = d / "Bad - NoLyrics.mp3"
    bad.write_bytes(conftest._minimal_mp3_bytes())

    proc = _run(str(d), env={"LRCLIB_URL": "http://127.0.0.1:1"})
    assert proc.returncode == 1
    assert (d / "Good - Track.lrc").exists()  # good file still processed
    assert "1 ok, 1 failed" in proc.stderr


def test_cli_batch_rejects_out_flag(tmp_path):
    d = tmp_path / "music"
    d.mkdir()
    proc = _run(str(d), "--out", str(tmp_path / "x.lrc"))
    assert proc.returncode == 2
    assert "--out" in proc.stderr


def test_cli_batch_empty_directory(tmp_path):
    d = tmp_path / "empty"
    d.mkdir()
    proc = _run(str(d))
    assert proc.returncode == 1
    assert "no audio files" in proc.stderr