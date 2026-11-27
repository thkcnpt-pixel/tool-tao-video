"""Gemini API (Free) với 8 model dự phòng + Fallback Template chống lỗi 503 tuyệt đối + 8 loại cảnh + Slot-Aware CTA + Smart Pinned Question."""
import json
import os
import re
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
THEMES = [
    "clean_light", "brutal_dark", "cyber_blue", "paper_cream",
    "emerald_tech", "warm_editorial", "neon_purple", "sunset_amber",
]
THEME_VISUAL_PROFILE = {
    "clean_light":    dict(visual_style="editorial_light", mascot=False, hook_layout="center_impact"),
    "paper_cream":    dict(visual_style="editorial_light", mascot=False, hook_layout="card_banner"),
    "brutal_dark":    dict(visual_style="neo_brutal",      mascot=False, hook_layout="card_banner"),
    "emerald_tech":   dict(visual_style="terminal_pro",    mascot=False, hook_layout="left_stack"),
    "warm_editorial": dict(visual_style="cinema_clean",    mascot=False, hook_layout="center_impact"),
    "sunset_amber":   dict(visual_style="cinema_clean",    mascot=False, hook_layout="left_stack"),
    "cyber_blue":     dict(visual_style="glass_neon",      mascot=True,  hook_layout="left_stack"),
    "neon_purple":    dict(visual_style="glass_neon",      mascot=True,  hook_layout="card_banner"),
}

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
    "TRUA": "Ca trưa: so sánh tính năng/chia sẻ giá trị, tối ưu chi phí thông minh. Ưu tiên comparison, chat_demo hoặc checklist_card.",
    "CHIEU": "Ca chiều tan tầm: giải cứu việc văn phòng cuối ngày (Excel, PDF, Báo cáo, Email nhanh). Ưu tiên bullet_steps, prompt_card hoặc myth_vs_fact.",
    "TOI": "Ca tối: câu lệnh Prompt thực chiến / quy trình tự động hóa sâu. Ưu tiên prompt_card, bullet_steps hoặc checklist_card.",
}

SLOT_VOICE = {
    "SANG": "vi-VN-HoaiMyNeural",
    "TRUA": "vi-VN-NamMinhNeural",
    "CHIEU": "vi-VN-HoaiMyNeural",
    "TOI": "vi-VN-NamMinhNeural",
}

# Nút CTA biến thiên thông minh theo từng ca phát sóng (Slot-Aware Conversion CTA)

HOOK_ARCHETYPES = [
    "CÔNG THỨC HOOK 1 (Cảnh báo sai lầm): Mở đầu bằng 'Đừng...' hoặc chỉ ra sai lầm 90% người dùng đang mắc phải khiến mất thời gian.",
    "CÔNG THỨC HOOK 2 (Con số & Tốc độ gây sốc): Mở đầu bằng con số đối lập mạnh (VD: '100 trang trong 10 giây', '3 tiếng còn 5 phút').",
    "CÔNG THỨC HOOK 3 (Bí mật thực chiến): Mở đầu kích thích tò mò ('Ít ai biết tính năng ẩn này...', 'Câu lệnh giúp mình tiết kiệm 2 giờ mỗi ngày').",
    "CÔNG THỨC HOOK 4 (Câu hỏi trực diện): Mở đầu chạm đúng nỗi đau công việc ('Còn làm thủ công việc này?', 'Khi nào nên nâng cấp AI?').",
]

SLOT_CTA_BUTTON = {
    "SANG": "👇 Lấy câu lệnh mẫu ở Bình luận đầu",
    "TRUA": "📋 Copy trọn bộ Prompt dưới Bình luận",
    "CHIEU": "⚡ Lưu ngay & Copy mẫu ở Bình luận",
    "TOI": "👇 Mở Bình luận lấy mẫu dùng ngay",
}

SERIES_RULES = [
    (r"excel|sheet|bảng tính|công thức|csv", "GIẢI CỨU EXCEL"),
    (r"pdf|word|tài liệu|hợp đồng|báo cáo|slide", "TỐI ƯU TÀI LIỆU"),
    (r"email|gmail|thư|họp|biên bản", "AI DÂN VĂN PHÒNG"),
    (r"code|lập trình|python|web|script|tự động", "TỰ ĐỘNG HÓA 30S"),
    (r"sai lầm|đừng|phí tiền|hiểu sai", "SAI LẦM DÙNG AI"),
    (r"prompt|câu lệnh", "PROMPT THỰC CHIẾN"),
]


def _suggest_series_badge(topic, ep_num):
    low = str(topic or "").lower()
    for pat, label in SERIES_RULES:
        if re.search(pat, low):
            return f"{label} #{ep_num}"
    pool = ("MẸO AI VĂN PHÒNG", "PROMPT THỰC CHIẾN", "AI FREE MÀ MẠNH", "TỰ ĐỘNG HÓA 30S")
    return f"{pool[ep_num % len(pool)]} #{ep_num}"


RSS_URLS = [
    "https://news.google.com/rss/search?q=AI+OR+Gemini+OR+ChatGPT+when:2d&hl=vi&gl=VN&ceid=VN:vi",
    "https://vnexpress.net/rss/so-hoa.rss",
]

SCHEMA_EXAMPLE = {
    "badge": "GIẢI CỨU EXCEL #12",
    "youtube_title": "Sửa lỗi file Excel 1.000 dòng chỉ trong 15 giây bằng AI",
    "bg_theme": "cyber_blue",
    "mascot": True,
    "voice": "vi-VN-HoaiMyNeural",
    "voice_rate": "+12%",
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
    "cta": {"highlight_metric": "70%", "summary": "Mẫu câu lệnh đầy đủ để sẵn dưới bình luận", "button_text": "📋 Copy trọn bộ Prompt dưới Bình luận", "voiceover": "..."},
    "caption": "Mô tả ngắn 1-2 câu súc tích #meoai #aithucchien #congnghe #shorts",
    "full_prompt": "Hãy đóng vai chuyên gia [lĩnh vực], phân tích [dữ liệu/tài liệu đính kèm], chỉ ra 3 vấn đề quan trọng nhất và xuất kết quả thành bảng gồm: Nguyên nhân, Cách khắc phục, Công thức chuẩn.",
    "pinned_question": "Bạn đang tốn nhiều thời gian nhất cho việc lặp lại nào mỗi ngày? Comment để mình làm tiếp phần sau nhé!",
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
    seed_idx = sum(ord(c) for c in f"{topic}|{recent[-1] if recent else ''}")
    chosen_theme = theme if theme in THEMES else THEMES[seed_idx % len(THEMES)]
    prof = THEME_VISUAL_PROFILE[chosen_theme]
    voice = ("vi-VN-HoaiMyNeural", "vi-VN-NamMinhNeural")[seed_idx % 2]
    cta_btn = SLOT_CTA_BUTTON.get(slot, "📋 Copy trọn bộ Prompt dưới Bình luận")
    series_badge = _suggest_series_badge(topic, (seed_idx % 18) + 1)
    hooks_txt = "\n".join("- " + h for h in top_hooks) if top_hooks else "(đang thu thập dữ liệu)"
    scene_range = "2 đến 3" if (seed_idx % 2 == 0) else "3 đến 4"
    return f"""Bạn là biên tập viên video ngắn tiếng Việt cho kênh 'Thiện AI Thực Chiến' (18-28 giây).
Chủ đề: {topic}
{SLOT_HINT.get(slot, '')}
Dùng bg_theme = "{chosen_theme}".

Các chủ đề đã làm gần đây (KHÔNG lặp lại góc nhìn/nội dung):
{avoid}

Các video hiệu quả nhất của kênh để học phong cách giật tít Hook ngắn gọn, cuốn hút:
{hooks_txt}

Yêu cầu:
- Chỉ trả về MỘT đối tượng JSON hợp lệ, đúng cấu trúc mẫu dưới đây, không markdown.
- Tiếng Việt có dấu, tự nhiên, tuyệt đối không dùng từ mua bán lộ liễu, không đọc số điện thoại/Zalo.
- badge: đặt đúng theo format Series có đánh số là "{series_badge}" (giúp người xem theo dõi trọn bộ Series trên kênh).
- youtube_title: tiêu đề tối ưu CTR & tìm kiếm tiếng Việt (35-58 ký tự), có con số hoặc kết quả cụ thể gây tò mò, KHÔNG chứa dấu # hay hashtag.
- HOOK 2 GIÂY ĐẦU: hook.voiceover tối đa 12 từ, đánh thẳng vào kết quả/nỗi đau cụ thể (con số, thời gian), không chào hỏi.
- Mỗi cảnh CHỮ TRÊN MÀN HÌNH CỰC NGẮN (ưu tiên 3-6 từ/mục) để đọc được ngay trên điện thoại; chi tiết đưa vào voiceover.
- hook.headline: đúng 3 dòng, mỗi dòng tối đa 18 ký tự; dòng cuối là dòng nhấn mạnh. Áp dụng phong cách: {HOOK_ARCHETYPES[seed_idx % len(HOOK_ARCHETYPES)]}
- scenes: chọn {scene_range} cảnh phù hợp nhất trong 8 loại: chat_demo, prompt_card, myth_vs_fact, checklist_card, ranking_card, comparison, stat_card, bullet_steps (mỗi loại tối đa 1 lần).
- checklist_card: items gồm 3 mục ngắn (mỗi mục tối đa 30 ký tự).
- ranking_card: ranks gồm đúng 3 mục xếp theo thứ tự từ Hạng 3 -> Hạng 2 -> Hạng 1 (mỗi mục tối đa 30 ký tự).
- prompt_card: prompt_text là câu lệnh tóm tắt 10-18 từ dễ đọc trên màn hình; result_note tối đa 40 ký tự.
- myth_vs_fact: myth và fact mỗi mục tối đa 40 ký tự.
- comparison: left_items và right_items cùng 3 mục, mỗi mục tối đa 28 ký tự. bullet_steps: đúng 3 bước, mỗi bước tối đa 40 ký tự.
- stat_card & cta: metric / highlight_metric bắt đầu bằng con số (vd 10X, 70%, 3X, 85%).
- cta.button_text: đặt đúng là "{cta_btn}". Trong `cta.voiceover`, khéo léo nhắc người xem lấy câu lệnh đầy đủ dưới phần bình luận trước khi nối sang cụm cầu nối vòng lặp.
- full_prompt: trọn bộ câu lệnh Prompt mẫu ĐẦY ĐỦ, CHI TIẾT (30-60 từ, có ngoặc vuông [như thế này] ở chỗ người dùng tự thay thông tin) để hệ thống tự động ghim vào Bình luận đầu tiên trên YouTube cho khán giả copy dùng ngay!
- pinned_question: 1 câu hỏi mở ngắn gọn kích thích tranh luận dưới bình luận.
- Mỗi voiceover 10-20 từ (tổng toàn video 45-95 từ).
- KỸ THUẬT CÂU GHÉP VÒNG LẶP (SPLIT-SENTENCE SEAMLESS LOOP — BẮT BUỘC):
  + Câu cuối của `cta.voiceover` và câu đầu của `hook.voiceover` PHẢI LÀ 2 NỬA CỦA CÙNG MỘT CÂU TIẾNG VIỆT!
  + Cụ thể: `cta.voiceover` kết thúc bằng một cụm dẫn mở KHÔNG CÓ DẤU CHẤM CUỐI (ví dụ: "...trọn bộ câu lệnh mình để sẵn dưới bình luận, và lý do chính là vì"), còn `hook.voiceover` bắt đầu nối tiếp luôn vào cụm đó (ví dụ: "90% người dùng AI vẫn đang làm thủ công bước này...").
  + TUYỆT ĐỐI KHÔNG ĐƯỢC copy nguyên câu của hook.voiceover sang cta.voiceover!
- mascot={str(prof["mascot"]).lower()}, voice="{voice}", voice_rate="+12%".

Cấu trúc mẫu (chỉ chọn {scene_range} cảnh trong scenes):
{json.dumps(SCHEMA_EXAMPLE, ensure_ascii=False, indent=1)}"""



LOOP_BRIDGES = (
    "và lý do chính là vì",
    "bởi vì sự thật là",
    "và điều ít ai để ý là",
    "nhưng hãy nhớ một điều là",
    "và bí quyết cốt lõi nằm ở chỗ",
    "bởi ngay lúc này",
    "và để hiểu tại sao thì",
)


def _enforce_seamless_loop(hook_obj, cta_obj, topic):
    """Đảm bảo 100% cuối cta.voiceover và đầu hook.voiceover ghép thành 1 câu tiếng Việt liền mạch không dấu chấm ngắt."""
    h_vo = str(hook_obj.get("voiceover", "")).strip()
    c_vo = str(cta_obj.get("voiceover", "")).strip()

    if c_vo.lower() == h_vo.lower() or len(c_vo) < 15:
        metric = cta_obj.get("highlight_metric", "70%")
        summary = cta_obj.get("summary", "tối ưu hiệu suất làm việc mỗi ngày")
        c_vo = f"Áp dụng ngay để đạt hiệu quả {metric}, {summary.lower()}"

    # Bỏ các câu chào đóng kín ở cuối CTA và các từ nối cụt lửng
    c_vo = re.sub(r"[.?!…]+\s*(Đừng quên|Hãy bấm|Nhớ bấm|Chúc các bạn)[^.?!…]*[.?!…]*$", "", c_vo, flags=re.I).strip()
    c_vo = c_vo.rstrip(".?!…,; ")
    c_vo = re.sub(r"(?:,?\s+(?:và|nhưng|hoặc|bởi|vì|để|để bắt đầu|nhé|nha))+$", "", c_vo, flags=re.I).rstrip(".?!…,; ")

    lower_c = c_vo.lower()
    has_bridge = any(lower_c.endswith(b) for b in LOOP_BRIDGES)
    if not has_bridge:
        lower_h = h_vo.lower()
        first_clause = re.split(r"[.?!]", h_vo)[0]
        if "?" in first_clause or lower_h.startswith(("tại sao", "làm sao", "khi nào", "có nên", "bạn có")):
            bridge = "và đã bao giờ bạn tự hỏi"
        elif lower_h.startswith(("đừng", "hãy", "chỉ cần", "thử")):
            bridge = "nhưng trước hết"
        elif re.match(r"^(\d+|hơn|chỉ|tới|năm)", lower_h):
            bridge = "và thực tế đáng kinh ngạc là"
        else:
            bridge = "và điều tuyệt vời nhất là"
        c_vo = f"{c_vo}, {bridge}"

    cta_obj["voiceover"] = c_vo

def validate(s, slot=""):
    def need(cond, msg):
        if not cond:
            raise ValueError(msg)
    str_list = lambda v, n=1: isinstance(v, list) and len(v) >= n and all(isinstance(x, str) and x.strip() for x in v)
    need(isinstance(s, dict), "không phải object")
    if s.get("bg_theme") not in THEMES:
        s["bg_theme"] = THEMES[0]
    prof = THEME_VISUAL_PROFILE[s["bg_theme"]]
    s["visual_style"] = prof["visual_style"]
    s["hook_layout"] = prof["hook_layout"]
    s["mascot"] = prof["mascot"]
    s.setdefault("badge", "THIỆN AI THỰC CHIẾN")
    if s.get("voice") not in ("vi-VN-HoaiMyNeural", "vi-VN-NamMinhNeural"):
        s["voice"] = SLOT_VOICE.get(slot, "vi-VN-HoaiMyNeural")
    s.setdefault("voice_rate", "+12%")
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
    c["button_text"] = SLOT_CTA_BUTTON.get(slot) or c.get("button_text") or "📋 Copy trọn bộ Prompt dưới Bình luận"
    need(isinstance(s.get("caption"), str) and s["caption"].strip(), "thiếu caption")

    yt_title = re.sub(r"#\S+", "", str(s.get("youtube_title") or "")).strip(" -–—.|")
    if not yt_title:
        clean_cap = re.sub(r"#\S+", "", s["caption"]).strip()
        yt_title = re.split(r"[.!?\n]", clean_cap)[0].strip()
    s["youtube_title"] = sanitize_tiktok_text(yt_title[:70])

    full_pr = str(s.get("full_prompt") or "").strip()
    if not full_pr:
        for sc in s["scenes"]:
            if sc.get("prompt_text"):
                full_pr = str(sc["prompt_text"]).strip()
                break
    s["full_prompt"] = full_pr[:420]
    s.setdefault("pinned_question", "Bạn đang tốn nhiều thời gian nhất cho việc lặp lại nào mỗi ngày? Chia sẻ dưới bình luận nhé!")

    all_vo = [h["voiceover"]] + [sc["voiceover"] for sc in s["scenes"]] + [c["voiceover"]]
    total_words = sum(len(str(v).split()) for v in all_vo)
    need(38 <= total_words <= 180, f"tổng số từ voiceover không hợp lý ({total_words} từ)")

    h["voiceover"] = sanitize_tiktok_text(h["voiceover"])
    for sc in s["scenes"]:
        sc["voiceover"] = sanitize_tiktok_text(sc["voiceover"])
    c["voiceover"] = sanitize_tiktok_text(c["voiceover"])
    s["caption"] = sanitize_tiktok_text(s["caption"])
    _enforce_seamless_loop(h, c, s.get("caption", ""))
    return s


def _fallback_script(topic, slot, theme):
    """Kịch bản dự phòng thông minh từ chủ đề nếu toàn bộ 8 model Google AI Studio bị sập 503 cùng lúc."""
    words = topic.split()
    l1 = " ".join(words[:4])[:18] or "Mẹo AI thực chiến"
    l2 = " ".join(words[4:8])[:18] or "giúp tiết kiệm giờ"
    return validate({
        "badge": _suggest_series_badge(topic, 1),
        "youtube_title": f"{topic[:52]} chỉ trong 15 giây",
        "bg_theme": theme if theme in THEMES else "clean_light",
        "mascot": False,
        "voice": SLOT_VOICE.get(slot, "vi-VN-HoaiMyNeural"),
        "voice_rate": "+12%",
        "hook": {
            "headline": [l1, l2, "Áp dụng ngay!"],
            "voiceover": f"Đừng làm thủ công nữa, mẹo {topic} này rút ngắn hàng giờ làm việc.",
        },
        "scenes": [
            {
                "type": "myth_vs_fact",
                "title": "Cách tiếp cận đúng",
                "myth": "Hỏi AI câu ngắn cụt lủn thiếu ngữ cảnh",
                "fact": "Giao rõ vai trò, dữ liệu và bảng kết quả",
                "voiceover": "Thay vì hỏi chung chung tốn hàng giờ chỉnh sửa, hãy giao rõ vai trò và định dạng bảng đầu ra.",
            },
            {
                "type": "bullet_steps",
                "title": "3 bước thực hiện chuẩn",
                "steps": [
                    "Đính kèm dữ liệu hoặc nội dung gốc",
                    "Dán câu lệnh mẫu kèm yêu cầu xuất bảng",
                    "Đối chiếu nhanh các con số quan trọng",
                ],
                "voiceover": "Chỉ cần tải tài liệu lên, dán câu lệnh mẫu rồi kiểm tra nhanh các con số quan trọng nhất.",
            },
            {
                "type": "stat_card",
                "title": "Hiệu quả thực tế",
                "metric": "5X",
                "summary": "Tăng tốc xử lý việc lặp lại mỗi ngày",
                "bullets": ["Giảm sai sót thủ công", "Áp dụng ngay trong 15 giây"],
                "voiceover": "Quy trình gọn nhẹ này giúp tăng gấp năm lần tốc độ xử lý và giảm hẳn sai sót.",
            },
        ],
        "cta": {
            "highlight_metric": "70%",
            "summary": "Câu lệnh đầy đủ để sẵn dưới bình luận",
            "button_text": SLOT_CTA_BUTTON.get(slot, "📋 Copy trọn bộ Prompt dưới Bình luận"),
            "voiceover": "Trọn bộ câu lệnh mẫu mình ghim sẵn dưới phần bình luận, và lý do bạn nên lưu ngay là vì",
        },
        "caption": f"{topic} cực dễ áp dụng trong 20 giây! #meoai #aithucchien #congnghe #shorts",
        "full_prompt": f"Hãy đóng vai chuyên gia xử lý {topic}, phân tích dữ liệu [đính kèm tại đây], chỉ ra 3 điểm cốt lõi nhất và trình bày kết quả dưới dạng bảng hành động chi tiết để áp dụng ngay.",
        "pinned_question": f"Bạn đã thử dùng AI cho '{topic}' chưa? Để lại bình luận bên dưới nhé!",
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
                if isinstance(raw, dict) and theme in THEMES:
                    raw["bg_theme"] = theme
                script = validate(raw, slot=slot)
                print(f"[gemini] OK model={model} key=#{key_idx} theme={script['bg_theme']} voice={script['voice']} scenes={[x['type'] for x in script['scenes']]}")
                return script
            except Exception as ex:
                msg = str(ex)
                print(f"[gemini] {model} lần {attempt + 1} lỗi: {msg[:150]}")
                if "HTTP 404" in msg or "HTTP 400" in msg:
                    break
                time.sleep(3 * (attempt + 1))
    print("[gemini] CẢNH BÁO: Toàn bộ 8 model Gemini đang quá tải 503 -> kích hoạt Fallback Script để ca phát sóng không bị gián đoạn!")
    return _fallback_script(topic, slot, theme)


def fetch_yt_autocomplete(seeds=("cách dùng ai", "mẹo chatgpt", "dùng ai làm excel", "gemini ai")):
    """Lấy gợi ý tìm kiếm thực tế của người dùng YouTube Việt Nam (không cần API key)."""
    found = []
    for q in seeds:
        try:
            r = requests.get(
                "https://suggestqueries.google.com/complete/search",
                params={"client": "firefox", "ds": "yt", "hl": "vi", "gl": "VN", "q": q},
                timeout=6,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            if r.status_code == 200:
                arr = r.json()
                if isinstance(arr, list) and len(arr) > 1 and isinstance(arr[1], list):
                    for item in arr[1][:4]:
                        s = str(item).strip()
                        if s and s not in found:
                            found.append(s)
        except Exception:
            continue
    return found[:12]


def _format_insights_block(insights=None):
    if not insights:
        return ""
    parts = []
    if insights.get("comments"):
        parts.append("Câu hỏi / Bình luận thật từ khán giả (ƯU TIÊN làm video trả lời trực tiếp):\n" + "\n".join(f"- {c}" for c in insights["comments"][:5]))
    if insights.get("winners"):
        parts.append("Các chủ đề ĐANG ĐƯỢC XEM & GIỮ CHÂN TỐT NHẤT (hãy đào sâu thêm góc mới thuộc nhóm này):\n" + "\n".join(f"- {w}" for w in insights["winners"][:3]))
    if insights.get("losers"):
        parts.append("Các chủ đề ÍT NGƯỜI XEM (tránh lặp lại kiểu tiếp cận này):\n" + "\n".join(f"- {l}" for l in insights["losers"][:3]))
    return ("\n\n" + "\n\n".join(parts)) if parts else ""


def generate_topic(slot, recent=(), api_key=None, insights=None):
    keys = get_api_keys(api_key)
    avoid = "\n".join(f"- {t}" for t in recent) or "(chưa có)"
    news_block = ""
    if slot == "SANG":
        headlines = fetch_tech_headlines()
        if headlines:
            news_block = "\nTin tức công nghệ/AI mới nhất hôm nay:\n" + "\n".join(f"- {h}" for h in headlines)
    trends = fetch_yt_autocomplete()
    trend_block = ("\nTừ khóa người Việt ĐANG TÌM NHIỀU trên YouTube:\n" + "\n".join(f"- {x}" for x in trends[:8])) if trends else ""
    ins_block = _format_insights_block(insights)
    prompt = f"""Bạn là biên tập viên kênh 'Thiện AI Thực Chiến'.
Ca phát sóng: {slot} — {SLOT_HINT.get(slot, '')}{news_block}{trend_block}{ins_block}
Các chủ đề đã làm gần đây (TUYỆT ĐỐI KHÔNG TRÙNG LẶP):
{avoid}

Hãy đề xuất 1 chủ đề video ngắn (20-30 giây) đánh trúng nhu cầu tìm kiếm hoặc câu hỏi của khán giả.
Trả về JSON: {{"topic": "Tên chủ đề ngắn gọn 10-18 từ", "bg_theme": "{'|'.join(THEMES)}"}}"""
    rotated_theme = THEMES[len(recent) % len(THEMES)]
    for model in MODELS[:5]:
        try:
            res, _ = _call_with_rotation(model, prompt, keys)
            topic = str(res.get("topic", "")).strip()
            if topic:
                return topic, rotated_theme
        except Exception:
            time.sleep(2)
    return f"3 mẹo ứng dụng AI tăng tốc công việc ca {slot}", rotated_theme


def generate_batch_topics(recent=(), days=3, api_key=None):
    keys = get_api_keys(api_key)
    avoid = "\n".join(f"- {t}" for t in recent) or "(chưa có)"
    headlines = fetch_tech_headlines()
    news_block = "\nTin tức AI/công nghệ mới nhất:\n" + "\n".join(f"- {h}" for h in headlines) if headlines else ""
    slots = ("SANG", "TRUA", "CHIEU", "TOI")
    count = days * len(slots)
    prompt = f"""Bạn là giám đốc nội dung kênh 'Thiện AI Thực Chiến'.
Hãy lập kế hoạch {count} chủ đề video ngắn (chia đều theo thứ tự SANG, TRUA, CHIEU, TOI cho {days} ngày tới).
{news_block}
Các chủ đề đã làm (KHÔNG TRÙNG LẶP):
{avoid}

Trả về JSON: {{"items": [{{"slot": "SANG", "bg_theme": "clean_light", "topic": "..."}}, ...]}}"""
    for model in MODELS[:5]:
        try:
            res, _ = _call_with_rotation(model, prompt, keys)
            items = res if isinstance(res, list) else res.get("items", [])
            out = []
            for idx, it in enumerate(items[:count]):
                sl = it.get("slot") if it.get("slot") in slots else slots[idx % len(slots)]
                th = THEMES[(len(recent) + idx) % len(THEMES)]
                tp = str(it.get("topic", "")).strip()
                if tp:
                    out.append((sl, th, tp))
            if len(out) >= 4:
                return out
        except Exception:
            time.sleep(2)
    return []


def generate_evergreen_topics(slot, count=6, recent=(), api_key=None, insights=None):
    """Sinh danh sách chủ đề EVERGREEN theo đúng nhu cầu tìm kiếm & phản hồi khán giả thực tế cho kho dự trữ Ca Trưa, Ca Chiều & Ca Tối."""
    keys = get_api_keys(api_key)
    avoid = "\n".join(f"- {t}" for t in recent[-35:]) or "(chưa có)"
    focus_map = {
        "TRUA": "So sánh tính năng AI Free vs Pro, bài toán tiết kiệm thời gian/chi phí thực tế, cách chọn công cụ AI thông minh cho dân văn phòng/kinh doanh",
        "CHIEU": "Giải cứu việc văn phòng cuối giờ: sửa nhanh lỗi Excel/Google Sheets, tóm tắt PDF/Word dài 100 trang, lập báo cáo & xử lý Email trong 15 giây",
        "TOI": "Quy trình 3 bước tự động hóa thực chiến, câu lệnh Prompt mẫu chuyên sâu copy-dùng-ngay cho công việc, học tập và sáng tạo nội dung",
    }
    focus = focus_map.get(slot, focus_map["TOI"])
    trends = fetch_yt_autocomplete()
    trend_block = ("\nTừ khóa người Việt ĐANG TÌM KIẾM NHIỀU NHẤT trên YouTube:\n" + "\n".join(f"- {x}" for x in trends[:10])) if trends else ""
    ins_block = _format_insights_block(insights)
    prompt = f"""Bạn là giám đốc nội dung kênh 'Thiện AI Thực Chiến'.
Hãy đề xuất {count} chủ đề video ngắn EVERGREEN (giá trị thực chiến bền vững, KHÔNG gắn ngày tháng cụ thể) cho ca {slot}:
Định hướng ca {slot}: {focus}.{trend_block}{ins_block}

Quy tắc tối ưu theo nhu cầu khán giả:
- Dành khoảng 60% chủ đề bám sát từ khóa người Việt đang tìm kiếm hoặc đào sâu nhóm chủ đề đang có điểm xem/giữ chân cao nhất.
- Nếu có câu hỏi từ bình luận khán giả, biến ít nhất 1 câu hỏi thành 1 chủ đề trả lời trực tiếp.

Các chủ đề đã có trong kho (TUYỆT ĐỐI KHÔNG TRÙNG Ý TƯỞNG):
{avoid}

Trả về JSON đúng định dạng:
{{"items": [{{"bg_theme": "{'|'.join(THEMES)}", "topic": "Tên chủ đề súc tích 10-18 từ"}}, ...]}}"""
    offset = {"TRUA": 0, "CHIEU": 2, "TOI": 5}.get(slot, 3)
    for model in MODELS[:5]:
        try:
            res, _ = _call_with_rotation(model, prompt, keys)
            raw_items = res if isinstance(res, list) else res.get("items", [])
            out = []
            for idx, it in enumerate(raw_items[:count]):
                if not isinstance(it, dict):
                    continue
                th = THEMES[(len(recent) + offset + idx) % len(THEMES)]
                tp = str(it.get("topic", "")).strip()
                if tp:
                    out.append((sl := slot, th, tp))
            if out:
                print(f"[gemini] đã sinh {len(out)} chủ đề Evergreen tối ưu theo nhu cầu khán giả cho ca {slot}")
                return out
        except Exception as ex:
            print(f"[gemini] generate_evergreen_topics ({model}) lỗi: {str(ex)[:100]}")
            time.sleep(2)
    return [(slot, THEMES[(len(recent) + offset) % len(THEMES)], f"Bí quyết ứng dụng AI tối ưu hiệu suất làm việc ca {slot}")]
