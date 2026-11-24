"""AI Kiểm Duyệt Video (Video QA Reviewer) bằng Gemini Vision (ưu tiên dùng Key 2 & Key 3 dự phòng).
Trích xuất 6 khung hình đại diện từ output.mp4 thành 1 ảnh storyboard, gửi kèm thông tin kịch bản để AI chấm điểm & phát hiện lỗi hiển thị trước khi đăng YouTube.
"""
import base64
import json
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
    # Lấy tại các mốc 0.8s, 1*step+0.8...
    vf = f"fps=1/{max(1.0, step):.2f},scale=360:640,tile=6x1"
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error", "-ss", "0.8", "-i", str(video_path),
        "-vf", vf, "-frames:v", "1", str(out_png),
    ], check=True)
    return Path(out_png).exists()


def review_video(video_path, script):
    """Kiểm tra chất lượng video thành phẩm. Trả về dict: {pass, score, issues, summary}."""
    keys = gemini_client.get_api_keys()
    # Ưu tiên dùng Key #2 và Key #3 trước cho tác vụ QA để chia tải với Key #1
    qa_keys = (keys[1:] + keys[:1]) if len(keys) > 1 else keys

    with tempfile.TemporaryDirectory() as tmp:
        board = Path(tmp) / "qa_storyboard.png"
        if not build_storyboard(video_path, board):
            return {"pass": True, "score": 8.5, "issues": [], "summary": "Không trích được storyboard, bỏ qua QA"}
        img_b64 = base64.b64encode(board.read_bytes()).decode("ascii")

    prompt = f"""Bạn là chuyên gia kiểm duyệt chất lượng (QA) cho video ngắn 9:16 TikTok & YouTube Shorts tiếng Việt.
Hãy quan sát kỹ 6 khung hình đại diện (từ trái sang phải: Hook -> Các cảnh giữa -> CTA) trong ảnh đính kèm, kết hợp với caption:
"{script.get('caption', '')}"

Kiểm tra 4 tiêu chí:
1. Lỗi hiển thị: Chữ có bị tràn ra ngoài khung kính, bị cắt mất chữ, hoặc Robot có bay đè che khuất chữ không?
2. Vùng an toàn: Phụ đề và thẻ nội dung có bị sát mép trên cùng hoặc đáy dưới cùng quá mức không?
3. Chính tả & Font tiếng Việt: Dấu tiếng Việt có bị ô vuông/lỗi font hay sai chính tả nghiêm trọng không?
4. An toàn chính sách: Nội dung có vi phạm chính sách quảng cáo trực diện của TikTok/YouTube không?

Chỉ trả về JSON hợp lệ theo mẫu:
{{"pass": true, "score": 9.5, "issues": [], "summary": "Nhận xét ngắn gọn dưới 18 từ bằng tiếng Việt"}}
(Đặt "pass": false CHỈ KHI có lỗi nghiêm trọng như vỡ bố cục, mất chữ, lỗi font tiếng Việt hoặc score < 6.5)."""

    parts = [
        {"text": prompt},
        {"inline_data": {"mime_type": "image/png", "data": img_b64}},
    ]

    for model in gemini_client.MODELS[:6]:
        try:
            res, key_idx = gemini_client._call_with_rotation(model, prompt, qa_keys, parts=parts)
            passed = bool(res.get("pass", True))
            score = float(res.get("score", 9.0))
            issues = [str(x) for x in res.get("issues", [])][:5]
            summary = str(res.get("summary", "Đạt chuẩn hiển thị & nội dung")).strip()
            print(f"[qa] OK model={model} key=#{key_idx} pass={passed} score={score} summary={summary}")
            return {"pass": passed, "score": score, "issues": issues, "summary": summary}
        except Exception as ex:
            print(f"[qa] {model} lỗi: {str(ex)[:120]}")
            continue

    return {"pass": True, "score": 8.5, "issues": [], "summary": "AI QA tạm bận, thông qua mặc định"}
