"""
JSON-lines front end for the Electron app. One JSON object per stdout line:
  {"event": "preview", "kind": ..., "name": ..., "tracks": [...], "heights": [...], "subtitles": [...]}
  {"event": "subtitles", "subtitles": [{"lang", "name", "auto"}, ...]}   (--list-subtitles)
  {"event": "start" | "track_start" | "track_done" | "track_error" | "progress" | "log", ...}
  {"event": "done", "ok": [...], "failed": [...], "folder": ..., "cancelled": bool, "error": ...}
  {"event": "error", "message": ...}
A line "cancel" on stdin stops the download (the host can also just kill the process).
"""
import argparse
import json
import sys
import threading

import core

# Only the fields the UI needs for a track list (the full dict has ~40 keys).
PREVIEW_FIELDS = ('video_id', 'artist', 'title', 'album', 'duration', 'cover_url')


def send(event, **data):
    sys.stdout.write(json.dumps({'event': event, **data}, ensure_ascii=False) + '\n')
    sys.stdout.flush()


def watch_stdin_for_cancel(cancel):
    for line in sys.stdin:
        if line.strip().lower() == 'cancel':
            cancel.set()
            return


def main():
    parser = argparse.ArgumentParser(description='YouTube downloader backend (JSON lines on stdout)')
    parser.add_argument('--url', required=True)
    parser.add_argument('--preview', action='store_true', help='list tracks and exit')
    parser.add_argument('--out', default='.')
    parser.add_argument('--bitrate', default='192', help='MP3 kbps (MP3 kbps, also the audio of a video download)')
    parser.add_argument('--mode', choices=core.MODES, default=core.MODE_MP3)
    parser.add_argument('--max-height', type=int, help='video resolution cap, e.g. 1080 (default: best)')
    parser.add_argument('--hevc', action='store_true', help='re-encode the video stream to HEVC/x265 (slow; default copies it)')
    parser.add_argument('--list-subtitles', action='store_true',
                        help='list the subtitle languages the link offers (union for a playlist) and exit')
    parser.add_argument('--sub-lang', action='append', dest='sub_langs', default=[],
                        help='save subtitles (.srt + .txt) in this language code (repeatable)')
    parser.add_argument('--captions', action='store_true', help='same as --sub-lang en')
    parser.add_argument('--enrich', action='store_true', help='fill gaps from Deezer, iTunes, MusicBrainz, LRCLIB')
    parser.add_argument('--ffmpeg-dir', help='folder containing ffmpeg and ffprobe')
    parser.add_argument('--video-id', action='append', dest='video_ids',
                        help='only download this video id (repeatable)')
    args = parser.parse_args()

    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')

    if args.list_subtitles:
        try:
            if not core.is_youtube_url(args.url):
                raise ValueError("That doesn't look like a YouTube video or playlist link.")
            subtitles = core.fetch_playlist_subtitles(args.url)
        except Exception as e:
            send('error', message=f"Could not read the subtitle languages: {e}")
            return 1
        send('subtitles', subtitles=subtitles)
        return 0

    if args.preview:
        try:
            result = core.preview_youtube(args.url)
        except (ValueError, RuntimeError) as e:
            send('error', message=str(e))
            return 1
        tracks = [{k: t.get(k) for k in PREVIEW_FIELDS} for t in result['tracks']]
        send('preview', kind=result['kind'], name=result['name'], tracks=tracks,
             heights=result['heights'], subtitles=result['subtitles'])
        return 0

    if not args.bitrate.isdigit():
        send('error', message='Bitrate must be a number of kbps.')
        return 1

    cancel = threading.Event()
    threading.Thread(target=watch_stdin_for_cancel, args=(cancel,), daemon=True).start()
    core.set_listener(lambda event, data: send(event, **data))

    sub_langs = list(dict.fromkeys(args.sub_langs + (['en'] if args.captions else [])))
    summary = core.download_youtube(
        args.url, args.bitrate, args.out,
        enrich=args.enrich, ffmpeg_dir=args.ffmpeg_dir,
        cancel=cancel, video_ids=args.video_ids,
        mode=args.mode, max_height=args.max_height, sub_langs=sub_langs, hevc=args.hevc,
    )
    send('done', **summary)
    return 1 if summary['error'] else 0


if __name__ == '__main__':
    sys.exit(main())
