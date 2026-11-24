"""Sinh 4 bản nhạc nền Studio Synthwave / Lo-Fi / Future Bass không bản quyền 100% bằng code (numpy + FFmpeg).
Tối ưu riêng cho loa điện thoại (giàu họa âm 150Hz-3800Hz, có nhịp trống Kick + Clap + Hi-hat giữ nhịp cuốn hút,
và tự động cắt dải tần Vocal Pocket 1.5kHz để không bao giờ đè giọng đọc tiếng Việt).
"""
from pathlib import Path
import subprocess
import numpy as np

SR = 44100
ROOT = Path(__file__).resolve().parent.parent
MUSIC_DIR = ROOT / "assets" / "music"


def _rich_wave(freq, t, phase=0.0):
    """Tổng hợp sóng giàu họa âm ấm (fundamental + octave + fifth nhẹ) nghe rõ trên loa điện thoại."""
    return (
        0.62 * np.sin(2 * np.pi * freq * t + phase)
        + 0.24 * np.sin(2 * np.pi * (freq * 2.0) * t + phase * 1.3)
        + 0.10 * np.sin(2 * np.pi * (freq * 3.0) * t)
        + 0.04 * np.sin(2 * np.pi * (freq * 1.5) * t)
    )


def _synth_track(chords, bpm=102, bars=8, seed=7):
    """Tổng hợp bản nhạc 8 khuôn nhịp lặp hoàn hảo: Stereo Pad + Punchy Bass + Arpeggio + Kick/Snare/Hi-Hat Groove."""
    rng = np.random.default_rng(seed)
    beat = 60.0 / bpm
    bar_dur = 4 * beat
    total = int(SR * bars * bar_dur)
    out = np.zeros((total, 2), dtype=np.float32)

    for b in range(bars):
        freqs = chords[b % len(chords)]
        s0, s1 = int(b * bar_dur * SR), int((b + 1) * bar_dur * SR)
        n = s1 - s0
        t = np.arange(n, dtype=np.float32) / SR
        env = np.minimum(t / 0.18, 1.0) * np.minimum((bar_dur - t) / 0.22, 1.0)

        # 1) Warm Stereo Synth Pad (detuned L/R)
        pad_l = np.zeros(n, dtype=np.float32)
        pad_r = np.zeros(n, dtype=np.float32)
        for i, f in enumerate(freqs):
            pad_l += 0.15 * _rich_wave(f * 0.997, t, i * 0.7)
            pad_r += 0.15 * _rich_wave(f * 1.003, t, i * 0.7 + 0.5)

        # 2) Punchy Mid-Bass (có họa âm 110-220Hz để loa điện thoại nghe rõ tiếng bass) + Sidechain pump theo phách
        root = freqs[0] * 0.5
        pump = 0.35 + 0.65 * (1.0 - np.exp(-((t % beat) * 10.0)))
        bass = 0.28 * (_rich_wave(root, t) + 0.45 * np.sin(2 * np.pi * root * 2.0 * t)) * pump

        # 3) Melodic Arpeggio Pluck (1/8 note groove giữ nhịp não bộ người xem)
        arp_l = np.zeros(n, dtype=np.float32)
        arp_r = np.zeros(n, dtype=np.float32)
        step = beat / 2.0
        pattern = [0, 1, 2, 3, 2, 1, 3, 1]
        for k in range(int(bar_dur / step)):
            p0 = int(k * step * SR)
            plen = min(int(step * SR), n - p0)
            if plen <= 0:
                continue
            pt = np.arange(plen, dtype=np.float32) / SR
            pf = freqs[pattern[k % len(pattern)] % len(freqs)] * 2.0
            penv = np.exp(-pt * 11.0) * np.minimum(pt / 0.005, 1.0)
            note = 0.15 * _rich_wave(pf, pt) * penv
            pan = 0.65 if k % 2 == 0 else 0.35
            arp_l[p0:p0 + plen] += note * pan
            arp_r[p0:p0 + plen] += note * (1.0 - pan)

        # 4) Drum Groove: Punchy Kick (phách 1, 2.5, 3), Crisp Snare/Clap (phách 2, 4), Hi-Hat 1/8
        drums_l = np.zeros(n, dtype=np.float32)
        drums_r = np.zeros(n, dtype=np.float32)

        # Kick ở phách 0, 1.5 (syncopated), 2
        for kb in (0.0, 1.5, 2.0):
            p0 = int(kb * beat * SR)
            plen = min(int(0.19 * SR), n - p0)
            if plen <= 0:
                continue
            pt = np.arange(plen, dtype=np.float32) / SR
            phase = 2 * np.pi * (52 * pt + 95 * (1 - np.exp(-pt * 34)) / 34)
            click = 0.12 * np.sin(2 * np.pi * 1100 * pt) * np.exp(-pt * 140)
            k_wave = (0.32 * np.sin(phase) * np.exp(-pt * 13) + click) * (1.0 if kb in (0.0, 2.0) else 0.65)
            drums_l[p0:p0 + plen] += k_wave
            drums_r[p0:p0 + plen] += k_wave

        # Soft Snare / Clap ở phách 1 và 3 (tức beat 2 và 4)
        for sb in (1.0, 3.0):
            p0 = int(sb * beat * SR)
            plen = min(int(0.14 * SR), n - p0)
            if plen <= 0:
                continue
            pt = np.arange(plen, dtype=np.float32) / SR
            noise = rng.uniform(-1.0, 1.0, plen).astype(np.float32)
            body = np.sin(2 * np.pi * 195 * pt) * np.exp(-pt * 35)
            s_wave = (0.14 * noise * np.exp(-pt * 24) + 0.10 * body) * np.minimum(pt / 0.003, 1.0)
            drums_l[p0:p0 + plen] += s_wave * 0.95
            drums_r[p0:p0 + plen] += s_wave * 1.05

        # Crisp Hi-Hat shaker mỗi 1/2 phách (off-beat nhấn mạnh hơn)
        hh_step = beat / 2.0
        for hk in range(int(bar_dur / hh_step)):
            p0 = int(hk * hh_step * SR)
            plen = min(int(0.055 * SR), n - p0)
            if plen <= 0:
                continue
            pt = np.arange(plen, dtype=np.float32) / SR
            noise = rng.uniform(-1.0, 1.0, plen).astype(np.float32)
            # Tạo âm sắc kim loại sáng bằng sóng tần số cao điều chế
            metal = np.sin(2 * np.pi * 6200 * pt) * noise
            accent = 0.09 if hk % 2 == 1 else 0.045
            hh = accent * metal * np.exp(-pt * 55)
            drums_l[p0:p0 + plen] += hh * 1.08
            drums_r[p0:p0 + plen] += hh * 0.92

        # 5) Transition Riser ở cuối khuôn 4 và khuôn 8 (giữ tai người nghe hưng phấn)
        if b in (3, 7):
            r_len = min(int(beat * 1.5 * SR), n)
            rt = np.arange(r_len, dtype=np.float32) / SR
            r_freq = 320 + 680 * (rt / (beat * 1.5)) ** 2
            riser = 0.09 * np.sin(2 * np.pi * r_freq * rt) * (rt / (beat * 1.5))
            drums_l[n - r_len:n] += riser
            drums_r[n - r_len:n] += riser

        out[s0:s1, 0] = (pad_l * env + bass + arp_l * env + drums_l)
        out[s0:s1, 1] = (pad_r * env + bass + arp_r * env + drums_r)

    peak = np.max(np.abs(out)) or 1.0
    pcm = np.clip(out / peak * 0.88, -1.0, 1.0)
    return (pcm * 32767).astype(np.int16)


TRACKS = {
    # cyber_blue (Tin công nghệ): Dm9 -> Bbmaj7 -> Gm7 -> A7sus4 (nhịp 106 BPM cuốn hút, hiện đại)
    "tech_pulse.mp3": ([(146.83, 220.0, 261.63, 329.63), (116.54, 174.61, 220.0, 293.66),
                        (196.0, 233.08, 293.66, 349.23), (220.0, 293.66, 329.63, 392.0)], 106, 11),
    # neon_purple (Đột phá / So sánh Pro): Em9 -> Cmaj7 -> Gmaj7 -> D6 (110 BPM năng lượng cao)
    "future_bass.mp3": ([(164.81, 246.94, 293.66, 369.99), (130.81, 196.0, 246.94, 329.63),
                         (196.0, 246.94, 293.66, 369.99), (146.83, 220.0, 246.94, 329.63)], 110, 22),
    # emerald_tech (Quy trình 3 bước / Mẹo sâu): Am9 -> Fmaj7 -> Cmaj7 -> G6 (100 BPM rõ nhịp, tập trung)
    "cyber_chill.mp3": ([(220.0, 261.63, 329.63, 392.0), (174.61, 220.0, 261.63, 329.63),
                         (261.63, 329.63, 392.0, 493.88), (196.0, 246.94, 293.66, 329.63)], 100, 33),
    # sunset_amber (Tư duy / Sai lầm vs Sự thật): Fm9 -> Dbmaj7 -> Abmaj7 -> Eb6 (95 BPM Lo-Fi Groove ấm)
    "lofi_focus.mp3": ([(174.61, 261.63, 311.13, 392.0), (138.59, 207.65, 261.63, 349.23),
                        (207.65, 261.63, 311.13, 392.0), (155.56, 233.08, 261.63, 349.23)], 95, 44),
}


def ensure_music(force=False):
    MUSIC_DIR.mkdir(parents=True, exist_ok=True)
    for name, (chords, bpm, seed) in TRACKS.items():
        path = MUSIC_DIR / name
        if path.exists() and not force:
            continue
        pcm = _synth_track(chords, bpm=bpm, seed=seed)
        # EQ Vocal Pocket: cắt nhẹ -4.5dB ở vùng giọng nói 1500Hz để giọng đọc nổi bật, đồng thời giữ bass & treble sắc nét
        af = "highpass=f=55,equalizer=f=1500:t=q:w=1.1:g=-4.5,lowpass=f=6800,acompressor=threshold=-14dB:ratio=2"
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "s16le", "-ar", str(SR), "-ac", "2", "-i", "-",
               "-af", af, "-c:a", "libmp3lame", "-b:a", "160k", str(path)]
        p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        p.stdin.write(pcm.tobytes())
        p.stdin.close()
        p.wait()
        print(f"[music] đã sinh studio beat {path.name} ({path.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    ensure_music(force=True)
