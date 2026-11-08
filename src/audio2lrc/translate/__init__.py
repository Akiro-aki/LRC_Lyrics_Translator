"""Translation backends."""

from audio2lrc.translate.base import Translator, translate_batched
from audio2lrc.translate.gemini import GeminiTranslator
from audio2lrc.translate.google import GoogleTranslator
from audio2lrc.translate.libretranslate import LibreTranslateTranslator
from audio2lrc.translate.openai_backend import OpenAITranslator

__all__ = [
    "Translator",
    "translate_batched",
    "GeminiTranslator",
    "GoogleTranslator",
    "LibreTranslateTranslator",
    "OpenAITranslator",
]