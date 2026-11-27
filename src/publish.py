"""Pipeline đăng bài (khi bấm nút Duyệt hoặc Tạo lại từ Telegram)."""
import argparse
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "integrations"))

from drive_client import DriveClient  # noqa: E402
from sheets_client import SheetsClient  # noqa: E402
from telegram_bot import TelegramBot  # noqa: E402
import youtube_uploader  # noqa: E402
import facebook_uploader  # noqa: E402


def find_target_row(sheets, video_id=None):
    rows = sheets.rows()
    if video_id:
        for r in rows:
            if r["id"] == video_id:
                if r["status"] not in ("DA_DUYET", "CHO_DUYET"):
                    print(f"[publish] BỎ QUA {video_id}: status hiện tại là {r['status']!r}")
                    return None
                return r
        return None
    approved = [r for r in rows if r["status"] == "DA_DUYET" and r["video_url_or_drive_id"]]
    return approved[0] if approved else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video-id", help="id dòng trong tab Schedule")
    ap.add_argument("--skip-youtube", action="store_true")
    a = ap.parse_args()

    sheets = SheetsClient()

    if a.video_id and str(a.video_id).startswith("REGEN:"):
        real_id = str(a.video_id).split("REGEN:", 1)[1]
        try:
            TelegramBot().clear_pending_webhook()
        except Exception:
            pass
        target = next((c for c in sheets.rows() if c["id"] == real_id), None)
        if target and target.get("status") == "DANG_TAO_LAI":
            return 0
        if target:
            sheets.update(target["_row"], status="DANG_TAO_LAI")
            bot = TelegramBot()
            notice_mid = bot.send_text(f"🔄 Đang viết lại kịch bản & dựng video mới cho {real_id} (~2-3 phút)...")
            bot.cleanup_duplicate_replies(int(target.get("telegram_msg_id") or 0) - 1, notice_mid)
        import produce
        sys.argv = ["produce.py", "--video-id", real_id]
        return produce.main()

    row = find_target_row(sheets, a.video_id)
    if not row:
        print(f"[publish] không có dòng DA_DUYET nào cần đăng (video_id={a.video_id!r})")
        return 0

    r = row["_row"]
    drive_id = row["video_url_or_drive_id"]
    sheets.update(r, status="DANG_DANG")
    try:
        TelegramBot().clear_pending_webhook()
    except Exception:
        pass
    print(f"[publish] đã khóa dòng {r} (status=DANG_DANG): id={row['id']} drive_id={drive_id}")

    pinned_q, yt_title, full_pr = "", "", ""
    try:
        sc_obj = json.loads(row.get("script_json") or "{}")
        pinned_q = sc_obj.get("pinned_question", "")
        yt_title = sc_obj.get("youtube_title", "")
        full_pr = sc_obj.get("full_prompt", "")
    except Exception:
        pass

    drive = DriveClient()
    with tempfile.TemporaryDirectory() as tmp:
        mp4 = str(Path(tmp) / f"{row['id']}.mp4")
        drive.download(drive_id, mp4)
        print(f"[drive] đã tải {mp4} ({Path(mp4).stat().st_size / 1e6:.1f} MB)")

        yt_url, yt_mode = None, ""
        if not a.skip_youtube:
            try:
                yt_res = youtube_uploader.upload_short(
                    mp4, row["caption"], row["topic"],
                    slot=row.get("slot", ""), auto_public=True,
                    pinned_question=pinned_q, youtube_title=yt_title, full_prompt=full_pr,
                )
                yt_url, yt_mode = (yt_res if isinstance(yt_res, tuple) else (yt_res, "PUBLIC"))
                print(f"[youtube] upload OK ({yt_mode}): {yt_url}")
            except Exception as ex:
                print(f"[youtube] CẢNH BÁO không upload được YouTube ({ex!r})")

        if facebook_uploader.is_configured():
            try:
                facebook_uploader.upload_reel(mp4, row["caption"], row["topic"])
            except Exception as ex:
                print(f"[facebook] CẢNH BÁO ({ex!r})")

        import tiktok_uploader
        if tiktok_uploader.is_configured():
            try:
                tiktok_uploader.upload_tiktok(mp4, row["caption"])
            except Exception as ex:
                print(f"[tiktok] CẢNH BÁO ({ex!r})")

        bot = TelegramBot()
        final_mid = bot.send_final(
            mp4,
            f"🚀 BẢN FINAL ĐÃ DUYỆT ({row['id']})\n"
            f"📌 Tải video này đăng TikTok kèm nhạc trend:\n\n"
            f"{row['caption']}",
            youtube_url=yt_url,
        )
        bot.cleanup_duplicate_replies(row.get("telegram_msg_id"), final_mid)
        print("[telegram] đã gửi bản final + caption sạch về Telegram")

    yt_id = yt_url.rsplit("/", 1)[-1] if yt_url else ""
    base_drv = str(drive_id).split("|")[0]
    new_ref = f"{base_drv}|{yt_id}" if yt_id else base_drv
    sheets.update(r, status="DA_DANG", video_url_or_drive_id=new_ref)
    print(f"[sheets] dòng {r}: status=DA_DANG")
    return 0


if __name__ == "__main__":
    sys.exit(main())
