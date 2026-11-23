"""Sinh nhạc nền Ambient/Synthwave không bản quyền 100% bằng code (numpy + FFmpeg) vào assets/music/."""
from pathlib import Path
import subprocess
import numpy as np

SR = 44100
ROOT = Path(__file__).resolve().parent.parent
MUSIC_DIR = ROOT / "assets" / "music"


def _synth_track(chords, bpm=96, bars=8):
    """Tổng hợp loop nhạc nền êm, ấm (low-passed pad + sub bass + nhịp pluck nhẹ)."""
    beat = 60.0 / bpm
    bar_dur = 4 * beat
    total = int(SR * bars * bar_dur)
    out = np.zeros((total, 2), dtype=np.float32)

    for b in range(bars):
        freqs = chords[b % len(chords)]
        s0, s1 = int(b * bar_dur * SR), int((b + 1) * bar_dur * SR)
        n = s1 - s0
        t = np.arange(n, dtype=np.float32) / SR
        env = np.minimum(t / 0.25, 1.0) * np.minimum((bar_dur - t) / 0.3, 1.0)

        # Warm stereo pad (detuned sine + triangle harmonic)
        pad_l = np.zeros(n, dtype=np.float32)
        pad_r = np.zeros(n, dtype=np.float32)
        for i, f in enumerate(freqs):
            pad_l += 0.22 * np.sin(2 * np.pi * (f * 0.998) * t + i)
            pad_r += 0.22 * np.sin(2 * np.pi * (f * 1.002) * t + i + 0.6)
            pad_l += 0.07 * np.sin(2 * np.pi * (f * 2.0) * t)
            pad_r += 0.07 * np.sin(2 * np.pi * (f * 2.0) * t + 0.4)

        # Sub bass ở nốt gốc
        root = freqs[0] * 0.5
        bass = 0.28 * np.sin(2 * np.pi * root * t) * (0.75 + 0.25 * np.sin(2 * np.pi * (1.0 / beat) * t))

        # Arpeggio pluck mềm mỗi nửa phách
        arp = np.zeros(n, dtype=np.float32)
        step = beat / 2.0
        for k in range(int(bar_dur / step)):
            p0 = int(k * step * SR)
            plen = min(int(step * SR), n - p0)
            if plen <= 0:
                continue
            pt = np.arange(plen, dtype=np.float32) / SR
            pf = freqs[k % len(freqs)] * 2.0
            penv = np.exp(-pt * 9.0) * np.minimum(pt / 0.008, 1.0)
            arp[p0:p0 + plen] += 0.14 * np.sin(2 * np.pi * pf * pt) * penv

        # Soft kick nhẹ ở phách 1 và 3
        kick = np.zeros(n, dtype=np.float32)
        for k in (0, 2):
            p0 = int(k * beat * SR)
            plen = min(int(0.18 * SR), n - p0)
            pt = np.arange(plen, dtype=np.float32) / SR
            phase = 2 * np.pi * (48 * pt + 70 * (1 - np.exp(-pt * 28)) / 28)
            kick[p0:p0 + plen] += 0.26 * np.sin(phase) * np.exp(-pt * 14)

        out[s0:s1, 0] = (pad_l + bass + arp * 0.9 + kick) * env
        out[s0:s1, 1] = (pad_r + bass + arp * 1.1 + kick) * env

    peak = np.max(np.abs(out)) or 1.0
    pcm = np.clip(out / peak * 0.85, -1.0, 1.0)
    return (pcm * 32767).astype(np.int16)


TRACKS = {
    # Am9 -> Fmaj7 -> Cmaj7 -> G6
    "cyber_chill.mp3": ([(220.0, 261.63, 329.63, 392.0), (174.61, 220.0, 261.63, 329.63),
                         (261.63, 329.63, 392.0, 493.88), (196.0, 246.94, 293.66, 329.63)], 96),
    # Dm9 -> Bbmaj7 -> Gm7 -> A7sus4
    "tech_pulse.mp3": ([(146.83, 220.0, 261.63, 329.63), (116.54, 174.61, 220.0, 293.66),
                        (196.0, 233.08, 293.66, 349.23), (220.0, 293.66, 329.63, 392.0)], 104),
    # Em9 -> Cmaj7 -> Gmaj7 -> D6 (Sáng: năng lượng, hiện đại)
    "future_bass.mp3": ([(164.81, 246.94, 293.66, 369.99), (130.81, 196.0, 246.94, 329.63),
                         (196.0, 246.94, 293.66, 369.99), (146.83, 220.0, 246.94, 329.63)], 108),
    # Fm9 -> Dbmaj7 -> Abmaj7 -> Eb6 (Tối: chiều sâu, tập trung)
    "lofi_focus.mp3": ([(174.61, 261.63, 311.13, 392.0), (138.59, 207.65, 261.63, 349.23),
                        (207.65, 261.63, 311.13, 392.0), (155.56, 233.08, 261.63, 349.23)], 92),
}


def ensure_music(force=False):
    MUSIC_DIR.mkdir(parents=True, exist_ok=True)
    for name, (chords, bpm) in TRACKS.items():
        path = MUSIC_DIR / name
        if path.exists() and not force:
            continue
        pcm = _synth_track(chords, bpm=bpm)
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "s16le", "-ar", str(SR), "-ac", "2", "-i", "-",
               "-af", "lowpass=f=4200", "-c:a", "libmp3lame", "-b:a", "160k", str(path)]
        p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        p.stdin.write(pcm.tobytes())
        p.stdin.close()
        p.wait()
        print(f"[music] đã sinh {path.name} ({path.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    ensure_music(force=True)
