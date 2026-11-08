"""Core data models."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class LyricLine:
    """A single lyric line.

    time is seconds from the start of the track, or None when the line has
    no timestamp (plain/unsynced lyrics, or LRC section markers).
    """

    time: float | None
    text: str

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        ts = f"{self.time:8.2f}" if self.time is not None else "     --  "
        return f"LyricLine({ts}, {self.text!r})"


@dataclass
class TrackMetadata:
    title: str | None = None
    artist: str | None = None
    album: str | None = None
    duration: float | None = None
    filename_guess: bool = False

    def lrclib_query(self) -> dict:
        """Params for an LRCLIB lookup, dropping empty fields."""
        params: dict[str, str | int] = {}
        if self.title:
            params["track_name"] = self.title
        if self.artist:
            params["artist_name"] = self.artist
        if self.album:
            params["album_name"] = self.album
        if self.duration and int(self.duration) > 0:
            params["duration"] = int(self.duration)
        return params

    def netease_query(self) -> str:
        """Search keywords for a NetEase / QQ Music lookup."""
        return self.search_query()

    def search_query(self) -> str:
        """Free-text search keywords: title then artist."""
        parts: list[str] = []
        if self.title:
            parts.append(self.title)
        if self.artist:
            parts.append(self.artist)
        return " ".join(parts)


@dataclass
class EmbeddedLyrics:
    """Lyrics extracted from the audio file's own tags."""

    text: str | None = None
    synced: bool = False
    note: str | None = None


@dataclass
class ResolvedLyrics:
    """Final lyrics resolution result."""

    source: str  # "embedded" | "lrclib.net" | "music.163.com" | "y.qq.com"
    lines: list[LyricLine] = field(default_factory=list)
    unsynced: bool = False
    confidence: float | None = None  # match confidence 0..1 (external sources)
    matched: str | None = None  # human-readable description of the matched record
    notes: list[str] = field(default_factory=list)  # why external sources were not used


@dataclass
class ProviderResult:
    """What a lyrics provider found for one track.

    confidence is the match confidence (0..1) of the record the lyrics came
    from; rejected explains why the closest candidate was turned down when
    nothing usable matched.
    """

    synced: list[LyricLine] | None = None
    plain: list[LyricLine] | None = None
    instrumental: bool = False
    confidence: float | None = None
    matched: str | None = None
    rejected: str | None = None


class LyricsNotFoundError(Exception):
    """Raised when no usable lyrics could be found anywhere."""


class TranslationError(Exception):
    """Raised when a translation backend fails irrecoverably."""