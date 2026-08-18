"""Lyrics resolution: embedded vs LRCLIB, per spec section 3."""

from __future__ import annotations

from audio2lrc.lrc.parser import parse_lrc
from audio2lrc.models import EmbeddedLyrics, LyricsNotFoundError, ResolvedLyrics, TrackMetadata
from audio2lrc.providers import lrclib


def resolve(
    meta: TrackMetadata,
    embedded: EmbeddedLyrics | None,
    *,
    prefer_embedded: bool = False,
    prefer_lrclib: bool = False,
    cache_dir: str | None = None,
) -> ResolvedLyrics:
    """Decide where lyrics come from.

    Priority (default): embedded-synced > lrclib-synced > lrclib-plain >
    embedded-unsynced > error. --prefer-embedded moves embedded ahead of
    any LRCLIB result; --prefer-lrclib does the reverse.
    """
    embedded_lines = parse_lrc(embedded.text) if embedded and embedded.text else []
    embedded_synced = bool(embedded and embedded.synced and embedded_lines)

    def use_embedded() -> ResolvedLyrics:
        return ResolvedLyrics(
            source="embedded", lines=embedded_lines, unsynced=not embedded_synced
        )

    if prefer_embedded and embedded_lines:
        return use_embedded()
    if embedded_synced and not prefer_lrclib:
        return use_embedded()

    lrclib_error: str | None = None
    lrclib_synced: list | None = None
    lrclib_plain: list | None = None
    instrumental = False
    try:
        lrclib_synced, lrclib_plain, instrumental = lrclib.fetch_lyrics(meta, cache_dir)
    except LyricsNotFoundError as exc:
        lrclib_error = str(exc)

    if instrumental:
        if prefer_embedded and embedded_lines:
            return use_embedded()
        raise LyricsNotFoundError(
            "LRCLIB reports this track as instrumental (no lyrics exist for it)"
        )

    if lrclib_synced:
        if prefer_embedded and embedded_lines:
            return use_embedded()
        return ResolvedLyrics(source="lrclib.net", lines=lrclib_synced, unsynced=False)

    if lrclib_plain:
        if prefer_embedded and embedded_lines:
            return use_embedded()
        return ResolvedLyrics(source="lrclib.net", lines=lrclib_plain, unsynced=True)

    if embedded_lines:
        return use_embedded()

    if lrclib_error:
        raise LyricsNotFoundError(lrclib_error)

    raise LyricsNotFoundError(
        "no lyrics found: no embedded lyrics and LRCLIB has no match for "
        f"{meta.artist or 'unknown artist'} - {meta.title or 'unknown title'}"
    )