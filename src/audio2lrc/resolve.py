"""Lyrics resolution: embedded vs external providers, per spec section 3."""

from __future__ import annotations

from audio2lrc.lrc.parser import parse_lrc
from audio2lrc.models import (
    EmbeddedLyrics,
    LyricsNotFoundError,
    ProviderResult,
    ResolvedLyrics,
    TrackMetadata,
)
from audio2lrc.links import parse_lrclib_url
from audio2lrc.providers import LyricsProvider
from audio2lrc.providers.lrclib import lrclib, _parse_lyrics
from audio2lrc.providers.matching import STRONG_CONFIDENCE, default_min_confidence
from audio2lrc.providers.netease import netease
from audio2lrc.providers.qqmusic import qqmusic

_PROVIDERS: dict[str, LyricsProvider] = {
    "lrclib": lrclib,
    "netease": netease,
    "qqmusic": qqmusic,
}
AUTO_ORDER = ("lrclib", "netease", "qqmusic")
PROVIDER_CHOICES = (*_PROVIDERS, "auto")


def resolve_from_url(url: str) -> tuple[ResolvedLyrics, TrackMetadata]:
    """Resolve lyrics from an LRCLIB link, e.g. ``https://lrclib.net/song/123``.

    This bypasses audio-tag matching entirely and fetches the record directly
    by its LRCLIB track ID. Returns (ResolvedLyrics, TrackMetadata) where the
    metadata comes from the fetched record (track/artist/album).
    """
    track_id = parse_lrclib_url(url)
    if track_id is None:
        raise LyricsNotFoundError(
            f"not a valid LRCLIB link: {url!r} "
            "(expected something like https://lrclib.net/song/<id> or .../tracks/<id>)"
        )
    data = lrclib.fetch_by_id(track_id)
    if data.get("instrumental"):
        raise LyricsNotFoundError(
            "LRCLIB reports this track as instrumental (no lyrics exist for it)"
        )
    synced = _parse_lyrics(data.get("syncedLyrics"))
    plain = _parse_lyrics(data.get("plainLyrics"))
    lines = synced or plain or []
    if not lines:
        raise LyricsNotFoundError(f"LRCLIB: no lyrics found for track id {track_id}")
    meta = TrackMetadata(
        title=data.get("trackName") or data.get("name"),
        artist=data.get("artistName"),
        album=data.get("albumName"),
        duration=data.get("duration"),
    )
    resolved = ResolvedLyrics(source="lrclib.net:link", lines=lines, unsynced=not synced)
    return resolved, meta


def resolve(
    meta: TrackMetadata,
    embedded: EmbeddedLyrics | None,
    *,
    prefer_embedded: bool = False,
    prefer_external: bool = False,
    provider: str = "lrclib",
    cache_dir: str | None = None,
    min_confidence: float | None = None,
) -> ResolvedLyrics:
    """Decide where lyrics come from.

    Priority (default): embedded-synced > provider-synced > provider-plain >
    embedded-unsynced > error.  --prefer-embedded moves embedded ahead of
    any external result; --prefer-external does the reverse.

    provider: "lrclib", "netease", "qqmusic", or "auto".  In auto mode every
    provider is asked in turn and the best verified match wins (synced over
    plain, then highest confidence); a strong synced match ends the search
    early.  Results below ``min_confidence`` are never used.
    """
    embedded_lines = parse_lrc(embedded.text) if embedded and embedded.text else []
    embedded_synced = bool(embedded and embedded.synced and embedded_lines)

    def use_embedded() -> ResolvedLyrics:
        return ResolvedLyrics(
            source="embedded", lines=embedded_lines, unsynced=not embedded_synced
        )

    if prefer_embedded and embedded_lines:
        return use_embedded()
    if embedded_synced and not prefer_external:
        return use_embedded()

    providers_to_try: list[LyricsProvider]
    if provider == "auto":
        providers_to_try = [_PROVIDERS[name] for name in AUTO_ORDER]
    elif provider in _PROVIDERS:
        providers_to_try = [_PROVIDERS[provider]]
    else:
        raise LyricsNotFoundError(f"unknown lyrics provider: {provider!r}")

    min_conf = default_min_confidence() if min_confidence is None else min_confidence

    found: list[tuple[LyricsProvider, ProviderResult]] = []
    instrumental: tuple[LyricsProvider, ProviderResult] | None = None
    rejections: list[str] = []
    errors: list[str] = []

    for p in providers_to_try:
        try:
            r = p.fetch_lyrics(meta, cache_dir, min_conf)
        except LyricsNotFoundError as exc:
            errors.append(str(exc))
            continue
        if r.rejected:
            rejections.append(f"{p.name}: {r.rejected}")
        confidence = r.confidence or 0.0
        if r.instrumental:
            if instrumental is None or confidence > (instrumental[1].confidence or 0.0):
                instrumental = (p, r)
            if confidence >= STRONG_CONFIDENCE:
                break
            continue
        if r.synced or r.plain:
            found.append((p, r))
            if r.synced and confidence >= STRONG_CONFIDENCE:
                break

    if found:
        p, r = max(found, key=lambda pr: (bool(pr[1].synced), pr[1].confidence or 0.0))
        return ResolvedLyrics(
            source=p.name,
            lines=r.synced or r.plain or [],
            unsynced=not r.synced,
            confidence=r.confidence,
            matched=r.matched,
        )

    if instrumental:
        p, r = instrumental
        raise LyricsNotFoundError(
            f"{p.name} reports this track as instrumental (no lyrics exist for it)"
            + (f"; matched {r.matched}" if r.matched else "")
        )

    if embedded_lines:
        fallback = use_embedded()
        fallback.notes = [f"rejected {r}" for r in rejections] + errors
        return fallback

    if errors and not rejections:
        raise LyricsNotFoundError(errors[-1])

    provider_names = " / ".join(p.name for p in providers_to_try)
    message = (
        "no lyrics found: no embedded lyrics and no verified match from "
        f"{provider_names} for "
        f"{meta.artist or 'unknown artist'} - {meta.title or 'unknown title'}"
    )
    if rejections:
        message += "\n  rejected: " + "\n  rejected: ".join(rejections)
    if errors:
        message += "\n  errors: " + "; ".join(errors)
    raise LyricsNotFoundError(message)
