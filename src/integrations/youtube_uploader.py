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


_RESOLVED_CLIENT = None


def _candidate_clients():
    pairs = []
    raw = os.environ.get("YOUTUBE_CLIENT_SECRET_JSON", "").strip()
    if raw.startswith("{"):
        try:
            data = json.loads(raw)
            box = data.get("installed") or data.get("web") or data
            if box.get("client_id") and box.get("client_secret"):
                pairs.append((box["client_id"], box["client_secret"]))
        except Exception:
            pass
    d_cid = os.environ.get("DRIVE_OAUTH_CLIENT_ID", "").strip()
    d_sec = os.environ.get("DRIVE_OAUTH_CLIENT_SECRET", "").strip()
    if d_cid and d_sec and (d_cid, d_sec) not in pairs:
        pairs.append((d_cid, d_sec))
    if not pairs:
        raise RuntimeError("Thiếu YOUTUBE_CLIENT_SECRET_JSON / DRIVE_OAUTH_CLIENT_ID")
    return pairs


def _build_credentials(scopes=None):
    global _RESOLVED_CLIENT
    from google.auth.transport.requests import Request as GoogleAuthRequest

    rt = os.environ.get("YOUTUBE_REFRESH_TOKEN", "").strip()
    if not rt:
        raise RuntimeError("Thiếu YOUTUBE_REFRESH_TOKEN")

    candidates = [_RESOLVED_CLIENT] if _RESOLVED_CLIENT else _candidate_clients()
    last_err = None
    for cid, csec in candidates:
        try:
            creds = Credentials(
                token=None,
                refresh_token=rt,
                client_id=cid,
                client_secret=csec,
                token_uri="https://oauth2.googleapis.com/token",
                scopes=scopes or YT_SCOPES,
            )
            creds.refresh(GoogleAuthRequest())
            _RESOLVED_CLIENT = (cid, csec)
            return creds
        except Exception as ex:
            last_err = ex
            if "unauthorized_client" in str(ex) or "invalid_client" in str(ex):
                continue
            raise
    raise last_err


def _parse_client_secret():
    if _RESOLVED_CLIENT:
        return _RESOLVED_CLIENT
    return _candidate_clients()[0]


def get_youtube_service(scopes=None):
    creds = _build_credentials(scopes=scopes or YT_SCOPES)
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


def post_top_comment(video_id, comment_text):
    """Tự động đăng 1 bình luận đầu tiên dưới video YouTube Shorts (tách riêng scope force-ssl để không ảnh hưởng upload)."""
    try:
        yt_cmt = get_youtube_service(["https://www.googleapis.com/auth/youtube.force-ssl"])
        yt_cmt.commentThreads().insert(
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
        print(f"[youtube] bỏ qua đăng bình luận (token chỉ cấp quyền upload, Prompt đã gắn ở đầu Mô tả: {ex!r})")
        return False


def fetch_retention_analytics(video_ids):
    """Đọc Tỷ lệ giữ chân trung bình (averageViewPercentage %) từ YouTube Analytics API (scope: yt-analytics.readonly)."""
    if not video_ids:
        return {}
    try:
        yta = build(
            "youtubeAnalytics", "v2",
            credentials=_build_credentials(["https://www.googleapis.com/auth/yt-analytics.readonly"]),
            cache_discovery=False,
        )
        today = datetime.datetime.now(VN).date()
        start = (today - datetime.timedelta(days=60)).strftime("%Y-%m-%d")
        end = today.strftime("%Y-%m-%d")
        res = yta.reports().query(
            ids="channel==MINE",
            startDate=start,
            endDate=end,
            metrics="views,averageViewPercentage,likes,comments",
            dimensions="video",
            filters=f"video=={','.join(video_ids[:40])}",
        ).execute()
        out = {}
        for row in res.get("rows", []):
            vid, v, apv = row[0], int(row[1]), float(row[2])
            out[vid] = {"views": v, "apv": round(apv, 1)}
        return out
    except Exception:
        return {}


def fetch_audience_comments(video_ids, limit=8):
    """Đọc các bình luận/câu hỏi thực tế của người xem dưới các video đã đăng để AI tự tạo nội dung trả lời đúng nhu cầu."""
    if not video_ids:
        return []
    comments = []
    try:
        yt = get_youtube_service(["https://www.googleapis.com/auth/youtube.readonly"])
        for vid in list(reversed(video_ids))[:6]:
            try:
                res = yt.commentThreads().list(
                    part="snippet", videoId=vid, maxResults=5, order="relevance", textFormat="plainText"
                ).execute()
                for it in res.get("items", []):
                    top = it.get("snippet", {}).get("topLevelComment", {}).get("snippet", {})
                    txt = str(top.get("textDisplay") or "").strip()
                    # Bỏ qua bình luận ghim Prompt của chính chủ kênh
                    if not txt or "MẪU CÂU LỆNH ĐẦY ĐỦ" in txt or "Comment ý kiến của bạn" in txt:
                        continue
                    if len(txt) >= 8:
                        comments.append(txt[:140])
            except Exception:
                continue
    except Exception:
        pass
    return comments[:limit]


def fetch_video_metrics(video_ids):
    """Đọc lượt xem + lượt thích + bình luận + % giữ chân (APV) thực tế và tính điểm chất lượng (Engagement & Retention Score)."""
    if not video_ids:
        return {}
    try:
        yt = get_youtube_service(["https://www.googleapis.com/auth/youtube.readonly"])
        res = yt.videos().list(part="statistics", id=",".join(video_ids[:50])).execute()
        ret_map = fetch_retention_analytics(video_ids)
        out = {}
        for it in res.get("items", []):
            vid = it["id"]
            st = it.get("statistics", {})
            v = int(st.get("viewCount", 0))
            lk = int(st.get("likeCount", 0))
            cm = int(st.get("commentCount", 0))
            apv = ret_map.get(vid, {}).get("apv", 0.0)
            # Trọng số học máy: Views + 35*Likes + 80*Comments + thưởng lớn cho video giữ chân APV > 70%
            apv_bonus = int(max(0.0, apv - 50.0) * 12) if apv else 0
            score = v + lk * 35 + cm * 80 + apv_bonus
            out[vid] = {"views": v, "likes": lk, "comments": cm, "apv": apv, "score": score}
        return out
    except Exception:
        return {}


def fetch_video_views(video_ids):
    """Đọc số lượt xem (viewCount) thực tế (tương thích ngược)."""
    metrics = fetch_video_metrics(video_ids)
    return {vid: m["views"] for vid, m in metrics.items()}


def upload_short(video_path, caption, topic="", slot="", auto_public=True, pinned_question="", youtube_title="", full_prompt=""):
    """Upload video lên YouTube Shorts:
    - Dùng đúng scope youtube.upload để tương thích 100% với Refresh Token hiện tại.
    - Gắn trọn bộ Prompt mẫu đầy đủ ngay đầu Mô tả + thử ghim Bình luận đầu tiên.
    """
    yt = get_youtube_service(["https://www.googleapis.com/auth/youtube.upload"])
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

    comment = format_prompt_comment(full_prompt, pinned_question)
    if not publish_at and privacy == "public":
        post_top_comment(vid, comment)

    return f"https://youtube.com/shorts/{vid}", mode_note


def format_prompt_comment(full_prompt="", pinned_question=""):
    q_line = (pinned_question or "").strip() or "Bạn đang tốn nhiều thời gian nhất cho việc nào mỗi ngày? Comment bên dưới nhé!"
    if full_prompt and str(full_prompt).strip():
        return (
            f"📌 MẪU CÂU LỆNH ĐẦY ĐỦ (Chạm giữ để Copy dùng ngay):\n"
            f"“{str(full_prompt).strip()}”\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💬 {q_line}"
        )
    return f"💬 {q_line}\n👉 Comment ý kiến của bạn, mình trả lời từng bình luận nhé!"


def backfill_scheduled_comments(rows, check_latest=6):
    """Tự động đăng bù Bình luận đầu tiên (chứa Full Prompt) cho các video Scheduled Public ngay sau khi đến giờ lên sóng Công khai."""
    candidates = []
    for r in reversed(rows):
        if r.get("status") != "DA_DANG":
            continue
        ref = str(r.get("video_url_or_drive_id", ""))
        if "|" in ref:
            candidates.append((ref.split("|", 1)[1], r))
        if len(candidates) >= check_latest:
            break
    if not candidates:
        return 0
    try:
        yt = get_youtube_service(["https://www.googleapis.com/auth/youtube.readonly"])
        vids = [c[0] for c in candidates]
        res = yt.videos().list(part="status,statistics", id=",".join(vids)).execute()
        info = {it["id"]: it for it in res.get("items", [])}
    except Exception:
        return 0

    posted = 0
    for vid, row in candidates:
        it = info.get(vid)
        if not it:
            continue
        priv = it.get("status", {}).get("privacyStatus")
        cmts = int(it.get("statistics", {}).get("commentCount", 0))
        if priv == "public" and cmts == 0:
            sc_obj = {}
            try:
                sc_obj = json.loads(row.get("script_json") or "{}")
            except Exception:
                pass
            cmt = format_prompt_comment(sc_obj.get("full_prompt", ""), sc_obj.get("pinned_question", ""))
            if post_top_comment(vid, cmt):
                posted += 1
    return posted
