"""Make one voice-over WAV per scene with Kokoro-82M (Apache-2.0), a free local voice.
Writes audio/<scene>.wav (48 kHz mono, silence trimmed) and audio/durations.json.

Setup (once):  pip install kokoro-onnx soundfile
Model files:   kokoro-v1.0.onnx and voices-v1.0.bin from
               https://github.com/thewh1teagle/kokoro-onnx/releases/tag/model-files-v1.0
Usage:         python tts_kokoro.py --model-dir <folder with the two files> [--voice am_michael] [--speed 1.0]
"""
import argparse, json, os, subprocess
import soundfile as sf
from kokoro_onnx import Kokoro

DEMO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

ap = argparse.ArgumentParser()
ap.add_argument('--model-dir', required=True)
ap.add_argument('--voice', default='am_michael')   # American English, male
ap.add_argument('--speed', type=float, default=1.0)
ap.add_argument('--only', help='comma-separated scene ids')
ap.add_argument('--out', default=os.path.join(DEMO, 'audio'))
args = ap.parse_args()

k = Kokoro(os.path.join(args.model_dir, 'kokoro-v1.0.onnx'), os.path.join(args.model_dir, 'voices-v1.0.bin'))
scenes = json.load(open(os.path.join(DEMO, 'scenes.json'), encoding='utf-8'))['scenes']
os.makedirs(args.out, exist_ok=True)
dur_path = os.path.join(args.out, 'durations.json')
durations = json.load(open(dur_path)) if os.path.exists(dur_path) and args.only else {}
only = set(args.only.split(',')) if args.only else None

for s in scenes:
    if not s.get('voiceover') or (only and s['id'] not in only):
        continue
    text = s.get('spoken', s['voiceover'])   # optional pronunciation-friendly text
    samples, rate = k.create(text, voice=args.voice, speed=args.speed, lang='en-us')
    raw = os.path.join(args.out, f"{s['id']}.raw.wav")
    sf.write(raw, samples, rate)
    out = os.path.join(args.out, f"{s['id']}.wav")
    af = ('silenceremove=start_periods=1:start_threshold=-50dB,areverse,'
          'silenceremove=start_periods=1:start_threshold=-50dB,areverse,adelay=100:all=1,apad=pad_dur=0.15')
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', raw, '-af', af, '-ar', '48000', '-ac', '1', out], check=True)
    os.remove(raw)
    d = float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', out],
                             capture_output=True, text=True).stdout)
    durations[s['id']] = round(d, 2)
    print(f"{s['id']}: {d:.2f}s  {text}")

json.dump(durations, open(dur_path, 'w'), indent=2)
print(f'Voice: Kokoro-82M {args.voice} (Apache-2.0). Disclose as AI-generated narration.')
