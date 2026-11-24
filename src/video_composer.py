"""FFmpeg: ghép nền + lớp UI/Robot/phụ đề + giọng đọc + Micro-SFX Choreography + nhạc nền Studio Sidechain Ducking."""
import subprocess
from pathlib import Path
import wave
import numpy as np

from ui_renderer import iter_frames

FPS = 30
SR = 44100


def _add_tone(buf, start_sec, dur_sec, freq_start, freq_end=None, vol=0.14, attack=0.005, decay=18.0, harmonic=0.4):
    """Chèn 1 hiệu ứng âm thanh ngắn (chirp/ding/pop) vào buffer tại đúng mốc thời gian."""
    n = len(buf)
    s0 = int(start_sec * SR)
    dur = int(dur_sec * SR)
    if s0 < 0 or s0 + dur >= n or dur <= 0:
        return
    t = np.arange(dur, dtype=np.float32) / SR
    if freq_end is not None and freq_end != freq_start:
        # Nội suy tần số mượt
        inst_f = freq_start + (freq_end - freq_start) * (t / dur_sec)
        phase = 2 * np.pi * np.cumsum(inst_f) / SR
    else:
        phase = 2 * np.pi * freq_start * t
    env = np.exp(-t * decay) * np.minimum(t / max(attack, 0.001), 1.0)
    wave_sig = np.sin(phase) + harmonic * np.sin(phase * 2.0)
    buf[s0:s0 + dur] += vol * wave_sig * env


def _make_sfx_track(timeline, workdir):
    """Thiết kế Micro-SFX khớp từng chuyển động hình ảnh để giữ chân người xem (Audio-Visual Retention):
    1. Opening Hook Riser + Crystal Ding (0.0s -> 0.35s) khi chữ Hook zoom-in.
    2. Soft Transition Whoosh đầu mỗi cảnh.
    3. Typing Keyboard Ticks khi gõ chữ ở chat_demo / prompt_card.
    4. Ascending Melodic Pops (C5 -> E5 -> G5 -> C6) khi từng dòng bảng so sánh / bước / checklist / ranking bật sáng.
    5. Digital Counter Ticks + Reward Chime khi số lớn (10X, 70%) nhảy ở stat_card / cta.
    6. Seamless Loop Bridge Whoosh ở 0.18s cuối video nối mượt về giây 0:00.
    """
    total = timeline["total"]
    n = int(total * SR)
    buf = np.zeros(n, dtype=np.float32)

    # 1) Opening Hook Riser (0.01s -> 0.22s) + Crystal Chime (0.20s)
    _add_tone(buf, 0.01, 0.22, 240.0, 920.0, vol=0.14, attack=0.02, decay=6.0, harmonic=0.25)
    _add_tone(buf, 0.20, 0.28, 1046.5, 1567.98, vol=0.18, attack=0.004, decay=14.0, harmonic=0.5)

    triad_notes = [523.25, 659.25, 783.99, 1046.50]  # C5, E5, G5, C6

    for seg in timeline["segments"]:
        st = seg["start"]
        dur = seg["dur"]
        stype = seg.get("type", "")

        # 2) Soft Whoosh đầu mỗi cảnh
        _add_tone(buf, st, 0.20, 220.0, 540.0, vol=0.13, attack=0.03, decay=11.0, harmonic=0.15)

        # 3) Theo từng loại cảnh UI
        if stype in ("chat_demo", "prompt_card"):
            # Tiếng gõ phím cơ mềm (tock-tock) lúc gõ prompt (12% -> 46% thời lượng cảnh)
            for k in range(8):
                tk_sec = st + dur * (0.12 + k * 0.042)
                _add_tone(buf, tk_sec, 0.025, 1400.0 + (k % 3) * 180.0, 600.0, vol=0.07, attack=0.002, decay=85.0, harmonic=0.2)
            # Tiếng Pop sáng khi thẻ AI Reply / Kết quả bật lên ở 52%
            _add_tone(buf, st + dur * 0.52, 0.16, 880.0, 1318.5, vol=0.15, attack=0.004, decay=22.0, harmonic=0.45)

        elif stype in ("comparison", "bullet_steps", "checklist_card", "ranking_card"):
            # Tiếng Pop nốt nhạc tăng dần (C5 -> E5 -> G5) mỗi khi 1 dòng / 1 bước / 1 hạng bật sáng
            for idx in range(3):
                pop_sec = st + dur * (0.15 + idx * 0.25)
                note = triad_notes[idx % len(triad_notes)]
                _add_tone(buf, pop_sec, 0.14, note, note * 1.25, vol=0.14, attack=0.003, decay=24.0, harmonic=0.4)

        elif stype == "myth_vs_fact":
            # Tiếng Buzz trầm nhẹ ở thẻ Sai lầm ❌ (0.08) + Tiếng Ding xanh sáng ở thẻ Cách làm đúng ✅ (0.48)
            _add_tone(buf, st + dur * 0.08, 0.15, 240.0, 180.0, vol=0.12, attack=0.005, decay=18.0, harmonic=0.6)
            _add_tone(buf, st + dur * 0.48, 0.20, 783.99, 1174.66, vol=0.16, attack=0.004, decay=18.0, harmonic=0.45)

        elif stype in ("stat_card", "cta"):
            # Tiếng Digital Counter Ticks khi số nhảy (0.10s -> 0.65s) + Tiếng Reward Ding khi chốt số (0.68s)
            for k in range(6):
                _add_tone(buf, st + 0.10 + k * 0.09, 0.028, 1050.0 + k * 110.0, None, vol=0.09, attack=0.002, decay=90.0)
            _add_tone(buf, st + 0.68, 0.22, 1174.66, 1567.98, vol=0.16, attack=0.004, decay=16.0, harmonic=0.5)

    # 6) Seamless Loop Bridge Whoosh ở 0.18s cuối cùng của video nối mượt về 0:00
    if total > 1.0:
        _add_tone(buf, total - 0.18, 0.17, 300.0, 760.0, vol=0.14, attack=0.02, decay=9.0, harmonic=0.2)

    pcm = (np.clip(buf, -1.0, 1.0) * 32767).astype(np.int16)
    sfx_path = Path(workdir) / "sfx.wav"
    with wave.open(str(sfx_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(pcm.tobytes())
    return sfx_path


def build_voice_track(seg_audios, durations, workdir):
    """Đệm mỗi đoạn thoại tới đúng thời lượng cảnh rồi nối thành voice.wav."""
    wavs = []
    for i, (a, d) in enumerate(zip(seg_audios, durations)):
        w = Path(workdir) / f"seg_{i}.wav"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(a), "-af", f"apad=whole_dur={d:.3f}",
                        "-t", f"{d:.3f}", "-ar", str(SR), "-ac", "2", str(w)], check=True)
        wavs.append(w)
    lst = Path(workdir) / "concat.txt"
    lst.write_text("".join(f"file '{w.resolve()}'\n" for w in wavs))
    voice = Path(workdir) / "voice.wav"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                    "-c", "copy", str(voice)], check=True)
    return voice


def extract_thumbnail(video_path, thumb_path=None, at_sec=1.2):
    thumb_path = Path(thumb_path or str(Path(video_path).with_suffix(".jpg")))
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error", "-ss", f"{at_sec:.2f}", "-i", str(video_path),
        "-frames:v", "1", "-q:v", "2", str(thumb_path),
    ], check=False)
    return thumb_path if thumb_path.exists() else None


def compose(timeline, bg_path, voice_path, out_path, music_path=None, music_volume=0.24, save_dir=None):
    """Ghép video với nhạc nền ở mức 0.24 (đã có EQ Vocal Pocket + Sidechain Ducking tự hạ xuống khi có tiếng đọc và nổi lên ở khoảng nghỉ)."""
    total = timeline["total"]
    sfx_path = _make_sfx_track(timeline, Path(voice_path).parent)
    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-stream_loop", "-1", "-i", str(bg_path),
           "-f", "image2pipe", "-framerate", str(FPS), "-c:v", "png", "-i", "-",
           "-i", str(voice_path),
           "-i", str(sfx_path)]
    if music_path:
        cmd += ["-stream_loop", "-1", "-i", str(music_path)]
        fc = (
            "[0:v][1:v]overlay=0:0:format=auto,format=yuv420p[v];"
            "[2:a]volume=1.38,asplit=2[vo][sc];"
            "[3:a]volume=0.32[sfx];"
            f"[4:a]volume={music_volume},equalizer=f=1500:t=q:w=1.2:g=-3.5[mraw];"
            "[mraw][sc]sidechaincompress=threshold=0.025:ratio=3.8:attack=12:release=220[m];"
            "[vo][sfx][m]amix=inputs=3:duration=first:normalize=0,alimiter=limit=0.96[a]"
        )
    else:
        fc = ("[0:v][1:v]overlay=0:0:format=auto,format=yuv420p[v];"
              "[2:a]volume=1.38[vo];[3:a]volume=0.32[sfx];"
              "[vo][sfx]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.96[a]")
    cmd += ["-filter_complex", fc, "-map", "[v]", "-map", "[a]", "-t", f"{total:.3f}", "-r", str(FPS),
            "-c:v", "libx264", "-preset", "medium", "-crf", "23", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(out_path)]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    try:
        for i, png in iter_frames(timeline, FPS, save_dir):
            p.stdin.write(png)
            if i % 150 == 0:
                print(f"[compose] {i}/{round(total * FPS)}")
    finally:
        p.stdin.close()
        rc = p.wait()
    if rc != 0:
        raise RuntimeError(f"ffmpeg lỗi (mã {rc})")
    extract_thumbnail(out_path)
    return out_path
