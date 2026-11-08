"""Shared candidate matching: make sure fetched lyrics belong to the track.

Every provider turns its search results into :class:`Candidate` objects and
runs them through :func:`rank`, which applies hard gates (title, version,
duration, artist) and assigns a 0..1 confidence.  The lyrics of the chosen
candidate are then cleaned (:func:`clean_lines`) and sanity-checked against
the track (:func:`check_lyrics`) before being accepted.
"""

from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any, Callable

from audio2lrc.lrc.parser import parse_lrc
from audio2lrc.models import LyricLine, ProviderResult, TrackMetadata

MIN_CONFIDENCE = 0.6
# A synced result at or above this confidence ends an "auto" search early.
STRONG_CONFIDENCE = 0.9

TITLE_GATE = 0.75
ARTIST_GATE = 0.6
MAX_DURATION_DIFF = 10.0  # seconds; candidates further off are a different cut
FULL_DURATION_DIFF = 2.0  # seconds; at or below this the duration score is 1.0
LYRICS_OVERRUN = 15.0  # seconds lyrics may run past the end of the track
MAX_CANDIDATES = 5

_WEIGHTS = {"title": 0.45, "artist": 0.25, "duration": 0.20, "album": 0.10}
_WEAK_CAP = 0.7  # confidence cap when neither artist nor duration can be compared
_UNVERIFIED_ARTIST_CAP = 0.85  # artist in another script; below STRONG_CONFIDENCE


def default_min_confidence() -> float:
    """MIN_CONFIDENCE, overridable with the LYRICS_MIN_CONFIDENCE env var."""
    raw = os.environ.get("LYRICS_MIN_CONFIDENCE", "").strip()
    if not raw:
        return MIN_CONFIDENCE
    try:
        return min(1.0, max(0.0, float(raw)))
    except ValueError:
        return MIN_CONFIDENCE


# -- candidates --------------------------------------------------------------


@dataclass
class Candidate:
    """One search result from a provider, normalised to common fields."""

    provider: str
    id: Any
    title: str
    artists: list[str] = field(default_factory=list)
    album: str | None = None
    duration: float | None = None  # seconds
    alt_titles: list[str] = field(default_factory=list)
    raw: dict = field(default_factory=dict)

    def describe(self) -> str:
        text = f'"{self.title}"'
        if self.artists:
            text += " by " + ", ".join(self.artists)
        if self.duration:
            text += f" ({format_time(self.duration)})"
        return text


@dataclass
class Match:
    candidate: Candidate
    confidence: float
    rejected: str | None = None


def format_time(seconds: float) -> str:
    seconds = int(round(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


# -- normalisation -----------------------------------------------------------

_BRACKET_RE = re.compile(r"[\(\[\{【〔「『]([^\)\]\}】〕」』]*)[\)\]\}】〕」』]")
_DASH_SUFFIX_RE = re.compile(r"\s[-–—~]\s*(.+)$")
_FEAT_INNER_RE = re.compile(r"^\s*(?:feat|ft|featuring|with|prod)\b\.?", re.I)
_FEAT_TAIL_RE = re.compile(r"\s(?:feat|ft|featuring)\b\.?\s.*$", re.I)
# Qualifiers that do not change the recording's lyrics.
_NEUTRAL_RE = re.compile(
    r"remaster|\b\d{4}\b|\bmono\b|\bstereo\b|\bexplicit\b|\bclean\b|"
    r"album ver|single ver|original ver|original mix|\bsingle\b|\bep\b|"
    r"\bfrom\b|\bost\b|soundtrack|theme|主题曲|插曲|片尾曲|片头曲",
    re.I,
)

# Version markers: a candidate carrying one the file's title lacks is a
# different recording (or has no vocals, or different words).
_VARIANTS: dict[str, str] = {
    "remix": r"\bremix|\brmx\b|\bbootleg\b|\bdj\b|dj版|抖音版",
    "live": r"\blive\b|现场|演唱会|\bconcert\b|the first take",
    "acoustic": r"\bacoustic\b|\bunplugged\b|不插电",
    "instrumental": r"\binstrumental\b|\binst\b|off\s*vocal|\bbacking track\b|伴奏|纯音乐|純音樂",
    "karaoke": r"\bkaraoke\b|カラオケ|\bminus one\b",
    "cover": r"\bcover\b|翻唱|翻自|[女男]声版|[女男]生版|[女男]聲版",
    "sped up": r"\bsped\s*up\b|\bspeed\s*up\b|加速版",
    "slowed": r"\bslowed\b|降速版",
    "nightcore": r"\bnightcore\b",
    "demo": r"\bdemo\b",
    "tv size": r"\btv\s*(?:size|ver)",
}
# Markers that are unambiguous even outside brackets.
_VARIANTS_ANYWHERE: dict[str, str] = {
    "instrumental": r"伴奏|纯音乐|純音樂|off\s*vocal",
    "karaoke": r"カラオケ",
    "cover": r"翻唱|翻自|[女男]声版|[女男]生版|[女男]聲版",
    "remix": r"dj版|抖音版",
    "live": r"现场版|\(live\)|live版",
}
_LANG_VERSION_RE = re.compile(
    r"\b(english|japanese|korean|chinese|mandarin|cantonese|spanish|french|"
    r"german|thai|eng|jpn|kor)\s*(?:ver|version)\b|"
    r"(日本語|日文|英文|韩文|韓文|中文|国语|國語|粤语|粵語)版?",
    re.I,
)


def _nfkc(s: str) -> str:
    return unicodedata.normalize("NFKC", s or "").casefold().strip()


def _qualifiers(s: str) -> list[str]:
    """Bracketed and dash-suffixed qualifier segments of a title."""
    parts = [m.group(1) for m in _BRACKET_RE.finditer(s)]
    m = _DASH_SUFFIX_RE.search(_BRACKET_RE.sub(" ", s))
    if m:
        parts.append(m.group(1))
    return parts


def normalize(s: str | None) -> str:
    """Normalise a title or artist for comparison.

    Folds width and case, drops featured-artist clauses and qualifiers that
    do not change the recording (remaster, year, mono, "from ..."), strips
    punctuation and collapses whitespace.  Version markers such as "(Live)"
    are kept so that :func:`variant_tags` and similarity still see them.
    """
    text = _nfkc(s or "")
    if not text:
        return ""

    def bracket(m: re.Match) -> str:
        inner = m.group(1)
        if _FEAT_INNER_RE.match(inner) or (_NEUTRAL_RE.search(inner) and not _is_variant(inner)):
            return " "
        return " " + inner + " "

    text = _BRACKET_RE.sub(bracket, text)
    m = _DASH_SUFFIX_RE.search(text)
    if m and _NEUTRAL_RE.search(m.group(1)) and not _is_variant(m.group(1)):
        text = text[: m.start()]
    text = _FEAT_TAIL_RE.sub("", text)
    text = re.sub(r"['’`´]", "", text)
    text = "".join(
        " " if unicodedata.category(ch)[0] in ("P", "S") else ch for ch in text
    )
    return " ".join(text.split())


def _is_variant(text: str) -> bool:
    text = _nfkc(text)
    return any(re.search(p, text) for p in _VARIANTS.values()) or bool(
        _LANG_VERSION_RE.search(text)
    )


def variant_tags(s: str | None) -> set[str]:
    """Version markers in a title (remix, live, instrumental, lang:english, ...)."""
    text = _nfkc(s or "")
    if not text:
        return set()
    tags: set[str] = set()
    scope = " ".join(_nfkc(q) for q in _qualifiers(text))
    for tag, pattern in _VARIANTS.items():
        if scope and re.search(pattern, scope):
            tags.add(tag)
    for tag, pattern in _VARIANTS_ANYWHERE.items():
        if re.search(pattern, text):
            tags.add(tag)
    for m in _LANG_VERSION_RE.finditer(scope or ""):
        tags.add("lang:" + (m.group(1) or m.group(2)).lower())
    return tags


def similarity(a: str | None, b: str | None) -> float:
    """0..1 similarity of two titles/artists after normalisation."""
    na, nb = normalize(a), normalize(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    return SequenceMatcher(None, na, nb).ratio()


def base_title(s: str | None) -> str:
    """Title with every non-version qualifier removed, normalised.

    "夜に駆ける (向夜晚奔去)" and "Song - From the Movie" both reduce to the bare
    title; version qualifiers such as "(Live)" are kept.
    """
    text = _nfkc(s or "")
    text = _BRACKET_RE.sub(lambda m: m.group(0) if _is_variant(m.group(1)) else " ", text)
    m = _DASH_SUFFIX_RE.search(text)
    if m and not _is_variant(m.group(1)):
        text = text[: m.start()]
    return normalize(text)


# Comparing bare titles (subtitle/translation dropped) is slightly weaker
# evidence than comparing the full titles.
_BASE_TITLE_PENALTY = 0.95


def title_similarity(meta_title: str, titles: list[str]) -> float:
    best = 0.0
    mine_base = base_title(meta_title)
    for t in titles:
        if not t:
            continue
        best = max(best, similarity(meta_title, t))
        theirs_base = base_title(t)
        if mine_base and theirs_base:
            if mine_base == theirs_base:
                best = max(best, _BASE_TITLE_PENALTY)
            else:
                ratio = SequenceMatcher(None, mine_base, theirs_base).ratio()
                best = max(best, ratio * _BASE_TITLE_PENALTY)
    return best


_ARTIST_SPLIT_RE = re.compile(
    r"\s*(?:,|&|/|;|、|，|\bx\b|\bfeat\b\.?|\bft\b\.?|\bfeaturing\b|\band\b|\bwith\b|\bvs\b\.?)\s*",
    re.I,
)


def _split_artists(text: str) -> list[str]:
    # A bracketed alias ("周杰伦 (Jay Chou)") counts as another name.
    text = _BRACKET_RE.sub(lambda m: ", " + m.group(1) + ", ", _nfkc(text))
    return [a for a in _ARTIST_SPLIT_RE.split(text) if a and a.strip()]


_CJK_RE = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af]")
_KANA_RE = re.compile(r"[\u3040-\u30ff]")
_romanizers: dict[str, Any] = {}


def _romanize(text: str) -> str | None:
    """Best-effort Latin form of a CJK name (kana via pykakasi, hanzi via pinyin)."""
    try:
        if _KANA_RE.search(text):
            if "ja" not in _romanizers:
                import pykakasi

                _romanizers["ja"] = pykakasi.kakasi()
            items = _romanizers["ja"].convert(text)
            return "".join(i["hepburn"] or i["orig"] for i in items)
        if "zh" not in _romanizers:
            from pypinyin import lazy_pinyin

            _romanizers["zh"] = lazy_pinyin
        return " ".join(_romanizers["zh"](text, errors=lambda x: x))
    except ImportError:
        return None


def _order_free_similarity(a: str, b: str) -> float:
    """Similarity ignoring word order and spacing ("yonezu kenshi" ~ "Kenshi Yonezu")."""
    ta, tb = normalize(a).split(), normalize(b).split()
    if not ta or not tb:
        return 0.0
    sorted_ratio = SequenceMatcher(None, " ".join(sorted(ta)), " ".join(sorted(tb))).ratio()
    joined_ratio = SequenceMatcher(None, "".join(ta), "".join(tb)).ratio()
    return max(sorted_ratio, joined_ratio)


def _name_similarity(a: str, b: str) -> float:
    sim = similarity(a, b)
    a_cjk, b_cjk = bool(_CJK_RE.search(a)), bool(_CJK_RE.search(b))
    if a_cjk != b_cjk:
        cjk, latin = (a, b) if a_cjk else (b, a)
        roman = _romanize(cjk)
        if roman:
            sim = max(sim, _order_free_similarity(roman, latin))
    elif not a_cjk:
        sim = max(sim, _order_free_similarity(a, b))
    return sim


def _scripts_differ(meta_artist: str, artists: list[str]) -> bool:
    """The file's artist and every candidate artist are written in different scripts."""
    mine = bool(_CJK_RE.search(meta_artist))
    return all(bool(_CJK_RE.search(a)) != mine for a in artists)


def artist_similarity(meta_artist: str, artists: list[str]) -> float:
    """Best similarity between the file's artist(s) and a candidate's artists."""
    if not meta_artist or not artists:
        return 0.0
    mine = _split_artists(meta_artist) or [meta_artist]
    theirs: list[str] = []
    for a in artists:
        theirs.extend(_split_artists(a) or [a])
    best = max((_name_similarity(x, y) for x in mine for y in theirs), default=0.0)
    return max(best, similarity(meta_artist, " ".join(artists)))


# -- scoring -----------------------------------------------------------------


def score_candidate(c: Candidate, meta: TrackMetadata) -> Match:
    """Score one candidate against the track; ``rejected`` says why it fails."""
    if not c.title:
        return Match(c, 0.0, "result has no title")

    scores: dict[str, float] = {}

    title_sim = 1.0
    if meta.title:
        title_sim = title_similarity(meta.title, [c.title, *c.alt_titles])
        scores["title"] = title_sim

    if meta.title:
        mine, theirs = variant_tags(meta.title), variant_tags(c.title)
        extra = theirs - mine
        # A language version the file asks for but the candidate lacks means
        # the words differ too.
        extra |= {t for t in mine - theirs if t.startswith("lang:")}
        if extra:
            return Match(c, title_sim, f"version mismatch ({', '.join(sorted(extra))})")

    if meta.title and title_sim < TITLE_GATE:
        return Match(c, title_sim, f"title mismatch (similarity {title_sim:.2f})")

    have_duration = bool(meta.duration and c.duration)
    if have_duration:
        diff = abs(meta.duration - c.duration)
        if diff > MAX_DURATION_DIFF:
            return Match(
                c,
                0.0,
                f"duration differs by {diff:.0f}s "
                f"({format_time(c.duration)} vs {format_time(meta.duration)})",
            )
        if diff <= FULL_DURATION_DIFF:
            scores["duration"] = 1.0
        else:
            scores["duration"] = max(
                0.0, 1.0 - (diff - FULL_DURATION_DIFF) / (MAX_DURATION_DIFF - FULL_DURATION_DIFF)
            )

    have_artist = bool(meta.artist and c.artists)
    artist_unverified = False
    if have_artist:
        artist_sim = artist_similarity(meta.artist, c.artists)
        if artist_sim < ARTIST_GATE and not meta.filename_guess:
            # "Kenshi Yonezu" vs "米津玄師": names in different scripts that
            # romanisation could not reconcile.  Accept only when title and
            # duration both match tightly, and never as a strong match.
            tight = (
                have_duration
                and abs(meta.duration - c.duration) <= FULL_DURATION_DIFF
                and title_sim >= 0.95
            )
            if not (tight and _scripts_differ(meta.artist, c.artists)):
                return Match(c, artist_sim, f"artist mismatch ({', '.join(c.artists)})")
            artist_unverified = True
        else:
            scores["artist"] = artist_sim

    if meta.album and c.album:
        album_sim = similarity(meta.album, c.album)
        # Album names differ legitimately (single vs album release), so only
        # a match adds confidence; a mismatch is not held against the result.
        if album_sim >= 0.6:
            scores["album"] = album_sim

    if not scores:
        return Match(c, 0.0, "nothing to compare (no title in tags)")

    total = sum(_WEIGHTS[k] for k in scores)
    confidence = sum(_WEIGHTS[k] * v for k, v in scores.items()) / total
    if not have_duration and not have_artist:
        confidence = min(confidence, _WEAK_CAP)
    if artist_unverified:
        confidence = min(confidence, _UNVERIFIED_ARTIST_CAP)
    return Match(c, round(confidence, 3))


def rank(
    candidates: list[Candidate],
    meta: TrackMetadata,
    min_confidence: float = MIN_CONFIDENCE,
) -> tuple[list[Match], Match | None]:
    """Return (accepted matches best-first, closest rejected match or None)."""
    accepted: list[Match] = []
    rejected: list[Match] = []
    for c in candidates:
        m = score_candidate(c, meta)
        if m.rejected is None and m.confidence < min_confidence:
            m.rejected = f"low confidence ({m.confidence:.2f} < {min_confidence:.2f})"
        (rejected if m.rejected else accepted).append(m)
    accepted.sort(key=lambda m: m.confidence, reverse=True)
    closest = max(rejected, key=lambda m: m.confidence, default=None)
    return accepted, closest


# -- lyric checks --------------------------------------------------------------

_CREDIT_RE = re.compile(
    r"^\s*(?:"
    # Chinese credit roles, optionally followed by a short qualifier
    # ("混音工程师", "吉他手") before the colon.
    r"(?:作词|作詞|作曲|编曲|編曲|制作|製作|监制|監製|出品|发行|發行|混音|母带|母帶|"
    r"和声|和聲|合声|合聲|和音|录音|錄音|吉他|贝斯|貝斯|鼓|弦乐|弦樂|键盘|鍵盤|钢琴|鋼琴|"
    r"配唱|人声|人聲|统筹|統籌|策划|企划|版权|版權|封面|原唱|音乐总监|音樂總監|"
    r"视觉|視覺|设计|設計|宣传|宣傳|营销|營銷|OP|SP)[^:：\n]{0,8}|"
    r"词|詞|曲|"
    r"lyrics?(?:\s+by)?|lyricist|written\s+by|writers?|composer|composed\s+by|"
    r"music(?:\s+by)?|arranged\s+by|arranger|produced\s+by|producers?|"
    r"mixed\s+by|mastered\s+by|recorded\s+by)\s*[:：]",
    re.I,
)
# Any "Label：Value" line in the leading block (before the first real lyric)
# is a credit: "Drums：David Stewart", "Vocal Directing: X", "OP: Y".
_LEADING_CREDIT_RE = re.compile(
    r"^\s*[^:：,.!?。！？]{1,30}\s*[:：]\s*\S.{0,80}$|"
    # "Recording Engineer - Pdogg": dash form only with a credit keyword.
    r"^\s*[^-–—,.!?]{0,20}(?:engineer|produc|record|mix|master|vocal|drum|guitar|bass|"
    r"keyboard|synth|program|arrang|compos|lyric|written|percussion|string|piano|"
    r"director|a&r)[^-–—]{0,15}\s[-–—]\s\S.{0,80}$",
    re.I,
)
# NetEase embeds credits as JSON objects on their own lines.
_JSON_LINE_RE = re.compile(r'^\s*\{\s*"[a-z]+"\s*:.*\}\s*$')
_NOTICE_RE = re.compile(r"著作权|著作權|未经.*许可|版权所有|享有本翻译作品")
_PLACEHOLDERS = (
    "纯音乐，请欣赏",
    "纯音乐,请欣赏",
    "此歌曲为没有填词的纯音乐",
    "纯音乐，请您欣赏",
    "純音樂，請欣賞",
    "暂无歌词",
    "暫無歌詞",
)


def clean_lines(lines: list[LyricLine], meta: TrackMetadata | None = None) -> list[LyricLine]:
    """Drop credit lines, copyright notices and a leading "Title - Artist" line."""
    out = [
        l for l in lines
        if l.text
        and not _CREDIT_RE.match(l.text)
        and not _NOTICE_RE.search(l.text)
        and not _JSON_LINE_RE.match(l.text)
    ]
    if out and meta and meta.title and _is_header(out[0].text, meta):
        out = out[1:]
    lead = 0
    while lead < len(out) and _LEADING_CREDIT_RE.match(out[lead].text):
        lead += 1
    # Only a block of credits followed by real lyrics; never strip everything.
    if lead < len(out):
        out = out[lead:]
    return out


def _is_header(text: str, meta: TrackMetadata) -> bool:
    """True for a "Title - Artist" (or "Artist - Title") line."""
    parts = re.split(r"\s+[-–—]\s+", text, maxsplit=1)
    if len(parts) != 2:
        return False
    for title, artist in (parts, parts[::-1]):
        if similarity(title, meta.title) >= 0.9 and (
            not meta.artist or artist_similarity(meta.artist, [artist]) >= ARTIST_GATE
        ):
            return True
    return False


def _lyric_texts(lines: list[LyricLine]) -> list[str]:
    return [
        l.text for l in lines
        if l.text.strip() and not (l.time is None and l.text.startswith("["))
    ]


def is_instrumental_placeholder(lines: list[LyricLine]) -> bool:
    texts = _lyric_texts(lines)
    if not texts or len(texts) > 3:
        return False
    joined = " ".join(texts)
    return any(p in joined for p in _PLACEHOLDERS)


def check_lyrics(lines: list[LyricLine], duration: float | None) -> str | None:
    """Return why these lyrics cannot belong to the track, or None if they fit."""
    texts = _lyric_texts(lines)
    if len(texts) < 2:
        return "too few lyric lines"
    if duration:
        times = [l.time for l in lines if l.time is not None]
        if times and max(times) > duration + LYRICS_OVERRUN:
            return (
                f"lyrics run to {format_time(max(times))} "
                f"but the track is {format_time(duration)}"
            )
    return None


# -- candidate loop shared by search-based providers ---------------------------

# fetch(candidate) -> (synced_text, plain_text, instrumental_flag)
Fetcher = Callable[[Candidate], "tuple[str | None, str | None, bool]"]


def select_lyrics(
    matches: list[Match],
    fetch: Fetcher,
    meta: TrackMetadata,
    closest: Match | None = None,
    max_candidates: int = MAX_CANDIDATES,
) -> dict:
    """Try the top matches and return a cacheable result dict.

    Prefers the best candidate with synced lyrics, then the best with plain
    lyrics.  Lyrics failing :func:`check_lyrics` are skipped.  The returned
    dict has one of the keys ``lrc`` / ``plain`` / ``instrumental`` /
    ``rejected`` plus ``confidence``, ``matched`` and ``id`` where relevant.
    """
    plain_hit: dict | None = None
    instrumental_hit: dict | None = None
    reject_reason: str | None = None

    for m in matches[:max_candidates]:
        c = m.candidate
        info = {"confidence": m.confidence, "matched": c.describe(), "id": c.id}
        synced_text, plain_text, instrumental = fetch(c)

        for text, key in ((synced_text, "lrc"), (plain_text, "plain")):
            if not text or not text.strip():
                continue
            lines = clean_lines(parse_lrc(text), meta)
            if is_instrumental_placeholder(lines):
                instrumental = True
                break
            reason = check_lyrics(lines, meta.duration)
            if reason:
                reject_reason = reject_reason or f"{c.describe()}: {reason}"
                continue
            if key == "lrc":
                return {"lrc": text, **info}
            if plain_hit is None:
                plain_hit = {"plain": text, **info}

        if instrumental and instrumental_hit is None:
            instrumental_hit = {"instrumental": True, **info}

    if plain_hit:
        return plain_hit
    if instrumental_hit:
        return instrumental_hit
    if reject_reason:
        return {"rejected": reject_reason}
    if matches:
        return {"rejected": f"{matches[0].candidate.describe()}: no lyrics available"}
    if closest:
        return {"rejected": f"closest result {closest.candidate.describe()}: {closest.rejected}"}
    return {}


def to_result(data: dict, meta: TrackMetadata) -> ProviderResult:
    """Turn a cached result dict back into a ProviderResult."""
    info = {"confidence": data.get("confidence"), "matched": data.get("matched")}
    if data.get("instrumental"):
        return ProviderResult(instrumental=True, **info)
    if data.get("lrc"):
        return ProviderResult(synced=clean_lines(parse_lrc(data["lrc"]), meta), **info)
    if data.get("plain"):
        return ProviderResult(plain=clean_lines(parse_lrc(data["plain"]), meta), **info)
    return ProviderResult(rejected=data.get("rejected"))
