"""FFmpeg: ghép nền + lớp UI/Robot/phụ đề + giọng đọc + SFX + nhạc nền có Sidechain Ducking + Thumbnail."""
import subprocess
from pathlib import Path
import wave
import numpy as np

from ui_renderer import iter_frames

FPS = 30
SR = 44100


def _make_sfx_track(timeline, workdir):
    """Sinh track SFX nhẹ (whoosh đầu mỗi cảnh + pop nhẹ khi robot bay tới waypoint + tick ở cảnh có số nhảy)."""
    total = timeline["total"]
    n = int(total * SR)
    buf = np.zeros(n, dtype=np.float32)

    # Opening Hook Chime (0.02s..0.28s): âm thanh mở màn sáng gọn giữ chân người xem trong 0.3s đầu
    hdur = min(int(0.26 * SR), n)
    if hdur > 0:
        ht = np.arange(hdur, dtype=np.float32) / SR
        henv = np.exp(-ht * 14) * np.minimum(ht / 0.005, 1.0)
        buf[:hdur] += 0.20 * (np.sin(2 * np.pi * 1046.5 * ht) + 0.6 * np.sin(2 * np.pi * 1567.98 * ht)) * henv

    for seg in timeline["segments"]:
        s0 = int(seg["start"] * SR)
        dur = int(0.22 * SR)
        if s0 + dur < n:
            t = np.arange(dur, dtype=np.float32) / SR
            freq = 260 + 420 * np.exp(-t * 14)
            env = np.sin(np.pi * t / 0.22) ** 1.5
            buf[s0:s0 + dur] += 0.16 * np.sin(2 * np.pi * freq * t) * env

        # Tiếng tick nhẹ khi số nhảy ở stat_card / cta
        if seg.get("type") in ("stat_card", "cta"):
            for k in range(5):
                tk0 = int((seg["start"] + 0.12 + k * 0.11) * SR)
                tdur = int(0.03 * SR)
                if tk0 + tdur < n:
                    tt = np.arange(tdur, dtype=np.float32) / SR
                    buf[tk0:tk0 + tdur] += 0.09 * np.sin(2 * np.pi * (1100 + k * 90) * tt) * np.exp(-tt * 90)

        # Tiếng chime/pop êm ở giữa cảnh
        s1 = int((seg["start"] + seg["dur"] * 0.45) * SR)
        dur1 = int(0.12 * SR)
        if s1 + dur1 < n:
            t = np.arange(dur1, dtype=np.float32) / SR
            env = np.exp(-t * 28) * np.minimum(t / 0.004, 1.0)
            buf[s1:s1 + dur1] += 0.12 * (np.sin(2 * np.pi * 880 * t) + 0.5 * np.sin(2 * np.pi * 1320 * t)) * env

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
    """Trích xuất khung hình Hook nét nhất (giây 1.2s) làm ảnh bìa thumbnail.jpg."""
    thumb_path = Path(thumb_path or str(Path(video_path).with_suffix(".jpg")))
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error", "-ss", f"{at_sec:.2f}", "-i", str(video_path),
        "-frames:v", "1", "-q:v", "2", str(thumb_path),
    ], check=False)
    return thumb_path if thumb_path.exists() else None


def compose(timeline, bg_path, voice_path, out_path, music_path=None, music_volume=0.18, save_dir=None):
    total = timeline["total"]
    sfx_path = _make_sfx_track(timeline, Path(voice_path).parent)
    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-stream_loop", "-1", "-i", str(bg_path),
           "-f", "image2pipe", "-framerate", str(FPS), "-c:v", "png", "-i", "-",
           "-i", str(voice_path),
           "-i", str(sfx_path)]
    if music_path:
        cmd += ["-stream_loop", "-1", "-i", str(music_path)]
        # Sidechain Ducking: khi có giọng đọc thì nhạc nền tự động dịu xuống, khi chuyển cảnh nhạc nổi lên
        fc = (
            "[0:v][1:v]overlay=0:0:format=auto,format=yuv420p[v];"
            "[2:a]volume=1.35,asplit=2[vo][sc];"
            "[3:a]volume=0.25[sfx];"
            f"[4:a]volume={music_volume}[mraw];"
            "[mraw][sc]sidechaincompress=threshold=0.03:ratio=4:attack=15:release=250[m];"
            "[vo][sfx][m]amix=inputs=3:duration=first:normalize=0,alimiter=limit=0.96[a]"
        )
    else:
        fc = ("[0:v][1:v]overlay=0:0:format=auto,format=yuv420p[v];"
              "[2:a]volume=1.35[vo];[3:a]volume=0.25[sfx];"
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
