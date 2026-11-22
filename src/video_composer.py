"""FFmpeg: ghép nền + lớp UI/Robot/phụ đề + giọng đọc + SFX chuyển cảnh + nhạc nền -> output.mp4"""
import subprocess
from pathlib import Path
import wave
import numpy as np

from ui_renderer import iter_frames

FPS = 30
SR = 44100


def _make_sfx_track(timeline, workdir):
    """Sinh track SFX nhẹ (whoosh đầu mỗi cảnh + pop nhẹ khi robot bay tới waypoint)."""
    total = timeline["total"]
    n = int(total * SR)
    buf = np.zeros(n, dtype=np.float32)

    # Tiếng soft-whoosh đầu mỗi cảnh
    for seg in timeline["segments"]:
        s0 = int(seg["start"] * SR)
        dur = int(0.22 * SR)
        if s0 + dur >= n:
            continue
        t = np.arange(dur, dtype=np.float32) / SR
        freq = 260 + 420 * np.exp(-t * 14)
        env = np.sin(np.pi * t / 0.22) ** 1.5
        buf[s0:s0 + dur] += 0.16 * np.sin(2 * np.pi * freq * t) * env

    # Tiếng chime/pop rất êm ở giữa cảnh
    for seg in timeline["segments"]:
        s0 = int((seg["start"] + seg["dur"] * 0.45) * SR)
        dur = int(0.12 * SR)
        if s0 + dur >= n:
            continue
        t = np.arange(dur, dtype=np.float32) / SR
        env = np.exp(-t * 28) * np.minimum(t / 0.004, 1.0)
        buf[s0:s0 + dur] += 0.12 * (np.sin(2 * np.pi * 880 * t) + 0.5 * np.sin(2 * np.pi * 1320 * t)) * env

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


def compose(timeline, bg_path, voice_path, out_path, music_path=None, music_volume=0.11, save_dir=None):
    total = timeline["total"]
    sfx_path = _make_sfx_track(timeline, Path(voice_path).parent)
    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-stream_loop", "-1", "-i", str(bg_path),
           "-f", "image2pipe", "-framerate", str(FPS), "-c:v", "png", "-i", "-",
           "-i", str(voice_path),
           "-i", str(sfx_path)]
    if music_path:
        cmd += ["-stream_loop", "-1", "-i", str(music_path)]
        fc = ("[0:v][1:v]overlay=0:0:format=auto,format=yuv420p[v];"
              f"[2:a]volume=1.35[vo];[3:a]volume=0.25[sfx];[4:a]volume={music_volume}[m];"
              "[vo][sfx][m]amix=inputs=3:duration=first:normalize=0,alimiter=limit=0.96[a]")
    else:
        fc = ("[0:v][1:v]overlay=0:0:format=auto,format=yuv420p[v];"
              "[2:a]volume=1.35[vo];[3:a]volume=0.25[sfx];[vo][sfx]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.96[a]")
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
    return out_path
