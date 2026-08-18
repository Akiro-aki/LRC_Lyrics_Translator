"""Translator interface + batched translation with per-line fallback."""

from __future__ import annotations

from abc import ABC, abstractmethod

from audio2lrc.models import TranslationError


class Translator(ABC):
    """Pluggable translation backend."""

    name: str = "base"

    @abstractmethod
    def translate(
        self, lines: list[str], source_lang: str | None, target_lang: str
    ) -> tuple[list[str], str | None]:
        """Translate a batch of lines.

        Returns (translated_lines, detected_source_lang). source_lang may be
        None (auto-detect); detected_source_lang is whatever the backend
        reports, or None if unknown. Must raise TranslationError on failure.
        """


def translate_batched(
    translator: Translator,
    lines: list[str],
    source_lang: str | None,
    target_lang: str,
    skip_indices: set[int] | None = None,
) -> tuple[list[str], str | None]:
    """Translate lines, skipping markers/empty lines.

    Batch translates first; if the returned count mismatches the input count,
    retries per-line. Line positions never shift: skipped lines keep their
    original text.
    """
    skip_indices = skip_indices or set()
    result: list[str] = [lines[i] for i in range(len(lines))]
    ids = [i for i in range(len(lines)) if i not in skip_indices]
    if not ids:
        return result, None
    to_translate = [lines[i] for i in ids]

    try:
        translated, detected = translator.translate(to_translate, source_lang, target_lang)
        if len(translated) == len(ids):
            for i, text in zip(ids, translated):
                result[i] = text
            return result, detected
    except TranslationError:
        pass

    detected: str | None = None
    for i, text in zip(ids, to_translate):
        try:
            single, det = translator.translate([text], source_lang, target_lang)
            detected = detected or det
            if len(single) == 1 and single[0].strip():
                result[i] = single[0]
        except TranslationError:
            pass  # keep the original line; never shift timestamps
    return result, detected