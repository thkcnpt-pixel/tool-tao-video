"""Pipeline đăng bài (Giai đoạn 4): kéo output.mp4 từ Drive -> YouTube Shorts (Private) + gửi bản final về Telegram."""
import argparse
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "integrations"))

from drive_client import DriveClient  # noqa: E402
from sheets_client import SheetsClient  # noqa: E402
from telegram_bot import TelegramBot  # noqa: E402
import youtube_uploader  # noqa: E402


def find_target_row(sheets, video_id=None):
    rows = sheets.rows()
    if video_id:
        for r in rows:
            if r["id"] == video_id:
                return r
    approved = [r for r in rows if r["status"] == "DA_DUYET" and r["video_url_or_drive_id"]]
    return approved[0] if approved else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video-id", help="id dòng trong tab Schedule (nếu bỏ trống sẽ lấy dòng DA_DUYET đầu tiên)")
    ap.add_argument("--skip-youtube", action="store_true")
    a = ap.parse_args()

    sheets = SheetsClient()
    row = find_target_row(sheets, a.video_id)
    if not row:
        print(f"[publish] không tìm thấy dòng DA_DUYET nào (video_id={a.video_id!r})")
        return 0

    r = row["_row"]
    drive_id = row["video_url_or_drive_id"]
    print(f"[publish] dòng {r}: id={row['id']} drive_id={drive_id}")

    drive = DriveClient()
    with tempfile.TemporaryDirectory() as tmp:
        mp4 = str(Path(tmp) / f"{row['id']}.mp4")
        drive.download(drive_id, mp4)
        print(f"[drive] đã tải {mp4} ({Path(mp4).stat().st_size / 1e6:.1f} MB)")

        yt_url = None
        if not a.skip_youtube:
            try:
                yt_url = youtube_uploader.upload_short(mp4, row["caption"], row["topic"], privacy="private")
                print(f"[youtube] upload Private OK: {yt_url}")
            except Exception as ex:
                print(f"[youtube] CẢNH BÁO không upload được YouTube ({ex!r}) -> vẫn gửi bản final về Telegram")

        TelegramBot().send_final(
            mp4,
            f"🚀 BẢN FINAL ĐÃ DUYỆT ({row['id']})\n"
            f"📌 Tải video này đăng TikTok kèm nhạc trend (copy caption bên dưới):\n\n"
            f"{row['caption']}",
            youtube_url=yt_url,
        )
        print("[telegram] đã gửi bản final + caption sạch về Telegram")

    sheets.update(r, status="DA_DANG")
    print(f"[sheets] dòng {r}: status=DA_DANG")
    return 0


if __name__ == "__main__":
    sys.exit(main())
