"""LibreTranslate backend (self-hosted or libretranslate.com)."""

from __future__ import annotations

import os

import requests

from audio2lrc.models import TranslationError
from audio2lrc.translate.base import Translator

_MAX_CHARS = 4500


def _chunk(lines: list[str]) -> list[list[str]]:
    chunks: list[list[str]] = [[]]
    size = 0
    for line in lines:
        if size + len(line) + 1 > _MAX_CHARS and chunks[-1]:
            chunks.append([])
            size = 0
        chunks[-1].append(line)
        size += len(line) + 1
    return chunks


class LibreTranslateTranslator(Translator):
    name = "libretranslate"

    def __init__(self, url: str | None = None, api_key: str | None = None):
        self.url = (url or os.environ.get("LIBRETRANSLATE_URL", "https://libretranslate.com")).rstrip("/")
        self.api_key = api_key if api_key is not None else os.environ.get("LIBRETRANSLATE_API_KEY") or None

    def translate(
        self, lines: list[str], source_lang: str | None, target_lang: str
    ) -> tuple[list[str], str | None]:
        if not lines:
            return [], None
        out: list[str] = []
        detected: str | None = None
        try:
            for chunk in _chunk(lines):
                payload: dict = {
                    "q": "\n".join(chunk),
                    "source": source_lang or "auto",
                    "target": target_lang,
                    "format": "text",
                }
                if self.api_key:
                    payload["api_key"] = self.api_key
                resp = requests.post(f"{self.url}/translate", json=payload, timeout=60)
                resp.raise_for_status()
                data = resp.json()
                out.extend(data["translatedText"].split("\n"))
                if not detected and isinstance(data.get("detectedLanguage"), dict):
                    lang = data["detectedLanguage"].get("language")
                    if lang:
                        detected = lang
        except Exception as exc:  # noqa: BLE001 - boundary: convert to TranslationError
            raise TranslationError(f"libretranslate request failed: {exc}") from exc
        return out, detected