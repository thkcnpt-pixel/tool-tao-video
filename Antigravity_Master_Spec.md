# MASTER SPEC — HỆ THỐNG SẢN XUẤT & PHÂN PHỐI VIDEO NGẮN 9:16 TỰ ĐỘNG 0Đ (BUILD TỪ ĐẦU)

> **Dành cho AI / Agent triển khai (Antigravity):** Đây là bản đặc tả kỹ thuật đầy đủ để xây dựng dự án mới hoàn toàn từ con số 0 (greenfield). Tuân thủ chính xác kiến trúc 0đ, phong cách đồ họa 100% bằng code có nhân vật Robot AI mini cute bay theo vùng highlight, tích hợp Google Drive làm kho lưu trữ/nhạc nền, và tuyệt đối không thêm thành phần trả phí hay dư thừa.

## 1. Tổng quan dự án

* **Mục tiêu:** Xây dựng pipeline tự động sản xuất và phân phối video dọc `9:16` (`1080×1920`, `30fps`, thời lượng 30–45 giây) cho YouTube Shorts và TikTok.
* **Chi phí vận hành:** **0đ/tháng** (không VPS, không thẻ thanh toán API, không dịch vụ đăng bài trung gian trả phí).
* **Nguyên tắc tài nguyên:** **100% sinh bằng code và tài nguyên nội bộ.** Không dùng kho stock ảnh/video bên ngoài (Pexels, Pixabay, Unsplash...), không cần clip MC người thật/Google Flow, không yêu cầu người dùng tự quay phim hay quay màn hình.
* **Lịch phát sóng mục tiêu (3 ca/ngày — giờ Việt Nam UTC+7):**
  * **Ca 1 (Sáng — 05:00):** Tin tức AI / công nghệ nhanh (ưu tiên cảnh `stat_card`). *Cron render lúc 04:00 giờ VN (`0 21 * * *` UTC).*
  * **Ca 2 (Trưa — 11:30):** So sánh tính năng / chia sẻ giá trị có lồng ghép khéo léo dịch vụ (ví dụ gói Gemini Pro) tự nhiên, tránh bị TikTok bóp tương tác (ưu tiên `chat_demo` + `comparison`). *Cron render lúc 10:30 giờ VN (`30 3 * * *` UTC).*
  * **Ca 3 (Tối — 18:00):** Mẹo thực chiến / quy trình 3 bước ứng dụng AI (ưu tiên `bullet_steps`). *Cron render lúc 17:00 giờ VN (`0 10 * * *` UTC).*

## 2. Kiến trúc hệ thống 0đ & Phân vai thành phần

| Thành phần | Vai trò chính thức | Ghi chú kỹ thuật |
| :--- | :--- | :--- |
| **Google Sheets** | CMS quản lý lịch, trạng thái và sổ chống trùng chủ đề | Tab `Schedule` lưu lịch sử 14–30 ngày gần nhất để AI không lặp tin. |
| **Google Drive** (kho lưu trữ sẵn có) | **Kho lưu trữ video thành phẩm & kho nhạc nền động** | Lưu vĩnh viễn mọi `output.mp4` đã render (lưu `drive_file_id` vào Sheets để bước đăng bài kéo về, không lo GitHub Artifacts hết hạn); đồng thời chứa thư mục nhạc nền `.mp3` để chủ kênh thả nhạc mới vào bất cứ lúc nào mà không cần sửa code GitHub. |
| **Gemini API (AI Studio Free)** | Sinh kịch bản JSON chuẩn + caption + hashtag | Dùng model văn bản miễn phí (Flash / Flash-Lite), ép `response_mime_type: "application/json"`. |
| **Core Video Engine (Python)** | Xưởng dựng video 9:16 tự động 100% bằng code | Kết hợp `edge-tts` + `HTML/CSS/SVG + Playwright` + `FFmpeg`. |
| **GitHub Actions** (2.000 phút/tháng Free) | Worker chạy theo lịch Cron và theo lệnh duyệt | Thức dậy trước giờ đăng 1 tiếng (`04:00`, `10:30`, `17:00` giờ VN), chạy xong tắt. |
| **Telegram Bot API** | Giao diện duyệt bài trên điện thoại | Nhận `output.mp4` (<50 MB) + caption + nút `[✅ Duyệt]` / `[❌ Hủy]`, hỗ trợ reply sửa caption, bảo mật bằng `TELEGRAM_CHAT_ID`. |
| **Google Apps Script Web App** | Trạm nhận Webhook 24/7 miễn phí | Lắng nghe sự kiện bấm nút từ Telegram → cập nhật Google Sheets → kích hoạt GitHub Actions qua `workflow_dispatch`. |
| **Đăng bài bán tự động** | Auto-prepare, Manual-publish | YouTube Shorts upload tự động chế độ Private qua YouTube Data API v3 (bật Public 1 chạm); TikTok tải từ Telegram (hoặc Drive) đăng tay 10s kèm nhạc trend. |

### Luồng dữ liệu End-to-End

```text
[Google Sheets (Tab Schedule)] — Chủ kênh (hoặc lịch săn tin) nhập chủ đề với status = CHO_TAO
        │
        ▼ (Cron 04:00 / 10:30 / 17:00 giờ VN hoặc chạy tay workflow_dispatch)
[GitHub Actions: produce_video.yml]
        ├── 1. Đọc dòng CHO_TAO + 10 chủ đề gần nhất để chống trùng
        ├── 2. Gọi Gemini API (Free) ──► Xuất JSON kịch bản + caption + hashtag, ghi ngược lại Sheets
        ├── 3. Kéo 1 bản nhạc nền .mp3 ngẫu nhiên từ [Google Drive: Music_Library] (fallback assets/music/)
        ├── 4. Chạy Edge-TTS ──► Giọng đọc tiếng Việt (.mp3) + mốc thời gian phụ đề (có fallback)
        ├── 5. Chạy HTML/CSS/SVG + Playwright ──► Render UI Glassmorphism + Robot mini cute bay theo highlight
        ├── 6. Chạy FFmpeg ──► Ghép [Nền Motion Graphics tự code] + [UI & Robot] + [Phụ đề] + [Giọng đọc] + [Nhạc nền 12%] ──► output.mp4
        ├── 7. Upload output.mp4 lên [Google Drive: Output_Videos] ──► Ghi drive_file_id vào cột video_url_or_drive_id
        └── 8. Gửi output.mp4 + Caption + nút [✅ Duyệt] [❌ Hủy] về Telegram Bot (cập nhật status = CHO_DUYET)
        │
        ▼ (Chủ kênh bấm nút trên điện thoại)
[Google Apps Script Web App] ──► Cập nhật Sheets (DA_DUYET / DA_HUY) ──► Gọi workflow_dispatch tới GitHub Actions
        │
        ▼
[GitHub Actions: publish_video.yml]
        ├── Kéo đúng file output.mp4 từ [Google Drive] theo drive_file_id trong Sheets
        ├── YouTube Shorts: Upload Private qua YouTube Data API v3
        └── TikTok: Gửi bản final + caption sạch về Telegram để đăng tay 10s kèm nhạc trend
```

## 3. Thiết kế hình ảnh, Mascot Robot & Quy chuẩn kỹ thuật

### 3.1. Nhân vật dẫn dắt: Robot AI mini cute (100% Vector SVG trong HTML)
* **Tạo hình:** Robot mini bo tròn phong cách tối giản hiện đại (thân trắng/kính mờ, mặt kính tối có mắt LED phát sáng, ăng-ten nhỏ phát sáng, hào quang động cơ bay nhẹ, má hồng nhẹ, cánh tay chỉ hướng).
* **4 biểu cảm tự động theo cảnh:** `amazed` (mắt tròn ngạc nhiên ở Hook / Stat Card), `curious` (nhìn tập trung ở Chat Prompt / Bullet Steps), `happy` (mắt cười `^ ^` ở AI Reply / Comparison), `wink` (nháy mắt thân thiện ở CTA).
* **Chuyển động thông minh theo highlight (BẮT BUỘC):**
  * Ở mỗi cảnh, robot **tự động bay mượt (ease-out interpolation) kèm nhún nhẹ** đến sát mép phần tử đang được highlight và giơ tay chỉ thẳng vào mục đó (không đè lên chữ):
    * **Hook:** Đậu cạnh dòng chữ highlight cuối cùng của tiêu đề.
    * **Chat Demo:** Đậu cạnh ô `Yêu cầu của bạn` lúc gõ prompt, rồi bay mượt xuống cạnh ô `Phản hồi tự động` khi AI bắt đầu trả lời.
    * **Comparison:** Khi từng dòng bảng so sánh (dòng 1 → 2 → 3) sáng lên ở cột nổi bật, robot bay lần lượt xuống đúng dòng đang highlight.
    * **Bullet Steps:** Bay lần lượt xuống từng thẻ bước `1 → 2 → 3` đang sáng.
    * **Stat Card / CTA:** Bay từ con số nổi bật (`70%`) xuống cạnh nút CTA (`👇 Xem chi tiết ở phần mô tả`).

### 3.2. Nền Motion Graphics tự sinh bằng code (`assets/bg/`)
* Viết script `src/bg_generator.py` sinh sẵn 4 vòng lặp nền liền mạch 6–8 giây (`1080×1920`, `30fps`) lưu trong `assets/bg/` để tái sử dụng siêu nhanh:
  * `cyber_blue.mp4` (xanh dương – cyan – indigo)
  * `neon_purple.mp4` (tím neon – cyan)
  * `emerald_tech.mp4` (xanh ngọc – teal)
  * `sunset_amber.mp4` (vàng hổ phách – hồng tím)
* Hiệu ứng nền: sóng ánh sáng aurora tối, lưới công nghệ mờ và các hạt dữ liệu phát sáng trôi tuần hoàn khép kín.

### 3.3. Vùng an toàn TikTok / YouTube Shorts & Thông số xuất file (BẮT BUỘC)
* **Trên cùng:** Chừa trống tối thiểu **12%** chiều cao (`>= 230px`) tránh thanh tab.
* **Dưới cùng:** Chừa trống tối thiểu **20%** chiều cao (`>= 384px`) tránh tên kênh, caption, thanh điều hướng.
* **Mép phải (nửa dưới):** Chừa trống tối thiểu **17%** chiều rộng (`>= 184px`) tránh cột nút Tim, Bình luận, Lưu, Chia sẻ.
* **Font tiếng Việt:** `Be Vietnam Pro` (nạp cục bộ từ `assets/fonts/BeVietnamPro-*.ttf`, fallback `Inter`/`Noto Sans`) đảm bảo 100% không lỗi dấu tiếng Việt.
* **Âm thanh & Phụ đề:**
  * Giọng đọc `edge-tts`: mặc định `vi-VN-HoaiMyNeural` (tốc độ `+8%`, cho phép cấu hình đổi sang `vi-VN-NamMinhNeural` trong JSON).
  * **Cơ chế chống mất phụ đề:** Ưu tiên đọc `WordBoundary` gom cụm 4–5 từ có highlight từ khóa; bắt buộc có fallback chia cụm theo tỷ lệ độ dài ký tự nếu API chỉ trả `SentenceBoundary`.
  * Phụ đề dạng hộp kính mờ bo tròn, đặt phía trên vùng an toàn 20% dưới cùng và lệch trái khỏi vùng 17% mép phải.
  * Nhạc nền không bản quyền (`.mp3` kéo từ Google Drive hoặc `assets/music/`) trộn ở mức âm lượng `0.10 – 0.15` (tự bỏ qua không lỗi nếu trống).
* **Thông số FFmpeg đầu ra:** `1080×1920`, `30fps`, `-c:v libx264`, `-pix_fmt yuv420p`, `-c:a aac -b:a 128k`, `-movflags +faststart`, dung lượng mục tiêu `5 MB – 15 MB` (<50 MB giới hạn Telegram).

## 4. Chuẩn JSON kịch bản đầu vào (`script.json`)

```json
{
  "badge": "TIN CÔNG NGHỆ 2026",
  "bg_theme": "cyber_blue",
  "mascot": true,
  "voice": "vi-VN-HoaiMyNeural",
  "voice_rate": "+8%",
  "hook": {
    "headline": ["Đừng nâng cấp AI", "trước khi xem", "bảng này!"],
    "voiceover": "Nhiều bạn mất tiền oan khi nâng cấp AI mà chưa biết 3 điểm khác biệt lớn nhất này."
  },
  "scenes": [
    {
      "type": "chat_demo",
      "title": "Thử giao việc thực tế",
      "user_prompt": "Tóm tắt báo cáo 50 trang và lập bảng so sánh",
      "ai_reply": "Đã hoàn thành trong 12 giây kèm biểu đồ và 3 điểm rủi ro chính.",
      "voiceover": "Chỉ cần nhập đúng một yêu cầu, hệ thống tự xử lý toàn bộ tài liệu dài trong vài giây."
    },
    {
      "type": "comparison",
      "title": "Free vs Pro khác gì?",
      "left_title": "Bản Free",
      "left_items": ["Mô hình tiêu chuẩn", "Giới hạn lượt hỏi", "Không có Flow video"],
      "right_title": "Bản Pro",
      "right_items": ["Mô hình mạnh nhất", "2TB Google Drive", "1.000+ tín dụng Flow"],
      "voiceover": "Bản Free chỉ đủ dùng cơ bản, còn Pro có ngay 2TB Drive và hơn 1.000 tín dụng tạo video Flow."
    },
    {
      "type": "stat_card",
      "title": "Tốc độ xử lý mới",
      "metric": "10X",
      "summary": "Nhanh gấp 10 lần quy trình thủ công truyền thống",
      "bullets": ["Tự động hóa trọn gói 0đ", "Chạy trực tiếp trên GitHub Actions"],
      "voiceover": "Quy trình mới giúp rút ngắn gấp 10 lần thời gian làm nội dung mỗi ngày."
    },
    {
      "type": "bullet_steps",
      "title": "3 bước chọn gói chuẩn",
      "steps": [
        "Xác định nhu cầu dùng hàng ngày hay thỉnh thoảng",
        "Tận dụng dung lượng 2TB Drive đi kèm cho tài liệu",
        "Thử bản tiêu chuẩn trước khi nâng cấp lâu dài"
      ],
      "voiceover": "Hãy chốt theo 3 bước này để không tốn tiền thừa mà vẫn tối ưu hiệu suất làm việc."
    }
  ],
  "cta": {
    "highlight_metric": "70%",
    "summary": "Tiết kiệm 70% thời gian làm việc mỗi ngày",
    "button_text": "Xem chi tiết ở phần mô tả",
    "voiceover": "Chọn đúng gói phù hợp giúp bạn tiết kiệm 70 phần trăm thời gian mỗi ngày."
  },
  "caption": "So sánh nhanh Free vs Pro 2026 cực dễ hiểu #ai #congnghe #shorts"
}
```

## 5. Cấu trúc thư mục dự án, Google Sheets & Secrets

### Cây thư mục mục tiêu
```text
auto-short-video/
├── .github/workflows/
│   ├── produce_video.yml        # Cron 04:00 / 10:30 / 17:00 giờ VN (21:00 / 03:30 / 10:00 UTC) + workflow_dispatch
│   └── publish_video.yml        # Chạy khi nhận lệnh duyệt từ Apps Script (kéo mp4 từ Drive -> YouTube/Telegram)
├── apps_script/
│   └── webhook.gs               # Google Apps Script Web App nhận callback Telegram
├── assets/
│   ├── bg/                      # 4 vòng lặp Motion Graphics tự sinh (.mp4)
│   ├── fonts/                   # BeVietnamPro-*.ttf
│   └── music/                   # Nhạc nền dự phòng cục bộ (.mp3)
├── templates/
│   ├── styles.css               # Glassmorphism + 4 theme + vùng an toàn 12%/20%/17%
│   └── scene.html               # Render 4 loại cảnh + Hook + CTA + Phụ đề + Robot SVG bay theo highlight
├── src/
│   ├── bg_generator.py          # Sinh nền Motion Graphics bằng code
│   ├── tts_engine.py            # Edge-TTS + trích xuất phụ đề có fallback
│   ├── ui_renderer.py           # Playwright render PNG nền trong suốt
│   ├── video_composer.py        # FFmpeg ghép nền + UI/Robot + phụ đề + trộn nhạc 12%
│   ├── render_video.py          # CLI dựng video từ script.json -> output.mp4
│   └── integrations/
│       ├── gemini_client.py     # Gọi Gemini API Free sinh JSON + chống trùng chủ đề
│       ├── sheets_client.py     # Đọc/ghi Google Sheets CMS
│       ├── drive_client.py      # Upload output.mp4 lên Drive & tải nhạc nền/video từ Drive
│       ├── telegram_bot.py      # Gửi video duyệt kèm nút InlineKeyboard
│       └── youtube_uploader.py  # Upload YouTube Shorts chế độ Private
├── samples/
│   └── sample_script.json
├── requirements.txt
├── .gitignore
└── README.md
```

### Cấu trúc Google Sheets (Tab `Schedule` — 10 cột)
1. `id` (VD: `20261122_SANG`)
2. `date` (`YYYY-MM-DD`)
3. `slot` (`SANG` | `TRUA` | `TOI`)
4. `topic` (Chủ đề)
5. `bg_theme` (`cyber_blue` | `neon_purple` | `emerald_tech` | `sunset_amber`)
6. `script_json` (JSON kịch bản do Gemini sinh ra)
7. `caption` (Tiêu đề + mô tả + hashtag)
8. `status` (`CHO_TAO` | `CHO_DUYET` | `DA_DUYET` | `DA_HUY` | `DA_DANG`)
9. `telegram_msg_id` (ID tin nhắn Telegram để xử lý reply sửa caption)
10. `video_url_or_drive_id` (`drive_file_id` của `output.mp4` trên Google Drive)

### GitHub Secrets cần cấu hình
* `GEMINI_API_KEY` (Google AI Studio Free)
* `GOOGLE_SERVICE_ACCOUNT_JSON` (dùng chung cho cả Sheets & Drive — nhớ share quyền Editor cho email Service Account)
* `GOOGLE_SHEET_ID`
* `DRIVE_OUTPUT_FOLDER_ID` (thư mục lưu mọi `output.mp4` thành phẩm trên Drive)
* `DRIVE_MUSIC_FOLDER_ID` (thư mục chứa nhạc nền `.mp3` trên Drive — tùy chọn)
* `TELEGRAM_BOT_TOKEN` & `TELEGRAM_CHAT_ID`
* `GITHUB_PAT` (dùng trong Google Apps Script để gọi `workflow_dispatch`)
* `YOUTUBE_CLIENT_SECRET_JSON` & `YOUTUBE_REFRESH_TOKEN` (chỉ cần ở Giai đoạn 4)

## 6. Ràng buộc tuyệt đối (KHÔNG ĐƯỢC LÀM)

1. **KHÔNG** tạo Web quản trị dư thừa (Web PWA, React Dashboard, Supabase, Firebase Auth) — duyệt bài hoàn toàn qua Telegram Bot.
2. **KHÔNG** dùng `FFmpeg drawtext` thuần để vẽ bảng so sánh, khung chat hay thẻ UI — bắt buộc dùng **HTML/CSS/SVG + Playwright** xuất lớp PNG trong suốt rồi mới ghép bằng FFmpeg.
3. **KHÔNG** dùng bất kỳ nguồn stock ảnh/video bên ngoài nào (Pexels, Pixabay, Unsplash...) và không yêu cầu người dùng tự quay phim/màn hình.
4. **KHÔNG** dùng bất kỳ dịch vụ hay API trả phí nào (không VPS, không API tạo video trả phí, không Blotato/Upload-Post).
5. **KHÔNG** tự động hóa trình duyệt đăng nhập Google Flow.

## 7. Lộ trình triển khai chuẩn & Prompt khởi động cho Antigravity

### Thứ tự triển khai 4 giai đoạn
1. **Giai đoạn 1 (Core Video Engine):** Xây dựng `bg_generator.py`, `templates/`, `tts_engine.py`, `ui_renderer.py`, `video_composer.py`, `render_video.py`, chạy thử xuất `output.mp4` từ `samples/sample_script.json` và kiểm tra trực quan vùng an toàn + chuyển động Robot bay theo highlight + giọng đọc tiếng Việt.
2. **Giai đoạn 2 (Gemini API + Google Sheets + Google Drive):** Xây dựng `sheets_client.py`, `drive_client.py` và `gemini_client.py` đọc dòng `CHO_TAO` + 10 chủ đề gần nhất chống trùng, sinh JSON hợp lệ, kéo nhạc nền từ Drive và upload `output.mp4` lên Drive.
3. **Giai đoạn 3 (Telegram Bot + Google Apps Script):** Xây dựng `telegram_bot.py` gửi `output.mp4` kèm nút `[✅ Duyệt]` / `[❌ Hủy]` và `apps_script/webhook.gs` lắng nghe callback cập nhật Sheets + kích hoạt `workflow_dispatch`.
4. **Giai đoạn 4 (GitHub Actions Cron & Đăng bài):** Hoàn thiện `produce_video.yml` (Cron `0 21 * * *`, `30 3 * * *`, `0 10 * * *` UTC tương ứng `04:00`, `10:30`, `17:00` giờ VN cho 3 khung đăng `05:00`, `11:30`, `18:00`), `publish_video.yml` (kéo video từ Drive) và `youtube_uploader.py`.

### Prompt mẫu để copy dán thẳng vào Antigravity

```text
Hãy đọc kỹ toàn bộ file đặc tả `antigravity_master_spec.md` đính kèm.
Bạn đóng vai trò Kỹ sư Phần mềm xây dựng toàn bộ dự án này mới hoàn toàn từ đầu theo đúng kiến trúc 0đ, 100% code (Robot AI mini cute SVG bay theo mục highlight + nền Motion Graphics tự sinh + Playwright + Edge-TTS + FFmpeg + Google Sheets/Drive + Telegram/Apps Script) và tuân thủ nghiêm ngặt mọi ràng buộc ở Mục 6.

Hãy triển khai tuần tự từng giai đoạn, bắt đầu ngay từ Giai đoạn 1 (Core Video Engine):
1. Khởi tạo cấu trúc thư mục chuẩn như Mục 5.
2. Viết đầy đủ code Giai đoạn 1 (bg_generator.py, templates/styles.css, templates/scene.html với Robot SVG bay theo highlight, tts_engine.py có fallback phụ đề, ui_renderer.py, video_composer.py, render_video.py, samples/sample_script.json, requirements.txt).
3. Chạy thử thực tế để sinh output/output.mp4, kiểm tra không lỗi dấu tiếng Việt, đúng vùng an toàn 12%/20%/17%, và báo cáo kết quả trước khi chuyển sang Giai đoạn 2.
```
