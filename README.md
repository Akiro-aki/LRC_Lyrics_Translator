# audio2lrc

**Audio file → synced lyrics → translated `.lrc` subtitle file.**

Point it at a local audio file (`.mp3`, `.flac`, `.m4a`, `.ogg`, ...). It reads
the file's own metadata tags (title/artist/album/duration), finds synced lyrics
from the embedded tags or from [LRCLIB](https://lrclib.net) /
[NetEase](https://music.163.com) / [QQ Music](https://y.qq.com), checks that
they really belong to the song, optionally translates them, and writes a
`.lrc` file next to the source.

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
- **Free synced lyrics** — falls back to LRCLIB, NetEase Cloud Music or QQ Music (no API key required), with on-disk caching
- **Verified matches** — every result is checked against the file's title, artist and duration; live/remix/karaoke/cover versions and lyrics for a different cut are rejected
- **Translation** — Google (free, no key), LibreTranslate, Gemini, or any OpenAI-compatible API
- **Romanization** — romaji for Japanese, pinyin for Chinese
- **Batch mode** — process a whole music library in one command (`--recursive`)
- **Interactive TUI** — `audio2lrc-tui` menu-driven prompts for choosing a file,
  folder, or an LRCLIB link plus all processing options
- **Fetch by LRCLIB link** — `--lrclib-link https://lrclib.net/song/<id>` (or
  `/tracks/<id>`) fetches lyrics straight from a shared song URL via the CLI or
  the TUI, no audio file needed
- **Wide format support** — mp3, flac, m4a/mp4, ogg/opus, wav, aiff, aac, wv, ape, mpc, spx

## Installation

### Requirements

- **Python 3.10+** (3.11/3.12/3.13 also supported).
- The following dependencies are installed automatically with the package:
  `mutagen` (tag/metadata reading), `requests` (HTTP), `langdetect` (language
  detection), `pykakasi` / `pypinyin` (Japanese/Chinese romanization),
  `prompt_toolkit` (the `audio2lrc-tui` interface).

No Nerd Font or external toolkit is required — the app and its TUI use plain
ASCII throughout.

### 0. Install Python (once, per platform)

- **Linux (Debian/Ubuntu)**
  ```bash
  sudo apt update && sudo apt install -y python3 python3-venv python3-pip
  ```
  **Fedora/RHEL:** `sudo dnf install -y python3 python3-pip`

- **macOS (Homebrew)**
  ```bash
  brew install python
  ```
  If you rely on the system interpreter, use `python3` (not `python`).

- **Windows**
  - Install from <https://www.python.org/downloads/> and tick **"Add Python to
    PATH"**, or
  - `winget install -e --id Python.Python.3.12`

### 1. Install uv (optional, recommended)

`uv` is a fast, cross-platform package manager. It manages Python versions and
virtualenvs for you. Get it with:

- **Unix (Linux / macOS):**
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```
- **Windows (PowerShell):**
  ```powershell
  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  ```

### 2. Choose a method

#### Method A — uv (recommended)

```bash
uv sync                      # creates .venv and installs deps
uv run audio2lrc --version   # verify the CLI
uv run audio2lrc-tui         # the interactive TUI
```

#### Method B — pip into a virtualenv (no uv)

```bash
python -m venv .venv
# Unix (Linux / macOS):
source .venv/bin/activate
# Windows (cmd or PowerShell):
#   .venv\Scripts\activate
pip install -e .
audio2lrc --version
audio2lrc-tui
```

> On Windows, use `py -m venv .venv` if the `python` command isn't on your PATH.

#### Method C — standalone wrapper script (`./run.sh`)

`run.sh` is a small **bash** wrapper that creates `.venv` and installs
dependencies on first use — no manual steps:

```bash
./run.sh --version
./run.sh song.mp3 --translate --target-lang en
```

**Windows note:** `run.sh` needs a bash shell. Windows users should use
**PowerShell** / **Git Bash** / **WSL** with `run.sh`, or install with **pip /
uv** (Methods A/B) so the `audio2lrc` command works natively in cmd/PowerShell.

### Platform notes

| Platform | Recommended approach | Notes |
|---|---|---|
| **Linux** | `uv` or `./run.sh` | Everything works; cache stored in `~/.cache/audio2lrc` by default. |
| **macOS** | `uv` or `./run.sh` | Everything works; same cache path as Linux. |
| **Windows** | `uv` or `pip` (Methods A/B) | `audio2lrc` / `audio2lrc-tui` run in cmd or PowerShell once installed. Avoid `./run.sh` unless you're in Git Bash / WSL. Set `CACHE_DIR` to a Windows path if the default cache location is undesired. |

### Verify the install

```bash
audio2lrc --version      # CLI
audio2lrc-tui --version  # interactive TUI
```

Installing the package provides **two** console commands: `audio2lrc` (CLI) and
`audio2lrc-tui` (interactive).

### Uninstall

```bash
pip uninstall audio2lrc
```

---

## How to use the app

### Quick start

```bash
# With the installed package (audio2lrc), or using ./run.sh:
./run.sh song.mp3                          # extract/fetch synced lyrics only
./run.sh song.flac --translate --target-lang en
./run.sh song.mp3 --translate --target-lang ja --romanize
./run.sh song.mp3 --out ./lyrics/song.lrc  # custom output path
```

If you installed the package, replace `./run.sh` with `audio2lrc`.

### Batch mode (directory scanning)

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
- Lyrics cache is shared across the batch, so duplicate lookups never repeat
  network calls.

### Interactive TUI (`audio2lrc-tui`)

A menu-driven terminal interface (built on `prompt_toolkit`) that asks the same
questions as the CLI flags, without typing flags by hand.

```bash
audio2lrc-tui            # if you installed the package
uv run audio2lrc-tui     # when using uv (or: .venv/bin/audio2lrc-tui)
```

How to use it, step by step:

1. **Choose a source type** — a single audio file, a directory (batch), or an
   LRCLIB link.
2. **Enter the path** — start typing and press **Tab** to autocomplete it
   (audio files only for file mode; directories for batch mode). Use **↑/↓**
   to pick from the dropdown and **Enter** to accept.
3. **Pick a lyrics provider** — auto / LRCLIB / NetEase / QQ Music.
4. **Set options** — translation (target/source language, backend, optional
   API key), romanization, embedded-vs-external preference, and the output
   `.lrc` path.
5. **Run** — confirm your choices and the pipeline processes the selection.

The link box validates the LRCLIB URL instead of offering autocomplete.

**Theme:** set a default via `A2LRC_THEME`: `opencode` (default), `system`
(adapts to terminal), `one-dark`, `tokyonight`, `catppuccin`, `nord`, `gruvbox`
(also changeable mid-run from the theme picker).

## Do I need an API?

| Scenario | Network? | API key? |
|---|---|---|
| File has embedded **synced** lyrics (SYLT / LRC text in tags) | No — fully offline | No |
| No usable embedded lyrics | Yes — LRCLIB, NetEase or QQ Music lookup (free, no key) | No |
| `--translate` | Yes — translation backend | Google: no key. LibreTranslate: only if the instance requires it. Gemini: yes. OpenAI: yes. |
| `--romanize` | Only first run with Japanese text (pykakasi downloads its dictionary once) | No |

- Lyrics lookups are **cached on disk** (`~/.cache/audio2lrc/`), so re-running on
  the same file never hits the network again.
- Translation backends are chosen via env/config — no keys are bundled in the app.

---

## Usage in detail

```
audio2lrc AUDIO [--translate] [--target-lang LANG] [--source-lang LANG]
           [--romanize] [--out PATH] [--prefer-embedded | --prefer-external]
           [--provider lrclib | netease | qqmusic | auto]
           [--min-confidence 0-1]
           [--lrclib-link URL]
           [--translator BACKEND] [--api-key KEY]
```

> You must provide either `AUDIO` or `--lrclib-link` (not both). `AUDIO` is
> optional on the command line only so the two modes coexist.

### Positional: `AUDIO`
Path to an audio file (mp3, flac, m4a/mp4, ogg/opus, wav, ...) **or a
directory**. When it's a directory, every audio file in it is processed in
batch mode (see below).

### `--lrclib-link URL`
Fetch lyrics directly from an LRCLIB song link instead of from an audio file.
The numeric track ID is read from the URL (e.g. `https://lrclib.net/song/12345`,
`/tracks/10194812`, `/lyrics/12345`, or `/api/get/12345`) and fetched via
LRCLIB's `GET /api/get/{id}` endpoint. No audio file or metadata is needed —
the track/artist/album come from the fetched record. The output `.lrc` is named
after the track title (override with `--out`). Translation and romanization
options work as usual.

```bash
./run.sh --lrclib-link https://lrclib.net/song/12345
./run.sh --lrclib-link "https://lrclib.net/song/12345" --translate --target-lang en
```

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

### `--prefer-embedded` / `--prefer-external`
Controls which source wins when both embedded lyrics and an external match
exist. Mutually exclusive.

Default priority:
1. embedded lyrics, if synced
2. provider synced lyrics (LRCLIB, NetEase or QQ Music)
3. provider plain-text match
4. embedded plain-text lyrics (marked unsynced)
5. error — no lyrics available

`--prefer-embedded` moves embedded lyrics ahead of any external result;
`--prefer-external` does the reverse.

### `--provider lrclib | netease | qqmusic | auto`
Select the lyrics source. Default: `lrclib` (or the `LYRICS_PROVIDER` env var).

- **`lrclib`** — [LRCLIB](https://lrclib.net), free, best coverage for Western music.
- **`netease`** — [NetEase Cloud Music](https://music.163.com), free, strong coverage for CJK music (Chinese, Japanese, Korean).
- **`qqmusic`** — [QQ Music](https://y.qq.com), free, the widest Chinese catalogue (e.g. Jay Chou is QQ-only) and good K-pop/J-pop coverage.
- **`auto`** — asks LRCLIB, then NetEase, then QQ Music, and keeps the best
  verified match (synced beats plain, then highest confidence). A synced
  match with confidence ≥ 0.9 ends the search early, so most Western tracks
  still cost a single LRCLIB request.

### `--min-confidence 0-1`
Reject external matches below this confidence. Default `0.6` (or the
`LYRICS_MIN_CONFIDENCE` env var). Raise it to be stricter, lower it if a
correct song keeps being rejected.

### How matches are verified

Search results are never trusted blindly. Every candidate from every provider
goes through the same checks before its lyrics are used:

- **Title** — compared after normalisation (case, full-width characters,
  `feat.` clauses, and neutral qualifiers such as `(Remastered 2011)`,
  `- Single` or a bracketed translation are ignored). Similarity must be ≥ 0.75.
- **Version** — a candidate marked *Live*, *Remix*, *Acoustic*,
  *Instrumental*, *Karaoke*, *Cover*, *Sped Up*, *Nightcore*, `伴奏`, `翻唱`,
  `女声版`, … is rejected unless the file's own title has the same marker. A
  language version (`English ver.`) must match too.
- **Duration** — more than 10 s off from the file means a different cut and is
  rejected; within 2 s scores full marks.
- **Artist** — must match (collaborations and bracketed aliases such as
  `周杰伦 (Jay Chou)` count). Names in different scripts are compared through
  romanisation (`Kenshi Yonezu` ≈ `よねづ けんし`). If that still fails, the
  match is only accepted when title *and* duration match tightly, and it is
  capped at confidence 0.85. Skipped when the artist was guessed from the
  filename.
- **Lyrics** — credit lines (`作词 :`, `Lyrics by:`, NetEase JSON credits),
  copyright notices and a leading `Title - Artist` line are stripped. Lyrics
  whose timestamps run past the end of the track are rejected, and "pure
  music" placeholders are reported as instrumental. Translated or romanised
  lyric tracks are never used in place of the original.

Confidence is a weighted score of title, artist, duration and album
agreement. The log shows the chosen record:

```
[audio2lrc] source: y.qq.com (synced, 40 lines)
[audio2lrc] matched: "晴天" by 周杰伦 (4:29), confidence 1.00
```

When nothing passes, the error lists the closest candidate from each
provider and why it was rejected (for example
`music.163.com: closest result "Song (Live)" by Artist (5:29): version mismatch (live)`).

---

## Configuration (translation backends)

Copy `.env.example` to `.env` (auto-loaded from the working directory or your
home directory) or export the variables directly.

### `TRANSLATOR_BACKEND` (default `google`)
- **`google`** — free endpoint, no key required. Default.
- **`libretranslate`** — self-hosted instance or libretranslate.com.
- **`openai`** — any OpenAI-compatible chat API (custom endpoints/LLMs).
- **`gemini`** — Google's Gemini API for text translation (default: `gemini-flash-lite-latest`).

You can also pick a backend per run with `--translator BACKEND` and pass its
key with `--api-key KEY` (overrides the env variables).

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

### Gemini
```
TRANSLATOR_BACKEND=gemini
GEMINI_API_KEY=...                                        # required
GEMINI_MODEL=gemini-flash-lite-latest                             # default
GEMINI_TPM=20000                                          # tokens/minute budget
GEMINI_RPM=28                                            # requests/minute ceiling
```

The backend paces itself against both quota dimensions: lyric lines are split
into requests sized to fit the token budget, each request waits until the
trailing 60s window has room under the **tokens/minute** limit *and* the
**requests/minute** ceiling (actual `usageMetadata` token counts are recorded),
and 429 responses are retried with backoff honoring `Retry-After`. The 28 RPM
default is conservative for the flash-lite free tier (~15-30 RPM); raise
`GEMINI_TPM`/`GEMINI_RPM` if you have a paid tier with higher limits.

> **Note:** "Live Translate" models (`gemini-3.5-live-translate-*`) are
> speech-to-speech only — they accept audio via the Live API and cannot
> translate text, so requests to them over `generateContent` fail with 404.
> Stick to text models like `gemini-flash-lite-latest`.

### Misc
```
LRCLIB_URL=https://lrclib.net   # override the lyrics API base
NETEASE_URL=https://music.163.com  # override the NetEase API base
QQMUSIC_URL=https://c.y.qq.com  # override the QQ Music API base
CACHE_DIR=~/.cache/audio2lrc    # override the lyrics cache location
A2LRC_THEME=opencode          # TUI theme: opencode | system | one-dark | tokyonight | catppuccin | nord | gruvbox
```

### Lyrics source
```
LYRICS_PROVIDER=lrclib   # lrclib | netease | qqmusic | auto
LYRICS_MIN_CONFIDENCE=0.6  # reject external matches below this confidence
```

---

## Rate limits

The app respects the rate limits of every external service it uses.  Lyrics
lookups are **cached on disk** so re-runs for the same track never hit the
network again.

| Service | Rate limit | API key? | Notes |
|---|---|---|---|
| **LRCLIB** | ~20 req/s (soft) | No | Returns `429` + `Retry-After` header when exceeded. |
| **NetEase Cloud Music** | ~1–2 req/s (undocumented) | No | Returns `429` when exceeded. May throttle non-Chinese IPs. |
| **QQ Music** | Undocumented | No | Unofficial endpoints; the desktop search API may refuse requests, in which case the legacy search is used. |
| **Google Translate** (free endpoint) | Undocumented; ~100 chars/s per IP | No | Unofficial endpoint, no SLA; switch backends if throttled. |
| **Gemini** | 15 RPM / 250K TPM / 1K RPD (free tier, `gemini-flash-lite-latest`) | Yes | App defaults to 28 RPM / 20K TPM via env vars. 429s retried with backoff. |
| **OpenAI-compatible** | Varies by model & tier (e.g. GPT-4o mini: 500 RPM / 200K TPM at Tier 1) | Yes | Limits are per-organization, not per-key. |
| **LibreTranslate** (managed) | 20 RPM sustained, 80 RPM burst (Pro tier) | Optional | Self-hosted: fully configurable by admin. |

- **LRCLIB** — the public instance (`lrclib.net`) enforces a generous soft
  limit.  When exceeded the server returns `429 Too Many Requests` with a
  `Retry-After` header.  The app caches responses on disk at
  `~/.cache/audio2lrc/` so the same song is only looked up once.

- **NetEase Cloud Music** — uses unofficial web API endpoints
  (`music.163.com/api/...`).  No official rate limit is published; community
  reports suggest ~1–2 requests/second before throttling.  High-volume
  scraping may result in IP bans.  The app caches responses on disk and only
  fetches lyrics for matched candidates (up to 5 per song).

- **QQ Music** — uses unofficial web endpoints (`u.y.qq.com` search,
  `c.y.qq.com` lyrics). No published limits; like NetEase, results are cached
  and only verified candidates (up to 5 per song) are fetched.

- **Google Translate** (free) — the unofficial `translate.googleapis.com`
  endpoint has no documented rate limit.  It is best-effort; if you hit `429`
  errors, wait a moment or switch to another translation backend.

- **Gemini** — the free tier allows 15 RPM / 250K TPM / 1,000 RPD for
  `gemini-flash-lite-latest`.  The app self-paces using configurable
  `GEMINI_TPM` (default 20,000) and `GEMINI_RPM` (default 28) env vars.
  429 responses are retried with exponential backoff honoring `Retry-After`.

- **OpenAI** — limits depend on your usage tier and model.  Check your
  current limits at <https://platform.openai.com/settings/limits>.

- **LibreTranslate** — the managed service at libretranslate.com enforces
  tier-based limits.  Self-hosted instances are fully configurable via
  `--req-limit`.

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
2. **Resolves lyrics** using the priority above. With `--lrclib-link` (or the
   TUI link mode) it skips the file entirely and fetches the record by its
   LRCLIB track ID.
3. **Translates** (only with `--translate`): batches all lines in one call;
   if the response line count mismatches, retries per-line. Section markers
   (`[Chorus]`, `[Instrumental]`, ...) and empty lines pass through unchanged.
   Lines the backend leaves identical are not duplicated in the output. If no
   line can be translated at all, the run fails with an error and nothing is
   written. Timestamps are never shifted.
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
| `error: no lyrics found` | The file is untagged or has no embedded lyrics and the lyrics source has no match. `--prefer-embedded` can help for files with embedded lyrics. Try `--provider auto` to search LRCLIB, NetEase and QQ Music. The error lists why each provider's closest result was rejected. |
| A correct song is rejected | Check the reason in the error. Fix the file's tags (title/artist), or lower `--min-confidence`. Tags in a different script from the provider (romaji vs kanji) only match when title and duration agree closely. |
| Wrong lyrics were written | Run with a higher `--min-confidence` (e.g. `0.8`); the log's `matched:` line shows which record was used. Delete the matching file in `~/.cache/audio2lrc/` to force a fresh lookup. |
| `low confidence: guessed artist/title from filename` | File has no ID3/Vorbis tags; rename it `Artist - Title.ext` for the best guess. |
| Translation fails / no output | Check the backend config in `.env` (see above). `TRANSLATOR_BACKEND=google` works without any key. If you get `429 Too Many Requests`, the translation backend is rate-limiting you — wait a while or switch backends. When nothing can be translated, the app reports an error and writes **no** `.lrc` (it never writes duplicate lines). |
| NetEase returns no lyrics | NetEase may throttle or block non-Chinese IPs. Try `--provider lrclib` or `--provider auto`. You can also set `NETEASE_URL` to a proxy. |
| `gemini ... 404 Not Found` | The configured `GEMINI_MODEL` doesn't support text `generateContent` (e.g. Live Translate models are audio-only). Set `GEMINI_MODEL=gemini-flash-lite-latest`. |
| `--target-lang` errors | `--translate` requires `--target-lang`, e.g. `--target-lang en`. |
| `--out` rejected | `--out` only works for single files, not in batch (directory) mode. |
| `not a valid LRCLIB link` | The `--lrclib-link` (or TUI link mode) couldn't find a numeric track ID. Use a `https://lrclib.net/song/<id>` or `https://lrclib.net/tracks/<id>` style URL; see [Usage in detail](#usage-in-detail). |
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
uv run pytest           # full test suite
```

- Tests live in `tests/` and cover tag extraction (mp3/flac/m4a), LRC
  parsing/writing, resolution priority rules, LRCLIB caching, LRCLIB-link
  parsing/fetching, theme palettes, batch-translation fallback and the CLI.
- The detailed design notes are in [audio2lrc-spec.md](audio2lrc-spec.md).

## License

[MIT](LICENSE)