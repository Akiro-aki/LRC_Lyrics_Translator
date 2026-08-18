# audio2lrc

**Audio file → synced lyrics → translated `.lrc` subtitle file.**

Point it at a local audio file (`.mp3`, `.flac`, `.m4a`, `.ogg`, ...). It reads
the file's own metadata tags (title/artist/album/duration), finds synced lyrics
from the embedded tags or from [LRCLIB](https://lrclib.net), optionally
translates them, and writes a `.lrc` file next to the source.

No manual song-name entry — everything comes from the file itself.

[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![CI](https://github.com/akiro/audio2lrc/actions/workflows/ci.yml/badge.svg)](https://github.com/akiro/audio2lrc/actions/workflows/ci.yml)

---

## What it does

```text
$ ./run.sh YOASOBI_Yoru_ni_Kakeru.flac --translate --target-lang en --romanize
[audio2lrc] metadata: YOASOBI - 夜に駆ける (4:21)
[audio2lrc] source: lrclib.net (synced, 73 lines)
[audio2lrc] wrote YOASOBI_Yoru_ni_Kakeru.lrc
```

The resulting `.lrc` (works in any player that supports synced lyrics):

```text
[ti:夜に駆ける]
[ar:YOASOBI]
[al:THE BOOK]
#X-SOURCE: lrclib.net
#X-TRANSLATED-FROM: ja
#X-TARGET-LANG: en
[00:12.34]沈むように溶けてゆくように
[00:12.34]Shizumu youni tokete yuku youni
[00:12.34]As if sinking, as if melting away
```

## Features

- **Zero configuration** — lyrics come from the file itself, no typing song names
- **Offline when possible** — uses lyrics already embedded in the file's tags
- **Free synced lyrics** — falls back to LRCLIB (no API key required), with on-disk caching
- **Translation** — Google (free, no key), LibreTranslate, or any OpenAI-compatible API
- **Romanization** — romaji for Japanese, pinyin for Chinese
- **Batch mode** — process a whole music library in one command (`--recursive`)
- **Wide format support** — mp3, flac, m4a/mp4, ogg/opus, wav, aiff, aac, wv, ape, mpc, spx

## Install

Requires **Python 3.10+**. Any of these work:

```bash
# Option A: with uv (fastest, recommended)
uv sync && uv run audio2lrc --version

# Option B: plain pip
pip install -e .

# Option C: no install at all — the wrapper script handles everything
./run.sh --version        # creates .venv and installs deps on first run
```

## Quick start

```bash
./run.sh song.mp3                          # extract/fetch synced lyrics only
./run.sh song.flac --translate --target-lang en
./run.sh song.mp3 --translate --target-lang ja --romanize
./run.sh song.mp3 --out ./lyrics/song.lrc  # custom output path
```

If you installed the package, replace `./run.sh` with `audio2lrc`.

## Do I need an API?

| Scenario | Network? | API key? |
|---|---|---|
| File has embedded **synced** lyrics (SYLT / LRC text in tags) | No — fully offline | No |
| No usable embedded lyrics | Yes — LRCLIB lookup (free, no key) | No |
| `--translate` | Yes — translation backend | Google: no key. LibreTranslate: only if the instance requires it. OpenAI: yes. |
| `--romanize` | Only first run with Japanese text (pykakasi downloads its dictionary once) | No |

- LRCLIB lookups are **cached on disk** (`~/.cache/audio2lrc/`), so re-running on
  the same file never hits the network again.
- Translation backends are chosen via env/config — no keys are bundled in the app.

---

## Usage in detail

```
audio2lrc AUDIO [--translate] [--target-lang LANG] [--source-lang LANG]
           [--romanize] [--out PATH] [--prefer-embedded | --prefer-lrclib]
```

### Positional: `AUDIO`
Path to an audio file (mp3, flac, m4a/mp4, ogg/opus, wav, ...) **or a
directory**. When it's a directory, every audio file in it is processed in
batch mode (see below).

### `--translate`
Enables translation. Without it, the app only extracts/fetches the original
lyrics and writes a plain `.lrc`.

### `--target-lang`
Required if `--translate` is set. ISO-639 language code of the desired output,
e.g. `en`, `ja`, `zh`, `fr`, `es`, `ko`.

### `--source-lang`
Optional; auto-detected when omitted (the backend reports the detected
language, which is written into the output comments). If the detected source
equals the target, translation is skipped and a note is written to the output
instead of silently no-op'ing.

### `--romanize`
Adds a transliteration line (e.g. romaji for Japanese, pinyin for Chinese)
between the original and the translation:

```
[00:12.34]元の歌詞の行
[00:12.34]Moto no kashi no gyou
[00:12.34]The original lyric line translated to English
```

Uses `pykakasi` (Japanese) and `pypinyin` (Chinese), which are installed with
the app. Japanese romanization downloads pykakasi's dictionary once on first
use (needs network that one time).

### `--out PATH`
Custom output path. Default: `{audio-filename}.lrc` next to the source.
Cannot be used in batch mode.

### `--prefer-embedded` / `--prefer-lrclib`
Controls which source wins when both embedded lyrics and an LRCLIB match
exist. Mutually exclusive.

Default priority:
1. embedded lyrics, if synced
2. LRCLIB, if synced
3. LRCLIB plain-text match
4. embedded plain-text lyrics (marked unsynced)
5. error — no lyrics available

`--prefer-embedded` moves embedded lyrics ahead of any LRCLIB result;
`--prefer-lrclib` does the reverse.

---

## Batch mode (directory scanning)

Pass a directory instead of a file to process every audio file in it. Each
`.lrc` is written **next to its song** (`{song-name}.lrc`), so files stay in
their original folders.

```bash
./run.sh ~/Music/Album                  # one .lrc per track, next to each song
./run.sh ~/Music/Album --recursive      # include subdirectories
./run.sh ~/Music/Album --translate --target-lang en
```

Behavior:
- Supported extensions: mp3, flac, m4a/mp4, ogg/oga/opus, wav, aiff/aif, aac,
  wv, ape, mpc, spx. Other files are skipped.
- Files are processed in sorted order, one at a time.
- A failing file (no lyrics found, unreadable, ...) is reported but **does not
  stop the run** — remaining files are still processed. The exit code is `1`
  if any file failed, `0` if all succeeded.
- `--out` is not allowed in batch mode.
- LRCLIB cache is shared across the batch, so duplicate lookups never repeat
  network calls.

---

## Configuration (translation backends)

Copy `.env.example` to `.env` (auto-loaded from the working directory or your
home directory) or export the variables directly.

### `TRANSLATOR_BACKEND` (default `google`)
- **`google`** — free endpoint, no key required. Default.
- **`libretranslate`** — self-hosted instance or libretranslate.com.
- **`openai`** — any OpenAI-compatible chat API (custom endpoints/LLMs).

### LibreTranslate
```
TRANSLATOR_BACKEND=libretranslate
LIBRETRANSLATE_URL=https://libretranslate.com   # or your self-hosted instance
LIBRETRANSLATE_API_KEY=                         # only if the instance requires it
```

### OpenAI-compatible
```
TRANSLATOR_BACKEND=openai
OPENAI_API_KEY=sk-...                           # required
OPENAI_BASE_URL=https://api.openai.com/v1       # or any compatible endpoint
OPENAI_MODEL=gpt-4o-mini
```

### Misc
```
LRCLIB_URL=https://lrclib.net   # override the lyrics API base
CACHE_DIR=~/.cache/audio2lrc    # override the lyrics cache location
```

---

## How it works

1. **Reads tags** — title, artist, album, duration; embedded lyrics:
   - **ID3 (mp3):** `SYLT` (synced) preferred over `USLT` (plain)
   - **Vorbis (flac/ogg/opus):** `LYRICS` / `UNSYNCEDLYRICS` — treated as
     unsynced unless they contain LRC timestamps
   - **MP4/M4A:** `©lyr` atom — same rule (some taggers embed full `.lrc`
     text there, which is detected and used as synced)
   - If title/artist tags are missing, falls back to parsing the filename
     (`Artist - Title.mp3`) and logs that it's a low-confidence guess.
2. **Resolves lyrics** using the priority above.
3. **Translates** (only with `--translate`): batches all lines in one call;
   if the response line count mismatches, retries per-line. Section markers
   (`[Chorus]`, `[Instrumental]`, ...) and empty lines pass through unchanged.
   Timestamps are never shifted.
4. **Writes the `.lrc`:**

   Without translation:
   ```
   [ti:Song Title]
   [ar:Artist Name]
   [al:Album]
   #X-SOURCE: embedded | lrclib.net
   [00:12.34]Lyric line
   ```

   Unsynced lyrics are still written as a valid `.lrc`: every line gets a
   `[00:00.00]` timestamp and the file gets `#X-UNSYNCED: true`.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `error: no lyrics found` | The file is untagged or has no embedded lyrics and LRCLIB has no match. `--prefer-embedded` can help for files with embedded lyrics. |
| `low confidence: guessed artist/title from filename` | File has no ID3/Vorbis tags; rename it `Artist - Title.ext` for the best guess. |
| Translation fails / no output | Check the backend config in `.env` (see above). `TRANSLATOR_BACKEND=google` works without any key. |
| `--target-lang` errors | `--translate` requires `--target-lang`, e.g. `--target-lang en`. |
| `--out` rejected | `--out` only works for single files, not in batch (directory) mode. |
| Works on files, not on my NAS/SMB share | Mount the share first (e.g. `sudo mount -t cifs //server/share /mnt/music -o username=USER,uid=$(id -u),gid=$(id -g)`) and point audio2lrc at the mount path. The app needs write access to write `.lrc` files next to the audio. |

## Exit codes

- `0` — success
- `1` — any error (unsupported file, no lyrics found anywhere, translation
  backend misconfigured, network failure, ...) — with a clear message on stderr

---

## Contributing

```bash
git clone https://github.com/akiro/audio2lrc.git
cd audio2lrc
uv sync --extra dev
uv run pytest          # 53 tests
```

- Tests live in `tests/` and cover tag extraction (mp3/flac/m4a), LRC
  parsing/writing, resolution priority rules, LRCLIB caching,
  batch-translation fallback and the CLI.
- The detailed design notes are in [audio2lrc-spec.md](audio2lrc-spec.md).

## License

[MIT](LICENSE)