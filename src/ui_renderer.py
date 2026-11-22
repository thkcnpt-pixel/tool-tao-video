"""Playwright: render từng khung PNG trong suốt (UI Glassmorphism + Robot + phụ đề)."""
from pathlib import Path

from playwright.sync_api import sync_playwright

TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "scene.html"


def iter_frames(timeline, fps=30, save_dir=None):
    """Sinh (index, png_bytes) cho toàn bộ timeline."""
    total = round(timeline["total"] * fps)
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--font-render-hinting=none"])
        page = browser.new_page(viewport={"width": 1080, "height": 1920}, device_scale_factor=1)
        page.goto(TEMPLATE.as_uri())
        page.evaluate("document.fonts.ready")
        n = page.evaluate("(tl) => init(tl)", timeline)
        print(f"[ui] {n} waypoint robot, {total} khung")
        for i in range(total):
            page.evaluate("(t) => seek(t)", i / fps)
            png = page.screenshot(type="png", omit_background=True)
            if save_dir and i in save_dir[1]:
                Path(save_dir[0], f"frame_{i:04d}.png").write_bytes(png)
            yield i, png
        browser.close()
