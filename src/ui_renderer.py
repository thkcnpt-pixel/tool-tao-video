"""Playwright Async + 3 Tab song song + CDP captureScreenshot: tăng tốc render ~2x (117ms -> 62ms/khung)."""
import asyncio
import base64
import subprocess
import sys
from pathlib import Path

from playwright.async_api import async_playwright

TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "scene.html"
WORKERS = 3


async def _launch_browser(p):
    launch_args = [
        "--font-render-hinting=none",
        "--disable-gpu",
        "--disable-dev-shm-usage",
        "--no-sandbox",
    ]
    try:
        return await p.chromium.launch(args=launch_args)
    except Exception:
        print("[ui] Chromium chưa cài sẵn -> cài nhanh theo nhu cầu (on-demand)...")
        subprocess.run(["sudo", "DEBIAN_FRONTEND=noninteractive", "apt-get", "update"], check=False)
        subprocess.run(["sudo", "DEBIAN_FRONTEND=noninteractive", "apt-get", "install", "-y", "fonts-noto-core"], check=False)
        subprocess.run([sys.executable, "-m", "playwright", "install", "--with-deps", "chromium"], check=True)
        return await p.chromium.launch(args=launch_args)


async def _produce_batches(timeline, fps, save_dir, q):
    total = round(timeline["total"] * fps)
    async with async_playwright() as p:
        browser = await _launch_browser(p)
        pages, cdps = [], []
        n_wp = 0
        for w in range(WORKERS):
            page = await browser.new_page(viewport={"width": 1080, "height": 1920}, device_scale_factor=1)
            await page.goto(TEMPLATE.as_uri())
            await page.evaluate("document.fonts.ready")
            cnt = await page.evaluate("(tl) => init(tl)", timeline)
            if w == 0:
                n_wp = cnt
            cdp = await page.context.new_cdp_session(page)
            await cdp.send("Emulation.setDefaultBackgroundColorOverride", {"color": {"r": 0, "g": 0, "b": 0, "a": 0}})
            pages.append(page)
            cdps.append(cdp)

        print(f"[ui] {n_wp} waypoint robot, {total} khung (parallel={WORKERS} tabs)")

        async def grab(w, idx):
            await pages[w].evaluate("(t) => seek(t)", idx / fps)
            res = await cdps[w].send("Page.captureScreenshot", {"format": "png", "fromSurface": True})
            png = base64.b64decode(res["data"])
            if save_dir and idx in save_dir[1]:
                Path(save_dir[0], f"frame_{idx:04d}.png").write_bytes(png)
            return idx, png

        for start in range(0, total, WORKERS):
            count = min(WORKERS, total - start)
            batch = await asyncio.gather(*(grab(w, start + w) for w in range(count)))
            for item in batch:
                await q.put(item)

        await browser.close()
    await q.put(None)


def iter_frames(timeline, fps=30, save_dir=None):
    """Generator đồng bộ trả về (index, png_bytes) từ 3 tab Chromium chạy song song."""
    loop = asyncio.new_event_loop()
    q = asyncio.Queue(maxsize=WORKERS * 3)
    task = loop.create_task(_produce_batches(timeline, fps, save_dir, q))
    try:
        while True:
            item = loop.run_until_complete(q.get())
            if item is None:
                break
            yield item
        loop.run_until_complete(task)
    finally:
        loop.close()
