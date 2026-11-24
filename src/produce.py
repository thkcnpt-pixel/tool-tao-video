"""Pipeline sản xuất & xuất bản tự động 100% (Full Auto-Approve cho mọi ca, đã sửa sạch SyntaxError):
Sheets -> Gemini -> Render -> Drive -> YouTube Shorts (Scheduled giờ vàng / Public + Smart Pinned Question) -> Telegram.
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
from gemini_client import generate_batch_topics, generate_script, generate_topic  # noqa: E402
from sheets_client import SheetsClient  # noqa: E402
from telegram_bot import TelegramBot  # noqa: E402
import youtube_uploader  # noqa: E402
import facebook_uploader  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
VN = datetime.timezone(datetime.timedelta(hours=7))


def current_vn_slot():
    h = datetime.datetime.now(VN).hour
    if h < 8:
        return "SANG"
    if h < 15:
        return "TRUA"
    return "TOI"


def retry_pending_youtube(sheets, drive, bot):
    """Nếu có video hôm trước bị kẹt quota YouTube (status == CHO_DANG_YT), tự động đăng bù."""
    pending_yt = [r for r in sheets.rows() if r["status"] == "CHO_DANG_YT" and r["video_url_or_drive_id"]]
    for row in pending_yt[:2]:
        try:
            with tempfile.TemporaryDirectory() as tmp:
                mp4 = str(Path(tmp) / f"{row['id']}.mp4")
                drive.download(row["video_url_or_drive_id"], mp4)
                yt_res = youtube_uploader.upload_short(mp4, row["caption"], row["topic"], slot=row.get("slot", ""), auto_public=True)
                yt_url, yt_mode = (yt_res if isinstance(yt_res, tuple) else (yt_res, "PUBLIC"))
                yt_id = yt_url.rsplit("/", 1)[-1]
                base_drv = str(row["video_url_or_drive_id"]).split("|")[0]
                sheets.update(row["_row"], status="DA_DANG", video_url_or_drive_id=f"{base_drv}|{yt_id}")
                bot.send_text(f"✅ Đã tự động đăng bù lên YouTube Shorts cho {row['id']}: {yt_url}")
        except Exception as ex:
            print(f"[youtube] chưa đăng bù được {row['id']} ({ex!r})")
            break


def maybe_refill_queue(sheets, now):
    pending = [r for r in sheets.rows() if r["status"] == "CHO_TAO"]
    if len(pending) >= 3:
        return
    recent = [r["topic"] for r in sheets.rows() if r["topic"]][-20:]
    batch = generate_batch_topics(recent, days=3)
    for idx, (sl, th, tp) in enumerate(batch):
        d = (now + datetime.timedelta(days=1 + idx // 3)).date()
        rid = f"{d:%Y%m%d}_{sl}_{now:%H%M}{idx}"
        sheets.add_row(id=rid, date=f"{d:%Y-%m-%d}", slot=sl, topic=tp, bg_theme=th, status="CHO_TAO")
    if batch:
        print(f"[sheets] Auto-Refill: đã bơm thêm {len(batch)} chủ đề CHO_TAO vào lịch")


def maybe_send_weekly_report(sheets, bot, now, slot):
    if now.weekday() != 6 or slot != "TOI":
        return
    rows = sheets.rows()
    cho_tao = sum(1 for r in rows if r["status"] == "CHO_TAO")
    da_dang = sum(1 for r in rows if r["status"] == "DA_DANG")
    top3 = sheets.top_performing_hooks(3)
    top_txt = "\n".join(f"  {i+1}. {h}" for i, h in enumerate(top3)) if top3 else "  (Đang cập nhật lượt xem)"
    bot.send_text(
        f"📊 BÁO CÁO TỔNG KẾT TUẦN — Thiện AI Thực Chiến\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"• Tổng số video đã xuất bản: {da_dang} video\n"
        f"• Số chủ đề sẵn sàng trong kho (CHO_TAO): {cho_tao} bài\n\n"
        f"🏆 Top 3 video hiệu quả nhất trên YouTube Shorts:\n{top_txt}\n\n"
        f"✨ Hệ thống vẫn đang tự động sản xuất & đăng bài 3 ca/ngày!"
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slot", choices=["SANG", "TRUA", "TOI"])
    ap.add_argument("--seed", help="thêm 1 dòng CHO_TAO với chủ đề này trước khi chạy")
    ap.add_argument("--video-id", help="chỉ định id dòng cần dựng (hoặc dựng lại)")
    ap.add_argument("--manual-approve", action="store_true")
    ap.add_argument("--output", default=str(ROOT / "output" / "output.mp4"))
    a = ap.parse_args()

    sheets = SheetsClient()
    sheets.ensure_tab()
    bot = TelegramBot()
    try:
        bot.clear_pending_webhook()
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
    eff_slot = row["slot"] or slot
    print(f"[produce] dòng {r}: {row['id']} | {row['topic']}")

    script = generate_script(row["topic"], eff_slot, sheets.recent_topics(15, exclude_row=r),
                             theme=row["bg_theme"] or None, top_hooks=sheets.top_performing_hooks(3))
    sheets.update(r, bg_theme=script["bg_theme"], script_json=json.dumps(script, ensure_ascii=False),
                  caption=script["caption"])
    print("[sheets] đã ghi script_json + caption")

    drive = DriveClient()
    try:
        retry_pending_youtube(sheets, drive, bot)
    except Exception:
        pass

    yt_url, yt_mode, fb_url, yt_quota_hit = None, "", None, False
    with tempfile.TemporaryDirectory() as tmp:
        music = drive.random_music(tmp)
        render_video.render(script, a.output, music=music)
        qa = video_qa.review_video(a.output, script)
        qa_pass = qa.get("pass", True) and qa.get("score", 9.0) >= 6.5
        qa_note = f"{qa.get('score', 9.0)}/10 — {qa.get('summary', 'Đạt chuẩn')}" + ("" if qa_pass else " ⚠️ (Cần xem lại)")

        vid = drive.upload(a.output, name=f"{row['id']}.mp4")
        drive.cleanup_old_videos(keep_latest=100)
        print(f"[drive] upload OK drive_file_id={vid}")

        if not a.manual_approve and qa_pass:
            try:
                yt_res = youtube_uploader.upload_short(
                    a.output, script["caption"], row["topic"],
                    slot=eff_slot, auto_public=True,
                    pinned_question=script.get("pinned_question", ""),
                )
                yt_url, yt_mode = (yt_res if isinstance(yt_res, tuple) else (yt_res, "PUBLIC"))
                print(f"[youtube] Auto-Publish OK ({yt_mode}): {yt_url}")
            except Exception as ex:
                print(f"[youtube] CẢNH BÁO không auto-upload được YouTube ({ex!r})")
                if "quota" in str(ex).lower():
                    yt_quota_hit = True

            if facebook_uploader.is_configured():
                try:
                    fb_url = facebook_uploader.upload_reel(a.output, script["caption"], row["topic"])
                except Exception as ex:
                    print(f"[facebook] CẢNH BÁO không auto-upload được Facebook Reels ({ex!r})")

        msg_id = bot.send_for_approval(a.output, row["id"], row["topic"], script["caption"],
                                       drive_id=vid, youtube_url=yt_url, youtube_mode=yt_mode, fb_url=fb_url, qa_note=qa_note)
        print(f"[telegram] đã gửi video msg_id={msg_id}")

    yt_id = yt_url.rsplit("/", 1)[-1] if yt_url else ""
    ref_val = f"{vid}|{yt_id}" if yt_id else vid
    if yt_url:
        final_status = "DA_DANG"
    elif yt_quota_hit:
        final_status = "CHO_DANG_YT"
    else:
        final_status = "CHO_DUYET"
    sheets.update(r, video_url_or_drive_id=ref_val, telegram_msg_id=msg_id, status=final_status)
    print(f"[sheets] dòng {r}: status={final_status}, msg_id={msg_id}, ref={ref_val}")

    try:
        maybe_refill_queue(sheets, now)
        maybe_send_weekly_report(sheets, bot, now, eff_slot)
    except Exception as ex:
        print(f"[produce] bỏ qua bước hậu kiểm ({ex!r})")
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
