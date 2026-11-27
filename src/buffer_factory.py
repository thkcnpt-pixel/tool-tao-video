"""Xưởng Sản Xuất Kho Dự Trữ 30 Ngày (Buffer Factory):
Duy trì kho 60 video dựng sẵn trên Google Drive (status = DA_DUNG_SAN) cho 2 ca Evergreen:
  - Ca Trưa (TRUA): 30 video dựng sẵn (30 ngày)
  - Ca Tối  (TOI) : 30 video dựng sẵn (30 ngày)
(Riêng Ca Sáng SANG không dựng trước vào kho 30 ngày để mỗi sáng luôn dựng trực tiếp theo tin nóng RSS).
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
import video_qa  # noqa: E402
from drive_client import DriveClient  # noqa: E402
from gemini_client import generate_evergreen_topics, generate_script  # noqa: E402
from sheets_client import SheetsClient  # noqa: E402
from telegram_bot import TelegramBot  # noqa: E402

VN = datetime.timezone(datetime.timedelta(hours=7))
TARGET_PER_SLOT = 7  # 30 Trưa + 30 Tối = 60 video dựng sẵn (đủ phát 30 ngày liên tục)


def pick_needed_slot(counts):
    """Chọn ca đang thiếu nhiều hơn để kho Trưa và Tối luôn cân bằng 1:1."""
    trua = counts.get("TRUA", 0)
    toi = counts.get("TOI", 0)
    if trua >= TARGET_PER_SLOT and toi >= TARGET_PER_SLOT:
        return None
    return "TRUA" if trua <= toi else "TOI"


def ensure_pending_row(sheets, slot, now):
    """Lấy dòng CHO_TAO của đúng ca (TRUA/TOI); nếu hết thì tự sinh 6 chủ đề Evergreen mới."""
    for r in sheets.rows():
        if r["status"] == "CHO_TAO" and r["slot"] == slot:
            return r
    all_topics = [r["topic"] for r in sheets.rows() if r["topic"]]
    insights = sheets.audience_insights()
    new_items = generate_evergreen_topics(slot, count=6, recent=all_topics, insights=insights)
    for idx, (sl, th, tp) in enumerate(new_items):
        d = (now + datetime.timedelta(days=1 + idx)).date()
        rid = f"BUF_{now:%Y%m%d_%H%M%S}_{sl}_{idx}"
        sheets.add_row(id=rid, date=f"{d:%Y-%m-%d}", slot=sl, topic=tp, bg_theme=th, status="CHO_TAO")
    for r in sheets.rows():
        if r["status"] == "CHO_TAO" and r["slot"] == slot:
            return r
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch-size", type=int, default=3, help="Số video dựng tối đa trong 1 đợt chạy ngầm")
    ap.add_argument("--target-per-slot", type=int, default=TARGET_PER_SLOT)
    ap.add_argument("--notify", action="store_true", help="Gửi thông báo tổng kết về Telegram sau khi nạp kho")
    a = ap.parse_args()

    sheets = SheetsClient()
    sheets.ensure_tab()
    sheets.recover_stale_locks()
    try:
        import youtube_uploader
        youtube_uploader.backfill_scheduled_comments(sheets.rows())
    except Exception:
        pass
    drive = DriveClient()
    top_hooks = sheets.top_performing_hooks(4)
    made = []

    for step in range(a.batch_size):
        counts = sheets.buffered_counts()
        trua_n, toi_n = counts.get("TRUA", 0), counts.get("TOI", 0)
        if trua_n >= a.target_per_slot and toi_n >= a.target_per_slot:
            print(f"[buffer] Kho dự trữ 30 ngày đã đầy ({trua_n + toi_n}/{a.target_per_slot * 2} video) -> nghỉ!")
            break

        slot = "TRUA" if trua_n <= toi_n else "TOI"
        now = datetime.datetime.now(VN)
        row = ensure_pending_row(sheets, slot, now)
        if not row:
            print(f"[buffer] Không lấy được chủ đề CHO_TAO cho ca {slot}")
            break

        r = row["_row"]
        sheets.update(r, status="DANG_TAO")
        print(f"[buffer] ({step + 1}/{a.batch_size}) Đang dựng sẵn vào kho [{slot}] dòng {r}: {row['id']} | {row['topic']}")

        recent_list = sheets.recent_topics(25, exclude_row=r)
        script = generate_script(row["topic"], slot, recent_list, theme=row["bg_theme"] or None, top_hooks=top_hooks)
        sheets.update(r, bg_theme=script["bg_theme"], script_json=json.dumps(script, ensure_ascii=False),
                      caption=script["caption"])

        with tempfile.TemporaryDirectory() as tmp:
            out_mp4 = str(Path(tmp) / f"{row['id']}.mp4")
            music = drive.random_music(tmp)
            render_video.render(script, out_mp4, music=music)

            qa = video_qa.review_video(out_mp4, script)
            if not (qa.get("pass", True) and qa.get("score", 9.0) >= 6.0):
                print(f"[buffer] QA lần 1 chưa đạt ({qa}) -> tự động dựng lại 1 lần (Self-Heal)")
                script = generate_script(row["topic"], slot, recent_list, theme=row["bg_theme"] or None, top_hooks=top_hooks)
                sheets.update(r, bg_theme=script["bg_theme"], script_json=json.dumps(script, ensure_ascii=False),
                              caption=script["caption"])
                render_video.render(script, out_mp4, music=music)
                qa = video_qa.review_video(out_mp4, script)

            vid = drive.upload(out_mp4, name=f"{row['id']}.mp4")

        sheets.update(r, video_url_or_drive_id=vid, status="DA_DUNG_SAN")
        drive.cleanup_old_videos(keep_latest=160, protected_ids=sheets.protected_drive_ids())
        made.append((slot, row["topic"], qa.get("score", 9.0)))
        print(f"[buffer] Đã cất vào kho DA_DUNG_SAN: {row['id']} -> drive_id={vid} (QA={qa.get('score')}/10)")

    final_counts = sheets.buffered_counts()
    total_buf = final_counts.get("TRUA", 0) + final_counts.get("TOI", 0)
    print(f"[buffer] Hoàn tất đợt chạy: dựng thêm {len(made)} video. Tổng kho hiện tại: {total_buf}/{a.target_per_slot * 2} "
          f"(TRUA={final_counts.get('TRUA', 0)}/{a.target_per_slot}, TOI={final_counts.get('TOI', 0)}/{a.target_per_slot})")

    if a.notify and made:
        lines = "\n".join(f"• [{sl}] {tp} (QA {sc}/10)" for sl, tp, sc in made)
        days_ready = min(final_counts.get("TRUA", 0), final_counts.get("TOI", 0))
        TelegramBot().send_text(
            f"📦 ĐÃ NẠP THÊM {len(made)} VIDEO VÀO KHO DỰ TRỮ 30 NGÀY\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{lines}\n\n"
            f"📊 Tồn kho dựng sẵn hiện tại: {total_buf}/{a.target_per_slot * 2} video\n"
            f"• Ca Trưa: {final_counts.get('TRUA', 0)}/{a.target_per_slot} video\n"
            f"• Ca Tối: {final_counts.get('TOI', 0)}/{a.target_per_slot} video\n"
            f"✨ Đủ phát tự động liên tục trong ~{days_ready} ngày!"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
