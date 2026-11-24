"""Gemini API (Free) với 8 model dự phòng + Fallback Template chống lỗi 503 tuyệt đối + 8 loại cảnh + Slot-Aware CTA + Smart Pinned Question."""
import json
import os
import time
import xml.etree.ElementTree as ET

import requests

# Chuỗi 8 model Free của Google AI Studio để khi 1-2 model bị 503 High Demand sẽ sang ngay model rảnh
MODELS = [
    "gemini-3.5-flash-lite",
    "gemini-3.5-flash",
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash",
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-omni-1.2-flash",
    "gemini-flash-lite-latest",
]
ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
THEMES = ["cyber_blue", "neon_purple", "emerald_tech", "sunset_amber"]

TIKTOK_SAFE_REPLACEMENTS = [
    ("mua ngay", "trải nghiệm ngay"),
    ("bán tài khoản", "hỗ trợ nâng cấp"),
    ("mua tài khoản", "nâng cấp tài khoản"),
    ("giá rẻ", "tối ưu chi phí"),
    ("inbox giá", "xem ở hồ sơ kênh"),
    ("chuyển khoản", "đăng ký"),
    ("thanh toán", "kích hoạt"),
    ("bán gói", "chia sẻ gói"),
]


def sanitize_tiktok_text(text):
    if not isinstance(text, str):
        return text
    out = text
    for bad, good in TIKTOK_SAFE_REPLACEMENTS:
        out = out.replace(bad, good).replace(bad.capitalize(), good.capitalize())
    return out


SCENE_TYPES = {
    "chat_demo", "comparison", "stat_card", "bullet_steps",
    "prompt_card", "myth_vs_fact", "checklist_card", "ranking_card",
}

SLOT_HINT = {
    "SANG": "Ca sáng: tin tức AI/công nghệ nhanh. Ưu tiên stat_card, ranking_card hoặc myth_vs_fact.",
    "TRUA": "Ca trưa: so sánh tính năng/chia sẻ giá trị, lồng ghép khéo léo gói AI Pro tự nhiên. Ưu tiên comparison, chat_demo hoặc checklist_card.",
    "TOI": "Ca tối: mẹo thực chiến / quy trình ứng dụng AI. Ưu tiên prompt_card, bullet_steps hoặc checklist_card.",
}

SLOT_VOICE = {
    "SANG": "vi-VN-HoaiMyNeural",
    "TRUA": "vi-VN-NamMinhNeural",
    "TOI": "vi-VN-HoaiMyNeural",
}

# Nút CTA biến thiên thông minh theo từng ca phát sóng (Slot-Aware Conversion CTA)
SLOT_CTA_BUTTON = {
    "SANG": "➕ Follow kênh cập nhật AI mỗi sáng",
    "TRUA": "📩 Hỗ trợ AI Pro • Zalo 0356.141.136",
    "TOI": "🔖 Lưu ngay video để áp dụng khi cần",
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
        {"type": "checklist_card", "title": "4 dấu hiệu cần nâng cấp AI",
         "items": ["Thường đọc PDF > 30 trang", "Cần lập bảng dữ liệu chuẩn", "Bị giới hạn lượt hỏi giữa chừng"], "voiceover": "..."},
        {"type": "ranking_card", "title": "Top 3 mẹo AI tiết kiệm giờ làm",
         "ranks": ["Hạng 3: Tóm tắt email dài", "Hạng 2: Tự kiểm tra lỗi Excel", "Hạng 1: Giao việc bằng Prompt mẫu"], "voiceover": "..."},
        {"type": "comparison", "title": "...", "left_title": "...", "left_items": ["..", "..", ".."],
         "right_title": "...", "right_items": ["..", "..", ".."], "voiceover": "..."},
        {"type": "stat_card", "title": "...", "metric": "10X", "summary": "...", "bullets": ["..", ".."], "voiceover": "..."},
        {"type": "bullet_steps", "title": "...", "steps": ["..", "..", ".."], "voiceover": "..."},
    ],
    "cta": {"highlight_metric": "70%", "summary": "...", "button_text": "➕ Follow kênh cập nhật AI mỗi sáng", "voiceover": "..."},
    "caption": "Tiêu đề + mô tả ngắn #ai #congnghe #shorts",
    "pinned_question": "Theo bạn tính năng AI nào giúp tiết kiệm nhiều thời gian nhất hiện nay? Bình luận ý kiến của bạn nhé!",
}


def fetch_tech_headlines(limit=8):
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
    cta_btn = SLOT_CTA_BUTTON.get(slot, "➕ Follow kênh nhận mẹo AI mỗi ngày")
    hooks_txt = "\n".join("- " + h for h in top_hooks) if top_hooks else "(đang thu thập dữ liệu)"
    return f"""Bạn là biên tập viên video ngắn tiếng Việt cho kênh 'Thiện AI Thực Chiến' (28-38 giây).
Chủ đề: {topic}
{SLOT_HINT.get(slot, '')}
{f'Dùng bg_theme = "{theme}".' if theme else 'Chọn bg_theme trong: ' + ', '.join(THEMES) + '.'}

Các chủ đề đã làm gần đây (KHÔNG lặp lại góc nhìn/nội dung):
{avoid}

Các video hiệu quả nhất của kênh để học phong cách giật tít Hook ngắn gọn, cuốn hút:
{hooks_txt}

Yêu cầu:
- Chỉ trả về MỘT đối tượng JSON hợp lệ, đúng cấu trúc mẫu dưới đây, không markdown.
- Tiếng Việt có dấu, tự nhiên, tuyệt đối không dùng từ mua bán lộ liễu.
- hook.headline: đúng 3 dòng, mỗi dòng tối đa 18 ký tự; dòng cuối là dòng nhấn mạnh.
- scenes: chọn 3 đến 4 cảnh phù hợp nhất trong 8 loại: chat_demo, prompt_card, myth_vs_fact, checklist_card, ranking_card, comparison, stat_card, bullet_steps (mỗi loại tối đa 1 lần).
- checklist_card: items gồm 3 mục ngắn (mỗi mục tối đa 42 ký tự).
- ranking_card: ranks gồm đúng 3 mục xếp theo thứ tự từ Hạng 3 -> Hạng 2 -> Hạng 1 (mỗi mục tối đa 42 ký tự).
- prompt_card: prompt_text là 1 câu lệnh mẫu thực tế 15-26 từ; result_note tối đa 40 ký tự.
- myth_vs_fact: myth và fact mỗi mục tối đa 60 ký tự.
- comparison: left_items và right_items cùng 3 mục, mỗi mục tối đa 28 ký tự. bullet_steps: đúng 3 bước, mỗi bước tối đa 60 ký tự.
- stat_card & cta: metric / highlight_metric bắt đầu bằng con số (vd 10X, 70%, 3X, 85%).
- cta.button_text: đặt đúng là "{cta_btn}".
- pinned_question: 1 câu hỏi mở thú vị liên quan trực tiếp đến chủ đề để đăng làm bình luận ghim kích thích người xem tranh luận.
- Mỗi voiceover 12-26 từ (tổng toàn video 60-145 từ).
- SEAMLESS LOOP: Câu cuối của cta.voiceover kết thúc sao cho khi lặp lại về giây 0:00 (hook.voiceover) nghe liền mạch tự nhiên!
- mascot=true, voice="{voice}", voice_rate="+22%".

Cấu trúc mẫu (chỉ chọn 3-4 cảnh trong scenes):
{json.dumps(SCHEMA_EXAMPLE, ensure_ascii=False, indent=1)}"""


def validate(s, slot=""):
    def need(cond, msg):
        if not cond:
            raise ValueError(msg)
    str_list = lambda v, n=1: isinstance(v, list) and len(v) >= n and all(isinstance(x, str) and x.strip() for x in v)
    need(isinstance(s, dict), "không phải object")
    if s.get("bg_theme") not in THEMES:
        s["bg_theme"] = THEMES[0]
    s.setdefault("badge", "THIỆN AI THỰC CHIẾN")
    s["mascot"] = bool(s.get("mascot", True))
    if s.get("voice") not in ("vi-VN-HoaiMyNeural", "vi-VN-NamMinhNeural"):
        s["voice"] = SLOT_VOICE.get(slot, "vi-VN-HoaiMyNeural")
    s.setdefault("voice_rate", "+22%")
    h = s.get("hook")
    need(isinstance(h, dict) and str_list(h.get("headline"), 1) and h.get("voiceover"), "hook sai")
    h["headline"] = [str(x).strip()[:28] for x in h["headline"][:3]]
    need(isinstance(s.get("scenes"), list) and 1 <= len(s["scenes"]) <= 5, "scenes sai")
    for sc in s["scenes"]:
        t = sc.get("type")
        need(t in SCENE_TYPES and sc.get("voiceover") and sc.get("title"), f"scene sai: {t}")
        sc["title"] = str(sc["title"]).strip()[:46]
        if t == "chat_demo":
            need(sc.get("user_prompt") and sc.get("ai_reply"), "chat_demo thiếu trường")
        elif t == "prompt_card":
            need(sc.get("prompt_text"), "prompt_card thiếu prompt_text")
            sc.setdefault("result_note", "Chuẩn xác & tiết kiệm thời gian")
        elif t == "myth_vs_fact":
            need(sc.get("myth") and sc.get("fact"), "myth_vs_fact thiếu myth/fact")
        elif t == "checklist_card":
            need(str_list(sc.get("items"), 2), "checklist_card thiếu items")
            sc["items"] = [str(x).strip()[:52] for x in sc["items"][:4]]
        elif t == "ranking_card":
            need(str_list(sc.get("ranks"), 2), "ranking_card thiếu ranks")
            sc["ranks"] = [str(x).strip()[:52] for x in sc["ranks"][:3]]
        elif t == "comparison":
            need(sc.get("left_title") and sc.get("right_title") and str_list(sc.get("left_items"), 2)
                 and str_list(sc.get("right_items"), 2), "comparison thiếu trường")
            n = min(len(sc["left_items"]), len(sc["right_items"]), 3)
            sc["left_items"] = [str(x).strip()[:36] for x in sc["left_items"][:n]]
            sc["right_items"] = [str(x).strip()[:36] for x in sc["right_items"][:n]]
        elif t == "stat_card":
            need(sc.get("metric") and sc.get("summary"), "stat_card thiếu trường")
            sc["bullets"] = [str(b).strip()[:55] for b in sc.get("bullets", []) if isinstance(b, str)][:3]
        elif t == "bullet_steps":
            need(str_list(sc.get("steps"), 2), "bullet_steps thiếu steps")
            sc["steps"] = [str(x).strip()[:75] for x in sc["steps"][:4]]
    c = s.get("cta")
    need(isinstance(c, dict) and c.get("highlight_metric") and c.get("summary") and c.get("voiceover"), "cta sai")
    c["button_text"] = SLOT_CTA_BUTTON.get(slot) or c.get("button_text") or "➕ Follow kênh nhận mẹo AI mỗi ngày"
    need(isinstance(s.get("caption"), str) and s["caption"].strip(), "thiếu caption")
    s.setdefault("pinned_question", "Bạn đang áp dụng công cụ AI nào cho công việc hàng ngày? Chia sẻ dưới phần bình luận nhé!")

    all_vo = [h["voiceover"]] + [sc["voiceover"] for sc in s["scenes"]] + [c["voiceover"]]
    total_words = sum(len(str(v).split()) for v in all_vo)
    need(40 <= total_words <= 180, f"tổng số từ voiceover không hợp lý ({total_words} từ)")

    h["voiceover"] = sanitize_tiktok_text(h["voiceover"])
    for sc in s["scenes"]:
        sc["voiceover"] = sanitize_tiktok_text(sc["voiceover"])
    c["voiceover"] = sanitize_tiktok_text(c["voiceover"])
    s["caption"] = sanitize_tiktok_text(s["caption"])
    return s


def _fallback_script(topic, slot, theme):
    """Kịch bản dự phòng thông minh từ chủ đề nếu toàn bộ 8 model Google AI Studio bị sập 503 cùng lúc."""
    words = topic.split()
    l1 = " ".join(words[:4])[:18] or "Mẹo AI thực chiến"
    l2 = " ".join(words[4:8])[:18] or "giúp tiết kiệm giờ"
    return validate({
        "badge": "THIỆN AI THỰC CHIẾN",
        "bg_theme": theme if theme in THEMES else "cyber_blue",
        "mascot": True,
        "voice": SLOT_VOICE.get(slot, "vi-VN-HoaiMyNeural"),
        "voice_rate": "+22%",
        "hook": {
            "headline": [l1, l2, "Áp dụng ngay!"],
            "voiceover": f"Đây là bí quyết về {topic} giúp bạn xử lý công việc nhanh gấp nhiều lần mỗi ngày.",
        },
        "scenes": [
            {
                "type": "myth_vs_fact",
                "title": "Cách tiếp cận đúng",
                "myth": "Làm thủ công tốn hàng giờ hoặc hỏi AI câu ngắn cụt lủn",
                "fact": "Giao rõ vai trò, dữ liệu đầu vào và định dạng kết quả mong muốn",
                "voiceover": "Thay vì làm thủ công tốn hàng giờ, bạn chỉ cần cung cấp rõ ngữ cảnh và định dạng đầu ra cho AI.",
            },
            {
                "type": "bullet_steps",
                "title": "3 bước thực hiện chuẩn",
                "steps": [
                    "Chuẩn bị nội dung hoặc tài liệu cần xử lý rõ ràng",
                    "Nhập câu lệnh yêu cầu tóm tắt kèm bảng hành động cụ thể",
                    "Kiểm tra lại các con số quan trọng trước khi xuất bản",
                ],
                "voiceover": "Áp dụng đúng ba bước từ chuẩn bị dữ liệu, giao câu lệnh chi tiết đến kiểm tra nhanh kết quả cuối cùng.",
            },
            {
                "type": "stat_card",
                "title": "Hiệu quả thực tế",
                "metric": "5X",
                "summary": "Tăng tốc độ hoàn thành công việc hàng ngày",
                "bullets": ["Giảm sai sót thủ công", "Dễ áp dụng cho mọi ngành nghề"],
                "voiceover": "Quy trình gọn nhẹ này giúp tăng gấp năm lần tốc độ xử lý tài liệu và giảm hẳn sai sót.",
            },
        ],
        "cta": {
            "highlight_metric": "70%",
            "summary": "Tiết kiệm 70% thời gian làm việc lặp lại mỗi ngày",
            "button_text": SLOT_CTA_BUTTON.get(slot, "➕ Follow kênh cập nhật AI mỗi sáng"),
            "voiceover": "Làm chủ công cụ thông minh giúp bạn tiết kiệm bảy mươi phần trăm thời gian, và đây chính là lý do",
        },
        "caption": f"{topic} cực dễ áp dụng trong 30 giây! #ai #congnghe #thiennguyenai #shorts",
        "pinned_question": f"Bạn đã thử áp dụng AI cho '{topic}' chưa? Để lại bình luận bên dưới nhé!",
    }, slot=slot)


def get_api_keys(explicit_key=None):
    """Lấy danh sách các Gemini API Key dự phòng theo thứ tự: GEMINI_API_KEY, GEMINI_API_KEY_2, GEMINI_API_KEY_3."""
    if explicit_key:
        return [explicit_key]
    keys = []
    for name in ("GEMINI_API_KEY", "GEMINI_API_KEY_2", "GEMINI_API_KEY_3"):
        val = os.environ.get(name, "").strip()
        if val and val not in keys:
            keys.append(val)
    if not keys:
        raise RuntimeError("Thiếu GEMINI_API_KEY")
    return keys


DEAD_KEYS = set()


def _call_with_rotation(model, prompt, keys, parts=None):
    """Thử gọi qua từng API Key; tự động cách ly Key lỗi 403 trong suốt phiên chạy để không tốn lượt gọi thừa."""
    last_err = None
    active_keys = [k for k in keys if k not in DEAD_KEYS] or keys
    for idx, k in enumerate(active_keys):
        try:
            return _call(model, prompt, k, parts=parts), idx + 1
        except Exception as ex:
            last_err = ex
            msg = str(ex)
            if "HTTP 403" in msg:
                DEAD_KEYS.add(k)
                print("[gemini] Key trả HTTP 403 -> tự động cách ly trong phiên chạy, chuyển sang Key sống")
                continue
            if any(code in msg for code in ("HTTP 429", "HTTP 503", "quota", "RESOURCE_EXHAUSTED", "Read timed out", "HTTPSConnectionPool")):
                print(f"[gemini] Key#{idx + 1} ({model}) bận/hết quota -> xoay sang Key kế tiếp")
                continue
            raise
    raise last_err

def _call(model, prompt, key, parts=None):
    req_parts = parts if parts is not None else [{"text": prompt}]
    body = {"contents": [{"parts": req_parts}],
            "generationConfig": {"response_mime_type": "application/json", "temperature": 0.9}}
    r = requests.post(ENDPOINT.format(model=model), headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                      json=body, timeout=55)
    if r.status_code != 200:
        raise RuntimeError(f"{model} HTTP {r.status_code}: {r.text[:180]}")
    data = r.json()
    parts = data["candidates"][0]["content"]["parts"]
    text = "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    return json.loads(text)


def generate_script(topic, slot="", recent=(), theme=None, api_key=None, retries=1, top_hooks=()):
    """Thử lần lượt 8 model x 3 API Key dự phòng; nếu tất cả quá tải thì dùng Fallback Script."""
    keys = get_api_keys(api_key)
    prompt = build_prompt(topic, slot, list(recent), theme, top_hooks=top_hooks)
    for model in MODELS:
        for attempt in range(retries + 1):
            try:
                raw, key_idx = _call_with_rotation(model, prompt, keys)
                script = validate(raw, slot=slot)
                if theme in THEMES:
                    script["bg_theme"] = theme
                print(f"[gemini] OK model={model} key=#{key_idx} voice={script['voice']} scenes={[x['type'] for x in script['scenes']]}")
                return script
            except Exception as ex:
                msg = str(ex)
                print(f"[gemini] {model} lần {attempt + 1} lỗi: {msg[:150]}")
                if "HTTP 404" in msg or "HTTP 400" in msg:
                    break
                time.sleep(3 * (attempt + 1))
    print("[gemini] CẢNH BÁO: Toàn bộ 8 model Gemini đang quá tải 503 -> kích hoạt Fallback Script để ca phát sóng không bị gián đoạn!")
    return _fallback_script(topic, slot, theme)


def generate_topic(slot, recent=(), api_key=None):
    keys = get_api_keys(api_key)
    avoid = "\n".join(f"- {t}" for t in recent) or "(chưa có)"
    news_block = ""
    if slot == "SANG":
        headlines = fetch_tech_headlines()
        if headlines:
            news_block = "\nTin tức công nghệ/AI mới nhất hôm nay:\n" + "\n".join(f"- {h}" for h in headlines)
    prompt = f"""Bạn là biên tập viên kênh 'Thiện AI Thực Chiến'.
Ca phát sóng: {slot} — {SLOT_HINT.get(slot, '')}{news_block}
Các chủ đề đã làm gần đây (TUYỆT ĐỐI KHÔNG TRÙNG LẶP):
{avoid}

Hãy đề xuất 1 chủ đề video ngắn (30-40 giây) mới mẻ, thực tế.
Trả về JSON: {{"topic": "Tên chủ đề ngắn gọn 10-18 từ", "bg_theme": "cyber_blue|neon_purple|emerald_tech|sunset_amber"}}"""
    for model in MODELS[:5]:
        try:
            res, _ = _call_with_rotation(model, prompt, keys)
            topic = str(res.get("topic", "")).strip()
            theme = res.get("bg_theme") if res.get("bg_theme") in THEMES else THEMES[0]
            if topic:
                return topic, theme
        except Exception:
            time.sleep(2)
    return f"3 mẹo ứng dụng AI tăng tốc công việc ca {slot}", THEMES[0]


def generate_batch_topics(recent=(), days=3, api_key=None):
    keys = get_api_keys(api_key)
    avoid = "\n".join(f"- {t}" for t in recent) or "(chưa có)"
    headlines = fetch_tech_headlines()
    news_block = "\nTin tức AI/công nghệ mới nhất:\n" + "\n".join(f"- {h}" for h in headlines) if headlines else ""
    count = days * 3
    prompt = f"""Bạn là giám đốc nội dung kênh 'Thiện AI Thực Chiến'.
Hãy lập kế hoạch {count} chủ đề video ngắn (chia đều theo thứ tự SANG, TRUA, TOI cho {days} ngày tới).
{news_block}
Các chủ đề đã làm (KHÔNG TRÙNG LẶP):
{avoid}

Trả về JSON: {{"items": [{{"slot": "SANG", "bg_theme": "cyber_blue", "topic": "..."}}, ...]}}"""
    for model in MODELS[:5]:
        try:
            res, _ = _call_with_rotation(model, prompt, keys)
            items = res.get("items", [])
            out = []
            for idx, it in enumerate(items[:count]):
                sl = it.get("slot") if it.get("slot") in ("SANG", "TRUA", "TOI") else ("SANG", "TRUA", "TOI")[idx % 3]
                th = it.get("bg_theme") if it.get("bg_theme") in THEMES else THEMES[idx % 4]
                tp = str(it.get("topic", "")).strip()
                if tp:
                    out.append((sl, th, tp))
            if len(out) >= 3:
                return out
        except Exception:
            time.sleep(2)
    return []
