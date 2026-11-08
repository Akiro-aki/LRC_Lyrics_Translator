"""Lyrics providers."""

from __future__ import annotations

from typing import Protocol

from audio2lrc.models import ProviderResult, TrackMetadata


class LyricsProvider(Protocol):
    """Pluggable lyrics source."""

    name: str

    def fetch_lyrics(
        self,
        meta: TrackMetadata,
        cache_dir: str | None = None,
        min_confidence: float | None = None,
    ) -> ProviderResult:
        """Fetch lyrics for a track.

        Every candidate is checked by ``providers.matching`` before its
        lyrics are accepted; the result carries the match confidence and a
        description of the matched record, or why the closest candidate was
        rejected.  Raises LyricsNotFoundError on request failures or when
        the track has no title to search for.
        """
