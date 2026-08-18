"""Romanization pass (Japanese -> romaji, Chinese -> pinyin).

Dependencies are imported lazily so the app works without them unless
--romanize is actually used on a CJK track.
"""

from __future__ import annotations

import re

from audio2lrc.models import TranslationError

_CJK_RE = re.compile(r"[\u3000-\u30ff\u4e00-\u9fff\u3400-\u4dbf]")
_HIRA_KATA_RE = re.compile(r"[\u3040-\u30ff]")  # hiragana + katakana


def _load_ja() -> object:
    try:
        import pykakasi

        return pykakasi.kakasi()
    except ImportError as exc:
        raise TranslationError(
            "pykakasi is required for Japanese romanization; run: uv add pykakasi"
        ) from exc


def _load_zh() -> object:
    try:
        from pypinyin import lazy_pinyin

        return lazy_pinyin
    except ImportError as exc:
        raise TranslationError(
            "pypinyin is required for Chinese romanization; run: uv add pypinyin"
        ) from exc


def _romanize_ja(text: str, kakasi: object) -> str:
    parts: list[str] = []
    for item in kakasi.convert(text):
        parts.append(item["hepburn"] or item["kunrei"] or item["orig"])
    return "".join(parts)


def _romanize_zh(text: str, lazy_pinyin: object) -> str:
    return " ".join(lazy_pinyin(text, errors=lambda s: s))


def romanize_lines(lines: list[str]) -> list[str]:
    """Romanize CJK text; non-CJK lines pass through unchanged.

    Japanese tracks are romanized with pykakasi, Chinese with pypinyin.
    """
    ja = zh = None
    out: list[str] = []
    for line in lines:
        if not _CJK_RE.search(line):
            out.append(line)
            continue
        if _HIRA_KATA_RE.search(line):
            ja = ja if ja is not None else _load_ja()
            out.append(_romanize_ja(line, ja))
        else:
            zh = zh if zh is not None else _load_zh()
            out.append(_romanize_zh(line, zh))
    return out