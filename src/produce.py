"""Pipeline sản xuất: Sheets -> Gemini (tự sinh chủ đề nếu hết dòng CHO_TAO) -> render -> Drive -> Telegram -> Sheets.

Dùng:
  python src/produce.py                        # lấy dòng CHO_TAO theo ca hiện tại (hết thì tự sinh chủ đề mới)
  python src/produce.py --slot SANG            # chỉ định ca
  python src/produce.py --seed "chủ đề"        # thêm 1 dòng CHO_TAO với chủ đề này rồi chạy
  python src/produce.py --video-id 20261123... # tạo lại (regenerate) đúng dòng chỉ định
"""
import argparse
import datetime
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "integrations"))

import render_video  # noqa: E402
from drive_client import DriveClient  # noqa: E402
from gemini_client import generate_script, generate_topic  # noqa: E402
from sheets_client import SheetsClient  # noqa: E402
from telegram_bot import TelegramBot  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
VN = datetime.timezone(datetime.timedelta(hours=7))


def current_vn_slot():
    h = datetime.datetime.now(VN).hour
    if h < 8:
        return "SANG"
    if h < 15:
        return "TRUA"
    return "TOI"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slot", choices=["SANG", "TRUA", "TOI"])
    ap.add_argument("--seed", help="thêm 1 dòng CHO_TAO với chủ đề này trước khi chạy")
    ap.add_argument("--video-id", help="chỉ định id dòng cần dựng (hoặc dựng lại)")
    ap.add_argument("--output", default=str(ROOT / "output" / "output.mp4"))
    a = ap.parse_args()

    sheets = SheetsClient()
    sheets.ensure_tab()
    try:
        TelegramBot().clear_pending_webhook()
    except Exception:
        pass

    now = datetime.datetime.now(VN)
    slot = a.slot or current_vn_slot()

    row = None
    if a.video_id:
        for cand in sheets.rows():
            if cand["id"] == a.video_id:
                row = cand
                break

    if not row and a.seed:
        row_id = f"{now:%Y%m%d_%H%M%S}_{slot}"
        sheets.add_row(id=row_id, date=f"{now:%Y-%m-%d}", slot=slot, topic=a.seed, status="CHO_TAO")
        print(f"[sheets] đã thêm dòng CHO_TAO: {a.seed}")
        for cand in sheets.rows():
            if cand["id"] == row_id:
                row = cand
                break

    if not row:
        row = sheets.next_pending(slot)

    if not row:
        recent = sheets.recent_topics(15)
        topic, theme = generate_topic(slot, recent)
        row_id = f"{now:%Y%m%d_%H%M%S}_{slot}"
        sheets.add_row(id=row_id, date=f"{now:%Y-%m-%d}", slot=slot, topic=topic, bg_theme=theme, status="CHO_TAO")
        print(f"[sheets] hết dòng CHO_TAO -> đã tự động tạo dòng mới: {row_id} | {topic}")
        row = sheets.next_pending(slot)

    r = row["_row"]
    print(f"[produce] dòng {r}: {row['id']} | {row['topic']}")

    script = generate_script(row["topic"], row["slot"] or slot, sheets.recent_topics(15, exclude_row=r),
                             theme=row["bg_theme"] or None, top_hooks=sheets.top_performing_hooks(3))
    sheets.update(r, bg_theme=script["bg_theme"], script_json=json.dumps(script, ensure_ascii=False),
                  caption=script["caption"])
    print("[sheets] đã ghi script_json + caption")

    drive = DriveClient()
    with tempfile.TemporaryDirectory() as tmp:
        music = drive.random_music(tmp)
        render_video.render(script, a.output, music=music)
        vid = drive.upload(a.output, name=f"{row['id']}.mp4")
        drive.cleanup_old_videos(keep_latest=100)
        print(f"[drive] upload OK drive_file_id={vid}")
        msg_id = TelegramBot().send_for_approval(a.output, row["id"], row["topic"], script["caption"], drive_id=vid)
        print(f"[telegram] đã gửi tin nhắn duyệt msg_id={msg_id}")
    sheets.update(r, video_url_or_drive_id=vid, telegram_msg_id=msg_id, status="CHO_DUYET")
    print(f"[sheets] dòng {r}: status=CHO_DUYET, msg_id={msg_id}, drive_id={vid}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        try:
            TelegramBot().send_text(f"⚠️ Lỗi khi dựng video tự động (produce.py):\n{type(exc).__name__}: {exc}")
        except Exception:
            pass
        raise
