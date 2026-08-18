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


@dataclass
class EmbeddedLyrics:
    """Lyrics extracted from the audio file's own tags."""

    text: str | None = None
    synced: bool = False
    note: str | None = None


@dataclass
class ResolvedLyrics:
    """Final lyrics resolution result."""

    source: str  # "embedded" | "lrclib.net"
    lines: list[LyricLine] = field(default_factory=list)
    unsynced: bool = False


class LyricsNotFoundError(Exception):
    """Raised when no usable lyrics could be found anywhere."""


class TranslationError(Exception):
    """Raised when a translation backend fails irrecoverably."""