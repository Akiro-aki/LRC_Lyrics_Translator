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
    original text. Raises TranslationError when nothing at all could be
    translated (so callers never mistake originals for translations).
    """
    skip_indices = skip_indices or set()
    result: list[str] = [lines[i] for i in range(len(lines))]
    ids = [i for i in range(len(lines)) if i not in skip_indices]
    if not ids:
        return result, None
    to_translate = [lines[i] for i in ids]

    last_error: TranslationError | None = None
    try:
        translated, detected = translator.translate(to_translate, source_lang, target_lang)
        if len(translated) == len(ids):
            for i, text in zip(ids, translated):
                result[i] = text
            if detected or any(result[i] != lines[i] for i in ids):
                return result, detected
    except TranslationError as exc:
        last_error = exc

    detected = None
    changed = False
    for i, text in zip(ids, to_translate):
        try:
            single, det = translator.translate([text], source_lang, target_lang)
            detected = detected or det
            if len(single) == 1 and single[0].strip():
                result[i] = single[0]
                changed = changed or single[0] != text
        except TranslationError as exc:
            last_error = last_error or exc
    if not changed and not detected:
        raise last_error or TranslationError(
            "translation failed: backend returned no usable translations"
        )
    return result, detected