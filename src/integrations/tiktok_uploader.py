"""TikTok Content Posting API v2 + Display API (video.list):
Tự động kích hoạt ngay khi cấu hình GitHub Secret `TIKTOK_CREDENTIALS_JSON`:
{
  "client_key": "...",
  "client_secret": "...",
  "refresh_token": "...",
  "mode": "direct"   // "direct" (đăng thẳng Công khai) hoặc "inbox" (đẩy vào Hộp thư TikTok để gắn nhạc trend 1 chạm)
}
"""
import json
import math
import os
from pathlib import Path

import requests

OAUTH_URL = "https://open.tiktokapis.com/v2/oauth/token/"
DIRECT_INIT_URL = "https://open.tiktokapis.com/v2/post/publish/video/init/"
INBOX_INIT_URL = "https://open.tiktokapis.com/v2/post/publish/inbox/video/init/"
VIDEO_LIST_URL = "https://open.tiktokapis.com/v2/video/list/?fields=id,title,view_count,like_count,comment_count,share_count"


def _load_config():
    raw = os.environ.get("TIKTOK_CREDENTIALS_JSON", "").strip()
    if not raw or not raw.startswith("{"):
        return None
    try:
        cfg = json.loads(raw)
        if cfg.get("client_key") and cfg.get("client_secret") and cfg.get("refresh_token"):
            return cfg
    except Exception:
        pass
    return None


def is_configured():
    return _load_config() is not None


def _get_access_token(cfg):
    r = requests.post(
        OAUTH_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_key": cfg["client_key"],
            "client_secret": cfg["client_secret"],
            "grant_type": "refresh_token",
            "refresh_token": cfg["refresh_token"],
        },
        timeout=25,
    )
    data = r.json()
    if "access_token" not in data:
        raise RuntimeError(f"TikTok OAuth refresh lỗi: {data}")
    return data["access_token"]


def upload_tiktok(video_path, caption):
    """Upload video 9:16 lên TikTok (Direct Post hoặc Inbox Draft tùy theo `mode` trong TIKTOK_CREDENTIALS_JSON)."""
    cfg = _load_config()
    if not cfg:
        return None

    token = _get_access_token(cfg)
    mode = str(cfg.get("mode", "inbox")).lower()
    size = Path(video_path).stat().st_size
    chunk_size = min(size, 10 * 1024 * 1024) if size > 5 * 1024 * 1024 else size
    total_chunks = max(1, math.ceil(size / chunk_size))
    if total_chunks == 1:
        chunk_size = size

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=UTF-8",
    }

    if mode == "direct":
        init_url = DIRECT_INIT_URL
        body = {
            "post_info": {
                "title": str(caption or "")[:2100],
                "privacy_level": cfg.get("privacy_level", "PUBLIC_TO_EVERYONE"),
                "disable_duet": False,
                "disable_comment": False,
                "disable_stitch": False,
            },
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": size,
                "chunk_size": chunk_size,
                "total_chunk_count": total_chunks,
            },
        }
    else:
        init_url = INBOX_INIT_URL
        body = {
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": size,
                "chunk_size": chunk_size,
                "total_chunk_count": total_chunks,
            }
        }

    r_init = requests.post(init_url, headers=headers, json=body, timeout=30)
    res = r_init.json()
    err = res.get("error", {})
    if err.get("code") not in (None, "ok", ""):
        raise RuntimeError(f"TikTok init ({mode}) lỗi: {res}")

    upload_url = res["data"]["upload_url"]
    publish_id = res["data"].get("publish_id", "")

    with open(video_path, "rb") as fh:
        for idx in range(total_chunks):
            chunk = fh.read(chunk_size)
            start = idx * chunk_size
            end = start + len(chunk) - 1
            up_headers = {
                "Content-Type": "video/mp4",
                "Content-Length": str(len(chunk)),
                "Content-Range": f"bytes {start}-{end}/{size}",
            }
            r_up = requests.put(upload_url, headers=up_headers, data=chunk, timeout=180)
            if r_up.status_code not in (200, 201, 206):
                raise RuntimeError(f"TikTok chunk {idx + 1}/{total_chunks} HTTP {r_up.status_code}: {r_up.text[:160]}")

    status_label = "DIRECT_PUBLIC" if mode == "direct" else "INBOX_DRAFT"
    print(f"[tiktok] upload OK ({status_label}) publish_id={publish_id}")
    return f"tiktok://{status_label}/{publish_id}"


def fetch_tiktok_top_videos(limit=5):
    """Đọc danh sách video hiệu quả nhất trên TikTok (scope: video.list) để kết hợp vào bộ AI tự học."""
    cfg = _load_config()
    if not cfg:
        return []
    try:
        token = _get_access_token(cfg)
        r = requests.post(
            VIDEO_LIST_URL,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"max_count": 20},
            timeout=20,
        )
        videos = r.json().get("data", {}).get("videos", [])
        scored = []
        for v in videos:
            views = int(v.get("view_count") or 0)
            likes = int(v.get("like_count") or 0)
            cmts = int(v.get("comment_count") or 0)
            shares = int(v.get("share_count") or 0)
            score = views + likes * 30 + cmts * 70 + shares * 90
            title = str(v.get("title") or "").strip()
            if title and views > 0:
                scored.append((score, f"[TikTok {views} xem, {likes} tim, {shares} share] {title[:80]}"))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [x[1] for x in scored[:limit]]
    except Exception as ex:
        print(f"[tiktok] bỏ qua đọc video.list ({ex!r})")
        return []
