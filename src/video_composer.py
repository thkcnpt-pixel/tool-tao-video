"""FFmpeg: ghép nền + lớp UI/Robot/phụ đề + giọng đọc + nhạc nền -> output.mp4"""
import subprocess
from pathlib import Path

from ui_renderer import iter_frames

FPS = 30


def build_voice_track(seg_audios, durations, workdir):
    """Đệm mỗi đoạn thoại tới đúng thời lượng cảnh rồi nối thành voice.wav."""
    wavs = []
    for i, (a, d) in enumerate(zip(seg_audios, durations)):
        w = Path(workdir) / f"seg_{i}.wav"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(a), "-af", f"apad=whole_dur={d:.3f}",
                        "-t", f"{d:.3f}", "-ar", "44100", "-ac", "2", str(w)], check=True)
        wavs.append(w)
    lst = Path(workdir) / "concat.txt"
    lst.write_text("".join(f"file '{w.resolve()}'\n" for w in wavs))
    voice = Path(workdir) / "voice.wav"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                    "-c", "copy", str(voice)], check=True)
    return voice


def compose(timeline, bg_path, voice_path, out_path, music_path=None, music_volume=0.12, save_dir=None):
    total = timeline["total"]
    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-stream_loop", "-1", "-i", str(bg_path),
           "-f", "image2pipe", "-framerate", str(FPS), "-c:v", "png", "-i", "-",
           "-i", str(voice_path)]
    if music_path:
        cmd += ["-stream_loop", "-1", "-i", str(music_path)]
        fc = ("[0:v][1:v]overlay=0:0:format=auto,format=yuv420p[v];"
              f"[3:a]volume={music_volume}[m];[2:a][m]amix=inputs=2:duration=first:normalize=0[a]")
    else:
        fc = "[0:v][1:v]overlay=0:0:format=auto,format=yuv420p[v];[2:a]anull[a]"
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
