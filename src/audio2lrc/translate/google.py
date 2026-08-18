"""Google Translate backend (unofficial free endpoint, no key needed)."""

from __future__ import annotations

import requests

from audio2lrc.models import TranslationError
from audio2lrc.translate.base import Translator

_URL = "https://translate.googleapis.com/translate_a/single"
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


class GoogleTranslator(Translator):
    name = "google"

    def translate(
        self, lines: list[str], source_lang: str | None, target_lang: str
    ) -> tuple[list[str], str | None]:
        if not lines:
            return [], None
        out: list[str] = []
        detected: str | None = None
        try:
            for chunk in _chunk(lines):
                resp = requests.post(
                    _URL,
                    params={
                        "client": "gtx",
                        "sl": source_lang or "auto",
                        "tl": target_lang,
                        "dt": "t",
                    },
                    data={"q": "\n".join(chunk)},
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()
                parts: list[str] = []
                for item in data[0]:
                    if isinstance(item, list):
                        parts.append(item[0] or "")
                    elif isinstance(item, str):
                        parts.append(item)
                out.extend("".join(parts).split("\n"))
                if not detected:
                    d = data[2] if len(data) > 2 else None
                    if isinstance(d, list) and d:
                        d = d[0]
                        if isinstance(d, list) and d:
                            d = d[0]
                    if isinstance(d, str) and d:
                        detected = d
        except Exception as exc:  # noqa: BLE001 - boundary: convert to TranslationError
            raise TranslationError(f"google translate request failed: {exc}") from exc
        return out, detected