"""Gemini API (Free) sinh script.json chuẩn + caption + hashtag, có chống trùng chủ đề."""
import json
import os
import time

import requests

MODELS = ["gemini-3.1-flash-lite", "gemini-3.5-flash", "gemini-3.8-flash", "gemini-flash-latest"]
ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
THEMES = ["cyber_blue", "neon_purple", "emerald_tech", "sunset_amber"]
SCENE_TYPES = {"chat_demo", "comparison", "stat_card", "bullet_steps"}

SLOT_HINT = {
    "SANG": "Ca sáng: tin tức AI/công nghệ nhanh. Ưu tiên cảnh stat_card.",
    "TRUA": "Ca trưa: so sánh tính năng/chia sẻ giá trị, lồng ghép khéo léo dịch vụ (ví dụ gói Gemini Pro) một cách tự nhiên, "
            "không quảng cáo lộ liễu. Ưu tiên chat_demo + comparison.",
    "TOI": "Ca tối: mẹo thực chiến / quy trình 3 bước ứng dụng AI. Ưu tiên bullet_steps.",
}

SCHEMA_EXAMPLE = {
    "badge": "TIN CÔNG NGHỆ 2026",
    "bg_theme": "cyber_blue",
    "mascot": True,
    "voice": "vi-VN-HoaiMyNeural",
    "voice_rate": "+15%",
    "hook": {"headline": ["Dòng 1", "Dòng 2", "Dòng nhấn mạnh!"], "voiceover": "..."},
    "scenes": [
        {"type": "chat_demo", "title": "...", "user_prompt": "...", "ai_reply": "...", "voiceover": "..."},
        {"type": "comparison", "title": "...", "left_title": "...", "left_items": ["..", "..", ".."],
         "right_title": "...", "right_items": ["..", "..", ".."], "voiceover": "..."},
        {"type": "stat_card", "title": "...", "metric": "10X", "summary": "...", "bullets": ["..", ".."], "voiceover": "..."},
        {"type": "bullet_steps", "title": "...", "steps": ["..", "..", ".."], "voiceover": "..."},
    ],
    "cta": {"highlight_metric": "70%", "summary": "...", "button_text": "Xem chi tiết ở phần mô tả", "voiceover": "..."},
    "caption": "Tiêu đề + mô tả ngắn #ai #congnghe #shorts",
}


def build_prompt(topic, slot, recent, theme=None):
    avoid = "\n".join(f"- {t}" for t in recent) or "(chưa có)"
    return f"""Bạn là biên tập viên video ngắn tiếng Việt cho YouTube Shorts/TikTok (30-45 giây).
Chủ đề: {topic}
{SLOT_HINT.get(slot, '')}
{f'Dùng bg_theme = "{theme}".' if theme else 'Chọn bg_theme trong: ' + ', '.join(THEMES) + '.'}

Các chủ đề đã làm gần đây (KHÔNG lặp lại góc nhìn/nội dung):
{avoid}

Yêu cầu:
- Chỉ trả về MỘT đối tượng JSON hợp lệ, đúng cấu trúc mẫu dưới đây (giữ nguyên tên khóa), không markdown.
- Tiếng Việt có dấu, giọng tự nhiên, không bịa số liệu gây hiểu lầm.
- hook.headline: đúng 3 dòng, mỗi dòng tối đa 18 ký tự; dòng cuối là dòng nhấn mạnh.
- scenes: 3 đến 4 cảnh, mỗi loại tối đa 1 lần, chọn trong chat_demo, comparison, stat_card, bullet_steps.
- comparison: left_items và right_items cùng 3 mục, mỗi mục tối đa 28 ký tự. bullet_steps: đúng 3 bước, mỗi bước tối đa 60 ký tự.
- stat_card: metric ngắn (vd 10X, 70%, 3 phút); bullets 2 mục ngắn.
- Mỗi voiceover 12-28 từ, tổng thời lượng đọc khoảng 30-40 giây (hook + scenes + cta).
- caption: tiêu đề hấp dẫn + 1 câu mô tả + 3-5 hashtag, tối đa 220 ký tự.
- mascot=true, voice="vi-VN-HoaiMyNeural", voice_rate="+8%".

Cấu trúc mẫu:
{json.dumps(SCHEMA_EXAMPLE, ensure_ascii=False, indent=1)}"""


def validate(s):
    """Raise ValueError nếu script không hợp lệ cho engine; trả về script đã chuẩn hóa."""
    def need(cond, msg):
        if not cond:
            raise ValueError(msg)
    str_list = lambda v, n=1: isinstance(v, list) and len(v) >= n and all(isinstance(x, str) and x.strip() for x in v)
    need(isinstance(s, dict), "không phải object")
    if s.get("bg_theme") not in THEMES:
        s["bg_theme"] = THEMES[0]
    s.setdefault("badge", "")
    s["mascot"] = bool(s.get("mascot", True))
    s.setdefault("voice", "vi-VN-HoaiMyNeural")
    s.setdefault("voice_rate", "+8%")
    h = s.get("hook")
    need(isinstance(h, dict) and str_list(h.get("headline"), 1) and h.get("voiceover"), "hook sai")
    h["headline"] = h["headline"][:3]
    need(isinstance(s.get("scenes"), list) and 1 <= len(s["scenes"]) <= 5, "scenes sai")
    for sc in s["scenes"]:
        t = sc.get("type")
        need(t in SCENE_TYPES and sc.get("voiceover") and sc.get("title"), f"scene sai: {t}")
        if t == "chat_demo":
            need(sc.get("user_prompt") and sc.get("ai_reply"), "chat_demo thiếu trường")
        elif t == "comparison":
            need(sc.get("left_title") and sc.get("right_title") and str_list(sc.get("left_items"), 2)
                 and str_list(sc.get("right_items"), 2), "comparison thiếu trường")
            n = min(len(sc["left_items"]), len(sc["right_items"]), 3)
            sc["left_items"], sc["right_items"] = sc["left_items"][:n], sc["right_items"][:n]
        elif t == "stat_card":
            need(sc.get("metric") and sc.get("summary"), "stat_card thiếu trường")
            sc["bullets"] = [b for b in sc.get("bullets", []) if isinstance(b, str)][:3]
        elif t == "bullet_steps":
            need(str_list(sc.get("steps"), 2), "bullet_steps thiếu steps")
            sc["steps"] = sc["steps"][:4]
    c = s.get("cta")
    need(isinstance(c, dict) and c.get("highlight_metric") and c.get("summary") and c.get("voiceover"), "cta sai")
    c.setdefault("button_text", "Xem chi tiết ở phần mô tả")
    need(isinstance(s.get("caption"), str) and s["caption"].strip(), "thiếu caption")
    return s


def _call(model, prompt, key):
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"response_mime_type": "application/json", "temperature": 0.9}}
    r = requests.post(ENDPOINT.format(model=model), headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                      json=body, timeout=60)
    if r.status_code != 200:
        raise RuntimeError(f"{model} HTTP {r.status_code}: {r.text[:200]}")
    data = r.json()
    parts = data["candidates"][0]["content"]["parts"]
    text = "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    return json.loads(text)


def generate_script(topic, slot="", recent=(), theme=None, api_key=None, retries=2):
    """Sinh script.json hợp lệ. Thử lần lượt các model Free, retry khi JSON/schema sai."""
    key = api_key or os.environ["GEMINI_API_KEY"]
    prompt = build_prompt(topic, slot, list(recent), theme)
    last = None
    for model in MODELS:
        for attempt in range(retries + 1):
            try:
                script = validate(_call(model, prompt, key))
                if theme in THEMES:
                    script["bg_theme"] = theme
                print(f"[gemini] OK model={model}")
                return script
            except Exception as ex:
                last = ex
                print(f"[gemini] {model} lần {attempt + 1} lỗi: {str(ex)[:160]}")
                if "HTTP 404" in str(ex) or "HTTP 400" in str(ex):
                    break  # model không dùng được -> đổi model
                time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"Gemini không sinh được script hợp lệ: {last}")
