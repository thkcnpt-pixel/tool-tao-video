# tool-tao-video

Hệ thống sản xuất & phân phối video ngắn `9:16` (`1080×1920`, `30fps`, 25–40 giây) tự động **0đ/tháng** cho YouTube Shorts & TikTok theo [`Antigravity_Master_Spec.md`](file:///home/antigravity/tool-tao-video/Antigravity_Master_Spec.md).

## Tiến độ triển khai
- [x] **Giai đoạn 1 – Core Video Engine** (4 nền Motion Graphics Dark Mode, Robot SVG bay theo highlight, Edge-TTS `+22%` có dự phòng `gTTS`, phụ đề Karaoke từng từ, nhạc nền & SFX bằng code, Playwright, FFmpeg)
- [x] **Giai đoạn 2 – Gemini API + Google Sheets + Google Drive** (sinh kịch bản JSON chống trùng 15 bài gần nhất, tự sinh chủ đề mới khi hết dòng `CHO_TAO`, upload `output.mp4` lên Drive OAuth)
- [x] **Giai đoạn 3 – Telegram Bot + Google Apps Script** (`@Thkcnpt_bot` gửi video kèm nút `✅ Duyệt` / `❌ Hủy`, reply sửa caption, chống lặp 3 lớp)
- [x] **Giai đoạn 4 – GitHub Actions Cron 3 ca/ngày & Upload YouTube Shorts** (`produce_video.yml`, `publish_video.yml`, `youtube_uploader.py` chế độ Private)

## Lịch chạy tự động 4 ca/ngày (Giờ Việt Nam UTC+7)
- **Ca 1 (Sáng):** Chạy lúc `04:43` (`43 21 * * *` UTC) → lên sóng `07:00`.
- **Ca 2 (Trưa):** Chạy lúc `09:43` (`43 2 * * *` UTC) → lên sóng `12:00`.
- **Ca 3 (Chiều):** Chạy lúc `14:43` (`43 7 * * *` UTC) → lên sóng `16:30`.
- **Ca 4 (Tối):** Chạy lúc `18:43` (`43 11 * * *` UTC) → lên sóng `20:30`.

## Lệnh chạy thủ công (khi cần)
```bash
python src/produce.py                              # Sản xuất video cho ca hiện tại
python src/produce.py --slot CHIEU                 # Sản xuất video theo ca chỉ định (SANG/TRUA/CHIEU/TOI)
python src/produce.py --seed "Chủ đề mới..."       # Thêm chủ đề mới và sản xuất ngay
python src/publish.py --video-id 20261123_SANG     # Đăng video đã duyệt lên YouTube + Telegram
```
