"""Sinh 8 nền Motion Graphics vòng lặp liền mạch 100% bằng code với 5 phong cách thị giác hoàn toàn khác nhau."""
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

# 8 theme với 5 kiểu nền khác hẳn nhau (aurora, light_dots, paper_lines, brutal_stripes, matrix_rain, warm_bokeh)
THEMES = {
    "cyber_blue": dict(
        mode="aurora",
        base=(3, 6, 18),
        layers=[(18, 85, 220), (0, 180, 230), (65, 50, 200)],
        grid=(70, 160, 255),
    ),
    "neon_purple": dict(
        mode="aurora",
        base=(8, 3, 20),
        layers=[(140, 40, 220), (0, 175, 220), (210, 45, 165)],
        grid=(180, 110, 255),
    ),
    "emerald_tech": dict(
        mode="matrix_rain",
        base=(3, 13, 11),
        layers=[(8, 130, 95), (0, 110, 125)],
        accent=(52, 211, 153),
    ),
    "sunset_amber": dict(
        mode="warm_bokeh",
        base=(22, 8, 14),
        layers=[(215, 115, 28), (195, 50, 95)],
        accent=(251, 191, 36),
    ),
    "clean_light": dict(
        mode="light_dots",
        base=(244, 247, 253),
        layers=[(205, 226, 255), (226, 214, 255), (196, 242, 235)],
        accent=(59, 130, 246),
    ),
    "paper_cream": dict(
        mode="paper_lines",
        base=(251, 245, 233),
        layers=[(253, 224, 190), (214, 238, 234)],
        accent=(234, 88, 12),
    ),
    "brutal_dark": dict(
        mode="brutal_stripes",
        base=(14, 14, 18),
        layers=[(42, 36, 14), (26, 26, 36)],
        accent=(250, 204, 21),
    ),
    "warm_editorial": dict(
        mode="warm_bokeh",
        base=(26, 11, 16),
        layers=[(175, 65, 55), (215, 145, 45)],
        accent=(251, 146, 60),
    ),
}

LW, LH = 270, 480
_xs = np.linspace(0, 1, LW, dtype=np.float32)[None, :]
_ys = np.linspace(0, 1, LH, dtype=np.float32)[:, None]
_vx = (_xs - 0.5) * 2.0
_vy = (_ys - 0.5) * 2.0
_center_dim = 1.0 - 0.26 * np.exp(-(_vx * _vx * 1.8 + _vy * _vy * 1.2))


def _aurora_base(theme, t, dim=True):
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
    if dim:
        img *= _center_dim[..., None]
    return np.clip(img, 0, 255).astype(np.uint8)


def _soft_light_base(theme, t):
    img = np.zeros((LH, LW, 3), dtype=np.float32)
    base = np.array(theme["base"], dtype=np.float32)
    img += base
    for i, col in enumerate(theme["layers"]):
        cx = 0.25 + 0.5 * ((i * 0.37) % 1.0) + 0.14 * math.sin(2 * math.pi * (t + i * 0.33))
        cy = 0.18 + 0.32 * i + 0.09 * math.cos(2 * math.pi * (t + i * 0.41))
        d2 = ((_xs - cx) / 0.52) ** 2 + ((_ys - cy) / 0.32) ** 2
        w = np.exp(-d2) * 0.55
        diff = np.array(col, dtype=np.float32) - base
        img += w[..., None] * diff
    return np.clip(img, 0, 255).astype(np.uint8)


def _frame(theme, idx, items):
    t = idx / FRAMES
    mode = theme.get("mode", "aurora")

    if mode == "aurora":
        base = Image.fromarray(_aurora_base(theme, t)).resize((W, H), Image.BICUBIC).convert("RGBA")
        over = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(over)
        gr, gg, gb = theme["grid"]
        step = 90
        off = int(t * step)
        for x in range(0, W + 1, step):
            d.line([(x, 0), (x, H)], fill=(gr, gg, gb, 14), width=1)
        for y in range(-step, H + step, step):
            d.line([(0, y + off), (W, y + off)], fill=(gr, gg, gb, 14), width=1)
        for (px, py, r, spd, ph) in items:
            y = (py - spd * H * t) % H
            a = int(105 + 90 * math.sin(2 * math.pi * (t * 2 + ph)))
            d.ellipse([px - r * 3, y - r * 3, px + r * 3, y + r * 3], fill=(gr, gg, gb, max(a // 7, 6)))
            d.ellipse([px - r, y - r, px + r, y + r], fill=(255, 255, 255, max(a, 35)))
        base.alpha_composite(over)
        return base.convert("RGB")

    if mode == "light_dots":
        base = Image.fromarray(_soft_light_base(theme, t)).resize((W, H), Image.BICUBIC).convert("RGBA")
        over = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(over)
        ar, ag, ab = theme["accent"]
        step = 64
        off = int(t * step)
        for x in range(32, W, step):
            for y in range(-step, H + step, step):
                yy = y + off
                d.ellipse([x - 2, yy - 2, x + 2, yy + 2], fill=(ar, ag, ab, 28))
        # Vòng tròn pastel mềm chuyển động ở góc
        for i, (px, py, r, spd, ph) in enumerate(items[:14]):
            yy = (py - spd * H * t) % (H + 200) - 100
            rad = int(r * 16)
            d.ellipse([px - rad, yy - rad, px + rad, yy + rad], outline=(ar, ag, ab, 24), width=2)
        base.alpha_composite(over)
        return base.convert("RGB")

    if mode == "paper_lines":
        base = Image.fromarray(_soft_light_base(theme, t)).resize((W, H), Image.BICUBIC).convert("RGBA")
        over = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(over)
        ar, ag, ab = theme["accent"]
        step = 76
        off = int(t * step)
        for y in range(-step, H + step, step):
            d.line([(0, y + off), (W, y + off)], fill=(120, 95, 70, 22), width=2)
        # Đường lề dọc kiểu sổ tay editorial
        d.line([(34, 0), (34, H)], fill=(ar, ag, ab, 50), width=4)
        for (px, py, r, spd, ph) in items[:18]:
            yy = (py + spd * H * t) % H
            sz = int(r * 5)
            d.rectangle([px - sz, yy - sz, px + sz, yy + sz], outline=(ar, ag, ab, 32), width=2)
        base.alpha_composite(over)
        return base.convert("RGB")

    if mode == "brutal_stripes":
        base = Image.fromarray(_aurora_base(theme, t, dim=False)).resize((W, H), Image.BICUBIC).convert("RGBA")
        over = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(over)
        ar, ag, ab = theme["accent"]
        step = 130
        off = int(t * step)
        for k in range(-H, W + H, step):
            x0 = k + off
            d.line([(x0, 0), (x0 - H // 2, H)], fill=(ar, ag, ab, 18), width=18)
        # Chữ thập hình học góc cạnh
        for (px, py, r, spd, ph) in items[:22]:
            yy = (py - spd * H * t) % H
            sz = int(r * 4)
            a = int(45 + 35 * math.sin(2 * math.pi * (t + ph)))
            d.line([(px - sz, yy), (px + sz, yy)], fill=(ar, ag, ab, a), width=2)
            d.line([(px, yy - sz), (px, yy + sz)], fill=(ar, ag, ab, a), width=2)
        base.alpha_composite(over)
        return base.convert("RGB")

    if mode == "matrix_rain":
        base = Image.fromarray(_aurora_base(theme, t)).resize((W, H), Image.BICUBIC).convert("RGBA")
        over = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(over)
        ar, ag, ab = theme["accent"]
        # Vòng radar đồng tâm nhẹ
        cx, cy = W // 2, H // 2
        for k in range(1, 5):
            rad = int(((k * 240 + t * 240) % 960) + 120)
            a = max(6, int(26 * (1 - rad / 1100)))
            d.ellipse([cx - rad, cy - rad, cx + rad, cy + rad], outline=(ar, ag, ab, a), width=2)
        # Các cột vệt sáng rơi dọc (digital rain)
        for (px, py, r, spd, ph) in items[:38]:
            col_x = int(px // 36) * 36 + 18
            yy = (py + spd * H * t) % H
            seg_len = int(48 + r * 26)
            a = int(50 + 55 * math.sin(2 * math.pi * (t * 2 + ph)))
            d.line([(col_x, yy - seg_len), (col_x, yy)], fill=(ar, ag, ab, max(18, a // 2)), width=3)
            d.ellipse([col_x - 3, yy - 3, col_x + 3, yy + 3], fill=(210, 255, 235, max(50, a)))
        base.alpha_composite(over)
        return base.convert("RGB")

    # warm_bokeh
    base = Image.fromarray(_aurora_base(theme, t)).resize((W, H), Image.BICUBIC).convert("RGBA")
    over = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    ar, ag, ab = theme["accent"]
    for (px, py, r, spd, ph) in items[:24]:
        yy = (py - spd * H * t) % H
        rad = int(r * 22)
        a = int(16 + 14 * math.sin(2 * math.pi * (t + ph)))
        d.ellipse([px - rad, yy - rad, px + rad, yy + rad], fill=(ar, ag, ab, max(6, a)))
        d.ellipse([px - rad // 2, yy - rad // 2, px + rad // 2, yy + rad // 2], fill=(255, 230, 180, max(8, a + 6)))
    base.alpha_composite(over)
    return base.convert("RGB")


def generate(name, force=False):
    if name not in THEMES:
        name = "cyber_blue"
    out = BG_DIR / f"{name}.mp4"
    if out.exists() and not force:
        return out
    BG_DIR.mkdir(parents=True, exist_ok=True)
    theme = THEMES[name]
    rnd = random.Random(name)
    items = [(rnd.uniform(0, W), rnd.uniform(0, H), rnd.uniform(2, 4.5), rnd.choice([1, 1, 2]), rnd.random()) for _ in range(65)]
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "23",
           "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for i in range(FRAMES):
        p.stdin.write(_frame(theme, i, items).tobytes())
    p.stdin.close()
    p.wait()
    print(f"[bg] {out} ({out.stat().st_size / 1e6:.1f} MB)")
    return out


def ensure_all(force=False):
    for n in THEMES:
        generate(n, force)


if __name__ == "__main__":
    ensure_all("--force" in sys.argv)
