"""Audio tag extraction tests (mp3 / flac / m4a)."""

from audio2lrc.audio.tags import read_track

from conftest import SYNCED_LRC, tag_flac, tag_m4a, tag_mp3


def test_mp3_sylt_extracted(mp3_path):
    tag_mp3(mp3_path, synced_text=SYNCED_LRC)
    meta, embedded = read_track(str(mp3_path))
    assert meta.title == "Song Title"
    assert meta.artist == "Artist Name"
    assert meta.album == "Some Album"
    assert meta.duration is not None
    assert embedded is not None
    assert embedded.synced is True
    assert embedded.note == "SYLT frame"


def test_mp3_uslt_is_unsynced(mp3_path):
    tag_mp3(mp3_path, plain_text="plain words\nno timestamps")
    _, embedded = read_track(str(mp3_path))
    assert embedded is not None
    assert embedded.synced is False
    assert embedded.note == "USLT frame"


def test_mp3_uslt_with_lrc_pattern_counts_as_synced(mp3_path):
    tag_mp3(mp3_path, plain_text="[00:01.00]has timestamps")
    _, embedded = read_track(str(mp3_path))
    assert embedded.synced is True


def test_mp3_sylt_preferred_over_uslt(mp3_path):
    tag_mp3(mp3_path, synced_text=SYNCED_LRC, plain_text="plain words")
    _, embedded = read_track(str(mp3_path))
    assert embedded.note == "SYLT frame"
    assert embedded.synced is True


def test_mp3_no_lyrics(mp3_path):
    tag_mp3(mp3_path)
    _, embedded = read_track(str(mp3_path))
    assert embedded is None


def test_flac_lyrics_unsynced(flac_path):
    tag_flac(flac_path, lyrics="first verse\nsecond verse")
    meta, embedded = read_track(str(flac_path))
    assert meta.title == "Song Title"
    assert embedded is not None
    assert embedded.synced is False
    assert embedded.note == "lyrics"


def test_flac_lyrics_with_timestamps_synced(flac_path):
    tag_flac(flac_path, lyrics=SYNCED_LRC)
    _, embedded = read_track(str(flac_path))
    assert embedded.synced is True


def test_flac_unsyncedlyrics_key(flac_path):
    from mutagen.flac import FLAC

    tag_flac(flac_path)
    f = FLAC(flac_path)
    f["UNSYNCEDLYRICS"] = "old school tag"
    f.save()
    _, embedded = read_track(str(flac_path))
    assert embedded is not None
    assert embedded.note == "unsyncedlyrics"
    assert embedded.synced is False


def test_m4a_lyr_atom(m4a_path):
    tag_m4a(m4a_path, lyrics="some lyrics here")
    meta, embedded = read_track(str(m4a_path))
    assert meta.title == "Song Title"
    assert meta.artist == "Artist Name"
    assert embedded is not None
    assert embedded.synced is False
    assert embedded.note == "\xa9lyr atom"


def test_m4a_lyr_with_lrc_pattern_synced(m4a_path):
    tag_m4a(m4a_path, lyrics=SYNCED_LRC)
    _, embedded = read_track(str(m4a_path))
    assert embedded.synced is True


def test_filename_fallback(mp3_path):
    from pathlib import Path

    import mutagen

    no_tags = mp3_path.parent / "Singer - Famous Song.mp3"
    no_tags.write_bytes(Path(mp3_path).read_bytes())
    tag_mp3(no_tags)
    from mutagen.mp3 import MP3

    audio = MP3(no_tags)
    audio.delete()
    meta, _ = read_track(str(no_tags))
    assert meta.artist == "Singer"
    assert meta.title == "Famous Song"
    assert meta.filename_guess is True


def test_unsupported_file(tmp_path):
    bad = tmp_path / "notes.txt"
    bad.write_text("hello")
    try:
        read_track(str(bad))
        assert False, "expected ValueError"
    except ValueError:
        pass