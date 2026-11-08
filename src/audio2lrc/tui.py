"""Interactive terminal UI (TUI) for audio2lrc.

Built on prompt_toolkit's dialogs. Collects the same options the CLI accepts
(file / directory / LRCLIB link, provider, translation settings, romanization,
output path) and runs the same processing pipeline.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

from prompt_toolkit.completion import PathCompleter
from prompt_toolkit.shortcuts import PromptSession, input_dialog, radiolist_dialog, yes_no_dialog
from prompt_toolkit.validation import Validator

from audio2lrc.links import parse_lrclib_url
from audio2lrc.theme import DEFAULT_THEME, available_themes, build_style, get_theme

MODE_LABELS = {
    "file": "A single audio file",
    "dir": "A directory of audio files (batch)",
    "link": "An LRCLIB link",
}

# Current prompt_toolkit Style applied to every dialog. Set from the env var
# at startup (collect_options) and updated after the theme picker runs.
_STYLE = build_style(get_theme("opencode"))


def _apply_theme(name: str | None) -> None:
    global _STYLE
    _STYLE = build_style(get_theme(name))


@dataclass
class TUIOptions:
    """Collected TUI settings, mirroring the CLI flags."""

    mode: str = "file"
    path: str | None = None
    theme: str = "opencode"
    provider: str = "lrclib"
    recursive: bool = False
    translate: bool = False
    target_lang: str | None = None
    source_lang: str | None = None
    translator: str | None = None
    api_key: str | None = None
    romanize: bool = False
    out: str | None = None
    prefer_external: bool = False
    prefer_embedded: bool = False


def _pick_mode() -> str:
    result = radiolist_dialog(
        title="audio2lrc",
        text="What do you want to process?",
        values=[(k, title) for k, title in MODE_LABELS.items()],
        ok_text="Next",
        style=_STYLE,
    ).run()
    if result is None:
        raise KeyboardInterrupt
    return result


def _pick_theme(current: str | None) -> str:
    result = radiolist_dialog(
        title="audio2lrc",
        text="Choose a color theme:",
        values=available_themes(),
        default=current,
        ok_text="Next",
        style=_STYLE,
    ).run()
    if result is None:
        raise KeyboardInterrupt
    return result


def _input_path(mode: str) -> str:
    if mode == "link":
        prompt_text = "LRCLIB song link (e.g. https://lrclib.net/song/<id>): "
        validator = _link_validator()
        completer = None
    else:
        what = "audio file" if mode == "file" else "directory"
        prompt_text = f"Path to the {what} (Tab to autocomplete): "
        validator = None
        if mode == "file":
            completer = PathCompleter(
                only_directories=False,
                expanduser=True,
                file_filter=lambda name: name.lower().endswith(
                    (".mp3", ".flac", ".m4a", ".wav", ".ogg", ".opus", ".wma")
                ),
            )
        else:
            completer = PathCompleter(only_directories=True, expanduser=True)
    # A plain PromptSession lets Tab run completion. prompt_toolkit's
    # dialogs (input_dialog) hard-wire Tab to "focus next", which is why the
    # completion key never fired there.
    session = PromptSession(style=_STYLE, validator=validator, completer=completer)
    path = session.prompt(prompt_text, complete_while_typing=True)
    return path.strip()


class _link_validator(Validator):
    def validate(self, document):  # noqa: D102
        from prompt_toolkit.validation import ValidationError

        if parse_lrclib_url(document.text) is None:
            raise ValidationError(
                message="Not a valid LRCLIB link (expected https://lrclib.net/song/<id> or .../tracks/<id>)"
            )


def _pick_provider() -> str:
    result = radiolist_dialog(
        title="audio2lrc",
        text="Which lyrics provider do you want to use?",
        values=[
            ("auto", "Auto (best verified match from all providers)"),
            ("lrclib", "LRCLIB (lrclib.net)"),
            ("netease", "NetEase Cloud Music (music.163.com)"),
            ("qqmusic", "QQ Music (y.qq.com)"),
        ],
        ok_text="Next",
        style=_STYLE,
    ).run()
    if result is None:
        raise KeyboardInterrupt
    return result


def _ask_translate() -> bool:
    return yes_no_dialog(
        title="audio2lrc", text="Translate the lyrics?", yes_text="Yes", no_text="No",
        style=_STYLE,
    ).run() or False


def _ask_target_lang() -> str:
    lang = input_dialog(
        title="audio2lrc",
        text="Target language code (e.g. en, es, zh, ja):",
        style=_STYLE,
    ).run()
    if lang is None:
        raise KeyboardInterrupt
    return lang.strip() or ""


def _ask_source_lang() -> str | None:
    lang = input_dialog(
        title="audio2lrc",
        text="Source language code (optional, auto-detected if left empty):",
        style=_STYLE,
    ).run()
    if lang is None:
        raise KeyboardInterrupt
    return lang.strip() or None


def _pick_translator() -> str:
    result = radiolist_dialog(
        title="audio2lrc",
        text="Translation backend:",
        values=[
            ("google", "Google Translate (free, default)"),
            ("libretranslate", "LibreTranslate (optional key)"),
            ("openai", "OpenAI-compatible (key required)"),
            ("gemini", "Gemini (key required)"),
        ],
        ok_text="Next",
        style=_STYLE,
    ).run()
    if result is None:
        raise KeyboardInterrupt
    return result


def _ask_api_key() -> str | None:
    key = input_dialog(
        title="audio2lrc",
        text="API key for this backend (or leave empty to use the env variable):",
        style=_STYLE,
    ).run()
    if key is None:
        raise KeyboardInterrupt
    return key.strip() or None


def _ask_romanize() -> bool:
    return yes_no_dialog(
        title="audio2lrc", text="Add romanized lines for non-Latin scripts?", yes_text="Yes", no_text="No",
        style=_STYLE,
    ).run() or False


def _ask_recursive() -> bool:
    return yes_no_dialog(
        title="audio2lrc", text="Scan subdirectories recursively?", yes_text="Yes", no_text="No",
        style=_STYLE,
    ).run() or False


def _ask_output(current: str | None) -> str | None:
    result = input_dialog(
        title="audio2lrc",
        text="Output .lrc path (leave empty to use the default next to the source):",
        style=_STYLE,
    ).run()
    if result is None:
        raise KeyboardInterrupt
    return (result.strip() or current)


def _ask_prefer() -> str:
    result = radiolist_dialog(
        title="audio2lrc",
        text="Prefer embedded lyrics in the file, or external lyrics?",
        values=[
            ("default", "Default (embedded synced first, else external)"),
            ("external", "Prefer external lyrics over embedded"),
            ("embedded", "Prefer embedded lyrics"),
        ],
        ok_text="Next",
        style=_STYLE,
    ).run()
    if result is None:
        raise KeyboardInterrupt
    return result


def collect_options() -> TUIOptions:
    """Drive the menu dialogs and return the collected options."""
    global _STYLE

    current = (os.environ.get("A2LRC_THEME") or DEFAULT_THEME).strip().replace("_", "-")
    _STYLE = build_style(get_theme(current))
    opts = TUIOptions()
    opts.theme = _pick_theme(current)
    _apply_theme(opts.theme)
    opts.mode = _pick_mode()
    opts.path = _input_path(opts.mode)
    opts.provider = _pick_provider()
    if opts.mode == "dir":
        opts.recursive = _ask_recursive()
    prefer = _ask_prefer()
    opts.prefer_external = prefer == "external"
    opts.prefer_embedded = prefer == "embedded"
    opts.translate = _ask_translate()
    if opts.translate:
        opts.target_lang = _ask_target_lang()
        if not opts.target_lang:
            raise ValueError("a target language is required when translating")
        opts.source_lang = _ask_source_lang()
        opts.translator = _pick_translator()
        if opts.translator in ("openai", "gemini", "libretranslate"):
            opts.api_key = _ask_api_key()
    opts.romanize = _ask_romanize()
    opts.out = _ask_output(None)
    return opts


def run_pipeline(opts: TUIOptions, cache_dir: str | None = None) -> int:
    """Execute the collected options and report progress.

    Returns a process exit code (0 = all ok).
    """
    from audio2lrc.cli import (
        _iter_audio_files,
        _log,
        _process_file,
        _process_link,
    )

    cache_dir = cache_dir or os.environ.get("CACHE_DIR") or None

    if opts.mode == "link":
        return 0 if _process_link(opts.path, _opts_to_args(opts)) else 1

    if not opts.path or not os.path.exists(opts.path):
        _log(f"path not found: {opts.path}")
        return 1

    if os.path.isdir(opts.path):
        if opts.out:
            _log("--- note: --out is ignored for directory batches")
        files = _iter_audio_files(opts.path, opts.recursive)
        if not files:
            _log(f"--- no audio files found in {opts.path}")
            return 1
        _log(f"--- batch: {len(files)} audio file(s) in {opts.path}")
        ok = failed = 0
        for f in files:
            _log(f"--- {f}")
            if _process_file(f, _opts_to_args(opts), cache_dir):
                ok += 1
            else:
                failed += 1
        _log(f"--- batch done: {ok} ok, {failed} failed")
        return 0 if failed == 0 else 1

    return 0 if _process_file(opts.path, _opts_to_args(opts), cache_dir) else 1


def _opts_to_args(opts: TUIOptions):
    """Map TUIOptions to an argparse-like Namespace for reuse of the CLI."""
    from types import SimpleNamespace

    return SimpleNamespace(
        provider=opts.provider or "lrclib",
        min_confidence=None,
        prefer_embedded=opts.prefer_embedded,
        prefer_external=opts.prefer_external,
        prefer_lrclib=False,
        translate=opts.translate,
        romanize=opts.romanize,
        source_lang=opts.source_lang,
        target_lang=opts.target_lang,
        translator=opts.translator,
        api_key=opts.api_key,
        out=opts.out,
        audio=opts.path,
    )


def main(argv: list[str] | None = None) -> int:
    """Entry point for the TUI."""
    from audio2lrc.cli import _load_dotenv

    _load_dotenv()
    try:
        opts = collect_options()
        return run_pipeline(opts)
    except KeyboardInterrupt:
        print("\n[audio2lrc] cancelled")
        return 130
    except ValueError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 2


if __name__ == "__main__":
    sys.exit(main())
