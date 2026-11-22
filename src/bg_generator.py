"""Sinh 4 nền Motion Graphics vòng lặp liền mạch 100% bằng code (numpy + PIL + FFmpeg)."""
import math
import random
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

W, H, FPS = 1080, 1920, 30
SECONDS = 6
FRAMES = FPS * SECONDS
ROOT = Path(__file__).resolve().parent.parent
BG_DIR = ROOT / "assets" / "bg"

# base: màu nền tối; layers: các dải aurora (RGB 0-255)
THEMES = {
    "cyber_blue": dict(base=(5, 10, 32), layers=[(30, 110, 255), (0, 220, 255), (90, 70, 240)], grid=(80, 170, 255)),
    "neon_purple": dict(base=(14, 5, 32), layers=[(170, 60, 255), (0, 220, 255), (255, 60, 200)], grid=(190, 120, 255)),
    "emerald_tech": dict(base=(3, 20, 22), layers=[(16, 210, 140), (0, 190, 190), (60, 130, 255)], grid=(80, 230, 190)),
    "sunset_amber": dict(base=(26, 8, 24), layers=[(255, 170, 30), (255, 80, 140), (150, 60, 220)], grid=(255, 190, 120)),
}

# Aurora tính ở độ phân giải thấp rồi phóng to cho nhanh
LW, LH = 270, 480
_xs = np.linspace(0, 1, LW, dtype=np.float32)[None, :]
_ys = np.linspace(0, 1, LH, dtype=np.float32)[:, None]


def _aurora(theme, t):
    """t in [0,1) ; mọi pha là bội nguyên của 2π => lặp hoàn hảo."""
    img = np.zeros((LH, LW, 3), dtype=np.float32)
    img += np.array(theme["base"], dtype=np.float32)
    for i, col in enumerate(theme["layers"]):
        k = i + 1
        y0 = 0.25 + 0.25 * i
        wave = 0.10 * np.sin(2 * math.pi * (1.5 * _xs + t * (1 if i % 2 == 0 else -1)) + i * 2.1)
        wave += 0.05 * np.sin(2 * math.pi * (3.0 * _xs - t * 2) + i)
        center = y0 + wave
        d = (_ys - center) / (0.11 + 0.03 * k)
        inten = np.exp(-d * d) * (0.55 + 0.25 * np.sin(2 * math.pi * (t + i / 3.0)))
        img += inten[..., None] * np.array(col, dtype=np.float32) * 0.55
    return np.clip(img, 0, 255).astype(np.uint8)


def _frame(theme, idx, particles):
    t = idx / FRAMES
    base = Image.fromarray(_aurora(theme, t)).resize((W, H), Image.BICUBIC)
    over = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    gr, gg, gb = theme["grid"]
    step = 90
    off = int(t * step)  # cuộn đúng 1 ô lưới / vòng lặp
    for x in range(0, W + 1, step):
        d.line([(x, 0), (x, H)], fill=(gr, gg, gb, 16), width=1)
    for y in range(-step, H + step, step):
        yy = y + off
        d.line([(0, yy), (W, yy)], fill=(gr, gg, gb, 16), width=1)
    for (px, py, r, spd, ph) in particles:
        y = (py - spd * H * t) % H
        a = int(120 + 100 * math.sin(2 * math.pi * (t * 2 + ph)))
        d.ellipse([px - r * 3, y - r * 3, px + r * 3, y + r * 3], fill=(gr, gg, gb, max(a // 6, 8)))
        d.ellipse([px - r, y - r, px + r, y + r], fill=(255, 255, 255, max(a, 40)))
    base = base.convert("RGBA")
    base.alpha_composite(over)
    return base.convert("RGB")


def generate(name, force=False):
    out = BG_DIR / f"{name}.mp4"
    if out.exists() and not force:
        return out
    BG_DIR.mkdir(parents=True, exist_ok=True)
    theme = THEMES[name]
    rnd = random.Random(name)
    particles = [(rnd.uniform(0, W), rnd.uniform(0, H), rnd.uniform(2, 5), rnd.choice([1, 1, 2]), rnd.random()) for _ in range(70)]
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "24",
           "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for i in range(FRAMES):
        p.stdin.write(_frame(theme, i, particles).tobytes())
    p.stdin.close()
    p.wait()
    print(f"[bg] {out} ({out.stat().st_size / 1e6:.1f} MB)")
    return out


def ensure_all(force=False):
    for n in THEMES:
        generate(n, force)


if __name__ == "__main__":
    ensure_all("--force" in sys.argv)
