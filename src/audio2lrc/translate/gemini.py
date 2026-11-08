"""Google Gemini backend with TPM- and RPM-aware pacing.

Rate limits are applied per project and vary by model and usage tier (free tier
is the most constrained). Two metrics need active handling:
- tokens-per-minute (TPM): requests are chunked to fit a per-request budget and
  paced against a rolling 60s token window;
- requests-per-minute (RPM): each request is also counted against a rolling
  window so we don't blast past the per-minute request ceiling (common on free
  tier where flash-lite is only ~15-30 RPM).
429 responses are retried with backoff (honoring Retry-After).
"""

from __future__ import annotations

import json
import os
import time
from collections import deque

import requests

from audio2lrc.models import TranslationError
from audio2lrc.translate.base import Translator

_PROMPT = (
    "You are a professional lyrics translator. Translate every line of the "
    "provided JSON array into {target}. "
    "Preserve the number of lines exactly (one output string per input line), "
    "keep empty strings empty, and do not add commentary. "
    'Respond with only a JSON object: {{"lines": [...], "detected_source": "<ISO 639 code or null>"}}.'
)

_WINDOW_SECONDS = 60.0
_CHARS_PER_TOKEN = 3
_LINE_OVERHEAD_TOKENS = 8
_REQUEST_OVERHEAD_TOKENS = 96
_MAX_ATTEMPTS = 6
_MAX_BACKOFF_SECONDS = 30.0


def _estimate_tokens(text: str) -> int:
    return max(1, (len(text) + _CHARS_PER_TOKEN - 1) // _CHARS_PER_TOKEN)


def _monotonic() -> float:
    return time.monotonic()


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


class _RateWindow:
    """Rolling count of tokens used over the trailing minute."""

    def __init__(self, limit: int):
        self.limit = max(1, limit)
        self._events: deque[tuple[float, int]] = deque()

    def _prune(self, now: float) -> None:
        while self._events and now - self._events[0][0] >= _WINDOW_SECONDS:
            self._events.popleft()

    def used(self, now: float | None = None) -> int:
        now = _monotonic() if now is None else now
        self._prune(now)
        return sum(tokens for _, tokens in self._events)

    def delay_for(self, tokens: int, now: float | None = None) -> float:
        """Seconds to wait before spending `tokens` stays within the limit."""
        now = _monotonic() if now is None else now
        self._prune(now)
        if tokens >= self.limit:
            # Waiting can never make an over-limit request fit; send it and
            # let the 429 retry path handle any rejection.
            return 0.0
        excess = self.used(now) + tokens - self.limit
        if excess <= 0:
            return 0.0
        seen = 0
        for ts, n in self._events:
            seen += n
            if seen >= excess:
                return max(0.05, _WINDOW_SECONDS - (now - ts) + 0.01)
        return _WINDOW_SECONDS

    def record(self, tokens: int, now: float | None = None) -> None:
        now = _monotonic() if now is None else now
        if tokens > 0:
            self._events.append((now, tokens))
        self._prune(now)


class GeminiTranslator(Translator):
    name = "gemini"

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        tpm: int | str | None = None,
        rpm: int | str | None = None,
        base_url: str | None = None,
    ):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY") or ""
        self.model = (
            model
            or os.environ.get("GEMINI_MODEL", "gemini-flash-lite-latest")
        )
        raw_tpm = tpm if tpm is not None else os.environ.get("GEMINI_TPM", "20000")
        try:
            self.tpm = int(raw_tpm)
        except (TypeError, ValueError):
            self.tpm = 20000
        raw_rpm = rpm if rpm is not None else os.environ.get("GEMINI_RPM", "28")
        try:
            self.rpm = max(1, int(raw_rpm))
        except (TypeError, ValueError):
            self.rpm = 28
        self.base_url = (
            base_url
            or os.environ.get(
                "GEMINI_BASE_URL",
                "https://generativelanguage.googleapis.com/v1beta",
            )
        ).rstrip("/")
        self.request_budget = max(256, self.tpm // 2)
        self._window = _RateWindow(self.tpm)
        self._rpm_window = _RateWindow(max(1, self.rpm))
        if not self.api_key:
            raise TranslationError(
                "GEMINI_API_KEY is not set; configure it in .env or pick a different TRANSLATOR_BACKEND"
            )

    def _line_cost(self, line: str) -> int:
        # input + mirrored-size output + JSON quoting overhead, per line
        return 2 * (_LINE_OVERHEAD_TOKENS + _estimate_tokens(line))

    def _chunk(self, lines: list[str]) -> list[list[str]]:
        chunks: list[list[str]] = [[]]
        size = _REQUEST_OVERHEAD_TOKENS
        for line in lines:
            cost = self._line_cost(line)
            if size + cost > self.request_budget and chunks[-1]:
                chunks.append([])
                size = _REQUEST_OVERHEAD_TOKENS
            chunks[-1].append(line)
            size += cost
        return chunks

    @staticmethod
    def _parse_json(content: str) -> dict:
        text = content.strip()
        if text.startswith("```"):
            text = text.strip("`").strip()
            if "\n" in text and not text.lstrip().startswith("{"):
                text = text.split("\n", 1)[1]
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("no JSON object found in response")
        data = json.loads(text[start : end + 1])
        if not isinstance(data, dict):
            raise ValueError("response JSON is not an object")
        return data

    def _throttle(self, estimated_tokens: int) -> None:
        while True:
            delays = [
                self._window.delay_for(estimated_tokens),
                self._rpm_window.delay_for(1),
            ]
            delay = max(delays)
            if delay <= 0:
                return
            _sleep(delay)

    def _extract_text(self, data: dict) -> str:
        candidates = data.get("candidates") or []
        if not candidates:
            raise ValueError("response has no candidates")
        parts = (candidates[0].get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts)
        if not text.strip():
            raise ValueError("response has no text content")
        return text

    def _model_unavailable_error(self) -> TranslationError:
        hint = ""
        if "live-translate" in self.model or "live_translate" in self.model:
            hint = (
                f' "{self.model}" is a speech-to-speech Live API model and accepts '
                "audio only — it cannot translate text via generateContent."
            )
        return TranslationError(
            f'gemini model "{self.model}" is not available for generateContent '
            "(404)." + hint + " Set GEMINI_MODEL to a text model "
            "(e.g. gemini-flash-lite-latest) or pick a different TRANSLATOR_BACKEND."
        )

    def _translate_chunk(
        self, lines: list[str], source_lang: str | None, target_lang: str
    ) -> tuple[list[str], str | None]:
        prompt = _PROMPT.format(target=target_lang)
        if source_lang:
            prompt += f" The source language is {source_lang}."
        prompt += f'\nInput JSON array:\n{json.dumps(lines, ensure_ascii=False)}'

        url = f"{self.base_url}/models/{self.model}:generateContent"
        headers = {"x-goog-api-key": self.api_key, "Content-Type": "application/json"}
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0},
        }
        estimated = _REQUEST_OVERHEAD_TOKENS + sum(self._line_cost(l) for l in lines)

        last_exc: Exception | None = None
        for attempt in range(_MAX_ATTEMPTS):
            self._throttle(estimated)
            try:
                resp = requests.post(url, headers=headers, json=payload, timeout=90)
                if resp.status_code == 404:
                    raise self._model_unavailable_error()
                if resp.status_code == 429 or resp.status_code >= 500:
                    retry_after = resp.headers.get("Retry-After")
                    try:
                        wait = float(retry_after)
                    except (TypeError, ValueError):
                        wait = min(_MAX_BACKOFF_SECONDS, 2.0 ** attempt)
                    last_exc = RuntimeError(f"HTTP {resp.status_code}")
                    _sleep(max(0.05, wait))
                    continue
                resp.raise_for_status()
                data = resp.json()
                parsed = self._parse_json(self._extract_text(data))
                translated = parsed["lines"]
                if not isinstance(translated, list):
                    raise ValueError("'lines' field is not a list")
                if len(translated) != len(lines):
                    raise ValueError(
                        f"got {len(translated)} lines for {len(lines)} input lines"
                    )
                usage = (data.get("usageMetadata") or {}).get("totalTokenCount")
                try:
                    spent = int(usage)
                except (TypeError, ValueError):
                    spent = estimated
                self._window.record(spent)
                self._rpm_window.record(1)
                detected = parsed.get("detected_source") or None
                return [str(x) for x in translated], detected
            except TranslationError:
                raise
            except Exception as exc:  # noqa: BLE001 - boundary: convert to TranslationError
                last_exc = exc
                break

        raise TranslationError(
            f"gemini translation failed after {attempt + 1} attempt(s): {last_exc}"
        )

    def translate(
        self, lines: list[str], source_lang: str | None, target_lang: str
    ) -> tuple[list[str], str | None]:
        if not lines:
            return [], None
        out: list[str] = []
        detected: str | None = None
        for chunk in self._chunk(lines):
            texts, det = self._translate_chunk(chunk, source_lang, target_lang)
            out.extend(texts)
            detected = detected or det
        return out, detected
