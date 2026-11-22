"""CLI: script.json -> output.mp4

Dùng:  python src/render_video.py samples/sample_script.json -o output/output.mp4
"""
import argparse
import json
import random
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bg_generator  # noqa: E402
import music_generator  # noqa: E402
import tts_engine  # noqa: E402
import video_composer  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PAD = 0.18  # giây nghỉ gọn cuối mỗi cảnh


def build_segments(script):
    segs = [dict(type="hook", data=script["hook"], voiceover=script["hook"]["voiceover"])]
    for s in script["scenes"]:
        segs.append(dict(type=s["type"], data=s, voiceover=s["voiceover"]))
    segs.append(dict(type="cta", data=script["cta"], voiceover=script["cta"]["voiceover"]))
    return segs


def pick_music(explicit):
    if explicit:
        return Path(explicit)
    music_generator.ensure_music()
    files = sorted((ROOT / "assets" / "music").glob("*.mp3"))
    return random.choice(files) if files else None


def render(script, out_path, music=None, frames_dir=None, frame_ids=()):
    theme = script.get("bg_theme", "cyber_blue")
    bg = bg_generator.generate(theme)
    voice = script.get("voice", tts_engine.DEFAULT_VOICE)
    rate = script.get("voice_rate") or tts_engine.DEFAULT_RATE
    if rate in ("+8%", "+15%"):
        rate = tts_engine.DEFAULT_RATE
    segs = build_segments(script)
    with tempfile.TemporaryDirectory() as tmp:
        t, audios, durs, cid = 0.0, [], [], 0
        for i, s in enumerate(segs):
            a = Path(tmp) / f"tts_{i}.mp3"
            d, chunks = tts_engine.synthesize(s["voiceover"], a, voice, rate)
            for c in chunks:
                c["id"] = cid
                cid += 1
            s.update(start=t, dur=d + PAD, subs=chunks)
            t += d + PAD
            audios.append(a)
            durs.append(d + PAD)
            print(f"[tts] {s['type']:<12} {d:5.1f}s  {len(chunks)} cụm phụ đề")
        timeline = dict(badge=script.get("badge", ""), bg_theme=theme, mascot=script.get("mascot", True),
                        segments=segs, total=t)
        vt = video_composer.build_voice_track(audios, durs, tmp)
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        save = (frames_dir, set(frame_ids)) if frames_dir else None
        video_composer.compose(timeline, bg, vt, out_path, pick_music(music), save_dir=save)
    size = Path(out_path).stat().st_size / 1e6
    print(f"[done] {out_path}  {t:.1f}s  {size:.1f} MB")
    return out_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("script")
    ap.add_argument("-o", "--output", default=str(ROOT / "output" / "output.mp4"))
    ap.add_argument("--music")
    ap.add_argument("--frames-dir", help="lưu vài khung PNG để kiểm tra trực quan")
    ap.add_argument("--frame-ids", default="", help="vd: 20,150,400")
    a = ap.parse_args()
    script = json.loads(Path(a.script).read_text(encoding="utf-8"))
    ids = [int(x) for x in a.frame_ids.split(",") if x]
    if a.frames_dir:
        Path(a.frames_dir).mkdir(parents=True, exist_ok=True)
    render(script, a.output, a.music, a.frames_dir, ids)


if __name__ == "__main__":
    main()
