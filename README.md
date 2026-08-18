# audio2lrc

Audio file → synced lyrics → translated `.lrc` subtitle file.

Point it at a local audio file (`.mp3`, `.flac`, `.m4a`, `.ogg`, ...). It reads
the file's own metadata tags (title/artist/album/duration), finds synced lyrics
from the embedded tags or from [LRCLIB](https://lrclib.net), optionally
translates them, and writes a `.lrc` file next to the source.

No manual song-name entry — everything comes from the file itself.

---

## Quick start

Requires Python 3.10+ and [uv](https://docs.astral.sh/uv/) (fast, handles the
virtualenv + dependencies automatically).

```bash
./run.sh song.mp3                          # extract/fetch synced lyrics only
./run.sh song.flac --translate --target-lang en
./run.sh song.mp3 --translate --target-lang ja --romanize
./run.sh song.mp3 --out ./lyrics/song.lrc  # custom output path
```

First run creates `.venv/` and installs dependencies; afterwards it starts
instantly. You can also install the package globally and use the `audio2lrc`
command directly:

```bash
uv sync                                   # create .venv
uv run audio2lrc song.mp3
```

---

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

### `--recursive` / `-r`
With a directory, also scan subdirectories.

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
Custom output path. Default: `{audio-filename}.lrc` next to the source, or
`{audio-filename}.{target-lang}.lrc` when translated. Cannot be used in batch
mode.

### `--recursive` / `-r`
When the positional arg is a directory, also scan its subdirectories.

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

## What it does, step by step

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

   With translation (stacked at the same timestamp):
   ```
   [ti:Song Title]
   [ar:Artist Name]
   [al:Album]
   #X-SOURCE: lrclib.net
   #X-TRANSLATED-FROM: ja
   #X-TARGET-LANG: en
   [00:12.34]元の歌詞の行
   [00:12.34]Moto no kashi no gyou
   [00:12.34]Original lyric line translated to English
   ```

   Unsynced lyrics are still written as a valid `.lrc`: every line gets a
   `[00:00.00]` timestamp and the file gets `#X-UNSYNCED: true`.

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

## Examples

```bash
# Just synced lyrics for a tagged mp3, using embedded tags if present
./run.sh ~/Music/Rick_Astley_Never_Gonna_Give_You_Up.mp3

# Translate a Japanese track to English with romaji added
./run.sh ~/Music/YOASOBI_Yoru_ni_Kakeru.flac --translate --target-lang en --romanize

# Process a whole album folder, one .lrc next to each song
./run.sh ~/Music/Album
./run.sh ~/Music/Music_Library --recursive --translate --target-lang en

# Prefer the file's own lyrics even if unsynced
./run.sh song.mp3 --prefer-embedded

# Output somewhere else
./run.sh song.mp3 --translate --target-lang es --out ./lyrics/song.es.lrc
```

## Exit codes

- `0` — success
- `1` — any error (unsupported file, no lyrics found anywhere, translation
  backend misconfigured, network failure, ...) — with a clear message on stderr

## Tests

```bash
uv run pytest
```

Covers tag extraction (mp3/flac/m4a), LRC parsing/writing, resolution
priority rules, LRCLIB caching, batch-translation fallback and the CLI.

## Non-goals (v1)

- No audio fingerprinting for untagged files (filename fallback is it)
- No bundled translation API keys
- The source audio file's tags are never modified — output is a separate `.lrc`