"""Metadata + embedded lyrics extraction via mutagen."""

from __future__ import annotations

import os
import re
from typing import Any

import mutagen
from mutagen.flac import FLAC
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4, MP4Tags
from mutagen.oggvorbis import VCommentDict

from audio2lrc.lrc.parser import looks_synced
from audio2lrc.models import EmbeddedLyrics, TrackMetadata

_ID3_PLAIN_KEYS = ("USLT", "SYLT")
_LRC_RE = re.compile(r"\[\d{1,3}:\d{1,2}(?:[.:]\d{1,3})?\]")


def _first(values: Any) -> str | None:
    if not values:
        return None
    v = values[0] if isinstance(values, (list, tuple)) else values
    if isinstance(v, bytes):
        v = v.decode("utf-8", errors="replace")
    v = str(v).strip()
    return v or None


def _vorbis_comments(tags: Any) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for key, values in tags.items():
        out[str(key).lower()] = [str(v) for v in values]
    return out


def _extract_embedded(text: str | None, note: str | None = None) -> EmbeddedLyrics | None:
    if not text or not text.strip():
        return None
    return EmbeddedLyrics(text=text.strip(), synced=looks_synced(text), note=note)


def _sylt_text(frame: Any) -> str:
    """SYLT frames store (text, time_ms) tuples; rebuild LRC-style lines so
    the timestamps survive parsing."""
    from audio2lrc.lrc.writer import format_timestamp

    lines: list[str] = []
    for item in frame.text:
        if isinstance(item, (tuple, list)) and len(item) >= 2:
            text, time_ms = item[0], item[1]
            lines.append(f"{format_timestamp(int(time_ms) / 1000)}{text}")
        else:
            lines.append(str(item))
    return "\n".join(lines)


def _read_mp3(path: str, f: MP3) -> tuple[TrackMetadata, EmbeddedLyrics | None]:
    tags = f.tags
    meta = TrackMetadata(duration=f.info.length)
    embedded: EmbeddedLyrics | None = None
    if tags is None:
        return meta, None

    meta.title = _first(tags.get("TIT2"))
    meta.artist = _first(tags.get("TPE1"))
    meta.album = _first(tags.get("TALB"))

    for frame in tags.getall("SYLT"):
        emb = _extract_embedded(_sylt_text(frame), "SYLT frame")
        if emb:
            embedded = emb
            break
    if embedded is None:
        for frame in tags.getall("USLT"):
            text = frame.text
            if isinstance(text, (list, tuple)):
                text = "\n".join(str(t) for t in text)
            emb = _extract_embedded(text, "USLT frame")
            if emb:
                embedded = emb
                break
    return meta, embedded


def _read_vorbis(path: str, f: Any) -> tuple[TrackMetadata, EmbeddedLyrics | None]:
    meta = TrackMetadata(duration=f.info.length)
    tags = _vorbis_comments(f.tags) if f.tags else {}
    meta.title = _first(tags.get("title"))
    meta.artist = _first(tags.get("artist"))
    meta.album = _first(tags.get("album"))

    embedded: EmbeddedLyrics | None = None
    for key in ("lyrics", "unsyncedlyrics"):
        if key in tags:
            text = "\n".join(tags[key])
            emb = _extract_embedded(text, key)
            if emb:
                embedded = emb
                break
    return meta, embedded


def _read_mp4(path: str, f: MP4) -> tuple[TrackMetadata, EmbeddedLyrics | None]:
    meta = TrackMetadata(duration=f.info.length)
    tags = f.tags
    embedded: EmbeddedLyrics | None = None
    if tags:
        meta.title = _first(tags.get("\xa9nam"))
        meta.artist = _first(tags.get("\xa9ART"))
        meta.album = _first(tags.get("\xa9alb"))
        text = _first(tags.get("\xa9lyr"))
        if text:
            embedded = _extract_embedded(text, "\xa9lyr atom")
    return meta, embedded


def read_track(path: str) -> tuple[TrackMetadata, EmbeddedLyrics | None]:
    """Read tags + embedded lyrics from an audio file.

    Returns (metadata, embedded_lyrics). metadata.duration is set when the
    container exposes it. Embedded lyrics are None when absent; when present,
    .synced tells whether they carry LRC-style timestamps.
    """
    f = mutagen.File(path)
    if f is None:
        raise ValueError(f"unsupported or unreadable audio file: {path}")

    if isinstance(f, MP3):
        meta, embedded = _read_mp3(path, f)
    elif isinstance(f.tags, MP4Tags):
        meta, embedded = _read_mp4(path, f)
    elif isinstance(f.tags, VCommentDict):
        meta, embedded = _read_vorbis(path, f)
    else:
        meta = TrackMetadata(duration=getattr(f.info, "length", None))
        embedded = None
        if f.tags is not None:
            meta.title = _first(f.tags.get("title") or f.tags.get("TIT2"))
            meta.artist = _first(f.tags.get("artist") or f.tags.get("TPE1"))
            meta.album = _first(f.tags.get("album") or f.tags.get("TALB"))

    if not (meta.title and meta.artist):
        _filename_fallback(path, meta)
    return meta, embedded


def _filename_fallback(path: str, meta: TrackMetadata) -> None:
    """Guess artist/title from 'Artist - Title.ext' as a last resort."""
    stem = os.path.splitext(os.path.basename(path))[0]
    if " - " not in stem:
        return
    artist, _, title = stem.partition(" - ")
    artist, title = artist.strip(), title.strip()
    if artist and title:
        if not meta.artist:
            meta.artist = artist
        if not meta.title:
            meta.title = title
        meta.filename_guess = True