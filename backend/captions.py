"""
Caption post-processing: de-duplicates YouTube's rolling auto-captions in the .srt
and writes a plain-text transcript next to it. Pure file handling: no logging, no printing.
"""
import html
import os
import re
import textwrap

WRITE_TRANSCRIPT_TXT = True   # also write '<video name>.txt' (plain-text transcript) next to the .srt
PARAGRAPH_GAP_MS = 2000      # start a new transcript paragraph after a pause this long...
PARAGRAPH_MAX_CHARS = 500    # ...or once a paragraph reaches roughly this many characters

_TIME_RE = re.compile(r'(\d+):(\d+):(\d+)[,.](\d+)')
_TAG_RE = re.compile(r'<[^>]+>')


def _ts_to_ms(ts):
    h, m, sec, frac = _TIME_RE.match(ts.strip()).groups()
    return ((int(h) * 60 + int(m)) * 60 + int(sec)) * 1000 + int(frac.ljust(3, '0')[:3])


def _ms_to_ts(ms):
    h, rem = divmod(ms, 3600000)
    m, rem = divmod(rem, 60000)
    sec, ms = divmod(rem, 1000)
    return f"{h:02}:{m:02}:{sec:02},{ms:03}"


def parse_srt(path):
    """Reads an .srt into a list of {'start': ms, 'end': ms, 'lines': [text lines]}."""
    with open(path, encoding='utf-8-sig') as f:
        content = f.read().replace('\r\n', '\n')

    cues = []
    for block in re.split(r'\n\s*\n', content.strip()):
        lines = block.split('\n')
        timing_idx = next((i for i, line in enumerate(lines) if '-->' in line), None)
        if timing_idx is None:
            continue

        start_raw, end_raw = lines[timing_idx].split('-->')
        text_lines = []
        for line in lines[timing_idx + 1:]:
            line = html.unescape(_TAG_RE.sub('', line)).strip()
            if line:
                text_lines.append(line)

        cues.append({
            'start': _ts_to_ms(start_raw.split()[0]),
            'end': _ts_to_ms(end_raw.split()[0]),
            'lines': text_lines,
        })
    return cues


def looks_rolling(cues):
    """
    YouTube auto-captions use a 'rolling' style where each cue repeats the previous cue's
    last line. Manual captions don't, so they are left untouched.
    """
    pairs = overlaps = 0
    for prev, cur in zip(cues, cues[1:]):
        if prev['lines'] and cur['lines']:
            pairs += 1
            if set(prev['lines']) & set(cur['lines']):
                overlaps += 1
    return pairs > 0 and overlaps / pairs >= 0.3


def dedupe_rolling_cues(cues):
    """
    Keeps each caption line only the first time it appears, and extends that cue so it stays
    on screen as long as the line was visible in the original rolling cues.
    """
    cleaned = []
    prev_lines = []
    owner = {}  # line text -> index of the cleaned cue that holds it

    for cue in cues:
        lines = cue['lines']
        if not lines:
            prev_lines = []  # screen was cleared; anything that follows is new
            continue

        new_lines = []
        for line in lines:
            if line in prev_lines:
                idx = owner.get(line)
                # Only extend when the cues are back-to-back, not across a long silence
                if idx is not None and cue['start'] - cleaned[idx]['end'] <= 500:
                    cleaned[idx]['end'] = max(cleaned[idx]['end'], cue['end'])
            else:
                new_lines.append(line)

        if new_lines:
            cleaned.append({'start': cue['start'], 'end': cue['end'], 'lines': new_lines})
            for line in new_lines:
                owner[line] = len(cleaned) - 1
        prev_lines = lines

    # Stop each cue where the next one begins so nothing overlaps
    for current, nxt in zip(cleaned, cleaned[1:]):
        if nxt['start'] > current['start'] and current['end'] > nxt['start']:
            current['end'] = nxt['start']

    return cleaned


def write_srt(cues, path):
    with open(path, 'w', encoding='utf-8') as f:
        for i, cue in enumerate([c for c in cues if c['lines']], start=1):
            f.write(f"{i}\n{_ms_to_ts(cue['start'])} --> {_ms_to_ts(cue['end'])}\n")
            f.write("\n".join(cue['lines']) + "\n\n")


def write_transcript(cues, path):
    """Writes the caption text as wrapped plain-text paragraphs, with no timestamps."""
    paragraphs, current, length, last_end = [], [], 0, None

    for cue in cues:
        if not cue['lines']:
            continue
        text = ' '.join(cue['lines'])
        paused = last_end is not None and cue['start'] - last_end >= PARAGRAPH_GAP_MS
        if current and (paused or length >= PARAGRAPH_MAX_CHARS):
            paragraphs.append(' '.join(current))
            current, length = [], 0
        current.append(text)
        length += len(text) + 1
        last_end = cue['end']

    if current:
        paragraphs.append(' '.join(current))

    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n\n'.join(textwrap.fill(re.sub(r'\s+', ' ', p), width=100) for p in paragraphs) + '\n')


def postprocess_captions(srt_path):
    """
    Cleans the .srt in place and writes the transcript. Returns a list of human-readable
    notes about what was done (for the caller to log).
    """
    notes = []
    cues = parse_srt(srt_path)
    if not any(c['lines'] for c in cues):
        return notes

    if looks_rolling(cues):
        cues = dedupe_rolling_cues(cues)
        write_srt(cues, srt_path)
        notes.append("Removed repeated lines from auto-generated captions.")

    if WRITE_TRANSCRIPT_TXT:
        txt_path = os.path.splitext(srt_path)[0] + '.txt'
        write_transcript(cues, txt_path)
        notes.append(f"Transcript saved: {txt_path}")
    return notes


def finalize_captions(base_path, langs):
    """
    yt-dlp saves each caption as '<name>.<lang>.srt'. Keeps the files for the requested
    language codes (named as yt-dlp wrote them) and post-processes each one. base_path is
    the media path without extension. Returns ([saved_srt_paths], [notes]); a note is added
    for every requested language that was not available.
    """
    saved, notes = [], []
    for lang in langs:
        path = f"{base_path}.{lang}.srt"
        if not os.path.exists(path):
            notes.append(f"No '{lang}' subtitles were available for this video.")
            continue
        saved.append(path)
        notes.append(f"Captions saved: {path}")
        notes.extend(postprocess_captions(path))
    return saved, notes
