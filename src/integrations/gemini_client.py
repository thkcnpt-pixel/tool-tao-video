"""Gemini API (Free) sinh script.json chuẩn + tự săn tin RSS 0đ cho Ca Sáng + hỗ trợ 6 loại cảnh + đảo giọng Nam/Nữ."""
import json
import os
import time
import xml.etree.ElementTree as ET

import requests

MODELS = ["gemini-3.1-flash-lite", "gemini-3.5-flash", "gemini-3.8-flash", "gemini-flash-latest"]
ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
THEMES = ["cyber_blue", "neon_purple", "emerald_tech", "sunset_amber"]
SCENE_TYPES = {"chat_demo", "comparison", "stat_card", "bullet_steps", "prompt_card", "myth_vs_fact"}

SLOT_HINT = {
    "SANG": "Ca sáng: tin tức AI/công nghệ nhanh. Ưu tiên cảnh stat_card + myth_vs_fact.",
    "TRUA": "Ca trưa: so sánh tính năng/chia sẻ giá trị, lồng ghép khéo léo dịch vụ (ví dụ gói Gemini Pro) một cách tự nhiên, "
            "không quảng cáo lộ liễu. Ưu tiên chat_demo + comparison.",
    "TOI": "Ca tối: mẹo thực chiến / quy trình 3 bước ứng dụng AI. Ưu tiên prompt_card + bullet_steps.",
}

SLOT_VOICE = {
    "SANG": "vi-VN-HoaiMyNeural",
    "TRUA": "vi-VN-NamMinhNeural",
    "TOI": "vi-VN-HoaiMyNeural",
}

RSS_URLS = [
    "https://news.google.com/rss/search?q=AI+OR+Gemini+OR+ChatGPT+when:2d&hl=vi&gl=VN&ceid=VN:vi",
    "https://vnexpress.net/rss/so-hoa.rss",
]

SCHEMA_EXAMPLE = {
    "badge": "TIN CÔNG NGHỆ 2026",
    "bg_theme": "cyber_blue",
    "mascot": True,
    "voice": "vi-VN-HoaiMyNeural",
    "voice_rate": "+22%",
    "hook": {"headline": ["Dòng 1", "Dòng 2", "Dòng nhấn mạnh!"], "voiceover": "..."},
    "scenes": [
        {"type": "chat_demo", "title": "...", "user_prompt": "...", "ai_reply": "...", "voiceover": "..."},
        {"type": "prompt_card", "title": "Câu lệnh mẫu thực chiến", "prompt_text": "Hãy đóng vai chuyên gia...",
         "result_note": "Rút ngắn 80% thời gian", "voiceover": "..."},
        {"type": "myth_vs_fact", "title": "90% người dùng hiểu sai", "myth": "Hỏi AI câu ngắn cụt lủn",
         "fact": "Giao vai trò + bối cảnh + định dạng đầu ra rõ ràng", "voiceover": "..."},
        {"type": "comparison", "title": "...", "left_title": "...", "left_items": ["..", "..", ".."],
         "right_title": "...", "right_items": ["..", "..", ".."], "voiceover": "..."},
        {"type": "stat_card", "title": "...", "metric": "10X", "summary": "...", "bullets": ["..", ".."], "voiceover": "..."},
        {"type": "bullet_steps", "title": "...", "steps": ["..", "..", ".."], "voiceover": "..."},
    ],
    "cta": {"highlight_metric": "70%", "summary": "...", "button_text": "Xem chi tiết ở phần mô tả", "voiceover": "..."},
    "caption": "Tiêu đề + mô tả ngắn #ai #congnghe #shorts",
}


def fetch_tech_headlines(limit=8):
    """Đọc RSS công nghệ/AI miễn phí trong ngày để cung cấp tin nóng cho Gemini."""
    items = []
    for url in RSS_URLS:
        try:
            r = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code != 200:
                continue
            root = ET.fromstring(r.content)
            for it in root.findall(".//item/title")[:limit]:
                if it.text and len(it.text.strip()) > 15:
                    items.append(it.text.strip())
        except Exception:
            continue
    return items[:limit]


def build_prompt(topic, slot, recent, theme=None, top_hooks=()):
    avoid = "\n".join(f"- {t}" for t in recent) or "(chưa có)"
    voice = SLOT_VOICE.get(slot, "vi-VN-HoaiMyNeural")
    return f"""Bạn là biên tập viên video ngắn tiếng Việt cho YouTube Shorts/TikTok (28-38 giây).
Chủ đề: {topic}
{SLOT_HINT.get(slot, '')}
{f'Dùng bg_theme = "{theme}".' if theme else 'Chọn bg_theme trong: ' + ', '.join(THEMES) + '.'}

Các chủ đề đã làm gần đây (KHÔNG lặp lại góc nhìn/nội dung):
{avoid}

Các video hiệu quả nhất của kênh để học phong cách giật tít Hook ngắn gọn, cuốn hút:
{chr(10).join("- " + h for h in top_hooks) if top_hooks else "(đang thu thập dữ liệu)"}

Yêu cầu:
- Chỉ trả về MỘT đối tượng JSON hợp lệ, đúng cấu trúc mẫu dưới đây (giữ nguyên tên khóa), không markdown.
- Tiếng Việt có dấu, giọng tự nhiên, không bịa số liệu gây hiểu lầm.
- hook.headline: đúng 3 dòng, mỗi dòng tối đa 18 ký tự; dòng cuối là dòng nhấn mạnh.
- scenes: chọn 3 đến 4 cảnh phù hợp nhất trong 6 loại: chat_demo, prompt_card, myth_vs_fact, comparison, stat_card, bullet_steps (mỗi loại tối đa 1 lần).
- prompt_card: prompt_text là 1 câu lệnh mẫu thực tế 15-28 từ để người xem bấm tạm dừng lưu lại; result_note tối đa 40 ký tự.
- myth_vs_fact: myth (sai lầm phổ biến) và fact (cách làm đúng) mỗi mục tối đa 65 ký tự.
- comparison: left_items và right_items cùng 3 mục, mỗi mục tối đa 28 ký tự. bullet_steps: đúng 3 bước, mỗi bước tối đa 60 ký tự.
- stat_card: metric bắt đầu bằng con số (vd 10X, 70%, 3X, 85%) để chạy hiệu ứng đếm số; bullets 2 mục ngắn.
- cta.highlight_metric: bắt đầu bằng con số (vd 70%, 10X, 3 giờ).
- Mỗi voiceover 12-26 từ, tổng thời lượng đọc khoảng 25-35 giây.
- caption: tiêu đề hấp dẫn + 1 câu mô tả + 3-5 hashtag, tối đa 220 ký tự.
- mascot=true, voice="{voice}", voice_rate="+22%".

Cấu trúc mẫu (chỉ chọn 3-4 cảnh trong danh sách scenes):
{json.dumps(SCHEMA_EXAMPLE, ensure_ascii=False, indent=1)}"""


def validate(s, slot=""):
    """Raise ValueError nếu script không hợp lệ cho engine; trả về script đã chuẩn hóa."""
    def need(cond, msg):
        if not cond:
            raise ValueError(msg)
    str_list = lambda v, n=1: isinstance(v, list) and len(v) >= n and all(isinstance(x, str) and x.strip() for x in v)
    need(isinstance(s, dict), "không phải object")
    if s.get("bg_theme") not in THEMES:
        s["bg_theme"] = THEMES[0]
    s.setdefault("badge", "TIN CÔNG NGHỆ 2026")
    s["mascot"] = bool(s.get("mascot", True))
    if s.get("voice") not in ("vi-VN-HoaiMyNeural", "vi-VN-NamMinhNeural"):
        s["voice"] = SLOT_VOICE.get(slot, "vi-VN-HoaiMyNeural")
    s.setdefault("voice_rate", "+22%")
    h = s.get("hook")
    need(isinstance(h, dict) and str_list(h.get("headline"), 1) and h.get("voiceover"), "hook sai")
    h["headline"] = h["headline"][:3]
    need(isinstance(s.get("scenes"), list) and 1 <= len(s["scenes"]) <= 5, "scenes sai")
    for sc in s["scenes"]:
        t = sc.get("type")
        need(t in SCENE_TYPES and sc.get("voiceover") and sc.get("title"), f"scene sai: {t}")
        if t == "chat_demo":
            need(sc.get("user_prompt") and sc.get("ai_reply"), "chat_demo thiếu trường")
        elif t == "prompt_card":
            need(sc.get("prompt_text"), "prompt_card thiếu prompt_text")
            sc.setdefault("result_note", "Chuẩn xác & tiết kiệm thời gian")
        elif t == "myth_vs_fact":
            need(sc.get("myth") and sc.get("fact"), "myth_vs_fact thiếu myth/fact")
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


def generate_script(topic, slot="", recent=(), theme=None, api_key=None, retries=2, top_hooks=()):
    """Sinh script.json hợp lệ. Thử lần lượt các model Free, retry khi JSON/schema sai."""
    key = api_key or os.environ["GEMINI_API_KEY"]
    prompt = build_prompt(topic, slot, list(recent), theme, top_hooks=top_hooks)
    last = None
    for model in MODELS:
        for attempt in range(retries + 1):
            try:
                script = validate(_call(model, prompt, key), slot=slot)
                if theme in THEMES:
                    script["bg_theme"] = theme
                print(f"[gemini] OK model={model} voice={script['voice']} scenes={[x['type'] for x in script['scenes']]}")
                return script
            except Exception as ex:
                last = ex
                print(f"[gemini] {model} lần {attempt + 1} lỗi: {str(ex)[:160]}")
                if "HTTP 404" in str(ex) or "HTTP 400" in str(ex):
                    break
                time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"Gemini không sinh được script hợp lệ: {last}")


def generate_topic(slot, recent=(), api_key=None):
    """Tự động nghĩ ra 1 chủ đề mới theo ca (ưu tiên tin RSS mới cho Ca Sáng), không trùng với recent."""
    key = api_key or os.environ["GEMINI_API_KEY"]
    avoid = "\n".join(f"- {t}" for t in recent) or "(chưa có)"
    news_block = ""
    if slot == "SANG":
        headlines = fetch_tech_headlines()
        if headlines:
            news_block = "\nTin tức công nghệ/AI mới nhất hôm nay (hãy chọn 1 tin thú vị nhất để làm chủ đề):\n" + "\n".join(f"- {h}" for h in headlines)

    prompt = f"""Bạn là biên tập viên kênh YouTube Shorts / TikTok về AI & Công nghệ năm 2026.
Ca phát sóng: {slot} — {SLOT_HINT.get(slot, '')}{news_block}
Các chủ đề đã làm gần đây (TUYỆT ĐỐI KHÔNG TRÙNG LẶP):
{avoid}

Hãy đề xuất 1 chủ đề video ngắn (30-40 giây) mới mẻ, thực tế, dễ thu hút người xem Việt Nam.
Trả về JSON đúng định dạng: {{"topic": "Tên chủ đề ngắn gọn 10-18 từ", "bg_theme": "cyber_blue|neon_purple|emerald_tech|sunset_amber"}}"""
    for model in MODELS:
        try:
            res = _call(model, prompt, key)
            topic = str(res.get("topic", "")).strip()
            theme = res.get("bg_theme") if res.get("bg_theme") in THEMES else THEMES[0]
            if topic:
                print(f"[gemini] tự sinh chủ đề mới ({slot}): {topic}")
                return topic, theme
        except Exception as ex:
            print(f"[gemini] generate_topic {model} lỗi: {ex}")
    return f"Mẹo ứng dụng AI tiết kiệm thời gian ca {slot}", THEMES[0]
