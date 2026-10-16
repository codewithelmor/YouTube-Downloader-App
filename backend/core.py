import os
import re
import ssl
import json
import time
import shutil
import subprocess
import difflib
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

# Use the operating system's trusted certificates (fixes CERTIFICATE_VERIFY_FAILED on
# corporate networks/proxies and on Python installs without root certificates).
try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

import yt_dlp
from captions import finalize_captions
from mutagen.id3 import (
    ID3, TIT2, TPE1, TALB, TPE2, TRCK, TPOS, TDRC, TDOR, TSRC, TCON, TBPM,
    TPUB, TCOP, TCMP, TSOP, TXXX, UFID, USLT, SYLT, COMM, WOAS, WOAR, APIC,
)

# ---------------------------------------------------------------------------
# YouTube -> MP3 downloader
# Takes a YouTube video or playlist link, downloads the audio with yt-dlp and converts
# it to MP3 with FFmpeg. No account or API key is needed.
#
# Tags start from what YouTube knows (title, channel, upload date, thumbnail, and the
# artist/album/track fields YouTube Music-style uploads carry) and can then be enriched
# from free, key-less public sources (each one optional and best effort):
#   * Deezer       -> ISRC, BPM, genre, label, UPC/barcode, disc number, explicit flag
#   * iTunes       -> genre, disc/track counts, copyright, 1400x1400 cover art
#   * MusicBrainz  -> MusicBrainz IDs, label, catalog number, genres, original year
#   * LRCLIB       -> plain and time-synced lyrics
# Enrichment only FILLS GAPS: it never overwrites what YouTube provided.
# ---------------------------------------------------------------------------

YOUTUBE_URL_PATTERN = re.compile(
    r'^(?:https?://)?(?:www\.|m\.|music\.)?(?:youtube\.com|youtu\.be|youtube-nocookie\.com)/', re.I)

# Max allowed difference (seconds) between the track and a result on Deezer / iTunes / LRCLIB
META_DURATION_TOLERANCE = 3
# Minimum title/artist similarity (0-1) to accept a match from another service
MATCH_THRESHOLD = 0.8
# Replace the YouTube thumbnail with iTunes' 1400px cover when it is the same album
UPGRADE_COVER = True
ITUNES_COVER_SIZE = 1400

# MusicBrainz asks every client to identify itself. Put your own contact here.
MB_USER_AGENT = 'YouTubeDownloader/1.0 ( your-email@example.com )'


def build_ssl_context():
    """SSL context for the script's own web requests (metadata and cover art downloads)."""
    try:
        import truststore  # noqa: F401 - already injected above; default context uses OS store
        return ssl.create_default_context()
    except ImportError:
        pass
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()

SSL_CONTEXT = build_ssl_context()

# ------------------------------ Events -------------------------------------
# The CLI leaves the listener unset and gets plain console output. A host program
# (the Electron app, via backend.py) installs a listener to receive structured events.

_listener = None
_cancel_event = None


class Cancelled(Exception):
    """Raised inside a download when the host asked to stop."""


def set_listener(fn):
    """Install fn(event_name, data_dict) to receive events, or None for console output."""
    global _listener
    _listener = fn

def emit(event, **data):
    if _listener:
        _listener(event, data)

def log(message):
    """Human-readable status line: printed by the CLI, sent as a 'log' event to a host."""
    if _listener:
        _listener('log', {'message': message.strip()})
    else:
        print(message)

def _check_cancel():
    if _cancel_event is not None and _cancel_event.is_set():
        raise Cancelled()


def sanitize_folder_name(name):
    """Strips characters that are unsafe for folder/file names across OSes."""
    name = re.sub(r'[\\/:*?"<>|]', '', name).strip()
    return name or "Untitled"


# ------------------------------ HTTP helpers --------------------------------

USER_AGENT = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
              '(KHTML, like Gecko) Chrome/124.0 Safari/537.36')

def http_get(url):
    """Fetches a page as text."""
    req = urllib.request.Request(url, headers={
        'User-Agent': USER_AGENT,
        'Accept-Language': 'en-US,en;q=0.9',
    })
    with urllib.request.urlopen(req, timeout=20, context=SSL_CONTEXT) as resp:
        return resp.read().decode('utf-8', errors='replace')

def http_get_json(url, headers=None, allow_404=False):
    """Fetches a JSON document. Returns None on HTTP 404 when allow_404 is set."""
    req_headers = {'User-Agent': USER_AGENT, 'Accept': 'application/json'}
    req_headers.update(headers or {})
    req = urllib.request.Request(url, headers=req_headers)
    try:
        with urllib.request.urlopen(req, timeout=20, context=SSL_CONTEXT) as resp:
            return json.loads(resp.read().decode('utf-8', errors='replace'))
    except urllib.error.HTTPError as e:
        if allow_404 and e.code == 404:
            return None
        raise


# --------------------------- YouTube link handling ---------------------------

def is_youtube_url(url):
    return bool(YOUTUBE_URL_PATTERN.search(url.strip()))

def _clean_channel(name):
    """'Artist - Topic' (auto-generated channels) -> 'Artist'; also drops 'VEVO'."""
    name = re.sub(r'\s*-\s*Topic$', '', name or '').strip()
    return re.sub(r'(?i)\s*vevo$', '', name).strip()

def _split_artists(text):
    return [a.strip() for a in re.split(r',|&|;|\bfeat\.?\b|\bft\.?\b|\bx\b', text or '') if a.strip()]

def _iso_date(upload_date):
    """yt-dlp's YYYYMMDD -> YYYY-MM-DD."""
    d = upload_date or ''
    return f'{d[:4]}-{d[4:6]}-{d[6:8]}' if re.fullmatch(r'\d{8}', d) else ''

def _title_and_artist(info):
    """
    Best (title, [artists]) for a video. Prefers the music fields YouTube Music-style
    uploads carry; otherwise splits an "Artist - Title" video title; otherwise uses the channel.
    """
    if info.get('track') and (info.get('artist') or info.get('creator')):
        return info['track'], _split_artists(info.get('artist') or info.get('creator'))

    title = (info.get('title') or '').strip()
    channel = _clean_channel(info.get('channel') or info.get('uploader'))
    if ' - ' in title:
        artist, _, rest = title.partition(' - ')
        if artist.strip() and rest.strip():
            return rest.strip(), _split_artists(artist)
    return title, [channel] if channel else []

def _thumbnail(info):
    return info.get('thumbnail') or next(
        (t['url'] for t in reversed(info.get('thumbnails') or []) if t.get('url')), None)

def track_from_info(info, **extra):
    """Builds a track dict from yt-dlp info (flat playlist entry or full video info)."""
    title, artists = _title_and_artist(info)
    video_id = info.get('id')
    return make_track(
        video_id, title, artists, info.get('duration'),
        album=info.get('album'),
        track_number=info.get('track_number'),
        release_date=_iso_date(info.get('release_date') or info.get('upload_date')),
        cover_url=_thumbnail(info),
        explicit=(info.get('age_limit') or 0) >= 18 or None,
        **extra,
    )

def fetch_youtube_tracks(url):
    """
    Lists the videos behind a YouTube link without downloading.
    Returns (kind, collection_name_or_None, [track dicts], [heights]) with kind 'video' or 'playlist'.
    Playlist entries come from the flat listing, so they are thin; download_track refines
    each track from the full video info.
    """
    opts = {'quiet': True, 'no_warnings': True, 'extract_flat': 'in_playlist',
            'ignoreerrors': True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url.strip(), download=False)
    if not info:
        raise RuntimeError("YouTube returned nothing for that link.")

    if info.get('_type') != 'playlist':
        return 'video', None, [track_from_info(info)], available_heights(info)

    tracks = []
    for entry in info.get('entries') or []:
        if not entry or not entry.get('id'):
            continue   # deleted / private videos come back empty
        tracks.append(track_from_info(entry))
    return 'playlist', info.get('title') or "Untitled", tracks, []


# ------------------------------ Track objects -------------------------------

def make_track(video_id, title, artists, duration_s, **extra):
    """Builds the track dict used by the rest of the script (missing fields stay empty)."""
    track = {
        # --- core fields (from YouTube) ---
        'artist': ', '.join(artists) or "Unknown Artist",
        'artists': list(artists),
        'primary_artist': artists[0] if artists else "",
        'title': title or "Unknown Title",
        'album': None,
        'album_artist': None,
        'track_number': None,
        'total_tracks': None,
        'disc_number': None,
        'disc_total': None,
        'disc_track_number': None,   # position within its own disc (multi-disc albums)
        'release_date': '',
        'isrc': None,
        'explicit': None,
        'video_id': video_id,
        'video_url': f'https://www.youtube.com/watch?v={video_id}',
        'cover_url': None,
        'duration': duration_s or 0,
        # --- filled by enrichment ---
        'genres': [],
        'bpm': None,
        'label': None,
        'copyright': None,
        'barcode': None,
        'catalog_number': None,
        'original_date': None,
        'artist_sort': None,
        'release_country': None,
        'hires_cover_url': None,
        'lyrics': None,
        'synced_lyrics': None,
        'mb_recording_id': None,
        'mb_release_id': None,
        'mb_release_group_id': None,
        'mb_release_track_id': None,
        'mb_artist_ids': [],
        'deezer_track_id': None,
        'itunes_track_id': None,
        'sources': ['YouTube'],
    }
    track.update({k: v for k, v in extra.items() if v})
    return track

# ------------------------ Matching helpers (enrichment) ---------------------

def _norm(text):
    """Lowercase, accent/punctuation-insensitive form used to compare names."""
    text = unicodedata.normalize('NFKC', text or '').casefold()
    text = re.sub(r'\(.*?\)|\[.*?\]', ' ', text)            # drop (feat. X), [Remastered]
    text = re.sub(r'\b(?:feat|ft|featuring)\b.*$', ' ', text)
    text = re.sub(r'\s[-–—]\s.*$', ' ', text)                # drop " - Remastered 2011" suffixes
    return re.sub(r'[\W_]+', ' ', text).strip()

def _similar(a, b):
    a, b = _norm(a), _norm(b)
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()

def _artist_matches(wanted, found):
    """True if two artist names are close, or one contains the other ('A' in 'A & B')."""
    na, nb = _norm(wanted), _norm(found)
    if not na or not nb:
        return False
    return na in nb or nb in na or _similar(wanted, found) >= MATCH_THRESHOLD

def _duration_ok(track, seconds):
    if not track['duration'] or not seconds:
        return True  # nothing to compare against
    return abs(track['duration'] - seconds) <= META_DURATION_TOLERANCE


# ------------------------------- Deezer -------------------------------------

def deezer_lookup(track):
    """ISRC, BPM, genre, label, UPC, disc number, explicit flag (no key needed)."""
    base = 'https://api.deezer.com'
    data = None

    if track['isrc']:
        data = http_get_json(f"{base}/track/isrc:{track['isrc']}", allow_404=True)
        if data and data.get('error'):
            data = None

    if not data:
        query = f'artist:"{track["primary_artist"]}" track:"{track["title"]}"'
        results = http_get_json(f"{base}/search?q={urllib.parse.quote(query)}&limit=10") or {}
        candidates = []
        for item in results.get('data') or []:
            if _similar(track['title'], item.get('title')) < MATCH_THRESHOLD:
                continue
            if not _artist_matches(track['primary_artist'], (item.get('artist') or {}).get('name')):
                continue
            if not _duration_ok(track, item.get('duration')):
                continue
            album_sim = _similar(track['album'], (item.get('album') or {}).get('title')) if track['album'] else 0
            candidates.append((album_sim, item))
        if not candidates:
            return {}
        best = max(candidates, key=lambda c: c[0])[1]
        data = http_get_json(f"{base}/track/{best['id']}")

    if not data or data.get('error'):
        return {}

    found = {
        'isrc': data.get('isrc'),
        'bpm': data.get('bpm') or None,
        'disc_number': data.get('disk_number') or None,
        'disc_track_number': data.get('track_position') or None,
        'explicit': data.get('explicit_lyrics'),
        'deezer_track_id': data.get('id'),
        'album': (data.get('album') or {}).get('title'),
    }
    album_id = (data.get('album') or {}).get('id')
    if album_id:
        time.sleep(0.2)
        album = http_get_json(f"{base}/album/{album_id}") or {}
        if not album.get('error'):
            found['label'] = album.get('label')
            found['barcode'] = album.get('upc')
            found['genres'] = [g['name'] for g in (album.get('genres') or {}).get('data') or [] if g.get('name')]
            found['release_date'] = album.get('release_date')
            found['album_artist'] = (album.get('artist') or {}).get('name')
            if not track['total_tracks']:
                found['total_tracks'] = album.get('nb_tracks')
    return found


# ------------------------------- iTunes -------------------------------------

def itunes_lookup(track):
    """Genre, disc counts, copyright, and a 1400px cover (no key needed)."""
    term = urllib.parse.quote(f"{track['primary_artist']} {track['title']}")
    results = http_get_json(
        f"https://itunes.apple.com/search?term={term}&media=music&entity=song&limit=15") or {}

    candidates = []
    for item in results.get('results') or []:
        if _similar(track['title'], item.get('trackName')) < MATCH_THRESHOLD:
            continue
        if not _artist_matches(track['primary_artist'], item.get('artistName')):
            continue
        if not _duration_ok(track, (item.get('trackTimeMillis') or 0) / 1000):
            continue
        album_sim = _similar(track['album'], item.get('collectionName')) if track['album'] else 0
        candidates.append((album_sim, item))
    if not candidates:
        return {}

    album_sim, item = max(candidates, key=lambda c: c[0])
    found = {
        'genres': [item['primaryGenreName']] if item.get('primaryGenreName') else [],
        'disc_number': item.get('discNumber'),
        'disc_total': item.get('discCount'),
        'disc_track_number': item.get('trackNumber'),
        'itunes_track_id': item.get('trackId'),
        'album': item.get('collectionName'),
        'album_artist': item.get('collectionArtistName') or item.get('artistName'),
        'total_tracks': item.get('trackCount'),
        'release_date': (item.get('releaseDate') or '')[:10],
        'explicit': (True if item.get('trackExplicitness') == 'explicit'
                     else False if item.get('trackExplicitness') == 'notExplicit' else None),
    }

    # Only swap in the hi-res cover when it is clearly the same album
    artwork = item.get('artworkUrl100')
    same_album = (not track['album']) or album_sim >= MATCH_THRESHOLD
    if UPGRADE_COVER and artwork and same_album:
        size = ITUNES_COVER_SIZE
        found['hires_cover_url'] = re.sub(r'\d+x\d+(bb)?(?=\.\w+$)', f'{size}x{size}bb', artwork)

    # Copyright text only appears on the album lookup
    if item.get('collectionId') and same_album:
        time.sleep(0.2)
        album = http_get_json(f"https://itunes.apple.com/lookup?id={item['collectionId']}") or {}
        for entry in album.get('results') or []:
            if entry.get('wrapperType') == 'collection' and entry.get('copyright'):
                found['copyright'] = entry['copyright']
                break
    return found


# ----------------------------- MusicBrainz ----------------------------------

_last_mb_call = 0.0

def mb_get(path):
    """MusicBrainz request, throttled to its 1 request/second rule."""
    global _last_mb_call
    wait = 1.1 - (time.time() - _last_mb_call)
    if wait > 0:
        time.sleep(wait)
    try:
        return http_get_json(f"https://musicbrainz.org/ws/2/{path}",
                             headers={'User-Agent': MB_USER_AGENT}, allow_404=True)
    finally:
        _last_mb_call = time.time()

def _ranked_names(items):
    """Genre/tag objects -> names, most-voted first."""
    items = sorted(items or [], key=lambda g: g.get('count', 0), reverse=True)
    return [g['name'] for g in items if g.get('name')]

def musicbrainz_lookup(track):
    """MusicBrainz IDs, label, catalog number, barcode, genres, original release date."""
    isrc = track.get('isrc')
    if not isrc:
        return {}

    isrc_result = mb_get(f"isrc/{urllib.parse.quote(isrc)}?fmt=json") or {}
    recordings = isrc_result.get('recordings') or []
    scored = [(_similar(track['title'], r.get('title')), r) for r in recordings]
    scored = [s for s in scored if s[0] >= 0.6]
    if not scored:
        return {}
    recording_stub = max(scored, key=lambda s: s[0])[1]

    recording = mb_get(f"recording/{recording_stub['id']}"
                       f"?inc=artist-credits+releases+release-groups+genres+tags&fmt=json") or {}
    found = {'mb_recording_id': recording_stub['id']}

    credits = [c for c in recording.get('artist-credit') or [] if c.get('artist')]
    found['mb_artist_ids'] = [c['artist']['id'] for c in credits if c['artist'].get('id')]
    if credits:
        found['artist_sort'] = credits[0]['artist'].get('sort-name')
    found['genres'] = _ranked_names(recording.get('genres')) or _ranked_names(recording.get('tags'))

    releases = recording.get('releases') or []
    if not releases:
        return found

    def release_rank(release):
        official = 1 if release.get('status') == 'Official' else 0
        album_sim = _similar(track['album'], release.get('title')) if track['album'] else 0
        date_ok = 1 if track['release_date'] and (release.get('date') or '')[:4] == track['release_date'][:4] else 0
        return (album_sim, official, date_ok)

    release_stub = max(releases, key=release_rank)
    release = mb_get(f"release/{release_stub['id']}"
                     f"?inc=labels+release-groups+genres+recordings+media&fmt=json") or {}

    found['mb_release_id'] = release_stub['id']
    found['album'] = release.get('title') or release_stub.get('title')
    found['barcode'] = release.get('barcode')
    found['release_country'] = release.get('country')
    label_infos = release.get('label-info') or []
    for info in label_infos:
        if (info.get('label') or {}).get('name'):
            found['label'] = info['label']['name']
            found['catalog_number'] = info.get('catalog-number')
            break

    group = release.get('release-group') or {}
    found['mb_release_group_id'] = group.get('id')
    found['original_date'] = group.get('first-release-date')
    if not found['genres']:
        found['genres'] = _ranked_names(release.get('genres')) or _ranked_names(group.get('genres'))

    for medium in release.get('media') or []:
        for entry in medium.get('tracks') or []:
            if (entry.get('recording') or {}).get('id') == recording_stub['id']:
                found['mb_release_track_id'] = entry.get('id')
                break
    return found


# ------------------------------- Lyrics -------------------------------------

LRC_LINE = re.compile(r'\[(\d+):(\d+(?:\.\d+)?)\](.*)')

def parse_synced_lyrics(lrc):
    """'[mm:ss.xx] text' lines -> [(text, milliseconds)] for the SYLT frame."""
    lines = []
    for raw in (lrc or '').splitlines():
        match = LRC_LINE.match(raw.strip())
        if match:
            ms = int((int(match.group(1)) * 60 + float(match.group(2))) * 1000)
            lines.append((match.group(3).strip(), ms))
    return lines

def lrclib_lookup(track):
    """Plain + synced lyrics from LRCLIB (free, no key)."""
    params = {
        'artist_name': track['primary_artist'],
        'track_name': track['title'],
    }
    if track['album']:
        params['album_name'] = track['album']
    if track['duration']:
        params['duration'] = int(round(track['duration']))

    data = http_get_json(f"https://lrclib.net/api/get?{urllib.parse.urlencode(params)}", allow_404=True)

    if not data:  # exact lookup missed; try a looser search
        search = urllib.parse.urlencode({'artist_name': track['primary_artist'], 'track_name': track['title']})
        for item in http_get_json(f"https://lrclib.net/api/search?{search}") or []:
            if _similar(track['title'], item.get('trackName')) >= MATCH_THRESHOLD \
                    and _duration_ok(track, item.get('duration')):
                data = item
                break
    if not data or data.get('instrumental'):
        return {}

    found = {'lyrics': data.get('plainLyrics') or None}
    synced = parse_synced_lyrics(data.get('syncedLyrics'))
    if synced:
        found['synced_lyrics'] = synced
    return found


# ------------------------------ Enrichment ----------------------------------

EMPTY = (None, '', [])

def merge_found(track, found, source):
    """Copies values from an enrichment source into the track, filling gaps only."""
    changed = False
    for key, value in found.items():
        if value in EMPTY:
            continue
        if key == 'genres':
            existing = {g.casefold() for g in track['genres']}
            for genre in value:
                genre = genre.strip()
                if genre and genre.casefold() not in existing:
                    track['genres'].append(genre)
                    existing.add(genre.casefold())
                    changed = True
        elif track.get(key) in EMPTY:
            track[key] = value
            changed = True
    if changed:
        track['sources'].append(source)

def enrich_track(track):
    """Runs every enrichment source; a failing source never stops the others."""
    sources = (
        ('Deezer', deezer_lookup),
        ('iTunes', itunes_lookup),
        ('MusicBrainz', musicbrainz_lookup),   # needs the ISRC, so it runs after Deezer
        ('LRCLIB', lrclib_lookup),
    )
    for name, lookup in sources:
        try:
            found = lookup(track)
        except Exception as e:
            log(f"   ⚠️ {name} lookup skipped: {e}")
            continue
        if found:
            merge_found(track, found, name)
    track['genres'] = track['genres'][:5]
    if not track['track_number'] and track['disc_track_number']:
        track['track_number'] = track['disc_track_number']


# ------------------------------ Album art ----------------------------------

_cover_cache = {}

def download_cover(url):
    """Downloads cover art bytes (cached so albums only fetch their cover once)."""
    if not url:
        return None
    if url not in _cover_cache:
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=20, context=SSL_CONTEXT) as resp:
                _cover_cache[url] = resp.read()
        except Exception as e:
            log(f"   ⚠️ Could not download album art: {e}")
            _cover_cache[url] = None
    return _cover_cache[url]

def pick_cover(track):
    """Hi-res cover when we have a verified one, otherwise the YouTube thumbnail."""
    for url in (track['hires_cover_url'], track['cover_url']):
        cover = download_cover(url)
        if cover:
            return cover
    return None


# ------------------------------ Tagging ------------------------------------

def _year(date_text):
    return (date_text or '')[:4] if re.match(r'^\d{4}', date_text or '') else ''

def write_id3_tags(mp3_path, track, cover_bytes):
    """
    Replaces whatever tags the conversion left behind with clean metadata
    and embeds the album art as the front cover. Returns the list of fields written.
    """
    tags = ID3()  # Fresh tag, so no leftover source-video metadata survives
    written = []

    def add(label, frame):
        tags.add(frame)
        written.append(label)

    def custom(description, value):
        """User-defined TXXX frame (read by Picard, foobar2000, MusicBee, Mp3tag, ...)."""
        if value not in EMPTY:
            tags.add(TXXX(encoding=3, desc=description, text=value if isinstance(value, list) else str(value)))

    # --- the essentials ---
    add('title', TIT2(encoding=3, text=track['title']))
    add('artist', TPE1(encoding=3, text=track['artist']))
    if track['album']:
        add('album', TALB(encoding=3, text=track['album']))
    if track['album_artist']:
        add('album artist', TPE2(encoding=3, text=track['album_artist']))
        if _norm(track['album_artist']) == 'various artists':
            add('compilation', TCMP(encoding=3, text='1'))

    # --- dates ---
    if track['release_date']:
        add('year/date', TDRC(encoding=3, text=track['release_date']))
    if track['original_date']:
        add('original year', TDOR(encoding=3, text=track['original_date']))

    # --- numbering ---
    if track['track_number']:
        # Multi-disc albums: use the number within the disc, as players expect
        multi_disc = (track['disc_total'] or 1) > 1 or (track['disc_number'] or 1) > 1
        if multi_disc and track['disc_track_number']:
            number = str(track['disc_track_number'])
        else:
            number = str(track['track_number'])
            if track['total_tracks']:
                number += f"/{track['total_tracks']}"
        add('track number', TRCK(encoding=3, text=number))
    if track['disc_number']:
        disc = str(track['disc_number'])
        if track['disc_total']:
            disc += f"/{track['disc_total']}"
        add('disc number', TPOS(encoding=3, text=disc))

    # --- classification ---
    if track['genres']:
        add('genre', TCON(encoding=3, text=track['genres']))
    if track['bpm']:
        add('BPM', TBPM(encoding=3, text=str(int(round(track['bpm'])))))
    if track['isrc']:
        add('ISRC', TSRC(encoding=3, text=track['isrc']))
    if track['label']:
        add('label', TPUB(encoding=3, text=track['label']))
    if track['copyright']:
        add('copyright', TCOP(encoding=3, text=track['copyright']))
    if track['artist_sort']:
        add('artist sort', TSOP(encoding=3, text=track['artist_sort']))

    # --- custom fields ---
    if len(track['artists']) > 1:
        custom('ARTISTS', track['artists'])
        written.append('artist list')
    custom('BARCODE', track['barcode'])
    custom('CATALOGNUMBER', track['catalog_number'])
    custom('MusicBrainz Album Release Country', track['release_country'])
    custom('MusicBrainz Album Id', track['mb_release_id'])
    custom('MusicBrainz Release Group Id', track['mb_release_group_id'])
    custom('MusicBrainz Release Track Id', track['mb_release_track_id'])
    custom('MusicBrainz Artist Id', track['mb_artist_ids'])
    custom('YouTube Video Id', track['video_id'])
    custom('Deezer Track Id', track['deezer_track_id'])
    custom('iTunes Track Id', track['itunes_track_id'])
    if track['explicit']:
        custom('EXPLICIT', '1')
        written.append('explicit flag')
    if track['mb_recording_id']:
        add('MusicBrainz recording ID',
            UFID(owner='http://musicbrainz.org', data=track['mb_recording_id'].encode('ascii')))
        written.append('MusicBrainz IDs')

    # --- links ---
    if track['video_url']:
        add('YouTube URL', WOAS(url=track['video_url']))

    # --- lyrics ---
    if track['lyrics']:
        add('lyrics', USLT(encoding=3, lang='XXX', desc='', text=track['lyrics']))
    if track['synced_lyrics']:
        add('synced lyrics', SYLT(encoding=3, lang='XXX', format=2, type=1, desc='',
                                  text=track['synced_lyrics']))

    # --- comment + cover ---
    add('comment', COMM(encoding=3, lang='eng', desc='',
                        text=f"Metadata from: {', '.join(track['sources'])}"))
    if cover_bytes:
        mime = 'image/png' if cover_bytes[:8] == b'\x89PNG\r\n\x1a\n' else 'image/jpeg'
        add('album art', APIC(encoding=3, mime=mime, type=3, desc='Cover', data=cover_bytes))

    tags.save(mp3_path, v2_version=3)  # ID3v2.3 for the widest player compatibility
    return written



# ------------------------------ Downloading --------------------------------

MODE_MP3 = 'mp3'             # audio only, tagged MP3 with cover art
MODE_VIDEO = 'video'         # MP4 video; optionally re-encoded to HEVC (x265) with MP3 audio
MODE_CAPTIONS = 'captions'   # English .srt (+ .txt transcript) only
MODES = (MODE_MP3, MODE_VIDEO, MODE_CAPTIONS)

HEVC_CRF = "23"          # x265 quality: lower = better quality / bigger file (18-28 is sane)
HEVC_PRESET = "medium"   # x265 speed: ultrafast ... medium ... slow ... veryslow

# Resolution caps offered for playlists (each video gets the best height at or below the cap)
RESOLUTION_TIERS = (4320, 2160, 1440, 1080, 720, 480, 360)

_NO_WINDOW = 0x08000000 if os.name == 'nt' else 0   # no console flash from the packaged app
_mode = MODE_MP3

def _progress_hook(d):
    """yt-dlp progress hook: reports download percent and aborts on cancel."""
    _check_cancel()
    if d.get('status') == 'downloading':
        total = d.get('total_bytes') or d.get('total_bytes_estimate')
        if total:
            emit('progress', percent=round(d.get('downloaded_bytes', 0) / total * 100, 1))
    elif d.get('status') == 'finished' and _mode == MODE_MP3:
        # MP3 mode converts straight after the download; video mode reports its own encode
        emit('progress', percent=100.0, converting=True)

def available_heights(info):
    """Distinct video heights (highest first) that a single video offers."""
    heights = {f['height'] for f in (info.get('formats') or [])
               if f.get('height') and f.get('vcodec') not in (None, 'none')}
    return sorted(heights, reverse=True)

def build_format_selector(max_height, prefer_mp4=False):
    """
    yt-dlp format string capped at the chosen resolution (None = best available).
    prefer_mp4: favour H.264/AAC streams, which merge into an MP4 without re-encoding.
    """
    cap = '' if max_height is None else f'[height<={max_height}]'
    selector = f'bestvideo{cap}+bestaudio/best{cap}'
    if prefer_mp4:
        # H.264 plays everywhere; AV1/VP9 in MP4 is the fallback (e.g. above 1080p)
        selector = (f'bestvideo[vcodec^=avc1]{cap}+bestaudio[ext=m4a]/'
                    f'bestvideo[ext=mp4]{cap}+bestaudio[ext=m4a]/' + selector)
    return selector

def build_ydl_opts(bitrate, output_dir, ffmpeg_dir=None, mode=MODE_MP3, max_height=None,
                   captions=False, hevc=False):
    """
    Builds the yt-dlp options dict.
    mp3:      best audio -> MP3 via FFmpegExtractAudio.
    video:    best video+audio merged into a temporary MKV (holds any codec combo YouTube
              serves); encode_mp4() then writes the MP4 with MP3 audio at the chosen bitrate.
              The video stream is copied by default (fast) or re-encoded to HEVC (hevc=True).
    captions: nothing is downloaded except the caption file.
    """
    opts = {
        'outtmpl': os.path.join(output_dir, '%(artist)s - %(title)s.%(ext)s'),
        'quiet': _listener is not None,   # a host gets structured progress instead
        'noprogress': _listener is not None,
        'progress_hooks': [_progress_hook],
        'ignoreerrors': True,
        'postprocessors': [],
    }
    if mode == MODE_CAPTIONS:
        opts.update({'skip_download': True, 'format': 'best', 'ignore_no_formats_error': True})
    elif mode == MODE_VIDEO:
        opts.update({'format': build_format_selector(max_height, prefer_mp4=not hevc),
                     'merge_output_format': 'mkv',
                     'writethumbnail': False, 'modify_chapters': False})
        opts['postprocessors'].append({'key': 'FFmpegMetadata', 'add_metadata': True})
    else:
        opts['format'] = 'bestaudio/best'
        opts['postprocessors'].append(
            {'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': bitrate})

    if mode == MODE_CAPTIONS or captions:
        opts.update({
            'writesubtitles': True,        # manual captions, when the uploader provided them
            'writeautomaticsub': True,     # fall back to auto-generated captions
            'subtitleslangs': ['en', 'en-orig', 'en-US', 'en-GB'],   # not 'en.*': that also matches auto-translations
        })
        opts['postprocessors'].append(
            {'key': 'FFmpegSubtitlesConvertor', 'format': 'srt', 'when': 'before_dl'})
    if ffmpeg_dir:
        opts['ffmpeg_location'] = ffmpeg_dir   # folder holding ffmpeg and ffprobe
    return opts

def _tool(name, ffmpeg_dir=None):
    """Path of ffmpeg/ffprobe: the bundled folder first, then PATH."""
    if ffmpeg_dir:
        for candidate in (name + '.exe', name):
            path = os.path.join(ffmpeg_dir, candidate)
            if os.path.exists(path):
                return path
    return shutil.which(name)

def check_ffmpeg(mode, ffmpeg_dir=None, hevc=False):
    """Returns an error message, or None when FFmpeg is usable for this mode."""
    if mode == MODE_MP3:
        return None   # yt-dlp reports a missing FFmpeg itself
    ffmpeg = _tool('ffmpeg', ffmpeg_dir)
    if not ffmpeg:
        return "FFmpeg was not found. Install it and put it on your PATH."
    if mode == MODE_VIDEO:
        try:
            out = subprocess.run([ffmpeg, '-hide_banner', '-encoders'], capture_output=True,
                                 text=True, check=True, creationflags=_NO_WINDOW).stdout
        except Exception as e:
            return f"Could not query FFmpeg encoders: {e}"
        wanted = ('libx265', 'libmp3lame') if hevc else ('libmp3lame',)
        missing = [enc for enc in wanted if enc not in out]
        if missing:
            return (f"Your FFmpeg build is missing required encoder(s): {', '.join(missing)}. "
                    "Install a full FFmpeg build.")
    return None

def encode_mp4(source_path, audio_kbps, duration, ffmpeg_dir=None, hevc=False):
    """
    Writes the downloaded file as an MP4 with MP3 audio at audio_kbps. The video stream is
    copied unchanged, or re-encoded to x265 (HEVC) when hevc is set. Then removes the temporary source. Emits 'progress' events and honours cancellation.
    Returns the final file path.
    """
    base = os.path.splitext(source_path)[0]
    final_path = base + '.mp4'
    temp_path = base + '.hevc-temp.mp4'

    cmd = [
        _tool('ffmpeg', ffmpeg_dir), '-y', '-hide_banner', '-loglevel', 'error',
        '-nostdin', '-progress', 'pipe:1', '-nostats',
        '-i', source_path,
        '-map', '0:v:0', '-map', '0:a:0?',
        '-map_metadata', '0',
        *(['-c:v', 'libx265', '-crf', HEVC_CRF, '-preset', HEVC_PRESET,
           '-tag:v', 'hvc1']                   # makes HEVC-in-MP4 playable on Apple devices
          if hevc else ['-c:v', 'copy']),
        '-c:a', 'libmp3lame', '-b:a', f'{audio_kbps}k', '-ac', '2',
        '-movflags', '+faststart',
        temp_path,
    ]
    if hevc:
        log(f"   🎞️ Encoding to HEVC/x265 (CRF {HEVC_CRF}, preset {HEVC_PRESET}) + MP3 {audio_kbps}kbps; this can take a while...")
    else:
        log(f"   🎞️ Writing MP4 (video copied) + MP3 {audio_kbps}kbps...")
    emit('progress', percent=0.0, converting=True)

    # stdin must not be inherited: for the Electron app it carries the 'cancel' command
    proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True,
                            encoding='utf-8', errors='replace', creationflags=_NO_WINDOW)
    errors = []
    try:
        for line in proc.stdout:
            _check_cancel()
            line = line.strip()
            if line.startswith('out_time_us='):
                value = line.split('=', 1)[1]   # microseconds; 'N/A' until output starts
                if value.isdigit() and duration:
                    percent = min(99.9, round(int(value) / 1e6 / duration * 100, 1))
                    emit('progress', percent=percent, converting=True)
            elif line and '=' not in line:
                errors.append(line)
        proc.wait()
    except BaseException:
        proc.kill()
        proc.wait()
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise

    if proc.returncode != 0:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise RuntimeError("FFmpeg failed while encoding the video. " + ' '.join(errors[-3:]))

    if os.path.exists(source_path) and os.path.abspath(source_path) != os.path.abspath(final_path):
        os.remove(source_path)
    os.replace(temp_path, final_path)
    emit('progress', percent=100.0, converting=True)
    return final_path

def locate_downloaded_file(ydl, info):
    """Finds the file yt-dlp just wrote for this video."""
    downloads = info.get('requested_downloads') or []
    if downloads and downloads[0].get('filepath') and os.path.exists(downloads[0]['filepath']):
        return downloads[0]['filepath']
    base = os.path.splitext(ydl.prepare_filename(info))[0]
    for ext in ('.mkv', '.mp4', '.webm'):
        if os.path.exists(base + ext):
            return base + ext
    return None

def download_track(ydl, track, enrich=True, mode=MODE_MP3, captions=False,
                   bitrate='192', ffmpeg_dir=None, hevc=False):
    """
    Downloads one video in the chosen mode. mp3: MP3 plus (optional) enrichment, ID3 tags and
    cover. video: MP4 with MP3 audio (video stream re-encoded to HEVC only when hevc=True). captions: just the English .srt/.txt. captions=True adds the
    captions next to an mp3/video download.
    """
    _check_cancel()
    info = ydl.extract_info(track['video_url'], download=False)
    if info is None:
        raise RuntimeError("could not retrieve the video")

    # Full video info is richer than the flat playlist listing: refine the tags from it
    full = track_from_info(info)
    for key, value in full.items():
        if key in ('sources', 'video_id', 'video_url'):
            continue
        if value not in EMPTY and (track.get(key) in EMPTY or key in ('title', 'artist', 'artists',
                                                                       'primary_artist', 'duration')):
            track[key] = value

    # The refined values drive the filename template: "<artist> - <title>.<ext>"
    info['artist'] = track['artist']
    info['title'] = track['title']

    ydl.process_info(info)
    base = os.path.splitext(ydl.prepare_filename(info))[0]

    if mode == MODE_CAPTIONS or captions:
        try:
            caption_path, notes = finalize_captions(base)
        except Exception as e:
            caption_path, notes = None, [f"Could not finalize captions: {e}"]
        for note in notes:
            log(f"   💬 {note}")
        if mode == MODE_CAPTIONS:
            if not caption_path:
                raise RuntimeError("no English captions available")
            return

    if mode == MODE_VIDEO:
        source_path = locate_downloaded_file(ydl, info)
        if not source_path:
            raise RuntimeError("download finished but the output file could not be found")
        final_path = encode_mp4(source_path, bitrate, track['duration'], ffmpeg_dir, hevc)
        log(f"   ✅ Saved: {final_path}")
        return

    mp3_path = base + '.mp3'
    if not os.path.exists(mp3_path):
        raise RuntimeError("MP3 conversion did not produce a file (is FFmpeg installed?)")

    if enrich:
        log("   🔎 Gathering extra metadata (Deezer, iTunes, MusicBrainz, lyrics)...")
        enrich_track(track)

    written = write_id3_tags(mp3_path, track, pick_cover(track))
    log(f"   🏷️  Tagged: {', '.join(written)}")

def preview_youtube(url):
    """
    Reads a YouTube link without downloading. Returns {'kind', 'name', 'tracks': [...],
    'heights': [...]} (heights: resolutions a single video offers, highest first; empty for
    playlists). Raises ValueError for a bad link and RuntimeError when YouTube can't be read.
    """
    if not is_youtube_url(url):
        raise ValueError("That doesn't look like a YouTube video or playlist link.")
    try:
        kind, name, tracks, heights = fetch_youtube_tracks(url)
    except Exception as e:
        raise RuntimeError(f"Could not read that YouTube link: {e} "
                           "(Check the link and your connection. Private videos and playlists "
                           "can't be read.)") from e
    return {'kind': kind, 'name': name, 'tracks': tracks, 'heights': heights}

def download_youtube(url, bitrate, output_dir, enrich=False, ffmpeg_dir=None,
                     cancel=None, video_ids=None, mode=MODE_MP3, max_height=None,
                     captions=False, hevc=False):
    """
    Handles YouTube video and playlist links.
    bitrate: MP3 kbps (also the audio of a video download).
    hevc: re-encode the video stream to HEVC/x265 (much slower; default copies it).
    mode: MODE_MP3, MODE_VIDEO or MODE_CAPTIONS. max_height: resolution cap for video
          (None = best available). captions: also save English captions with mp3/video.
    cancel: optional threading.Event; set it to stop after/within the current video.
    video_ids: optional collection of video ids; only those videos are downloaded.
    Returns {'ok': [label, ...], 'failed': [{'track': label, 'error': msg}], 'folder': path,
             'cancelled': bool, 'error': msg-or-None}.
    """
    global _cancel_event, _mode
    _cancel_event = cancel
    _mode = mode
    summary = {'ok': [], 'failed': [], 'folder': output_dir, 'cancelled': False, 'error': None}

    problem = check_ffmpeg(mode, ffmpeg_dir, hevc)
    if problem:
        log(f"❌ {problem}")
        summary['error'] = problem
        return summary

    try:
        preview = preview_youtube(url)
    except (ValueError, RuntimeError) as e:
        log(f"❌ {e}")
        summary['error'] = str(e)
        return summary

    kind, name, tracks = preview['kind'], preview['name'], preview['tracks']
    if video_ids is not None:
        wanted = set(video_ids)
        tracks = [t for t in tracks if t['video_id'] in wanted]

    total = len(tracks)
    if total == 0:
        log("⚠️ No downloadable videos were found.")
        summary['error'] = "No downloadable videos were found."
        return summary

    target_dir = output_dir
    if name:
        target_dir = os.path.join(output_dir, sanitize_folder_name(name))
        os.makedirs(target_dir, exist_ok=True)
        log(f"\n📃 YouTube {kind} detected: \"{name}\" ({total} video(s))")
        log(f"📁 Saving to: {target_dir}")
    summary['folder'] = target_dir
    emit('start', kind=kind, name=name, total=total, folder=target_dir)

    ydl_opts = build_ydl_opts(bitrate, target_dir, ffmpeg_dir, mode, max_height, captions, hevc)

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        for index, track in enumerate(tracks, start=1):
            if cancel is not None and cancel.is_set():
                summary['cancelled'] = True
                break
            label = f"{track['artist']} - {track['title']}"
            log(f"\n[{index}/{total}] Processing: {label}")
            emit('track_start', index=index, total=total, label=label)
            try:
                download_track(ydl, track, enrich=enrich, mode=mode, captions=captions,
                               bitrate=bitrate, ffmpeg_dir=ffmpeg_dir, hevc=hevc)
                summary['ok'].append(label)
                emit('track_done', index=index, label=label)
            except Cancelled:
                summary['cancelled'] = True
                break
            except Exception as e:
                log(f"❌ Skipped \"{label}\" due to an error: {e}")
                summary['failed'].append({'track': label, 'error': str(e)})
                emit('track_error', index=index, label=label, error=str(e))

    if summary['cancelled']:
        log(f"\n⏹️ Cancelled. {len(summary['ok'])}/{total} saved to: {target_dir}")
    else:
        log(f"\n🎉 Download complete! {len(summary['ok'])}/{total} saved to: {target_dir}")
    _cancel_event = None
    return summary
