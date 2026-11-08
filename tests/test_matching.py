"""Shared lyric-match verification tests."""

import pytest

from audio2lrc.lrc.parser import parse_lrc
from audio2lrc.models import TrackMetadata
from audio2lrc.providers.matching import (
    Candidate,
    check_lyrics,
    clean_lines,
    is_instrumental_placeholder,
    normalize,
    rank,
    score_candidate,
    select_lyrics,
    similarity,
    variant_tags,
)

META = TrackMetadata(title="Song", artist="Artist", album="Album", duration=200.0)


def cand(title="Song", artists=("Artist",), album="Album", duration=200.0, id=1):
    return Candidate("test", id, title, list(artists), album, duration)


# -- normalisation -------------------------------------------------------------

@pytest.mark.parametrize("raw, expected", [
    ("Song (feat. Someone)", "song"),
    ("Song ft. Someone Else", "song"),
    ("Song - Remastered 2011", "song"),
    ("Song (2009 Remaster)", "song"),
    ("Song [Mono]", "song"),
    ("Song - Single", "song"),
    ("Ｓｏｎｇ", "song"),  # full-width
    ("Don't Stop Me Now", "dont stop me now"),
    ("夜に駆ける", "夜に駆ける"),
])
def test_normalize(raw, expected):
    assert normalize(raw) == expected


def test_normalize_keeps_version_markers():
    assert normalize("Song (Live)") == "song live"
    assert normalize("Song - Live 2019") == "song live 2019"


@pytest.mark.parametrize("title, tag", [
    ("Song (Live)", "live"),
    ("Song - Live at Wembley", "live"),
    ("Song (Remix)", "remix"),
    ("Song [Karaoke Version]", "karaoke"),
    ("Song (Instrumental)", "instrumental"),
    ("Song (伴奏)", "instrumental"),
    ("Song 伴奏", "instrumental"),
    ("Song (Acoustic)", "acoustic"),
    ("Song (Sped Up)", "sped up"),
    ("Song (English Ver.)", "lang:english"),
])
def test_variant_tags(title, tag):
    assert tag in variant_tags(title)


def test_variant_tags_ignore_words_in_the_title_itself():
    assert variant_tags("Live Forever") == set()
    assert variant_tags("Song") == set()


def test_similarity_ignores_featured_artists():
    assert similarity("Song (feat. X)", "Song") == 1.0


# -- gates -----------------------------------------------------------------------

def test_exact_match_high_confidence():
    m = score_candidate(cand(), META)
    assert m.rejected is None
    assert m.confidence == pytest.approx(1.0)


@pytest.mark.parametrize("title, reason", [
    ("Song (Live)", "live"),
    ("Song (Remix)", "remix"),
    ("Song (Karaoke)", "karaoke"),
    ("Song (Instrumental)", "instrumental"),
])
def test_version_mismatch_rejected(title, reason):
    m = score_candidate(cand(title=title), META)
    assert m.rejected and "version mismatch" in m.rejected and reason in m.rejected


def test_version_accepted_when_file_has_same_tag():
    meta = TrackMetadata(title="Song (Live)", artist="Artist", duration=200.0)
    assert score_candidate(cand(title="Song - Live"), meta).rejected is None


def test_language_version_requested_but_missing_rejected():
    meta = TrackMetadata(title="Song (English Ver.)", artist="Artist", duration=200.0)
    m = score_candidate(cand(title="Song"), meta)
    assert m.rejected and "lang:english" in m.rejected


def test_different_title_rejected():
    m = score_candidate(cand(title="Another Tune"), META)
    assert m.rejected and "title mismatch" in m.rejected


def test_duration_within_gate_accepted_with_lower_score():
    close = score_candidate(cand(duration=201.0), META)
    off = score_candidate(cand(duration=209.0), META)
    assert off.rejected is None
    assert off.confidence < close.confidence


def test_duration_beyond_gate_rejected():
    m = score_candidate(cand(duration=212.0), META)
    assert m.rejected and "duration differs by 12s" in m.rejected


def test_wrong_artist_rejected():
    m = score_candidate(cand(artists=["Totally Different Band"]), META)
    assert m.rejected and "artist mismatch" in m.rejected


def test_wrong_artist_tolerated_when_artist_guessed_from_filename():
    meta = TrackMetadata(title="Song", artist="Artist", duration=200.0, filename_guess=True)
    m = score_candidate(cand(artists=["Totally Different Band"]), meta)
    assert m.rejected is None
    assert m.confidence < score_candidate(cand(), meta).confidence


def test_collaboration_artist_matches_one_of_many():
    meta = TrackMetadata(title="Song", artist="Artist feat. Guest", duration=200.0)
    assert score_candidate(cand(artists=["Artist", "Guest"]), meta).rejected is None


def test_album_mismatch_not_penalised():
    assert score_candidate(cand(album="Greatest Hits"), META).confidence == pytest.approx(1.0)


def test_title_only_match_is_capped():
    meta = TrackMetadata(title="Song")
    m = score_candidate(cand(artists=[], duration=None), meta)
    assert m.rejected is None
    assert m.confidence <= 0.7


def test_alt_title_can_match():
    meta = TrackMetadata(title="Into the Night", artist="YOASOBI")
    c = Candidate("t", 1, "夜に駆ける", ["YOASOBI"], alt_titles=["Into the Night"])
    assert score_candidate(c, meta).rejected is None


def test_rank_orders_and_reports_closest_rejection():
    good = cand(id=1, duration=203.0)
    best = cand(id=2, duration=200.0)
    live = cand(id=3, title="Song (Live)")
    accepted, closest = rank([good, live, best], META)
    assert [m.candidate.id for m in accepted] == [2, 1]
    assert closest.candidate.id == 3


def test_rank_applies_min_confidence():
    meta = TrackMetadata(title="Song")
    accepted, closest = rank([cand(artists=[], duration=None)], meta, min_confidence=0.8)
    assert accepted == []
    assert "low confidence" in closest.rejected


# -- lyric checks --------------------------------------------------------------

def test_clean_lines_drops_credits_and_notices():
    lines = parse_lrc(
        "[00:00.00]作词 : A\n[00:00.10]作曲：B\n[00:00.20]Lyrics by: C\n"
        "[00:01.00]real line\n[00:02.00]another\n"
        "[00:03.00]TME享有本翻译作品的著作权"
    )
    assert [l.text for l in clean_lines(lines)] == ["real line", "another"]


def test_clean_lines_drops_title_artist_header():
    lines = parse_lrc("[00:00.00]Song - Artist\n[00:01.00]Song is my first line")
    out = clean_lines(lines, META)
    assert [l.text for l in out] == ["Song is my first line"]


def test_check_lyrics_overrun_rejected():
    lines = parse_lrc("[00:01.00]a\n[03:40.00]b")
    assert "lyrics run to 3:40" in check_lyrics(lines, 200.0)
    assert check_lyrics(parse_lrc("[00:01.00]a\n[03:30.00]b"), 200.0) is None


def test_check_lyrics_too_short():
    assert check_lyrics(parse_lrc("[00:01.00]only one"), 200.0) == "too few lyric lines"


def test_instrumental_placeholder():
    assert is_instrumental_placeholder(parse_lrc("[00:00.00]纯音乐，请欣赏"))
    assert not is_instrumental_placeholder(parse_lrc("[00:00.00]a\n[00:01.00]b"))


def test_select_lyrics_prefers_synced_candidate():
    accepted, _ = rank([cand(id=1), cand(id=2, duration=202.0)], META)
    lyrics = {1: (None, "a\nb", False), 2: ("[00:01.00]a\n[00:02.00]b", None, False)}
    result = select_lyrics(accepted, lambda c: lyrics[c.id], META)
    assert result["id"] == 2 and "lrc" in result


def test_select_lyrics_skips_failing_lyrics():
    accepted, _ = rank([cand(id=1), cand(id=2)], META)
    lyrics = {1: ("[00:01.00]a\n[09:00.00]b", None, False), 2: ("[00:01.00]a\n[00:02.00]b", None, False)}
    assert select_lyrics(accepted, lambda c: lyrics[c.id], META)["id"] == 2


def test_translated_subtitle_in_brackets_still_matches():
    meta = TrackMetadata(title="夜に駆ける", artist="YOASOBI", duration=261.0)
    m = score_candidate(cand(title="夜に駆ける (向夜晚奔去)", artists=["YOASOBI"], duration=261.0), meta)
    assert m.rejected is None
    assert 0.9 < m.confidence < 1.0


def test_bracketed_live_still_rejected_after_base_title():
    meta = TrackMetadata(title="夜に駆ける", artist="YOASOBI", duration=261.0)
    m = score_candidate(cand(title="夜に駆ける (DOME LIVE 2024)", artists=["YOASOBI"], duration=263.0), meta)
    assert m.rejected and "live" in m.rejected


def test_artist_alias_in_brackets():
    meta = TrackMetadata(title="晴天", artist="周杰伦", duration=269.0)
    m = score_candidate(cand(title="晴天", artists=["周杰伦 (Jay Chou)"], duration=269.0), meta)
    assert m.confidence == pytest.approx(1.0)


def test_header_with_artist_alias_stripped():
    meta = TrackMetadata(title="晴天", artist="周杰伦")
    lines = parse_lrc("[00:00.00]晴天 - 周杰伦 (Jay Chou)\n[00:01.00]故事的小黄花")
    assert [l.text for l in clean_lines(lines, meta)] == ["故事的小黄花"]


def test_leading_credit_block_stripped_but_not_later_lines():
    lines = parse_lrc(
        "[00:00.00]Drums：David Stewart\n[00:00.50]Vocal Directing: Someone\n"
        "[00:00.70]Recording Engineer - Pdogg @ Studio\n"
        "[00:01.00]Shining through the city\n[00:02.00]Me: and you: forever"
    )
    assert [l.text for l in clean_lines(lines)] == [
        "Shining through the city", "Me: and you: forever"]


def test_dash_line_without_credit_keyword_kept():
    lines = parse_lrc("[00:01.00]Baby - I love you\n[00:02.00]second line")
    assert [l.text for l in clean_lines(lines)] == ["Baby - I love you", "second line"]


def test_romanised_artist_matches_kana_alias():
    meta = TrackMetadata(title="IRIS OUT", artist="Kenshi Yonezu", duration=151.6)
    m = score_candidate(cand(title="IRIS OUT", artists=["米津玄師 (よねづ けんし)"], duration=151.0), meta)
    assert m.rejected is None
    assert m.confidence > 0.9


def test_cross_script_artist_accepted_only_with_tight_title_and_duration():
    meta = TrackMetadata(title="IRIS OUT", artist="Kenshi Yonezu", duration=151.6)
    tight = score_candidate(cand(title="IRIS OUT", artists=["米津玄師"], duration=151.0), meta)
    loose = score_candidate(cand(title="IRIS OUT", artists=["米津玄師"], duration=158.0), meta)
    assert tight.rejected is None and tight.confidence <= 0.85
    assert loose.rejected and "artist mismatch" in loose.rejected


def test_same_script_wrong_artist_still_rejected_even_when_tight():
    meta = TrackMetadata(title="Song", artist="Artist", duration=200.0)
    assert score_candidate(cand(artists=["Someone Else"], duration=200.0), meta).rejected


def test_artist_word_order_ignored():
    meta = TrackMetadata(title="Song", artist="Yonezu Kenshi", duration=200.0)
    assert score_candidate(cand(artists=["Kenshi Yonezu"]), meta).confidence > 0.9
