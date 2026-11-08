"""On-disk result cache shared by the lyrics providers."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from typing import Callable

from audio2lrc.models import TrackMetadata

# Bump when matching rules change so results chosen under older (looser)
# rules are looked up again instead of being reused.
MATCH_VERSION = 2


def default_cache_dir() -> str:
    base = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    return os.path.join(base, "audio2lrc")


def cache_path(cache_dir: str, prefix: str, meta: TrackMetadata) -> str:
    key = hashlib.sha1(
        f"v{MATCH_VERSION}|{meta.title or ''}|{meta.artist or ''}|"
        f"{meta.album or ''}|{meta.duration or ''}".encode("utf-8")
    ).hexdigest()
    return os.path.join(cache_dir, f"{prefix}_{key}.json")


def read_cache(path: str) -> dict | None:
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def write_cache(path: str, data: dict, label: str) -> None:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False)
        os.replace(tmp, path)
    except OSError as exc:
        sys.stderr.write(f"warning: could not write {label} cache: {exc}\n")


def _is_stale(data: dict, min_confidence: float) -> bool:
    """A cached result no longer fits the current confidence threshold."""
    found = data.get("lrc") or data.get("plain") or data.get("instrumental")
    if found:
        return (data.get("confidence") or 0.0) < min_confidence
    # No match was found under a stricter threshold: a looser one may find one.
    return data.get("min_confidence", 0.0) > min_confidence


def cached_lookup(
    path: str,
    min_confidence: float,
    compute: Callable[[], dict],
    label: str,
) -> dict:
    """Return the cached result at ``path``, or compute and cache a fresh one."""
    data = read_cache(path)
    if data is not None and not _is_stale(data, min_confidence):
        return data
    data = compute()
    data["min_confidence"] = min_confidence
    write_cache(path, data, label)
    return data
