"""OpenAI-compatible chat backend for translation."""

from __future__ import annotations

import json
import os

import requests

from audio2lrc.models import TranslationError
from audio2lrc.translate.base import Translator

_PROMPT = (
    "You are a professional lyrics translator. Translate every line of the "
    "provided JSON array into {target}. "
    "Preserve the number of lines exactly (one output string per input line), "
    "keep empty strings empty, and do not add commentary. "
    'Respond with a JSON object: {{"lines": [...], "detected_source": "<ISO 639 code or null>"}}.'
)


class OpenAITranslator(Translator):
    name = "openai"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY") or ""
        self.base_url = (base_url or os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
        self.model = model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        if not self.api_key:
            raise TranslationError(
                "OPENAI_API_KEY is not set; configure it in .env or pick a different TRANSLATOR_BACKEND"
            )

    def translate(
        self, lines: list[str], source_lang: str | None, target_lang: str
    ) -> tuple[list[str], str | None]:
        if not lines:
            return [], None
        prompt = _PROMPT.format(target=target_lang)
        if source_lang:
            prompt += f" The source language is {source_lang}."
        prompt += f'\nInput JSON array:\n{json.dumps(lines, ensure_ascii=False)}'

        try:
            resp = requests.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "temperature": 0,
                    "response_format": {"type": "json_object"},
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=90,
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            data = json.loads(content)
            translated = data["lines"]
            if not isinstance(translated, list):
                raise TranslationError("openai returned a non-list 'lines' field")
            if len(translated) != len(lines):
                raise TranslationError(
                    f"openai returned {len(translated)} lines for {len(lines)} input lines"
                )
            detected = data.get("detected_source") or None
            return [str(x) for x in translated], detected
        except TranslationError:
            raise
        except TranslationError:
            raise
        except Exception as exc:  # noqa: BLE001 - boundary: convert to TranslationError
            raise TranslationError(f"openai translation failed: {exc}") from exc