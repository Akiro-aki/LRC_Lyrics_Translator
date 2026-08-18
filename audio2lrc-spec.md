# Build Spec: Audio File → Synced Lyrics → Translated .lrc

## Goal

Build a CLI app that:

1. Takes a **local audio file** as input (`.mp3`, `.flac`, `.m4a`, `.ogg`, etc.).
2. Reads the file's **metadata tags** (title, artist, album, duration) and checks for **embedded lyrics** (e.g. `USLT`/`SYLT` frames in ID3, `LYRICS`/`UNSYNCEDLYRICS` in Vorbis comments, `©lyr` in MP4 atoms).
3. Gets synced lyrics by:
   - Using **embedded lyrics** directly if present and synced, **or**
   - Querying **LRCLIB** using the extracted metadata (title + artist + duration) if no usable embedded lyrics exist.
4. Optionally **translates** the lyrics into a target language.
5. Outputs a `.lrc` file — original-only, or original+translation stacked, depending on whether translation was requested.

No manual song-name entry needed; metadata comes from the file itself.

---

## 1. Input / CLI

```
audio2lrc song.mp3
audio2lrc song.flac --translate --target-lang en
audio2lrc song.mp3 --translate --target-lang ja --romanize
audio2lrc song.mp3 --out ./lyrics/song.lrc
```

- Positional arg: path to the audio file. Required.
- `--translate`: enables the translation step. Without it, the app just extracts/fetches original synced lyrics and writes a plain `.lrc`.
- `--target-lang`: required if `--translate` is set.
- `--source-lang`: optional; auto-detect if omitted.
- `--romanize`: optional, same as prior specs — adds a transliterated line for non-Latin scripts.
- `--out`: optional output path; default to `{audio-filename}.lrc` (or `.{target-lang}.lrc` if translated), next to the source file.
- `--prefer-embedded` / `--prefer-lrclib`: optional flag to control which source wins if **both** embedded lyrics and an LRCLIB match are available (default: prefer embedded if it's synced, otherwise prefer LRCLIB if it has synced lyrics and embedded doesn't).

---

## 2. Reading metadata + embedded lyrics

Use a well-supported tag-reading library for the implementation language (e.g. `mutagen` for Python, `music-metadata` for Node/TS) to support the range of formats above without hand-rolling tag parsers.

Extract:
- `title`, `artist`, `album` — used for the LRCLIB query.
- `duration` (seconds) — used to disambiguate LRCLIB search results.
- Embedded lyrics, checking format-specific fields:
  - **ID3 (mp3):** `USLT` (unsynced lyrics) and `SYLT` (synced lyrics) frames — prefer `SYLT` if present since it already has timestamps.
  - **Vorbis comments (flac/ogg):** `LYRICS` or `UNSYNCEDLYRICS` — these are almost always plain text; treat as unsynced.
  - **MP4/M4A:** `©lyr` atom — plain text, treat as unsynced unless it happens to contain LRC-style timestamps (some taggers embed full `.lrc` text here — detect by checking for `[mm:ss.xx]` patterns before assuming it's plain).

If title/artist tags are missing or empty, fall back to parsing the filename (e.g. `Artist - Title.mp3`) as a last resort, and clearly log that this is a guess (filename parsing is unreliable — treat it as lower-confidence than tag data).

---

## 3. Lyrics resolution logic

```
1. Read tags + embedded lyrics from the file.
2. If embedded lyrics exist and are synced (SYLT, or LRC-pattern text in a plain field):
     -> use them directly, skip LRCLIB query (unless --prefer-lrclib is set).
3. Else, query LRCLIB with (title, artist, duration):
     -> if a synced match is found, use it.
     -> else if only a plain-text match is found, use that (mark unsynced).
     -> else if embedded lyrics exist but are unsynced, fall back to those (mark unsynced).
     -> else, no lyrics available — error out clearly, don't fabricate content.
4. Proceed to translation step (if requested) and .lrc writing, same as prior specs.
```

Cache LRCLIB lookups locally (keyed by title+artist+duration) so re-running on the same file doesn't re-query.

---

## 4. Translation (only if `--translate` is set)

Same approach as the earlier standalone spec — keep this pluggable, don't hardcode or embed any vendor key:

- `Translator` interface: `translate(lines: string[], sourceLang: string|null, targetLang: string) -> string[]`.
- Batch all lines in one call where possible; verify the returned line count matches the input count before accepting the result — mismatch triggers a per-line retry fallback (never let this shift timestamps).
- Skip translation for section markers (`[Chorus]`, `[Instrumental]`, etc.) and truly empty lines — pass them through unchanged.
- If `--source-lang` is unset, auto-detect per track; if detected source == target, skip translation and note that in the output comments rather than silently no-op'ing.
- If `--romanize` is set, run an extra romanization pass and insert that line between original and translation (same convention as before).
- Backend selection (LibreTranslate / Google / custom endpoint / LLM API) is user-configured via env var or config file, exactly as in the prior specs — never bundle a key in the app itself.

---

## 5. Output format

**Without `--translate`:** a normal single-language `.lrc`, sourced from whichever branch in Section 3 resolved:

```
[ti:Song Title]
[ar:Artist Name]
[al:Album]
#X-SOURCE: embedded | lrclib.net
[00:12.34]Lyric line
```

**With `--translate`:** stacked original + translation (and romanization, if requested) at the same timestamp, same convention as the earlier specs:

```
[ti:Song Title]
[ar:Artist Name]
[al:Album]
#X-SOURCE: embedded | lrclib.net
#X-TRANSLATED-FROM: ja
#X-TARGET-LANG: en
[00:12.34]元の歌詞の行
[00:12.34]Moto no kashi no gyou
[00:12.34]Original lyric line translated to English
```

If the resolved lyrics were unsynced (no timestamps at all), still produce a valid `.lrc` using a single `[00:00.00]` block per line, and add `#X-UNSYNCED: true` so downstream tools/users know not to expect real timing.

---

## 6. Suggested project structure

```
audio2lrc/
├── src/
│   ├── cli.py (or .ts) — arg parsing, orchestration
│   ├── audio/
│   │   └── tags.py — metadata + embedded lyrics extraction (mutagen / music-metadata)
│   ├── providers/
│   │   └── lrclib.py — LRCLIB search/get
│   ├── lrc/
│   │   ├── parser.py — parse LRC text -> LyricLine[] (used for embedded SYLT text and LRCLIB responses alike)
│   │   └── writer.py — LyricLine[] -> .lrc text
│   ├── translate/
│   │   ├── base.py — Translator interface
│   │   └── <backend>.py
│   └── models.py — LyricLine, TrackMetadata dataclasses
├── tests/
│   ├── fixtures/ (sample tagged audio files, sample LRCLIB responses)
│   ├── test_tags.py
│   ├── test_lrc.py
│   └── test_translate.py
├── .env.example
├── requirements.txt (or package.json)
└── README.md
```

---

## 7. Testing checklist

- MP3 with `SYLT` frame: extracted directly, no LRCLIB call made.
- MP3 with only `USLT` (plain text): falls through to LRCLIB if a synced match exists there; otherwise uses the plain embedded text, marked unsynced.
- FLAC/OGG with `LYRICS` Vorbis comment: treated as unsynced unless it matches LRC timestamp patterns.
- File with no tags at all: filename-parsing fallback triggers, logs a low-confidence warning, still attempts LRCLIB lookup.
- `--translate` with mismatched batch translation response: per-line fallback triggers, timestamps unaffected.
- `--romanize` on a CJK track: three stacked lines in correct order (original, romanized, translated).
- Re-running on the same file: LRCLIB cache hit, no duplicate network call.

---

## 8. Non-goals (v1)

- No audio fingerprinting (e.g. AcoustID/Chromaprint) to identify mystery/untagged files — tag + filename fallback is enough for v1; fingerprinting can be a later enhancement if untagged files turn out to be common.
- No batch/folder processing — single file per run for v1.
- No bundled translation API keys — user-supplied via env/config only.
- No modification of the source audio file's own tags — output is a separate `.lrc` file, not written back into the audio file.
