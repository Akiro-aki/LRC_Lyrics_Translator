"""Serialize LyricLine lists back to .lrc text."""

from __future__ import annotations

from audio2lrc.models import LyricLine, TrackMetadata


def format_timestamp(seconds: float) -> str:
    if seconds < 0:
        seconds = 0.0
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    centis = int(round((seconds - int(seconds)) * 100))
    if centis == 100:
        centis = 0
        secs += 1
        if secs == 60:
            secs = 0
            minutes += 1
    return f"[{minutes:02d}:{secs:02d}.{centis:02d}]"


def render_lrc(
    meta: TrackMetadata,
    lines: list[LyricLine],
    *,
    source: str | None = None,
    unsynced: bool = False,
    translated_from: str | None = None,
    target_lang: str | None = None,
    romanized: bool = False,
    note: str | None = None,
) -> str:
    """Render a complete .lrc document.

    For unsynced tracks every line is written with a [00:00.00] timestamp
    (real timing is not expected) and #X-UNSYNCED: true is emitted.
    """
    out: list[str] = []

    if meta.title:
        out.append(f"[ti:{meta.title}]")
    if meta.artist:
        out.append(f"[ar:{meta.artist}]")
    if meta.album:
        out.append(f"[al:{meta.album}]")

    if source:
        out.append(f"#X-SOURCE: {source}")
    if unsynced:
        out.append("#X-UNSYNCED: true")
    if translated_from:
        out.append(f"#X-TRANSLATED-FROM: {translated_from}")
    if target_lang:
        out.append(f"#X-TARGET-LANG: {target_lang}")
    if romanized:
        out.append("#X-ROMANIZED: true")
    if note:
        out.append(f"#X-NOTE: {note}")

    for line in lines:
        if line.time is not None:
            out.append(f"{format_timestamp(line.time)}{line.text}")
        elif unsynced:
            out.append(f"[00:00.00]{line.text}")
        else:
            out.append(line.text)

    return "\n".join(out) + "\n"