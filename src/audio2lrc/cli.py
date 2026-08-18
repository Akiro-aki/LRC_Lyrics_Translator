"""CLI entry point: argument parsing + orchestration."""

from __future__ import annotations

import argparse
import os
import sys

from audio2lrc import __version__
from audio2lrc.audio.tags import read_track
from audio2lrc.lrc.parser import parse_lrc
from audio2lrc.lrc.writer import render_lrc
from audio2lrc.models import (
    LyricLine,
    LyricsNotFoundError,
    TrackMetadata,
    TranslationError,
)
from audio2lrc.resolve import resolve
from audio2lrc.translate import (
    GoogleTranslator,
    LibreTranslateTranslator,
    OpenAITranslator,
    translate_batched,
)
from audio2lrc.translate.romanize import romanize_lines


def _load_dotenv() -> None:
    for path in (".env", os.path.expanduser("~/.env")):
        try:
            with open(path, encoding="utf-8") as fh:
                for raw in fh:
                    line = raw.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, _, value = line.partition("=")
                    key, value = key.strip(), value.strip().strip("\"'")
                    os.environ.setdefault(key, value)
        except OSError:
            continue


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="audio2lrc",
        description="Extract/fetch synced lyrics for an audio file (or every audio "
        "file in a directory) and optionally translate them into .lrc files.",
    )
    p.add_argument("audio", help="path to an audio file (mp3, flac, m4a, ogg, ...) or a directory")
    p.add_argument("--translate", action="store_true", help="translate the lyrics")
    p.add_argument("--target-lang", metavar="LANG", help="target language code (required with --translate)")
    p.add_argument("--source-lang", metavar="LANG", help="source language code (auto-detected if omitted)")
    p.add_argument("--romanize", action="store_true", help="add a romanized line for non-Latin scripts")
    p.add_argument("--out", metavar="PATH", help="output .lrc path (default: next to the audio file)")
    p.add_argument("--recursive", "-r", action="store_true",
                   help="scan subdirectories when the positional arg is a directory")
    group = p.add_mutually_exclusive_group()
    group.add_argument("--prefer-embedded", action="store_true", help="prefer the file's embedded lyrics")
    group.add_argument("--prefer-lrclib", action="store_true", help="prefer an LRCLIB match")
    p.add_argument("--version", action="version", version=f"audio2lrc {__version__}")
    return p


def _log(message: str) -> None:
    sys.stderr.write(f"[audio2lrc] {message}\n")


def _normalize_lang(lang: str | None) -> str | None:
    if not lang:
        return None
    return lang.strip().lower().split("-")[0].split("_")[0]


def _build_translator() -> GoogleTranslator | LibreTranslateTranslator | OpenAITranslator:
    backend = os.environ.get("TRANSLATOR_BACKEND", "google").strip().lower()
    if backend == "libretranslate":
        return LibreTranslateTranslator()
    if backend == "openai":
        return OpenAITranslator()
    return GoogleTranslator()


def _output_path(audio: str, out: str | None) -> str:
    if out:
        return out
    stem, _ = os.path.splitext(audio)
    return f"{stem}.lrc"


AUDIO_EXTENSIONS = {
    ".mp3", ".flac", ".m4a", ".mp4", ".ogg", ".oga", ".opus",
    ".wav", ".aiff", ".aif", ".aac", ".wv", ".ape", ".mpc", ".spx",
}


def _iter_audio_files(root: str, recursive: bool) -> list[str]:
    files: list[str] = []
    if recursive:
        for dirpath, _, names in os.walk(root):
            for name in sorted(names):
                if os.path.splitext(name)[1].lower() in AUDIO_EXTENSIONS:
                    files.append(os.path.join(dirpath, name))
    else:
        for name in sorted(os.listdir(root)):
            full = os.path.join(root, name)
            if os.path.isfile(full) and os.path.splitext(name)[1].lower() in AUDIO_EXTENSIONS:
                files.append(full)
    return files


def _skip_indices(lines: list[LyricLine]) -> set[int]:
    skip: set[int] = set()
    for i, line in enumerate(lines):
        if not line.text.strip() or (line.time is None and line.text.startswith("[")):
            skip.add(i)
    return skip


def _build_output_lines(
    lines: list[LyricLine],
    *,
    translate: bool,
    romanize: bool,
    source_lang: str | None,
    target_lang: str | None,
) -> tuple[list[LyricLine], str | None, str | None, bool]:
    """Apply translation/romanization, returning (lines, detected, note, romanized)."""
    if not translate:
        if romanize:
            texts = [l.text for l in lines]
            rom = romanize_lines(texts)
            out: list[LyricLine] = []
            for line, r in zip(lines, rom):
                out.append(line)
                if r != line.text:
                    out.append(LyricLine(line.time, r))
            return out, None, None, True
        return lines, None, None, False

    skip = _skip_indices(lines)
    translator = _build_translator()
    texts = [l.text for l in lines]
    translated, detected = translate_batched(translator, texts, source_lang, target_lang)
    detected = _normalize_lang(detected)
    target = _normalize_lang(target_lang)

    note: str | None = None
    if detected and target and detected == target:
        note = (
            f"source and target language are the same ({detected}); "
            "translation skipped, original lyrics kept"
        )
        translated = None

    rom: list[str] | None = None
    if romanize:
        rom = romanize_lines(texts)

    out = []
    romanized = False
    for i, line in enumerate(lines):
        out.append(line)
        if rom is not None and rom[i] != line.text:
            out.append(LyricLine(line.time, rom[i]))
            romanized = True
        if translated is not None and i not in skip and translated[i] != line.text:
            out.append(LyricLine(line.time, translated[i]))
    return out, detected, note, romanized


def _process_file(audio: str, args: argparse.Namespace, cache_dir: str | None) -> bool:
    try:
        meta, embedded = read_track(audio)
    except (OSError, ValueError) as exc:
        sys.stderr.write(f"error: {audio}: {exc}\n")
        return False

    if meta.filename_guess:
        _log(
            f"low confidence: guessed artist/title from filename "
            f"({meta.artist} - {meta.title})"
        )
    _log(
        f"metadata: {meta.artist or '?'} - {meta.title or '?'}"
        + (f" ({meta.duration:.1f}s)" if meta.duration else "")
    )
    if embedded:
        kind = "synced" if embedded.synced else "unsynced"
        _log(f"embedded lyrics found ({kind}, from {embedded.note})")

    try:
        resolved = resolve(
            meta,
            embedded,
            prefer_embedded=args.prefer_embedded,
            prefer_lrclib=args.prefer_lrclib,
            cache_dir=cache_dir,
        )
    except LyricsNotFoundError as exc:
        sys.stderr.write(f"error: {audio}: {exc}\n")
        return False

    _log(
        f"source: {resolved.source} ({'synced' if not resolved.unsynced else 'unsynced'}, "
        f"{len(resolved.lines)} lines)"
    )

    translated_from: str | None = None
    target_lang: str | None = None
    romanized = False
    note: str | None = None

    lines = resolved.lines
    if args.translate or args.romanize:
        try:
            lines, detected, note, romanized = _build_output_lines(
                resolved.lines,
                translate=args.translate,
                romanize=args.romanize,
                source_lang=args.source_lang,
                target_lang=args.target_lang,
            )
        except TranslationError as exc:
            sys.stderr.write(f"error: {audio}: {exc}\n")
            return False
        if args.translate:
            translated_from = detected or args.source_lang or "unknown"
            target_lang = _normalize_lang(args.target_lang)
            if note:
                _log(f"note: {note}")

    text = render_lrc(
        meta,
        lines,
        source=resolved.source,
        unsynced=resolved.unsynced,
        translated_from=translated_from,
        target_lang=target_lang,
        romanized=romanized,
        note=note,
    )

    out_path = _output_path(audio, args.out)
    try:
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(text)
    except OSError as exc:
        sys.stderr.write(f"error: cannot write {out_path}: {exc}\n")
        return False

    _log(f"wrote {out_path}")
    return True


def main(argv: list[str] | None = None) -> int:
    _load_dotenv()
    args = _build_parser().parse_args(argv)

    if args.translate and not args.target_lang:
        sys.stderr.write("error: --target-lang is required when --translate is set\n")
        return 2

    cache_dir = os.environ.get("CACHE_DIR") or None

    if os.path.isdir(args.audio):
        if args.out:
            sys.stderr.write("error: --out cannot be used when scanning a directory\n")
            return 2
        files = _iter_audio_files(args.audio, args.recursive)
        if not files:
            sys.stderr.write(
                f"error: no audio files found in {args.audio}"
                + (" (recursively)" if args.recursive else "")
                + "\n"
            )
            return 1
        _log(f"batch: {len(files)} audio file(s) in {args.audio}")
        ok = failed = 0
        for f in files:
            _log(f"--- {f}")
            if _process_file(f, args, cache_dir):
                ok += 1
            else:
                failed += 1
        _log(f"batch done: {ok} ok, {failed} failed")
        return 0 if failed == 0 else 1

    return 0 if _process_file(args.audio, args, cache_dir) else 1


if __name__ == "__main__":
    sys.exit(main())