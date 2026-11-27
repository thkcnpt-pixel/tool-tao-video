"""Trạm Điều Phối Sản Xuất & Phát Sóng Thông Minh (Hybrid Live + 30-Day Vault):
- Ca Sáng (SANG - 04:00 VN): Luôn săn tin nóng RSS & dựng trực tiếp mỗi sáng để tin tức tươi mới 100%.
- Ca Trưa (TRUA - 10:30 VN) & Ca Tối (TOI - 17:00 VN): Ưu tiên lấy ngay video đã dựng sẵn trong Kho Dự Trữ 30 Ngày (status = DA_DUNG_SAN) đẩy lên YouTube Shorts + Telegram trong 20 giây! (Nếu kho đang trống hoặc chạy lệnh /tao <chủ đề> thì dựng trực tiếp ngay).
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
import video_composer  # noqa: E402
import video_qa  # noqa: E402
from drive_client import DriveClient  # noqa: E402
from gemini_client import generate_evergreen_topics, generate_script, generate_topic  # noqa: E402
from sheets_client import SheetsClient  # noqa: E402
from telegram_bot import TelegramBot  # noqa: E402
import youtube_uploader  # noqa: E402
import facebook_uploader  # noqa: E402
import tiktok_uploader  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
VN = datetime.timezone(datetime.timedelta(hours=7))



def build_community_post(topic, script):
    """Tạo bài viết ngắn 3 gạch đầu dòng từ kịch bản để chủ kênh chạm 1 cái copy đăng Zalo / Tab Cộng đồng YouTube."""
    try:
        pts = []
        for sc in script.get("scenes", [])[:3]:
            t = sc.get("type")
            if t == "bullet_steps" and sc.get("steps"):
                pts.extend(sc["steps"][:2])
            elif t == "checklist_card" and sc.get("items"):
                pts.extend(sc["items"][:2])
            elif t == "myth_vs_fact" and sc.get("fact"):
                pts.append(sc["fact"])
            elif sc.get("title"):
                pts.append(sc["title"])
        bullets = "\n".join(f"✅ {p}" for p in pts[:3])
        fp = str(script.get("full_prompt") or "").strip()
        tail = f"📋 Mẫu Prompt: “{fp[:140]}”" if fp else "💬 Bạn đang dùng mẹo AI nào mỗi ngày? Chia sẻ bên dưới nhé!"
        return f"🤖 {topic}\n{bullets}\n{tail}"[:360]
    except Exception:
        return ""

def current_vn_slot():
    h = datetime.datetime.now(VN).hour
    if h < 9:
        return "SANG"
    if h < 13:
        return "TRUA"
    if h < 18:
        return "CHIEU"
    return "TOI"


def retry_pending_youtube(sheets, drive, bot):
    pending_yt = [r for r in sheets.rows() if r["status"] == "CHO_DANG_YT" and r["video_url_or_drive_id"]]
    for row in pending_yt[:2]:
        try:
            sc_obj = json.loads(row.get("script_json") or "{}")
            with tempfile.TemporaryDirectory() as tmp:
                mp4 = str(Path(tmp) / f"{row['id']}.mp4")
                drive.download(row["video_url_or_drive_id"], mp4)
                yt_res = youtube_uploader.upload_short(
                    mp4, row["caption"], row["topic"],
                    slot=row.get("slot", ""), auto_public=True,
                    pinned_question=sc_obj.get("pinned_question", ""),
                    youtube_title=sc_obj.get("youtube_title", ""),
                    full_prompt=sc_obj.get("full_prompt", ""),
                )
                yt_url, yt_mode = (yt_res if isinstance(yt_res, tuple) else (yt_res, "PUBLIC"))
                yt_id = yt_url.rsplit("/", 1)[-1]
                base_drv = str(row["video_url_or_drive_id"]).split("|")[0]
                sheets.update(row["_row"], status="DA_DANG", video_url_or_drive_id=f"{base_drv}|{yt_id}")
                bot.send_text(f"✅ Đã tự động đăng bù lên YouTube Shorts cho {row['id']}: {yt_url}")
        except Exception as ex:
            print(f"[youtube] chưa đăng bù được {row['id']} ({ex!r})")
            break


def maybe_refill_evergreen_topics(sheets, now):
    """Đảm bảo luôn có sẵn chủ đề CHO_TAO cho Trưa, Chiều & Tối để Xưởng Buffer Factory chạy ngầm."""
    rows = sheets.rows()
    all_topics = [r["topic"] for r in rows if r["topic"]]
    insights = sheets.audience_insights()
    for sl in ("TRUA", "CHIEU", "TOI"):
        pend_sl = [r for r in rows if r["status"] == "CHO_TAO" and r["slot"] == sl]
        if len(pend_sl) < 2:
            batch = generate_evergreen_topics(sl, count=4, recent=all_topics, insights=insights)
            for idx, (s_name, th, tp) in enumerate(batch):
                d = (now + datetime.timedelta(days=1 + idx)).date()
                rid = f"{d:%Y%m%d}_{s_name}_{now:%H%M}{idx}"
                sheets.add_row(id=rid, date=f"{d:%Y-%m-%d}", slot=s_name, topic=tp, bg_theme=th, status="CHO_TAO")
                all_topics.append(tp)


def maybe_send_weekly_report(sheets, bot, now, slot):
    if now.weekday() != 6 or slot != "TOI":
        return
    rows = sheets.rows()
    da_dang = sum(1 for r in rows if r["status"] == "DA_DANG")
    buf_counts = sheets.buffered_counts()
    buf_total = buf_counts.get("TRUA", 0) + buf_counts.get("CHIEU", 0) + buf_counts.get("TOI", 0)
    top3 = sheets.top_performing_hooks(3)
    top_txt = "\n".join(f"  {i+1}. {h}" for i, h in enumerate(top3)) if top3 else "  (Đang cập nhật lượt xem)"
    bot.send_text(
        f"📊 BÁO CÁO TỔNG KẾT TUẦN — Thiện AI Thực Chiến\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"• Tổng số video đã xuất bản: {da_dang} video\n"
        f"• Kho dự trữ thông minh 4 ca/ngày: {buf_total}/21 video "
        f"(Trưa: {buf_counts.get('TRUA', 0)}/7 | Chiều: {buf_counts.get('CHIEU', 0)}/7 | Tối: {buf_counts.get('TOI', 0)}/7)\n\n"
        f"🏆 Top 3 video hiệu quả nhất trên YouTube Shorts:\n{top_txt}\n\n"
        f"✨ Ca Sáng săn tin nóng mỗi sáng; Ca Trưa, Chiều & Tối phát siêu tốc từ Kho Dự Trữ!"
    )


def publish_from_vault(row, eff_slot, sheets, drive, bot, manual_approve=False):
    """Lấy ngay video DA_DUNG_SAN từ Google Drive xuất bản lên YouTube Shorts + Telegram trong ~25 giây!"""
    r = row["_row"]
    vid = str(row["video_url_or_drive_id"]).split("|")[0]
    sheets.update(r, status="DANG_DANG")
    buf_left = sheets.buffered_counts()
    rem = buf_left.get("TRUA", 0) + buf_left.get("CHIEU", 0) + buf_left.get("TOI", 0)
    print(f"[vault] Xuất kho siêu tốc dòng {r} [{eff_slot}]: {row['id']} | drive_id={vid} (Còn {rem}/21 bài trong kho)")

    pinned_q, yt_title, full_pr, comm_txt = "", "", "", ""
    try:
        sc_obj = json.loads(row.get("script_json") or "{}")
        pinned_q = sc_obj.get("pinned_question", "")
        yt_title = sc_obj.get("youtube_title", "")
        full_pr = sc_obj.get("full_prompt", "")
        comm_txt = build_community_post(row["topic"], sc_obj)
    except Exception:
        pass

    yt_url, yt_mode, fb_url, yt_quota_hit = None, "", None, False
    with tempfile.TemporaryDirectory() as tmp:
        mp4 = str(Path(tmp) / f"{row['id']}.mp4")
        drive.download(vid, mp4)
        video_composer.extract_thumbnail(mp4)

        if not manual_approve:
            try:
                yt_res = youtube_uploader.upload_short(
                    mp4, row["caption"], row["topic"],
                    slot=eff_slot, auto_public=True,
                    pinned_question=pinned_q, youtube_title=yt_title, full_prompt=full_pr,
                )
                yt_url, yt_mode = (yt_res if isinstance(yt_res, tuple) else (yt_res, "PUBLIC"))
                print(f"[youtube] Vault Auto-Publish OK ({yt_mode}): {yt_url}")
                yt_id_now = yt_url.rsplit("/", 1)[-1] if yt_url else ""
                if yt_id_now:
                    sheets.update(r, video_url_or_drive_id=f"{vid}|{yt_id_now}", status="DA_DANG")
            except Exception as ex:
                print(f"[youtube] CẢNH BÁO không auto-upload được YouTube ({ex!r})")
                if "quota" in str(ex).lower():
                    yt_quota_hit = True

            if facebook_uploader.is_configured():
                try:
                    fb_url = facebook_uploader.upload_reel(mp4, row["caption"], row["topic"])
                except Exception as ex:
                    print(f"[facebook] CẢNH BÁO ({ex!r})")

            if tiktok_uploader.is_configured():
                try:
                    tiktok_uploader.upload_tiktok(mp4, row["caption"])
                except Exception as ex:
                    print(f"[tiktok] CẢNH BÁO ({ex!r})")

        vault_note = f"Đã kiểm duyệt sẵn • Tồn kho còn {rem}/21 video"
        msg_id = bot.send_for_approval(
            mp4, row["id"], row["topic"], row["caption"],
            drive_id=vid, youtube_url=yt_url, youtube_mode=yt_mode, fb_url=fb_url, qa_note=vault_note, community_post=comm_txt,
        )

    yt_id = yt_url.rsplit("/", 1)[-1] if yt_url else ""
    ref_val = f"{vid}|{yt_id}" if yt_id else vid
    final_status = "DA_DANG" if yt_url else ("CHO_DANG_YT" if yt_quota_hit else "CHO_DUYET")
    sheets.update(r, video_url_or_drive_id=ref_val, telegram_msg_id=msg_id, status=final_status)
    print(f"[vault] Hoàn tất xuất bản dòng {r}: status={final_status}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slot", choices=["SANG", "TRUA", "CHIEU", "TOI"])
    ap.add_argument("--seed", help="thêm 1 dòng CHO_TAO với chủ đề này và dựng ngay")
    ap.add_argument("--video-id", help="chỉ định id dòng cần dựng (hoặc dựng lại)")
    ap.add_argument("--manual-approve", action="store_true")
    ap.add_argument("--output", default=str(ROOT / "output" / "output.mp4"))
    a = ap.parse_args()

    sheets = SheetsClient()
    sheets.ensure_tab()
    sheets.recover_stale_locks()
    bot = TelegramBot()
    drive = DriveClient()
    try:
        bot.clear_pending_webhook()
        retry_pending_youtube(sheets, drive, bot)
        youtube_uploader.backfill_scheduled_comments(sheets.rows())
    except Exception:
        pass

    now = datetime.datetime.now(VN)
    slot = a.slot or current_vn_slot()

    # 1) NẾU LÀ CA TRƯA / CA CHIỀU / CA TỐI CHẠY TỰ ĐỘNG -> ƯU TIÊN XUẤT KHO SIÊU TỐC TỪ KHO DỰ TRỮ!
    if slot in ("TRUA", "CHIEU", "TOI") and not a.seed and not a.video_id:
        vault_row = sheets.next_buffered(slot)
        if vault_row:
            publish_from_vault(vault_row, slot, sheets, drive, bot, manual_approve=a.manual_approve)
            try:
                maybe_refill_evergreen_topics(sheets, now)
                maybe_send_weekly_report(sheets, bot, now, slot)
            except Exception as ex:
                print(f"[produce] bỏ qua hậu kiểm ({ex!r})")
            return 0

    # 2) DỰNG TRỰC TIẾP (LIVE): Luôn áp dụng cho Ca Sáng (SANG - Tin nóng RSS), lệnh /tao <chủ đề>, nút Tạo lại, hoặc khi kho đang trống
    row = None
    if a.video_id:
        row = next((c for c in sheets.rows() if c["id"] == a.video_id), None)

    if not row and a.seed:
        row_id = f"{now:%Y%m%d_%H%M%S}_{slot}"
        sheets.add_row(id=row_id, date=f"{now:%Y-%m-%d}", slot=slot, topic=a.seed, status="CHO_TAO")
        print(f"[sheets] đã thêm dòng CHO_TAO: {a.seed}")
        row = next((c for c in sheets.rows() if c["id"] == row_id), None)

    if not row and slot == "SANG":
        # Ca Sáng: chỉ lấy dòng CHO_TAO được gán riêng cho SANG; nếu không có thì tự săn tin nóng RSS mới nhất sáng nay!
        row = next((c for c in sheets.rows() if c["status"] == "CHO_TAO" and c["slot"] == "SANG"), None)
        if not row:
            recent = sheets.recent_topics(20)
            topic, theme = generate_topic("SANG", recent)
            row_id = f"{now:%Y%m%d_%H%M%S}_SANG"
            sheets.add_row(id=row_id, date=f"{now:%Y-%m-%d}", slot="SANG", topic=topic, bg_theme=theme, status="CHO_TAO")
            print(f"[sheets] Ca Sáng săn tin nóng mới: {row_id} | {topic}")
            row = next((c for c in sheets.rows() if c["id"] == row_id), None)

    if not row:
        row = sheets.next_pending(slot)

    if not row:
        recent = sheets.recent_topics(20)
        topic, theme = generate_topic(slot, recent)
        row_id = f"{now:%Y%m%d_%H%M%S}_{slot}"
        sheets.add_row(id=row_id, date=f"{now:%Y-%m-%d}", slot=slot, topic=topic, bg_theme=theme, status="CHO_TAO")
        row = sheets.next_pending(slot)

    r = row["_row"]
    eff_slot = row["slot"] or slot
    sheets.update(r, status="DANG_TAO")
    print(f"[produce] đã khóa dòng {r} (status=DANG_TAO): {row['id']} | {row['topic']}")

    recent_list = sheets.recent_topics(20, exclude_row=r)
    top_hooks = sheets.top_performing_hooks(3)
    script = generate_script(row["topic"], eff_slot, recent_list, theme=row["bg_theme"] or None, top_hooks=top_hooks)
    sheets.update(r, bg_theme=script["bg_theme"], script_json=json.dumps(script, ensure_ascii=False),
                  caption=script["caption"])

    yt_url, yt_mode, fb_url, yt_quota_hit = None, "", None, False
    with tempfile.TemporaryDirectory() as tmp:
        music = drive.random_music(tmp)
        render_video.render(script, a.output, music=music)
        qa = video_qa.review_video(a.output, script)
        qa_pass = qa.get("pass", True) and qa.get("score", 9.0) >= 6.0
        if not qa_pass:
            print(f"[qa] Lần 1 chưa đạt ({qa}) -> tự động dựng lại 1 lần (Self-Heal)!")
            script = generate_script(row["topic"], eff_slot, recent_list, theme=row["bg_theme"] or None, top_hooks=top_hooks)
            sheets.update(r, bg_theme=script["bg_theme"], script_json=json.dumps(script, ensure_ascii=False), caption=script["caption"])
            render_video.render(script, a.output, music=music)
            qa = video_qa.review_video(a.output, script)
            qa_pass = qa.get("pass", True) and qa.get("score", 9.0) >= 6.0
        qa_note = f"{qa.get('score', 9.0)}/10 — {qa.get('summary', 'Đạt chuẩn')}" + ("" if qa_pass else " ⚠️ (Cần xem lại)")

        vid = drive.upload(a.output, name=f"{row['id']}.mp4")
        drive.cleanup_old_videos(keep_latest=160, protected_ids=sheets.protected_drive_ids())
        print(f"[drive] upload OK drive_file_id={vid}")

        if not a.manual_approve and qa_pass:
            try:
                yt_res = youtube_uploader.upload_short(
                    a.output, script["caption"], row["topic"],
                    slot=eff_slot, auto_public=True,
                    pinned_question=script.get("pinned_question", ""),
                    youtube_title=script.get("youtube_title", ""),
                    full_prompt=script.get("full_prompt", ""),
                )
                yt_url, yt_mode = (yt_res if isinstance(yt_res, tuple) else (yt_res, "PUBLIC"))
                print(f"[youtube] Auto-Publish OK ({yt_mode}): {yt_url}")
                yt_id_now = yt_url.rsplit("/", 1)[-1] if yt_url else ""
                if yt_id_now:
                    sheets.update(r, video_url_or_drive_id=f"{vid}|{yt_id_now}", status="DA_DANG")
            except Exception as ex:
                print(f"[youtube] CẢNH BÁO không auto-upload được YouTube ({ex!r})")
                if "quota" in str(ex).lower():
                    yt_quota_hit = True

            if facebook_uploader.is_configured():
                try:
                    fb_url = facebook_uploader.upload_reel(a.output, script["caption"], row["topic"])
                except Exception as ex:
                    print(f"[facebook] CẢNH BÁO ({ex!r})")

            if tiktok_uploader.is_configured():
                try:
                    tiktok_uploader.upload_tiktok(a.output, script["caption"])
                except Exception as ex:
                    print(f"[tiktok] CẢNH BÁO ({ex!r})")

        msg_id = bot.send_for_approval(a.output, row["id"], row["topic"], script["caption"],
                                       drive_id=vid, youtube_url=yt_url, youtube_mode=yt_mode, fb_url=fb_url, qa_note=qa_note, community_post=build_community_post(row["topic"], script))

    yt_id = yt_url.rsplit("/", 1)[-1] if yt_url else ""
    ref_val = f"{vid}|{yt_id}" if yt_id else vid
    final_status = "DA_DANG" if yt_url else ("CHO_DANG_YT" if yt_quota_hit else "CHO_DUYET")
    sheets.update(r, video_url_or_drive_id=ref_val, telegram_msg_id=msg_id, status=final_status)
    print(f"[sheets] dòng {r}: status={final_status}, msg_id={msg_id}, ref={ref_val}")

    try:
        maybe_refill_evergreen_topics(sheets, now)
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
