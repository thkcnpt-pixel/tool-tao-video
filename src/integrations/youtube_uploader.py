"""Upload YouTube Shorts + Tự động lên lịch Công khai đúng khung giờ vàng (05:00/11:30/18:00 VN) + Tự đăng Top Comment + Đọc View Analytics."""
import datetime
import json
import os
import re

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

YT_SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
    "https://www.googleapis.com/auth/youtube.readonly",
]
VN = datetime.timezone(datetime.timedelta(hours=7))

# Giờ vàng phát sóng theo ca (giờ, phút) theo giờ Việt Nam UTC+7
SLOT_SCHEDULE_VN = {
    "SANG": (7, 0),    # đi làm/đi học, lướt điện thoại buổi sáng
    "TRUA": (12, 0),   # nghỉ trưa
    "TOI": (20, 0),    # khung vàng tối sau bữa cơm
}


def _parse_client_secret():
    raw = os.environ.get("YOUTUBE_CLIENT_SECRET_JSON", "").strip()
    if not raw:
        raise RuntimeError("Thiếu YOUTUBE_CLIENT_SECRET_JSON")
    if raw.startswith("{"):
        data = json.loads(raw)
        box = data.get("installed") or data.get("web") or data
        return box["client_id"], box["client_secret"]
    raise RuntimeError("YOUTUBE_CLIENT_SECRET_JSON không phải JSON hợp lệ")


def get_youtube_service(scopes=None):
    rt = os.environ.get("YOUTUBE_REFRESH_TOKEN", "").strip()
    if not rt:
        raise RuntimeError("Thiếu YOUTUBE_REFRESH_TOKEN")
    cid, csec = _parse_client_secret()
    creds = Credentials(
        token=None,
        refresh_token=rt,
        client_id=cid,
        client_secret=csec,
        token_uri="https://oauth2.googleapis.com/token",
        scopes=scopes or YT_SCOPES,
    )
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def next_golden_publish_at(slot=""):
    """Tính mốc giờ vàng sắp tới (ISO 8601 UTC).
    - Nếu thời điểm bấm Duyệt cách giờ vàng của ca đó trong khoảng [10 phút .. 8 tiếng] -> lên lịch (Scheduled) đúng giờ vàng.
    - Nếu đã qua giờ vàng của ca đó (hoặc sát dưới 10 phút) -> trả None để đăng Công khai (Public) ngay lập tức!
    """
    now_vn = datetime.datetime.now(VN)
    hm = SLOT_SCHEDULE_VN.get(str(slot).upper())
    if not hm:
        return None
    target_vn = now_vn.replace(hour=hm[0], minute=hm[1], second=0, microsecond=0)
    diff_min = (target_vn - now_vn).total_seconds() / 60.0
    if 10 <= diff_min <= 480:
        utc_dt = target_vn.astimezone(datetime.timezone.utc)
        return utc_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    return None


def _split_caption(caption, topic, youtube_title="", full_prompt=""):
    tags = re.findall(r"#\S+", caption)
    clean = re.sub(r"#\S+", "", caption).strip()
    raw_title = re.sub(r"#\S+", "", str(youtube_title or "")).strip(" -–—.|")
    if not raw_title:
        raw_title = re.split(r"[.!?\n]", clean)[0].strip() or topic or "Mẹo AI Thực Chiến"
    title = raw_title[:95].strip()

    prompt_block = (
        f"📌 MẪU CÂU LỆNH ĐẦY ĐỦ (Copy dùng ngay):\n“{full_prompt.strip()}”\n\n"
        if full_prompt and full_prompt.strip()
        else ""
    )
    desc = (
        f"{prompt_block}"
        f"{clean}\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🤖 Thiện AI Thực Chiến (@thiennguyen_ai)\n"
        "⚡ Mẹo AI & Tự động hóa tiếng Việt – bấm Đăng ký để xem trọn bộ Series!\n\n"
        "#Shorts #MeoAI #AIThucChien " + " ".join(tags)
    )
    return title[:100], desc.strip()


def post_top_comment(yt, video_id, comment_text):
    """Tự động đăng 1 bình luận đầu tiên dưới video YouTube Shorts để giữ chân người xem đọc & copy Prompt."""
    try:
        yt.commentThreads().insert(
            part="snippet",
            body={
                "snippet": {
                    "videoId": video_id,
                    "topLevelComment": {"snippet": {"textOriginal": comment_text}},
                }
            },
        ).execute()
        print(f"[youtube] đã tự động đăng bình luận Prompt mẫu trên video {video_id}")
        return True
    except Exception as ex:
        print(f"[youtube] bỏ qua đăng bình luận ({ex!r})")
        return False


def fetch_video_metrics(video_ids):
    """Đọc lượt xem + lượt thích + bình luận thực tế và tính điểm chất lượng giữ chân/tương tác (Engagement Score)."""
    if not video_ids:
        return {}
    try:
        yt = get_youtube_service(["https://www.googleapis.com/auth/youtube.readonly"])
        res = yt.videos().list(part="statistics", id=",".join(video_ids[:50])).execute()
        out = {}
        for it in res.get("items", []):
            st = it.get("statistics", {})
            v = int(st.get("viewCount", 0))
            lk = int(st.get("likeCount", 0))
            cm = int(st.get("commentCount", 0))
            # Trọng số tương tác: 1 Like ~ 35 views, 1 Comment ~ 80 views -> ưu tiên bài giữ chân & kích thích hành động thật
            score = v + lk * 35 + cm * 80
            out[it["id"]] = {"views": v, "likes": lk, "comments": cm, "score": score}
        return out
    except Exception as ex:
        print(f"[youtube] bỏ qua đọc analytics ({ex!r})")
        return {}


def fetch_video_views(video_ids):
    """Đọc số lượt xem (viewCount) thực tế (tương thích ngược)."""
    metrics = fetch_video_metrics(video_ids)
    return {vid: m["views"] for vid, m in metrics.items()}


def upload_short(video_path, caption, topic="", slot="", auto_public=True, pinned_question="", youtube_title="", full_prompt=""):
    """Upload video lên YouTube Shorts:
    - Dùng tiêu đề SEO sạch (không nhồi hashtag) tăng tỷ lệ bấm xem.
    - Ghim trọn bộ Prompt mẫu đầy đủ vào Bình luận đầu tiên + Mô tả để kéo người xem mở khung bình luận (tăng APV > 110%).
    """
    yt = get_youtube_service(YT_SCOPES)
    title, desc = _split_caption(caption, topic, youtube_title=youtube_title, full_prompt=full_prompt)
    publish_at = next_golden_publish_at(slot) if auto_public else None
    if not auto_public:
        privacy = "private"
    elif publish_at:
        privacy = "private"  # YouTube API yêu cầu privacyStatus="private" kèm publishAt để Scheduled Public
    else:
        privacy = "public"

    status_body = {
        "privacyStatus": privacy,
        "selfDeclaredMadeForKids": False,
    }
    if publish_at:
        status_body["publishAt"] = publish_at

    body = {
        "snippet": {
            "title": title,
            "description": desc,
            "tags": list(dict.fromkeys(["Shorts", "MeoAI", "AIThucChien", "ThuThuatAI", "CongNgheAI", "TuDongHoa", "HocAI"] + [t.lstrip("#") for t in re.findall(r"#\w+", caption)]))[:15],
            "categoryId": "28",
            "defaultLanguage": "vi",
            "defaultAudioLanguage": "vi",
        },
        "status": status_body,
    }
    media = MediaFileUpload(video_path, mimetype="video/mp4", resumable=True, chunksize=4 * 1024 * 1024)
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    vid = resp["id"]
    mode_note = f"Scheduled Public ({publish_at})" if publish_at else privacy.upper()
    print(f"[youtube] upload OK id={vid} title={title!r} mode={mode_note}")

    q_line = pinned_question.strip() if pinned_question else "Bạn đang tốn nhiều thời gian nhất cho việc nào mỗi ngày? Comment bên dưới nhé!"
    if full_prompt and full_prompt.strip():
        comment = (
            f"📌 MẪU CÂU LỆNH ĐẦY ĐỦ (Chạm giữ để Copy dùng ngay):\n"
            f"“{full_prompt.strip()}”\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💬 {q_line}"
        )
    else:
        comment = f"💬 {q_line}\n👉 Comment ý kiến của bạn, mình trả lời từng bình luận nhé!"
    if not publish_at and privacy == "public":
        post_top_comment(yt, vid, comment)

    return f"https://youtube.com/shorts/{vid}", mode_note
