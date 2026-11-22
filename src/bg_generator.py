"""Sinh 4 nền Motion Graphics vòng lặp liền mạch 100% bằng code (Dark High-Contrast để nổi bật chữ & UI)."""
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

# Nền tối sâu (Deep Dark Mode) để thẻ Glassmorphism và chữ trắng nổi bật rõ ràng
THEMES = {
    "cyber_blue": dict(base=(3, 6, 18), layers=[(18, 85, 220), (0, 180, 230), (65, 50, 200)], grid=(70, 160, 255)),
    "neon_purple": dict(base=(8, 3, 20), layers=[(140, 40, 220), (0, 175, 220), (210, 45, 165)], grid=(180, 110, 255)),
    "emerald_tech": dict(base=(2, 12, 14), layers=[(10, 170, 115), (0, 150, 160), (45, 105, 210)], grid=(70, 215, 175)),
    "sunset_amber": dict(base=(16, 4, 15), layers=[(215, 130, 20), (215, 55, 115), (120, 45, 185)], grid=(245, 175, 105)),
}

LW, LH = 270, 480
_xs = np.linspace(0, 1, LW, dtype=np.float32)[None, :]
_ys = np.linspace(0, 1, LH, dtype=np.float32)[:, None]
# Vignette: làm tối vùng trung tâm và viền để chữ/UI nổi bật
_vx = (_xs - 0.5) * 2.0
_vy = (_ys - 0.5) * 2.0
_center_dim = 1.0 - 0.28 * np.exp(-(_vx * _vx * 1.8 + _vy * _vy * 1.2))


def _aurora(theme, t):
    """t in [0,1) ; mọi pha là bội nguyên của 2π => lặp hoàn hảo."""
    img = np.zeros((LH, LW, 3), dtype=np.float32)
    img += np.array(theme["base"], dtype=np.float32)
    for i, col in enumerate(theme["layers"]):
        k = i + 1
        y0 = 0.22 + 0.28 * i
        wave = 0.10 * np.sin(2 * math.pi * (1.5 * _xs + t * (1 if i % 2 == 0 else -1)) + i * 2.1)
        wave += 0.05 * np.sin(2 * math.pi * (3.0 * _xs - t * 2) + i)
        center = y0 + wave
        d = (_ys - center) / (0.10 + 0.025 * k)
        inten = np.exp(-d * d) * (0.48 + 0.20 * np.sin(2 * math.pi * (t + i / 3.0)))
        img += inten[..., None] * np.array(col, dtype=np.float32) * 0.32
    img *= _center_dim[..., None]
    return np.clip(img, 0, 255).astype(np.uint8)


def _frame(theme, idx, particles):
    t = idx / FRAMES
    base = Image.fromarray(_aurora(theme, t)).resize((W, H), Image.BICUBIC)
    over = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    gr, gg, gb = theme["grid"]
    step = 90
    off = int(t * step)
    for x in range(0, W + 1, step):
        d.line([(x, 0), (x, H)], fill=(gr, gg, gb, 14), width=1)
    for y in range(-step, H + step, step):
        yy = y + off
        d.line([(0, yy), (W, yy)], fill=(gr, gg, gb, 14), width=1)
    for (px, py, r, spd, ph) in particles:
        y = (py - spd * H * t) % H
        a = int(110 + 95 * math.sin(2 * math.pi * (t * 2 + ph)))
        d.ellipse([px - r * 3, y - r * 3, px + r * 3, y + r * 3], fill=(gr, gg, gb, max(a // 7, 6)))
        d.ellipse([px - r, y - r, px + r, y + r], fill=(255, 255, 255, max(a, 35)))
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
    particles = [(rnd.uniform(0, W), rnd.uniform(0, H), rnd.uniform(2, 4.5), rnd.choice([1, 1, 2]), rnd.random()) for _ in range(65)]
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "23",
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
