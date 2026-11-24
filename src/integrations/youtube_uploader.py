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
    "SANG": (5, 0),
    "TRUA": (11, 30),
    "TOI": (18, 0),
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


def _split_caption(caption, topic):
    tags = re.findall(r"#\S+", caption)
    clean = re.sub(r"#\S+", "", caption).strip()
    first_sent = re.split(r"[.!?\n]", clean)[0].strip() or topic or "AI Shorts"
    title = first_sent[:88].strip()
    if "#shorts" not in title.lower():
        title = f"{title} #Shorts"
    desc = (
        f"{caption}\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🤖 Thiện AI Thực Chiến (@thiennguyen_ai)\n"
        "📩 Hỗ trợ AI & Nâng cấp Gemini Pro / Zalo: 0356.141.136\n"
        "⚡ Lịch video mới mỗi ngày: 05:00 | 11:30 | 18:00\n\n"
        "#Shorts " + " ".join(tags)
    )
    return title[:100], desc.strip()


def post_top_comment(yt, video_id, comment_text):
    """Tự động đăng 1 bình luận đầu tiên dưới video YouTube Shorts để tăng tương tác & chuyển đổi."""
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
        print(f"[youtube] đã tự động đăng bình luận đầu tiên trên video {video_id}")
        return True
    except Exception as ex:
        print(f"[youtube] bỏ qua đăng bình luận ({ex!r})")
        return False


def fetch_video_views(video_ids):
    """Đọc số lượt xem (viewCount) thực tế của danh sách video YouTube để Gemini học từ các bài nhiều view."""
    if not video_ids:
        return {}
    try:
        yt = get_youtube_service(["https://www.googleapis.com/auth/youtube.readonly"])
        res = yt.videos().list(part="statistics", id=",".join(video_ids[:50])).execute()
        out = {}
        for it in res.get("items", []):
            st = it.get("statistics", {})
            out[it["id"]] = int(st.get("viewCount", 0))
        return out
    except Exception as ex:
        print(f"[youtube] bỏ qua đọc analytics ({ex!r})")
        return {}


def upload_short(video_path, caption, topic="", slot="", auto_public=True, pinned_question=""):
    """Upload video lên YouTube Shorts:
    - Nếu bấm Duyệt trước giờ vàng của ca -> tự động Lên lịch Công khai (Scheduled) đúng 05:00 / 11:30 / 18:00 giờ VN.
    - Nếu bấm Duyệt sau giờ vàng của ca -> tự động bật Công khai (Public) ngay lập tức.
    - Tự động đăng 1 bình luận đầu tiên dưới video.
    """
    yt = get_youtube_service(["https://www.googleapis.com/auth/youtube.upload"])
    title, desc = _split_caption(caption, topic)
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
            "tags": list(dict.fromkeys(["Shorts", "AI", "CongNghe", "Gemini", "TikTok"] + [t.lstrip("#") for t in re.findall(r"#\w+", caption)]))[:15],
            "categoryId": "28",
            "defaultLanguage": "vi",
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
    print(f"[youtube] upload OK id={vid} mode={mode_note}")

    # Tự động thử đăng bình luận đầu tiên
    clean_line = re.sub(r"#\S+", "", caption).strip()
    q_line = pinned_question.strip() if pinned_question else "Bạn đang dùng công cụ AI nào mỗi ngày? Bình luận bên dưới nhé!"
    comment = f"💬 {q_line}\n━━━━━━━━━━━━━━━━━━━━\n📩 Hỗ trợ AI & Nâng cấp Gemini Pro chính chủ / Zalo: 0356.141.136"
    post_top_comment(yt, vid, comment)

    return f"https://youtube.com/shorts/{vid}", mode_note
