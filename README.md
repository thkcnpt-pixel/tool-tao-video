# tool-tao-video

Pipeline tự động sản xuất video dọc 9:16 (1080×1920, 30fps) 0đ — xem `Antigravity_Master_Spec.md` để biết đặc tả đầy đủ.

## Tiến độ
- [x] **Giai đoạn 1 – Core Video Engine** (nền code, Robot SVG bay theo highlight, Edge-TTS, Playwright, FFmpeg)
- [ ] Giai đoạn 2 – Gemini + Google Sheets + Drive
- [ ] Giai đoạn 3 – Telegram Bot + Apps Script
- [ ] Giai đoạn 4 – GitHub Actions + YouTube

## Cài đặt
```bash
sudo apt-get install -y ffmpeg
pip install -r requirements.txt
python -m playwright install --with-deps chromium
```

## Chạy thử
```bash
python src/bg_generator.py                       # (tuỳ chọn) sinh lại 4 nền, thêm --force để ghi đè
python src/render_video.py samples/sample_script.json -o output/output.mp4
```
Tuỳ chọn: `--music file.mp3` (mặc định lấy ngẫu nhiên trong `assets/music/`, trống thì bỏ qua),
`--frames-dir output/frames --frame-ids 40,300` để lưu khung PNG kiểm tra.

Render ~3–4 phút cho video ~33 giây. Nếu edge-tts không kết nối được, pipeline vẫn chạy với âm thanh im lặng và in cảnh báo.
