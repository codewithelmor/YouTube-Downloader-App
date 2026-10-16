# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

YouTube video/playlist link -> tagged MP3 files, HEVC MP4 video, or captions in any language the video offers (`--mode mp3|video|captions`, plus repeatable `--sub-lang <code>`; `--captions` = `--sub-lang en`; `--list-subtitles` lists a link's languages, the union for a playlist; `--hevc` re-encodes video to add captions to the others). No credentials: yt-dlp downloads, FFmpeg converts. There are no tests and no linter configured.

Two front ends share one Python core:
- CLI: `python backend/cli.py` (interactive prompts)
- Electron + TypeScript desktop app in `app/`, which spawns the Python backend as a subprocess

## Commands

```bash
pip install -r backend/requirements.txt    # Python 3.10+ (truststore needs it)
python backend/cli.py                      # interactive CLI

# JSON-lines backend, as the Electron app drives it
python -X utf8 -u backend/backend.py --url <youtube-url> --preview
python -X utf8 -u backend/backend.py --url <url> --out <dir> --bitrate 192 [--mode mp3|video|captions] [--max-height 1080] [--hevc] [--sub-lang <code>]... [--enrich] [--video-id <id>]... [--ffmpeg-dir <dir>]

cd app && npm install && npm start         # dev: compiles TS, launches Electron (needs python + system ffmpeg on PATH)
cd app && npm run typecheck                # tsc --noEmit; the only static check available

# Full installer (FFmpeg + PyInstaller backend + electron-builder); output in app/dist/
powershell -ExecutionPolicy Bypass -File scripts\build-all.ps1 [-Clean]   # Windows
scripts/build-all.sh [--clean]                                            # Linux / macOS
```

PyInstaller cannot cross-compile: each OS must build on itself (`.github/workflows/build.yml` does all three). `build-all.*` runs `fetch-ffmpeg` -> `build-backend` -> `npm run dist`, and writes to the git-ignored `build/` (FFmpeg in `build/bin`, frozen backend in `build/backend`), which `app/package.json` `extraResources` copies into the package.

## Architecture

**`backend/core.py`** holds all logic (link parsing, enrichment, ID3 tagging, yt-dlp download, HEVC encode); `backend/captions.py` holds pure caption cleanup (srt de-duplication, transcript) and returns notes for core to `log()`. Pipeline: `fetch_youtube_tracks` (flat listing -> `track_from_info`) -> `download_track` (full video info refines the track dict, yt-dlp download + FFmpeg mp3 -> optional `enrich_track` from Deezer/iTunes/MusicBrainz/LRCLIB, gap-filling only, off by default -> `write_id3_tags`). `download_track` branches on mode: video merges to a temp MKV (prefers H.264/AAC) then `encode_mp4` (video copied, MP3 audio; `--hevc` re-encodes video to x265) (ffmpeg `-progress` parsed into `progress` events, cancel kills ffmpeg); captions-only uses `skip_download`. `check_ffmpeg` verifies libmp3lame (and libx265 with HEVC) up front for video. Tracks are plain dicts from `make_track` (~40 keys).

**The core must stay UI-agnostic.** It reports through `log()` and `emit(event, **data)`. With no listener set (`set_listener`), `log` prints and `emit` is a no-op, which is the CLI mode. `backend.py` installs a listener that serializes events as JSON lines. Cancellation is a `threading.Event` passed to `download_youtube` and checked in the yt-dlp progress hook, so it works mid-download. Do not add `print()`/`input()` to `core.py`; prompts belong in `cli.py`.

**Event contract spans three files.** `backend/backend.py` writes the events (`preview` (also carries `heights` and `subtitles`; a playlist's `subtitles` is empty and comes from `--list-subtitles` as a `subtitles` event), `start`, `track_start`, `progress`, `track_done`, `track_error`, `log`, `done`, `error`), `app/src/types.d.ts` types them (`BackendEvent`, `DoneEvent`), and `app/src/main.ts` and `app/src/renderer/renderer.ts` consume them. Changing an event means updating all of them. `types.d.ts` is deliberately ambient (no imports/exports) so `renderer.ts` compiles to a plain browser script under the CSP in `index.html`; adding an `import`/`export` to the renderer breaks it at runtime (`exports is not defined`).

**Electron process split.** `main.ts` spawns the backend (`python3`/`python backend.py` in dev, `resources/backend/backend[.exe]` when packaged, plus `--ffmpeg-dir resources/bin`), parses stdout lines, and forwards them to the renderer over IPC. `preload.ts` exposes the `Api` interface as `window.api`. Cancel writes `cancel\n` to the backend's stdin, then force-kills after 8s. Compiled output goes to `app/out/` (git-ignored); `npm run build` also copies `index.html` and `style.css` there via `scripts/copy-static.js`.

## Gotchas

- Always run the backend with `-X utf8 -u` (emoji log output, unbuffered stdout); Electron also sets `PYTHONIOENCODING`.
- FFmpeg and FFprobe both must be present; the code only reaches FFmpeg through yt-dlp's `ffmpeg_location` (set from `--ffmpeg-dir`) or PATH.
- `download_youtube` re-fetches the link even after a UI preview, and selected videos are filtered by `video_id` (`--video-id`). `--enrich` is opt-in.
- yt-dlp breaks when YouTube changes; a frozen backend needs a rebuild to pick up a newer yt-dlp. It currently warns that no JS runtime is found, though downloads still work.
- `MB_USER_AGENT` in `core.py` is a placeholder email, and `appId`/`homepage` in `app/package.json` are placeholders.
- On this repo's Windows setup under Node 26, Electron's postinstall silently fails to extract its binary. `build-all.*` repairs it; for plain `npm start` extract the zip from `%LOCALAPPDATA%\electron\Cache` into `node_modules/electron/dist` and write `electron.exe` to `node_modules/electron/path.txt`.
- Linux/macOS packaging scripts and the CI workflow have not been run yet; only the Windows build is verified.
