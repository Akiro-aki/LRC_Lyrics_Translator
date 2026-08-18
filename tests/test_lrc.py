"""LRC parser + writer tests."""

from audio2lrc.lrc.parser import looks_synced, parse_lrc
from audio2lrc.lrc.writer import format_timestamp, render_lrc
from audio2lrc.models import LyricLine, TrackMetadata

TEXT = """[ti:Title]
[ar:Artist]
[al:Album]
[00:01.00]First line
[00:02.50]Second line
[Chorus]
[00:03.25]Third line
[01:02.123]Millisecond precision
[00:04.5]Tenth precision
[00:05.00][00:07.00]Repeated timestamp
[00:08]No fraction
"""


def test_parse_synced():
    lines = parse_lrc(TEXT)
    first = lines[0]
    assert first.time == 1.0
    assert first.text == "First line"
    assert lines[1].time == 2.5
    assert lines[1].text == "Second line"


def test_parse_markers_kept_untimed():
    lines = parse_lrc(TEXT)
    marker = [l for l in lines if l.text == "[Chorus]"]
    assert len(marker) == 1
    assert marker[0].time is None


def test_parse_precision():
    lines = parse_lrc(TEXT)
    assert any(l.time == 62.123 for l in lines)
    assert any(l.time == 4.5 for l in lines)
    assert any(l.time == 8.0 for l in lines)


def test_parse_repeated_timestamp_splits():
    lines = parse_lrc(TEXT)
    repeated = [l for l in lines if l.text == "Repeated timestamp"]
    assert [l.time for l in repeated] == [5.0, 7.0]


def test_parse_plain_text_unsynced():
    lines = parse_lrc("just some plain text\nanother line")
    assert [l.text for l in lines] == ["just some plain text", "another line"]
    assert all(l.time is None for l in lines)


def test_metadata_tags_dropped():
    assert not any(l.text.startswith(("[ti:", "[ar:", "[al:")) for l in parse_lrc(TEXT))


def test_looks_synced():
    assert looks_synced("[00:12.34]hi")
    assert not looks_synced("plain words only")


def test_format_timestamp():
    assert format_timestamp(0) == "[00:00.00]"
    assert format_timestamp(12.34) == "[00:12.34]"
    assert format_timestamp(75.999) == "[01:16.00]"
    assert format_timestamp(599.99) == "[09:59.99]"


def test_render_plain():
    meta = TrackMetadata(title="T", artist="A", album="B")
    text = render_lrc(meta, [LyricLine(12.34, "hello")], source="embedded")
    assert "[ti:T]" in text
    assert "[ar:A]" in text
    assert "[al:B]" in text
    assert "#X-SOURCE: embedded" in text
    assert "[00:12.34]hello" in text


def test_render_unsynced_marker_and_00():
    meta = TrackMetadata(title="T")
    text = render_lrc(
        meta,
        [LyricLine(None, "plain line"), LyricLine(None, "[Chorus]")],
        source="lrclib.net",
        unsynced=True,
    )
    assert "#X-UNSYNCED: true" in text
    assert "[00:00.00]plain line" in text
    assert "[00:00.00][Chorus]" in text


def test_render_translated_stacked():
    meta = TrackMetadata(title="T", artist="A")
    lines = [
        LyricLine(1.0, "original"),
        LyricLine(1.0, "romaji"),
        LyricLine(1.0, "translated"),
    ]
    text = render_lrc(
        meta,
        lines,
        source="lrclib.net",
        translated_from="ja",
        target_lang="en",
        romanized=True,
    )
    assert "#X-TRANSLATED-FROM: ja" in text
    assert "#X-TARGET-LANG: en" in text
    assert "#X-ROMANIZED: true" in text
    assert text.count("[00:01.00]") == 3