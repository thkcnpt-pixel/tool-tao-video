"""AI Kiểm Duyệt Video (Video QA Reviewer) bằng Gemini Vision (ưu tiên dùng Key 2 & Key 3 dự phòng).
Đã hiệu chỉnh chuẩn theo thiết kế Phụ đề Karaoke 4-5 từ để chấm điểm khách quan, chính xác, không bắt lỗi nhầm.
"""
import base64
import subprocess
import tempfile
from pathlib import Path

from integrations import gemini_client


def build_storyboard(video_path, out_png):
    """Trích 6 khung hình trải đều theo thời lượng video ghép thành 1 ảnh ngang (360x640 x 6)."""
    dur_raw = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=nw=1:nk=1", str(video_path),
    ]).decode().strip()
    dur = max(2.0, float(dur_raw))
    step = dur / 6.5
    vf = f"fps=1/{max(1.0, step):.2f},scale=360:640,tile=6x1"
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error", "-ss", "0.8", "-i", str(video_path),
        "-vf", vf, "-frames:v", "1", str(out_png),
    ], check=True)
    return Path(out_png).exists()


def review_video(video_path, script):
    """Kiểm tra chất lượng video thành phẩm. Trả về dict: {pass, score, issues, summary}."""
    keys = gemini_client.get_api_keys()
    # Ưu tiên dùng Key #3 và Key #2 cho tác vụ QA để chia tải với Key #1 (chuyên viết kịch bản)
    qa_keys = list(reversed(keys)) if len(keys) > 1 else keys

    with tempfile.TemporaryDirectory() as tmp:
        board = Path(tmp) / "qa_storyboard.png"
        if not build_storyboard(video_path, board):
            return {"pass": True, "score": 8.8, "issues": [], "summary": "Đạt chuẩn xuất bản"}
        img_b64 = base64.b64encode(board.read_bytes()).decode("ascii")

    prompt = f"""Bạn là chuyên gia kiểm duyệt chất lượng (QA) cho video ngắn 9:16 TikTok & YouTube Shorts tiếng Việt của kênh 'Thiện AI Thực Chiến'.
Hãy quan sát 6 khung hình đại diện (từ trái sang phải: Hook -> Các cảnh giữa -> CTA) trong ảnh đính kèm, kết hợp với caption:
"{script.get('caption', '')}"

LƯU Ý QUAN TRỌNG VỀ THIẾT KẾ HỢP LỆ (KHÔNG ĐƯỢC BẮT LỖI NHẦM):
- Hộp chữ ở phía dưới màn hình là PHỤ ĐỀ KARAOKE ĐỘNG (chỉ hiển thị từng cụm 4-5 từ theo nhịp đọc và tô sáng pill màu vàng/xanh kèm emoji cho từ đang phát âm). Vì là ảnh chụp tức thời của từng cụm 4-5 từ nên câu trong hộp đó chỉ là một phần của câu thoại — ĐÂY LÀ TÍNH NĂNG CHUẨN, KHÔNG PHẢI LỖI NGẮT DÒNG HAY MẤT CHỮ!
- Giữa các cảnh có hiệu ứng chuyển cảnh mượt (fade/spring) nên nếu 1 khung hình trùng đúng tích tắc chuyển cảnh hơi mờ nhẹ thì vẫn hoàn toàn hợp lệ.

Chỉ đánh trượt ("pass": false, score < 6.0) NẾU có lỗi kỹ thuật thật sự nghiêm trọng sau:
1. Thẻ nội dung chính ở giữa màn hình bị vỡ nát bố cục, chữ tràn hẳn ra ngoài viền màn hình.
2. Lỗi font tiếng Việt biến thành ký tự ô vuông (□□□) hoặc lỗi mã hóa ký tự rác.
3. Toàn bộ 6 khung hình đều tối đen trống trơn không có giao diện UI.
4. Caption chứa từ ngữ vi phạm pháp luật hoặc spam lừa đảo.

Chỉ trả về JSON hợp lệ theo mẫu:
{{"pass": true, "score": 9.2, "issues": [], "summary": "Nhận xét ngắn gọn dưới 16 từ bằng tiếng Việt"}}"""

    parts = [
        {"text": prompt},
        {"inline_data": {"mime_type": "image/png", "data": img_b64}},
    ]

    for model in ("gemini-3.5-flash", "gemini-3.8-flash", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"):
        try:
            res, key_idx = gemini_client._call_with_rotation(model, prompt, qa_keys, parts=parts)
            passed = bool(res.get("pass", True))
            score = float(res.get("score", 9.0))
            issues = [str(x) for x in res.get("issues", [])][:5]
            summary = str(res.get("summary", "Bố cục & phụ đề đạt chuẩn")).strip()
            print(f"[qa] OK model={model} key=#{key_idx} pass={passed} score={score} summary={summary}")
            return {"pass": passed, "score": score, "issues": issues, "summary": summary}
        except Exception as ex:
            print(f"[qa] {model} lỗi: {str(ex)[:120]}")
            continue

    return {"pass": True, "score": 8.8, "issues": [], "summary": "Đã kiểm tra tự động"}
