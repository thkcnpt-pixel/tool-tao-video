"""Pipeline sản xuất (Giai đoạn 2): Sheets -> Gemini -> render -> Drive -> Sheets.

Dùng:
  python src/produce.py                  # lấy dòng CHO_TAO đầu tiên
  python src/produce.py --slot SANG      # ưu tiên đúng ca
  python src/produce.py --seed "chủ đề"  # thêm 1 dòng CHO_TAO mẫu rồi chạy
Telegram (status CHO_DUYET) sẽ nối ở Giai đoạn 3.
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
from gemini_client import generate_script  # noqa: E402
from sheets_client import SheetsClient  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
VN = datetime.timezone(datetime.timedelta(hours=7))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slot", choices=["SANG", "TRUA", "TOI"])
    ap.add_argument("--seed", help="thêm 1 dòng CHO_TAO với chủ đề này trước khi chạy")
    ap.add_argument("--output", default=str(ROOT / "output" / "output.mp4"))
    a = ap.parse_args()

    sheets = SheetsClient()
    sheets.ensure_tab()
    if a.seed:
        now = datetime.datetime.now(VN)
        slot = a.slot or "SANG"
        sheets.add_row(id=f"{now:%Y%m%d_%H%M%S}_{slot}", date=f"{now:%Y-%m-%d}", slot=slot, topic=a.seed,
                       status="CHO_TAO")
        print(f"[sheets] đã thêm dòng CHO_TAO: {a.seed}")

    row = sheets.next_pending(a.slot)
    if not row:
        print("[produce] không có dòng CHO_TAO nào")
        return 0
    r = row["_row"]
    print(f"[produce] dòng {r}: {row['id']} | {row['topic']}")

    script = generate_script(row["topic"], row["slot"], sheets.recent_topics(10, exclude_row=r),
                             theme=row["bg_theme"] or None)
    sheets.update(r, bg_theme=script["bg_theme"], script_json=json.dumps(script, ensure_ascii=False),
                  caption=script["caption"])
    print("[sheets] đã ghi script_json + caption")

    drive = DriveClient()
    with tempfile.TemporaryDirectory() as tmp:
        music = drive.random_music(tmp)  # None -> render_video fallback assets/music/
        render_video.render(script, a.output, music=music)
        vid = drive.upload(a.output, name=f"{row['id']}.mp4")
    print(f"[drive] upload OK drive_file_id={vid}")
    # Giai đoạn 3 sẽ đổi sang CHO_DUYET sau khi gửi Telegram thành công
    sheets.update(r, video_url_or_drive_id=vid, status="CHO_DUYET")
    print(f"[sheets] dòng {r}: status=CHO_DUYET, video_url_or_drive_id={vid}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
