"""Parse LRC text into LyricLine lists."""

from __future__ import annotations

import re

from audio2lrc.models import LyricLine

# [mm:ss.xx], [mm:ss.xxx], [mm:ss.x], [m:ss.xx]
_TIMESTAMP_RE = re.compile(r"\[(\d{1,3}):(\d{1,2})(?:[.:](\d{1,3}))?\]")

# Metadata tags such as [ti:...], [ar:...], [offset:+500]
_META_RE = re.compile(r"^\[(ti|ar|al|by|re|ve|au|length|offset|id):.*\]$")

# Section markers such as [Chorus], [Instrumental], [Verse 1]
_MARKER_RE = re.compile(r"^\[([^:\]]+)\]$")


def _to_seconds(m: str, s: str, frac: str | None) -> float:
    secs = int(m) * 60 + int(s)
    if not frac:
        return float(secs)
    digits = frac
    if len(digits) == 1:
        return secs + int(digits) / 10  # tenths
    if len(digits) == 2:
        return secs + int(digits) / 100  # centiseconds
    return secs + int(digits) / 1000  # milliseconds


def parse_lrc(text: str) -> list[LyricLine]:
    """Parse LRC text into LyricLine objects.

    Metadata tags ([ti:], [ar:], ...) are dropped. Section markers
    ([Chorus], ...) are kept with time=None so they can be passed through
    untouched. Lines with several timestamps produce one LyricLine each.
    """
    lines: list[LyricLine] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or _META_RE.match(line):
            continue

        if _MARKER_RE.match(line) and not _TIMESTAMP_RE.search(line):
            lines.append(LyricLine(None, line))
            continue

        times = [_to_seconds(*t) for t in _TIMESTAMP_RE.findall(line)]
        rest = _TIMESTAMP_RE.sub("", line).strip()
        if times and rest:
            for t in times:
                lines.append(LyricLine(t, rest))
        elif not times and rest:
            # Plain unsynced text line (e.g. embedded Vorbis lyrics).
            lines.append(LyricLine(None, rest))

    return lines


def looks_synced(text: str) -> bool:
    """True if the text contains LRC-style timestamps."""
    return bool(_TIMESTAMP_RE.search(text))