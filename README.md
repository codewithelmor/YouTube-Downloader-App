# YouTube Downloader

Turn a **YouTube video or playlist link** into any of:

- **Audio**: tagged **MP3** files with embedded cover art.
- **Video**: **MP4** at the resolution you choose (up to 8K, if the video has it). Audio is always MP3 at the bitrate you choose; the video stream is copied by default (fast), or optionally re-encoded to **x265 (HEVC)** for smaller files (much slower).
- **Captions**: `.srt` subtitles in any language the video offers (you pick one or several), plus a plain-text `.txt` transcript for each, on their own or alongside audio/video.

No account or API key required. Use it from the command line or the Electron desktop app.

## How it works

1. `yt-dlp` reads the link (a single video or a whole playlist; playlists get their own subfolder).
2. **Audio**: it downloads the best audio and FFmpeg converts it to MP3. Tags come from YouTube: title, artist (from the music fields, an "Artist - Title" video title, or the channel name, with "- Topic" and VEVO stripped), album when present, upload date, and the thumbnail as cover art. Optional **extra metadata** fills gaps from Deezer, iTunes, MusicBrainz and LRCLIB (genre, BPM, label, ISRC, lyrics, 1400px cover); it is off by default because it matches by artist and title, which can mismatch non-music videos.
3. **Video**: it downloads the best video and audio streams at or below your resolution cap (preferring H.264/AAC, which plays everywhere) and FFmpeg writes them to an MP4 with MP3 audio at your chosen bitrate, copying the video stream unchanged, so it is fast. With **HEVC** on (`--hevc`, or the checkbox in the app) the video is re-encoded to x265 (`hvc1`-tagged so it plays on Apple devices). The temporary source is deleted. Files are named `<artist> - <title>.mp4`.
4. **Captions**: you choose from the languages the video actually offers (uploader-provided, plus YouTube's auto-generated captions, marked auto; machine translations are not listed). For a playlist the list is the union over all its videos, and each video saves the chosen languages it has. Files are named `<video name>.<lang>.srt` (and `.txt`), the form players pick up. Auto-generated captions have YouTube's repeated rolling lines removed. Set `WRITE_TRANSCRIPT_TXT = False` in `backend/captions.py` to skip the `.txt` transcript.

For a single video the resolution list shows what that video actually offers. For a playlist you pick a cap (8K ... 360p) and each video downloads at that height or the best one below it.

## Installation

| Requirement | Notes |
|---|---|
| Python 3.10+ | Required by `truststore` |
| FFmpeg (with FFprobe) | On your `PATH` for CLI use. Video needs `libmp3lame`, and HEVC also `libx265` (checked at start) |
| Node.js | Only for developing or packaging the desktop app |

Install FFmpeg: `brew install ffmpeg` (macOS), `sudo apt install ffmpeg` (Debian/Ubuntu), `winget install Gyan.FFmpeg` (Windows).

```bash
python -m venv venv            # activate it for your shell
pip install -r backend/requirements.txt
```

## Usage

### Command line

```bash
python backend/cli.py
```

You are asked for the YouTube link, what to download (audio, video or captions only), a target folder, then the options that apply: video resolution, MP3 bitrate, which subtitle languages to also save, and (audio) whether to fetch extra metadata.

### Desktop app

```bash
cd app
npm install
npm start          # compiles TypeScript and launches Electron (needs python and ffmpeg on PATH)
npm run typecheck
```

Paste a link, load the list, pick the videos you want, choose what to download (audio, video, captions), the options, and a folder, then download. Cancel stops mid-download. Packaged installers bundle FFmpeg and the backend.

### JSON-lines backend

This is how the Electron app drives Python. Always run it with `-X utf8 -u`.

```bash
python -X utf8 -u backend/backend.py --url <youtube-url> --preview
python -X utf8 -u backend/backend.py --url <youtube-url> --out ./music --bitrate 192 [--mode mp3|video|captions] [--max-height 1080] [--hevc] [--sub-lang <code>]... [--enrich] [--video-id <id>]... [--ffmpeg-dir <dir>]
```

Supported links: `youtube.com/watch?v=...`, `youtu.be/...`, `music.youtube.com/...`, and `youtube.com/playlist?list=...`. Private videos and private playlists cannot be read.

## Building Installers

PyInstaller cannot cross-compile, so build on the OS you are targeting.

| OS | Command | Output in `app/dist/` |
|----|---------|-----------------------|
| Windows | `powershell -ExecutionPolicy Bypass -File scripts\build-all.ps1` | `*Setup*.exe` |
| Linux | `scripts/build-all.sh` | `*.AppImage`, `*.deb` |
| macOS | `scripts/build-all.sh` | `*.dmg` |

Add `-Clean` / `--clean` for a fresh build. Builds are unsigned. Only the Windows build has been verified.

## Project Structure

```text
YouTube-Downloader-App/
├── .agents
│   └── skills
│       └── skill-creator
│           ├── agents
│           │   ├── analyzer.md
│           │   ├── comparator.md
│           │   └── grader.md
│           ├── assets
│           │   └── eval_review.html
│           ├── eval-viewer
│           │   ├── generate_review.py
│           │   └── viewer.html
│           ├── references
│           │   └── schemas.md
│           ├── scripts
│           │   ├── __init__.py
│           │   ├── aggregate_benchmark.py
│           │   ├── generate_report.py
│           │   ├── improve_description.py
│           │   ├── package_skill.py
│           │   ├── quick_validate.py
│           │   ├── run_eval.py
│           │   ├── run_loop.py
│           │   └── utils.py
│           ├── LICENSE.txt
│           └── SKILL.md
├── .claude
│   ├── commands
│   │   └── commit.md
│   ├── skills
│   │   └── app-icon-restyle
│   │       ├── scripts
│   │       │   └── export_icons.py
│   │       └── SKILL.md
│   └── settings.json
├── .github
│   └── workflows
│       └── build.yml
├── app
│   ├── assets
│   │   ├── icons
│   │   │   ├── 128x128.png
│   │   │   ├── 16x16.png
│   │   │   ├── 256x256.png
│   │   │   ├── 32x32.png
│   │   │   ├── 48x48.png
│   │   │   ├── 512x512.png
│   │   │   └── 64x64.png
│   │   ├── icon.ico
│   │   └── icon.png
│   ├── scripts
│   │   └── copy-static.js
│   ├── src
│   │   ├── renderer
│   │   │   ├── index.html
│   │   │   ├── renderer.ts
│   │   │   └── style.css
│   │   ├── main.ts
│   │   ├── preload.ts
│   │   └── types.d.ts
│   ├── package-lock.json
│   ├── package.json
│   └── tsconfig.json
├── backend
│   ├── backend.py
│   ├── captions.py
│   ├── cli.py
│   ├── core.py
│   └── requirements.txt
├── docs
│   └── product
│       └── 10-launch
│           ├── demo
│           │   ├── automation
│           │   │   ├── cards.py
│           │   │   ├── cursor.ps1
│           │   │   ├── explorer.ps1
│           │   │   ├── package-lock.json
│           │   │   ├── package.json
│           │   │   ├── record.js
│           │   │   └── tts_kokoro.py
│           │   ├── captions
│           │   │   ├── youtube-downloader-v1.0.0-overview.srt
│           │   │   └── youtube-downloader-v1.0.0-overview.vtt
│           │   ├── thumbnail
│           │   │   ├── end.png
│           │   │   └── title.png
│           │   ├── demo-plan.md
│           │   ├── edit.json
│           │   ├── qc-report.md
│           │   ├── scenes.json
│           │   └── script.md
│           └── published-links.md
├── scripts
│   ├── build-all.ps1
│   ├── build-all.sh
│   ├── build-backend.ps1
│   ├── build-backend.sh
│   ├── fetch-ffmpeg.ps1
│   ├── fetch-ffmpeg.sh
│   └── update_readme_tree.py
├── .gitattributes
├── .gitignore
├── CLAUDE.md
├── README.md
└── skills-lock.json
```

`core.py` is UI-agnostic: it reports through `log()` and `emit()` and never prints or prompts, so both front ends can share it.



## Video notes

- **HEVC re-encoding is optional and CPU-heavy.** x265 is slow, especially at 4K and 8K. Tune `HEVC_CRF` (lower = better quality, bigger file; 18-28 is sane) and `HEVC_PRESET` (`ultrafast` ... `veryslow`) at the top of the download section in `backend/core.py`.
- **HEVC re-encoding is lossy.** YouTube serves AV1/VP9/H.264, not HEVC, so converting to x265 recompresses the video.
- **Resolution depends on the video.** Many have nothing above 1080p. The cap is never an upscale.
- **MP3 in MP4** plays in VLC, mpv and most modern players, but some Apple/TV apps prefer AAC.
- Video downloads get yt-dlp's metadata (title, artist, date) but not ID3 enrichment or embedded cover art.

## Troubleshooting

- **"Could not read that YouTube link":** check the link and your connection. If every link suddenly fails, update yt-dlp (`pip install -U yt-dlp`); a frozen backend needs a rebuild.
- **"MP3 conversion did not produce a file":** FFmpeg or FFprobe is missing from `PATH`.
- **Wrong artist or title:** for non-music videos the artist is the channel name. Videos titled "Artist - Title" are split automatically.

## Legal Notice

For personal use with content you have the right to download. Downloading may violate YouTube's terms of service or the law in your jurisdiction; you are responsible for how you use this tool. Not affiliated with or endorsed by YouTube, Deezer, Apple or MusicBrainz.

## License

No license file has been added yet. Until one is, all rights are reserved by the author.
