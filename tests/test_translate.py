"""Translation tests: batching, fallback, skipping, romanization."""

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