# Demo plan: YouTube Downloader 1.0.0

Date: 2026-10-24 | Owner: Elmor Cabalfin | Status: Draft

## Goal

- **Type:** Quick overview
- **Target length:** 0:45 (allowed range 0:30-1:00)
- **Audience:** People who see the project on GitHub or social media (assumption - change if this is for colleagues or a client)
- **After watching, they should:** Download the installer and try it with their own link
- **Shared on:** README (GitHub) and a LinkedIn post (assumption)

## Story

| Part | What we say | What we show | Seconds |
|---|---|---|---|
| Problem | You found a live performance and want to keep it as a music file. | Title card, then the empty app window | 3 + 5 |
| Solution | Paste the link, pick MP3 at 128 kbps, click Download. | J1 steps 1-4 | 23 |
| Result | A tagged MP3 with title, artist and cover art, ready in seconds. | J1 step 5: Explorer with the file and its details | 8 |
| Call to action | No sign-in needed. Get it from the link below. | End card | 4 |

## Journey

**J1 - Save a YouTube video as an MP3 (128 kbps)**

| Step | Action | Result on screen |
|---|---|---|
| 1 | Paste `https://www.youtube.com/watch?v=Vz2ezV_cvtg` into the link box, click **Load** | Button shows "Loading…", then the list shows one row: cover, "Tumatakbo (Live Performance)", "Mojofly", "4:59" |
| 2 | **Download**: Audio (MP3). **Audio quality**: 128 kbps | Options show MP3 and 128 kbps; output folder is visible |
| 3 | Click **Download** | Row shows "Downloading" then "Converting", progress bars fill |
| 4 | Wait | Row shows "Done", text shows "Finished" and "1 of 1 file(s) saved." |
| 5 | Click **Open folder**, select the file, show its details | `Mojofly - Tumatakbo (Live Performance).mp3`, 4.6 MB, cover art thumbnail, Bit rate 128 kbps, title and artist filled |

**Dry run (2026-10-24, backend only):** the download finished in about 6 seconds. The file is 4.6 MB, 4:59 long, 129 kbps measured, tagged with title, artist, date 2022-05-08, YouTube URL and cover art. This is fast enough to record in one take with no cut.

## Production settings

- App type and driver: Electron desktop app, driven with Playwright (`_electron.launch`), or by hand
- Resolution / fps: 1920×1080 / 30
- Vertical cut: yes, 1080×1920, under 45 s, cropped to the app window
- Voice-over: local text-to-speech, Kokoro-82M voice `am_michael` (American English, male; Apache-2.0, free). Generated with `automation/tts_kokoro.py`
- AI voice disclosure: if TTS is used, add "Voice: text-to-speech" to the end card and the video description
- Music: none (the downloaded song plays for 3 s at the end only if rights allow - see risks)
- Branding: app icon and window title "YouTube Downloader"; no other brand marks
- Captions: .srt + .vtt from the script; burned-in for the vertical cut

## Setup before recording

- Clean desktop, notifications off (Windows Focus), taskbar auto-hide
- Output folder for MP3 set to an empty folder, for example `Music\Demo` (the app remembers one folder per mode)
- Mode set to Audio (MP3), bitrate 128 kbps, Subtitles "None", "Extra metadata for music" off
- Link copied to the clipboard; delete any earlier copy of the MP3 so the app saves a fresh file
- Leave the **Log** panel closed (it shows a yt-dlp warning about a missing JavaScript runtime; downloads still work)

## Risks

- **Copyright and YouTube terms:** the demo downloads a commercial song. Before publishing, get permission from Mojofly or their label, or swap in a video you own or one with a Creative Commons license. Do not play the song in the video without rights.
- YouTube changes can break yt-dlp. Run the dry run again on the recording day.

## Out of scope

- Video (MP4/HEVC), captions-only mode, subtitle languages, playlists, and "Extra metadata for music": real features, but each needs its own scene and would push the demo past 60 s. Good candidates for a 2-minute walkthrough later.
- The CLI (`backend/cli.py`): different audience.
