# tool-tao-video

Hệ thống sản xuất & phân phối video ngắn `9:16` (`1080×1920`, `30fps`, 25–40 giây) tự động **0đ/tháng** cho YouTube Shorts & TikTok theo [`Antigravity_Master_Spec.md`](file:///home/antigravity/tool-tao-video/Antigravity_Master_Spec.md).

## Tiến độ triển khai
- [x] **Giai đoạn 1 – Core Video Engine** (4 nền Motion Graphics Dark Mode, Robot SVG bay theo highlight, Edge-TTS `+22%` có dự phòng `gTTS`, phụ đề Karaoke từng từ, nhạc nền & SFX bằng code, Playwright, FFmpeg)
- [x] **Giai đoạn 2 – Gemini API + Google Sheets + Google Drive** (sinh kịch bản JSON chống trùng 15 bài gần nhất, tự sinh chủ đề mới khi hết dòng `CHO_TAO`, upload `output.mp4` lên Drive OAuth)
- [x] **Giai đoạn 3 – Telegram Bot + Google Apps Script** (`@Thkcnpt_bot` gửi video kèm nút `✅ Duyệt` / `❌ Hủy`, reply sửa caption, chống lặp 3 lớp)
- [x] **Giai đoạn 4 – GitHub Actions Cron 3 ca/ngày & Upload YouTube Shorts** (`produce_video.yml`, `publish_video.yml`, `youtube_uploader.py` chế độ Private)

## Lịch chạy tự động hàng ngày (Giờ Việt Nam UTC+7)
- **Ca 1 (Sáng):** Render lúc `04:00` (`0 21 * * *` UTC) → gửi Telegram duyệt để đăng khung `05:00`.
- **Ca 2 (Trưa):** Render lúc `10:30` (`30 3 * * *` UTC) → gửi Telegram duyệt để đăng khung `11:30`.
- **Ca 3 (Tối):** Render lúc `17:00` (`0 10 * * *` UTC) → gửi Telegram duyệt để đăng khung `18:00`.

## Lệnh chạy thủ công (khi cần)
```bash
python src/produce.py                              # Sản xuất video cho ca hiện tại
python src/produce.py --slot SANG                  # Sản xuất video theo ca chỉ định
python src/produce.py --seed "Chủ đề mới..."       # Thêm chủ đề mới và sản xuất ngay
python src/publish.py --video-id 20261123_SANG     # Đăng video đã duyệt lên YouTube + Telegram
```
