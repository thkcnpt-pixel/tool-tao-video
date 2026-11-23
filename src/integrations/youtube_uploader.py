"""Upload YouTube Shorts chế độ Private qua YouTube Data API v3 (OAuth Refresh Token)."""
import json
import os
import re

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

YT_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def _parse_client_secret():
    raw = os.environ.get("YOUTUBE_CLIENT_SECRET_JSON", "").strip()
    if not raw:
        raise RuntimeError("Thiếu YOUTUBE_CLIENT_SECRET_JSON")
    if raw.startswith("{"):
        data = json.loads(raw)
        box = data.get("installed") or data.get("web") or data
        return box["client_id"], box["client_secret"]
    raise RuntimeError("YOUTUBE_CLIENT_SECRET_JSON không phải JSON hợp lệ")


def get_youtube_service():
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
        scopes=YT_SCOPES,
    )
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def _split_caption(caption, topic):
    """Tách caption thành (title <= 100 ký tự có #Shorts, description)."""
    tags = re.findall(r"#\S+", caption)
    clean = re.sub(r"#\S+", "", caption).strip()
    first_sent = re.split(r"[.!?\n]", clean)[0].strip() or topic or "AI Shorts"
    title = first_sent[:88].strip()
    if "#shorts" not in title.lower():
        title = f"{title} #Shorts"
    desc = f"{caption}\n\n#Shorts " + " ".join(tags)
    return title[:100], desc.strip()


def upload_short(video_path, caption, topic="", privacy="private", publish_at=None):
    """Upload video lên YouTube ở chế độ Private. Trả về URL YouTube Shorts."""
    yt = get_youtube_service()
    title, desc = _split_caption(caption, topic)
    body = {
        "snippet": {
            "title": title,
            "description": desc,
            "tags": list(dict.fromkeys(["Shorts", "AI", "CongNghe", "Gemini", "TikTok"] + [t.lstrip("#") for t in re.findall(r"#\w+", caption)]))[:15],
            "categoryId": "28",  # Science & Technology
            "defaultLanguage": "vi",
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
            **({"publishAt": publish_at} if publish_at and privacy == "private" else {}),
        },
    }
    media = MediaFileUpload(video_path, mimetype="video/mp4", resumable=True, chunksize=4 * 1024 * 1024)
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    vid = resp["id"]
    return f"https://youtube.com/shorts/{vid}"
