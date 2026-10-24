"""Make the title and end cards (PNG) and turn each into a short video segment
with a markers.json, so assemble.py places their voice-over like any scene.
Usage: python cards.py   (from this folder)
"""
import json, os, subprocess

DEMO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
APP = os.path.abspath(os.path.join(DEMO, '../../../../app'))
FONT = 'C\\:/Windows/Fonts/segoeui.ttf'
BOLD = 'C\\:/Windows/Fonts/segoeuib.ttf'
BG, TEXT, MUTED, ACCENT = '0x121212', '0xf1f1f1', '0x9a9a9a', '0x1db954'
VERSION = 'v1.0.0'
durations = json.load(open(os.path.join(DEMO, 'audio/durations.json')))
LEAD = 0.3


def esc(s):
    return s.replace('\\', '\\\\').replace(':', '\\:').replace("'", "\\'")


def text(s, font, size, color, y, x='(w-text_w)/2'):
    return f"drawtext=fontfile='{font}':text='{esc(s)}':fontsize={size}:fontcolor={color}:x={x}:y={y}"


def card(name, lines, icon_y=None):
    out = os.path.join(DEMO, 'thumbnail', f'{name}.png')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    vf = ','.join(text(*l) for l in lines)
    if icon_y is not None:
        args = ['-f', 'lavfi', '-i', f'color=c={BG}:s=1920x1080', '-i', os.path.join(APP, 'assets/icon.png'),
                '-filter_complex', f'[1]scale=180:180[i];[0][i]overlay=(W-w)/2:{icon_y},{vf}']
    else:
        args = ['-f', 'lavfi', '-i', f'color=c={BG}:s=1920x1080', '-vf', vf]
    subprocess.run(['ffmpeg', '-v', 'error', '-y', *args, '-frames:v', '1', out], check=True)
    return out


def segment(name, png, seconds):
    d = os.path.join(DEMO, 'recordings', f'card-{name}')
    os.makedirs(d, exist_ok=True)
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-loop', '1', '-t', f'{seconds:.2f}', '-i', png,
                    '-vf', 'fps=30,format=yuv420p', '-c:v', 'libx264', '-crf', '16', os.path.join(d, 'raw.mp4')], check=True)
    json.dump({'scenes': [{'id': name, 'start': 0, 'end': seconds}]}, open(os.path.join(d, 'markers.json'), 'w'), indent=2)


title = card('title', [
    ('YouTube Downloader', BOLD, 96, TEXT, 470),
    ('Links in. Music files out.', FONT, 52, ACCENT, 600),
    (VERSION, FONT, 34, MUTED, 690),
], icon_y=250)
end = card('end', [
    ('Try it', BOLD, 84, TEXT, 380),
    ('github.com/codewithelmor/YouTube-Downloader-App', FONT, 52, ACCENT, 500),
    (f'YouTube Downloader {VERSION}  ·  No sign-in needed', FONT, 36, MUTED, 600),
    ('Narration: AI-generated voice (Kokoro text-to-speech)', FONT, 28, MUTED, 960),
])
segment('title', title, durations['title'] + LEAD + 0.5)
segment('end', end, durations['end'] + LEAD + 1.4)
print('cards and card segments written')
