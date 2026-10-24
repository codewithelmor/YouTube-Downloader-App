# Demo quality check

Video: `exports/youtube-downloader-v1.0.0-overview.mp4` | SHA-256: `267059aee0a2235f362cb08a5fb107a1fe580480e7dd3b358d6de25493c238de` | App version: 1.0.0 | Checked: 2026-10-24

| # | Check | Severity if failed | Result | Notes |
|---|---|---|---|---|
| 1 | Every planned journey is shown from start to finish | High | Pass | J1: paste link, Load, MP3 + 128 kbps, Download, Open folder, file in Explorer |
| 2 | Each journey ends with its result visible for at least 1.5 s | High | Pass | "Finished / 1 of 1 file(s) saved." ~4 s; Explorer details ~8 s |
| 3 | No failed, skipped, or hidden steps; no error dialogs or crashes | High | Pass | Run log: every step `ok`, `JOURNEY PASS` (take 2) |
| 4 | No private data | High | Pass | Paths are `C:\demo\...`; Explorer navigation pane shows only standard folders and drives |
| 5 | No notifications, other apps, bookmarks, or personal browser items | High | Pass | App recorded from the page; Explorer captured as a window region |
| 6 | Captions present (.srt and .vtt), timed, spelled correctly | High | Pass | 13 cues from the script; "128 kbps" written as digits |
| 7 | App version on cards matches the build | High | Pass | v1.0.0 = `app/package.json` |
| 8 | Plays: H.264 High, yuv420p, AAC 48 kHz, faststart | High | Pass | |
| 9 | Resolution and fps as planned (1920×1080 / 30) | Medium | Pass | |
| 10 | Length within plan (± 15%) | Medium | Pass | 47.7 s vs 45 s target (+6%) |
| 11 | Loudness about -16 LUFS, true peak ≤ -1 dB | Medium | Pass | -17.1 LUFS, -1.5 dBTP |
| 12 | Voice matches the screen in each scene (sync) | Medium | Pass | Voice placed at each scene marker + 0.3 s |
| 13 | Pacing: readable typing, clear cursor, holds on results | Medium | Pass | Drawn cursor with click highlight in the app; real cursor in Explorer |
| 14 | No long black or frozen parts (> 6 s) except planned holds | Medium | Note | freezedetect flags 0:18.6-0:25.3 (cursor moves only, settings shown while narration plays). Accepted |
| 15 | Branding consistent | Low | Pass | App icon, #121212 background, #1db954 accent |
| 16 | Title and end card text true; AI voice disclosed | Medium | Pass | "Narration: AI-generated voice (Kokoro text-to-speech)" on end card |
| 17 | Music licensed | High | Pass | No music; the downloaded song is never played |

**Voice:** Kokoro-82M `am_michael` (American English, male; Apache-2.0), local. Speech-to-text check (faster-whisper small.en) matched the script word for word.

**Result:** Pass

**Open risk (not a QC item):** the demo downloads a commercial song (Mojofly - Tumatakbo). Keep the Loom video at owner or workspace visibility unless rights are cleared. Run `market-legal-check` before making it public.
