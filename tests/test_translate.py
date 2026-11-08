"""Translation tests: batching, fallback, skipping, romanization."""

import json

import pytest

from audio2lrc.models import TranslationError
from audio2lrc.translate.base import translate_batched
from audio2lrc.translate.google import GoogleTranslator
from audio2lrc.translate.libretranslate import LibreTranslateTranslator
from audio2lrc.translate.romanize import romanize_lines

LINES = ["first line", "[Chorus]", "", "second line"]


class FakeTranslator:
    def __init__(self, batch_result, detected="ja", single_result=None):
        self.batch_result = batch_result
        self.detected = detected
        self.single_result = single_result
        self.calls = []

    def translate(self, lines, source_lang, target_lang):
        self.calls.append(list(lines))
        if len(lines) == 1 and self.single_result is not None:
            return list(self.single_result), self.detected
        if self.batch_result is None:
            raise TranslationError("boom")
        return list(self.batch_result), self.detected


def test_batch_translate_all_lines():
    t = FakeTranslator(["uno", "dos", "tres", "cuatro"])
    result, detected = translate_batched(t, LINES, None, "es")
    assert result == ["uno", "dos", "tres", "cuatro"]
    assert detected == "ja"
    assert len(t.calls) == 1


def test_skipped_lines_pass_through_unchanged():
    t = FakeTranslator(["uno", "dos"])
    result, _ = translate_batched(t, LINES, None, "es", skip_indices={1, 2})
    assert result == ["uno", "[Chorus]", "", "dos"]
    assert t.calls == [["first line", "second line"]]


def test_count_mismatch_triggers_per_line_fallback():
    t = FakeTranslator(["too"], single_result=["uno"])  # batch: 1 result for 2 lines
    result, _ = translate_batched(t, LINES, None, "es", skip_indices={1, 2})
    assert result == ["uno", "[Chorus]", "", "uno"]
    assert len(t.calls) > 1


def test_backend_total_failure_raises():
    t = FakeTranslator(None)
    with pytest.raises(TranslationError):
        translate_batched(t, LINES, None, "es")


def test_partial_failure_keeps_originals_for_failed_lines():
    class PartialFake:
        calls = 0

        def translate(self, lines, source_lang, target_lang):
            PartialFake.calls += 1
            if PartialFake.calls == 1:
                raise TranslationError("boom")
            if PartialFake.calls == 2:
                return ["uno"], "ja"
            raise TranslationError("boom")

    result, detected = translate_batched(PartialFake(), LINES, None, "es")
    assert result == ["uno", "[Chorus]", "", "second line"]
    assert detected == "ja"


def test_all_lines_skipped_no_call():
    t = FakeTranslator([])
    result, _ = translate_batched(t, ["[Chorus]", "[Instrumental]"], None, "es",
                                  skip_indices={0, 1})
    assert result == ["[Chorus]", "[Instrumental]"]
    assert t.calls == []


class FakePost:
    def __init__(self, json_data):
        self._json = json_data
        self.kwargs = None

    def __call__(self, url, **kwargs):
        self.kwargs = kwargs
        return self

    def raise_for_status(self):
        pass

    def json(self):
        return self._json


def test_google_response_parsing(monkeypatch):
    fake = FakePost(
        [
            [["hola", "hi", None, None], "\n", ["mundo", "world", None, None]],
            None,
            [["es"]],
        ]
    )
    monkeypatch.setattr("audio2lrc.translate.google.requests.post", fake)
    t = GoogleTranslator()
    result, detected = t.translate(["hi", "world"], None, "es")
    assert result == ["hola", "mundo"]
    assert detected == "es"
    assert fake.kwargs["params"]["sl"] == "auto"
    assert fake.kwargs["params"]["tl"] == "es"


def test_google_failure_raises(monkeypatch):
    class Boom:
        def raise_for_status(self):
            raise RuntimeError("network down")

    def bad_post(url, **kwargs):
        return Boom()

    monkeypatch.setattr("audio2lrc.translate.google.requests.post", bad_post)
    with pytest.raises(TranslationError):
        GoogleTranslator().translate(["hi"], None, "es")


def test_libretranslate_response_parsing(monkeypatch):
    fake = FakePost(
        {"translatedText": "bonjour\nmonde", "detectedLanguage": {"language": "fr"}}
    )
    monkeypatch.setattr("audio2lrc.translate.libretranslate.requests.post", fake)
    t = LibreTranslateTranslator(url="http://localhost:5000")
    result, detected = t.translate(["hello", "world"], None, "fr")
    assert result == ["bonjour", "monde"]
    assert detected == "fr"
    assert fake.kwargs["json"]["target"] == "fr"


def test_openai_requires_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from audio2lrc.translate.openai_backend import OpenAITranslator

    with pytest.raises(TranslationError):
        OpenAITranslator(api_key="")


def _gemini_ok(lines, detected="ja", total_tokens=50):
    text = json.dumps({"lines": lines, "detected_source": detected})
    return {
        "candidates": [{"content": {"parts": [{"text": text}]}}],
        "usageMetadata": {"totalTokenCount": total_tokens},
    }


class FakeGeminiResponse:
    def __init__(self, status=200, payload=None, headers=None):
        self.status_code = status
        self._payload = payload or {}
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


def test_gemini_requires_key(monkeypatch):
    from audio2lrc.translate.gemini import GeminiTranslator

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(TranslationError):
        GeminiTranslator(api_key="")


def test_gemini_response_parsing(monkeypatch):
    from audio2lrc.translate.gemini import GeminiTranslator

    calls = []

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append({"url": url, "headers": headers})
        return FakeGeminiResponse(payload=_gemini_ok(["hola", "mundo"], detected="es"))

    monkeypatch.setattr("audio2lrc.translate.gemini.requests.post", fake_post)
    t = GeminiTranslator(api_key="k", tpm=100000)
    result, detected = t.translate(["hi", "world"], None, "es")
    assert result == ["hola", "mundo"]
    assert detected == "es"
    assert calls[0]["url"].endswith("/models/gemini-flash-lite-latest:generateContent")
    assert calls[0]["headers"]["x-goog-api-key"] == "k"


def test_gemini_parses_fenced_json(monkeypatch):
    from audio2lrc.translate.gemini import GeminiTranslator

    fenced = '```json\n{"lines": ["bonjour"], "detected_source": null}\n```'
    payload = {"candidates": [{"content": {"parts": [{"text": fenced}]}}]}

    monkeypatch.setattr(
        "audio2lrc.translate.gemini.requests.post",
        lambda *a, **k: FakeGeminiResponse(payload=payload),
    )
    result, detected = GeminiTranslator(api_key="k").translate(["hello"], None, "fr")
    assert result == ["bonjour"]
    assert detected is None


def test_gemini_count_mismatch_raises(monkeypatch):
    from audio2lrc.translate.gemini import GeminiTranslator

    monkeypatch.setattr(
        "audio2lrc.translate.gemini.requests.post",
        lambda *a, **k: FakeGeminiResponse(payload=_gemini_ok(["only-one"])),
    )
    with pytest.raises(TranslationError):
        GeminiTranslator(api_key="k").translate(["a", "b"], None, "es")


def test_gemini_throttles_within_tpm(monkeypatch):
    from audio2lrc.translate import gemini as gemini_mod

    clock = {"now": 0.0}
    sleeps: list[float] = []
    monkeypatch.setattr(gemini_mod, "_monotonic", lambda: clock["now"])
    monkeypatch.setattr(gemini_mod, "_sleep", lambda s: sleeps.append(s) or clock.__setitem__("now", clock["now"] + s))
    monkeypatch.setattr(
        gemini_mod.requests,
        "post",
        lambda *a, **k: FakeGeminiResponse(payload=_gemini_ok(["x"], total_tokens=80)),
    )

    t = gemini_mod.GeminiTranslator(api_key="k", tpm=150)
    t.translate(["hello"], None, "es")
    assert sleeps == []  # first call fits in the empty window
    t.translate(["hello"], None, "es")
    assert sleeps and sleeps[-1] > 0  # second call must wait for window room


def test_gemini_throttles_within_rpm(monkeypatch):
    from audio2lrc.translate import gemini as gemini_mod

    clock = {"now": 0.0}
    sleeps: list[float] = []
    monkeypatch.setattr(gemini_mod, "_monotonic", lambda: clock["now"])
    monkeypatch.setattr(gemini_mod, "_sleep", lambda s: sleeps.append(s) or clock.__setitem__("now", clock["now"] + s))
    monkeypatch.setattr(
        gemini_mod.requests,
        "post",
        lambda *a, **k: FakeGeminiResponse(payload=_gemini_ok(["x"])),
    )

    t = gemini_mod.GeminiTranslator(api_key="k", tpm=100000, rpm=2)
    t.translate(["hello"], None, "es")
    t.translate(["hello"], None, "es")
    assert sleeps == []  # two requests fit inside rpm=2
    t.translate(["hello"], None, "es")
    assert sleeps and sleeps[-1] > 0  # third request must wait for RPM window room


def test_gemini_404_fails_fast_with_hint(monkeypatch):
    from audio2lrc.translate import gemini as gemini_mod

    calls = []
    monkeypatch.setattr(
        gemini_mod.requests,
        "post",
        lambda *a, **k: (calls.append(1), FakeGeminiResponse(status=404))[1],
    )
    sleeps: list[float] = []
    monkeypatch.setattr(gemini_mod, "_sleep", lambda s: sleeps.append(s))

    t = gemini_mod.GeminiTranslator(api_key="k")
    with pytest.raises(TranslationError) as excinfo:
        t.translate(["hi"], None, "es")
    assert "GEMINI_MODEL" in str(excinfo.value)
    assert len(calls) == 1 and sleeps == []


def test_gemini_404_live_translate_hint(monkeypatch):
    from audio2lrc.translate import gemini as gemini_mod

    monkeypatch.setattr(
        gemini_mod.requests,
        "post",
        lambda *a, **k: FakeGeminiResponse(status=404),
    )
    t = gemini_mod.GeminiTranslator(
        api_key="k", model="gemini-3.5-live-translate-preview"
    )
    with pytest.raises(TranslationError) as excinfo:
        t.translate(["hi"], None, "es")
    assert "audio only" in str(excinfo.value)


def test_gemini_retries_on_429(monkeypatch):
    from audio2lrc.translate import gemini as gemini_mod

    responses = [
        FakeGeminiResponse(status=429, headers={"Retry-After": "0.01"}),
        FakeGeminiResponse(payload=_gemini_ok(["hola"], detected="es")),
    ]
    seen = []

    def fake_post(*a, **k):
        seen.append(1)
        return responses.pop(0)

    sleeps: list[float] = []
    monkeypatch.setattr(gemini_mod, "_sleep", lambda s: sleeps.append(s))
    monkeypatch.setattr(gemini_mod.requests, "post", fake_post)

    result, detected = gemini_mod.GeminiTranslator(api_key="k").translate(
        ["hi"], None, "es"
    )
    assert result == ["hola"]
    assert detected == "es"
    assert len(seen) == 2 and len(sleeps) == 1


def test_build_output_lines_skips_identical_translations(monkeypatch):
    from audio2lrc.cli import _build_output_lines
    from audio2lrc.models import LyricLine

    lines = [LyricLine(12.34, "same text"), LyricLine(25.0, "hello")]
    monkeypatch.setattr(
        "audio2lrc.cli.translate_batched",
        lambda *a, **k: (["same text", "hola"], "ja"),
    )
    out, detected, note, romanized = _build_output_lines(
        lines, translate=True, romanize=False,
        source_lang=None, target_lang="es",
    )
    assert [l.text for l in out] == ["same text", "hello", "hola"]
    assert detected == "ja"
    assert not romanized


def test_romanize_passthrough_non_cjk():
    assert romanize_lines(["hello", "world"]) == ["hello", "world"]


def test_romanize_chinese():
    out = romanize_lines(["你好，世界"])
    assert out[0] and out[0] != "你好，世界"
    assert any(ch in "abcdefghijklmnopqrstuvwxyz" for ch in out[0].lower())