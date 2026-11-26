"""CLI: script.json -> output.mp4 (Nhấn giọng động Dynamic Prosody theo cảnh + Khớp nhạc nền theo Theme)."""
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
PAD = 0.18
PAD_LAST = 0.0

# Khớp nhạc nền theo đúng màu chủ đề / tâm trạng video (Theme-Matched Soundtrack)
THEME_MUSIC_MAP = {
    "cyber_blue": "tech_pulse.mp3",
    "neon_purple": "future_bass.mp3",
    "emerald_tech": "cyber_chill.mp3",
    "sunset_amber": "lofi_focus.mp3",
    "clean_light": "cyber_chill.mp3",
    "paper_cream": "lofi_focus.mp3",
    "brutal_dark": "future_bass.mp3",
    "warm_editorial": "lofi_focus.mp3",
}

# Hồ sơ hình ảnh theo từng theme để mỗi video có bố cục, phụ đề, nền & mascot khác hẳn nhau
THEME_VISUAL_PROFILE = {
    "clean_light":    dict(visual_style="editorial_light", mascot=False, hook_layout="center_impact"),
    "paper_cream":    dict(visual_style="editorial_light", mascot=False, hook_layout="card_banner"),
    "brutal_dark":    dict(visual_style="neo_brutal",      mascot=False, hook_layout="card_banner"),
    "emerald_tech":   dict(visual_style="terminal_pro",    mascot=False, hook_layout="left_stack"),
    "warm_editorial": dict(visual_style="cinema_clean",    mascot=False, hook_layout="center_impact"),
    "sunset_amber":   dict(visual_style="cinema_clean",    mascot=False, hook_layout="left_stack"),
    "cyber_blue":     dict(visual_style="glass_neon",      mascot=True,  hook_layout="left_stack"),
    "neon_purple":    dict(visual_style="glass_neon",      mascot=True,  hook_layout="card_banner"),
}


def build_segments(script):
    segs = [dict(type="hook", data=script["hook"], voiceover=script["hook"]["voiceover"])]
    for s in script["scenes"]:
        segs.append(dict(type=s["type"], data=s, voiceover=s["voiceover"]))
    segs.append(dict(type="cta", data=script["cta"], voiceover=script["cta"]["voiceover"]))
    return segs


def pick_music(explicit, theme="cyber_blue"):
    if explicit:
        return Path(explicit)
    music_generator.ensure_music()
    music_dir = ROOT / "assets" / "music"
    matched = music_dir / THEME_MUSIC_MAP.get(theme, "")
    if matched.is_file():
        return matched
    files = sorted(music_dir.glob("*.mp3"))
    return random.choice(files) if files else None


def dynamic_rate_for_segment(seg_type, base_rate):
    """Dynamic Prosody (tự nhiên hơn): Hook nhanh vừa (+16%), thân bài & CTA theo base_rate (+12%)."""
    if seg_type == "hook":
        return "+16%"
    return base_rate if base_rate not in ("+22%", "+20%", "+25%") else "+12%"


def render(script, out_path, music=None, frames_dir=None, frame_ids=()):
    theme = script.get("bg_theme", "cyber_blue")
    bg = bg_generator.generate(theme)
    voice = script.get("voice", tts_engine.DEFAULT_VOICE)
    base_rate = script.get("voice_rate") or tts_engine.DEFAULT_RATE
    segs = build_segments(script)
    with tempfile.TemporaryDirectory() as tmp:
        t, audios, durs, cid = 0.0, [], [], 0
        rate_fn = lambda st: dynamic_rate_for_segment(st, base_rate)
        synth_list = tts_engine.synthesize_segments(segs, tmp, voice, rate_fn)
        for i, (s, (a, d, chunks, seg_rate, v_tag)) in enumerate(zip(segs, synth_list)):
            for c in chunks:
                c["id"] = cid
                cid += 1
            pad = PAD_LAST if i == len(segs) - 1 else PAD
            s.update(start=t, dur=d + pad, subs=chunks)
            t += d + pad
            audios.append(a)
            durs.append(d + pad)
            print(f"[tts] {s['type']:<14} {d:5.1f}s ({v_tag}, rate={seg_rate})  {len(chunks)} cụm phụ đề")
        prof = THEME_VISUAL_PROFILE.get(theme, THEME_VISUAL_PROFILE["cyber_blue"])
        visual_style = script.get("visual_style") or prof["visual_style"]
        hook_layout = script.get("hook_layout") or prof["hook_layout"]
        mascot = script["mascot"] if "mascot" in script else prof["mascot"]
        timeline = dict(
            badge=script.get("badge", ""),
            topic=script.get("youtube_title") or script.get("caption", ""),
            bg_theme=theme,
            visual_style=visual_style,
            hook_layout=hook_layout,
            mascot=mascot,
            segments=segs,
            total=t,
        )
        vt = video_composer.build_voice_track(audios, durs, tmp)
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        save = (frames_dir, set(frame_ids)) if frames_dir else None
        video_composer.compose(timeline, bg, vt, out_path, pick_music(music, theme=theme), save_dir=save)
    size = Path(out_path).stat().st_size / 1e6
    print(f"[done] {out_path}  {t:.1f}s  {size:.1f} MB")
    return out_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("script")
    ap.add_argument("-o", "--output", default=str(ROOT / "output" / "output.mp4"))
    ap.add_argument("--music")
    ap.add_argument("--frames-dir")
    ap.add_argument("--frame-ids", default="")
    a = ap.parse_args()
    script = json.loads(Path(a.script).read_text(encoding="utf-8"))
    ids = [int(x) for x in a.frame_ids.split(",") if x]
    if a.frames_dir:
        Path(a.frames_dir).mkdir(parents=True, exist_ok=True)
    render(script, a.output, a.music, a.frames_dir, ids)


if __name__ == "__main__":
    main()
