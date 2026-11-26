"""Facebook Reels Uploader (0đ) qua Meta Graph API v21.0:
Tự động đăng video 9:16 lên Fanpage Facebook Reels ở chế độ Công khai + Tự động đăng bình luận đầu tiên chứa Zalo.
Nếu chưa cấu hình FB_PAGE_ID / FB_PAGE_ACCESS_TOKEN thì tự động bỏ qua an toàn.
"""
import os
import re
from pathlib import Path

import requests

GRAPH_API = "https://graph.facebook.com/v21.0"
RUPLOAD_API = "https://rupload.facebook.com/video-upload/v21.0"


def is_configured():
    return bool(os.environ.get("FB_PAGE_ID", "").strip() and os.environ.get("FB_PAGE_ACCESS_TOKEN", "").strip())


def post_reel_comment(video_id, token, comment_text):
    """Tự động đăng bình luận đầu tiên dưới Facebook Reel (tốt cho thuật toán phân phối của Facebook)."""
    try:
        r = requests.post(
            f"{GRAPH_API}/{video_id}/comments",
            data={"message": comment_text, "access_token": token},
            timeout=30,
        )
        if r.status_code == 200:
            print(f"[facebook] đã tự động đăng bình luận đầu tiên dưới Reel {video_id}")
            return True
    except Exception as ex:
        print(f"[facebook] bỏ qua bình luận Reel ({ex!r})")
    return False


def upload_reel(video_path, caption, topic=""):
    """Đăng video 9:16 lên Facebook Page Reels theo quy trình 3 bước chuẩn của Meta (start -> rupload -> finish).
    Trả về URL Facebook Reel (hoặc None nếu chưa cấu hình).
    """
    page_id = os.environ.get("FB_PAGE_ID", "").strip()
    token = os.environ.get("FB_PAGE_ACCESS_TOKEN", "").strip()
    if not page_id or not token:
        return None

    video_path = Path(video_path)
    file_size = video_path.stat().st_size

    # Bước 1: Khởi tạo phiên upload Reels
    r1 = requests.post(
        f"{GRAPH_API}/{page_id}/video_reels",
        data={"upload_phase": "start", "access_token": token},
        timeout=30,
    )
    res1 = r1.json()
    if "video_id" not in res1:
        raise RuntimeError(f"Facebook Reels start lỗi: {res1}")
    video_id = res1["video_id"]
    upload_url = res1.get("upload_url") or f"{RUPLOAD_API}/{video_id}"

    # Bước 2: Đẩy binary file mp4 lên máy chủ rupload.facebook.com
    with open(video_path, "rb") as fh:
        r2 = requests.post(
            upload_url,
            headers={
                "Authorization": f"OAuth {token}",
                "offset": "0",
                "file_size": str(file_size),
                "Content-Type": "application/octet-stream",
            },
            data=fh,
            timeout=180,
        )
    res2 = r2.json()
    if not res2.get("success"):
        raise RuntimeError(f"Facebook Reels binary upload lỗi: {res2}")

    # Bước 3: Hoàn tất & xuất bản Công khai (PUBLISHED)
    desc = (
        f"{caption}\n\n"
        f"🤖 Thiện AI Thực Chiến — Mẹo AI & Tự động hóa 30s\n"
        f"⚡ Follow trang để lưu trọn bộ Series ứng dụng AI thực tế!\n"
        f"#reels #meoai #aithucchien #congnghe #thiennguyenai"
    )
    r3 = requests.post(
        f"{GRAPH_API}/{page_id}/video_reels",
        data={
            "upload_phase": "finish",
            "video_id": video_id,
            "video_state": "PUBLISHED",
            "description": desc,
            "access_token": token,
        },
        timeout=60,
    )
    res3 = r3.json()
    if not res3.get("success"):
        raise RuntimeError(f"Facebook Reels finish lỗi: {res3}")

    reel_url = f"https://www.facebook.com/reel/{video_id}"
    print(f"[facebook] upload Reel PUBLIC OK: {reel_url}")

    clean_line = re.sub(r"#\S+", "", caption).strip()
    cmt = (
        f"📌 {clean_line}\n"
        f"💬 Bạn đang muốn tự động hóa công việc nào bằng AI? Bình luận bên dưới mình làm hướng dẫn chi tiết nhé!"
    )
    post_reel_comment(video_id, token, cmt)
    return reel_url
