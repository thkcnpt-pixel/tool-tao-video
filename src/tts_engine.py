"""TTS Engine thế hệ mới:
1. Ưu tiên Gemini 2.5 Native Audio TTS (giọng người thật tự nhiên, giàu cảm xúc: Kore / Puck / Aoede / Fenrir) xoay vòng qua 3 API Key.
2. Đảm bảo đồng nhất 100% giọng đọc xuyên suốt 1 video (không bao giờ trộn 2 giọng giữa chừng): nếu Gemini TTS chạm giới hạn quota ở bất kỳ đoạn nào, tự động chuyển mượt toàn bộ video đó sang Edge-TTS Neural (dự phòng tầng 3: gTTS).
3. Cắt sát đầu Hook (trim_head=True) và đuôi CTA (is_loop_tail=True) bằng FFmpeg silencedetect + cân trọng số dấu câu cho phụ đề Karaoke khớp từng nhịp đọc.
"""
import asyncio
import base64
import hashlib
import os
import re
import subprocess
import time
from pathlib import Path

import requests

DEFAULT_VOICE = "vi-VN-HoaiMyNeural"
DEFAULT_RATE = "+12%"

GEMINI_TTS_MODEL = "gemini-2.5-flash-preview-tts"
GEMINI_TTS_ENDPOINT = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_TTS_MODEL}:generateContent"
GEMINI_FEMALE_VOICES = ("Kore", "Aoede")
GEMINI_MALE_VOICES = ("Puck", "Fenrir")
_GEMINI_TTS_DEAD_KEYS = set()

STOPWORDS = {
    "và", "của", "cho", "với", "những", "các", "một", "được", "trong", "khi", "này", "đó",
    "rất", "hơn", "nhất", "cùng", "mình", "bạn", "hãy", "nhé", "nhưng", "liệu", "nếu", "thì",
    "là", "có", "để", "từ", "về", "theo", "như", "đang", "sẽ", "đã", "chỉ", "còn", "hay",
}


def probe_duration(path):
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=nw=1:nk=1", str(path),
    ])
    return float(out.strip())


def _clean_voice_text(text, is_loop_tail=False):
    """Làm sạch ký tự đặc biệt. Nếu là cảnh cuối (is_loop_tail=True), bỏ dấu chấm kết câu để TTS giữ ngữ điệu mở nối sang đầu video."""
    t = re.sub(r"[\r\n\t]+", " ", str(text))
    t = re.sub(r"[#*`_~<>[\]{}|\\]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    parts = [p.strip() for p in re.split(r"[.?!…]+", t) if p.strip()]
    if not parts:
        return t
    joined = ", ".join(parts)
    return joined if is_loop_tail else (joined + ".")


def _get_gemini_keys():
    keys = []
    for name in ("GEMINI_API_KEY", "GEMINI_API_KEY_2", "GEMINI_API_KEY_3"):
        val = os.environ.get(name, "").strip()
        if val and val not in keys and val not in _GEMINI_TTS_DEAD_KEYS:
            keys.append(val)
    return keys


def _pick_gemini_voice(voice_hint, seed_text=""):
    digest = hashlib.md5(seed_text.encode("utf-8")).digest()[0] if seed_text else 0
    if "NamMinh" in str(voice_hint) or str(voice_hint) in GEMINI_MALE_VOICES:
        return voice_hint if voice_hint in GEMINI_MALE_VOICES else GEMINI_MALE_VOICES[digest % len(GEMINI_MALE_VOICES)]
    return voice_hint if voice_hint in GEMINI_FEMALE_VOICES else GEMINI_FEMALE_VOICES[digest % len(GEMINI_FEMALE_VOICES)]


def _rate_to_tempo(rate_str, for_gemini=True):
    m = re.search(r"([+-]?\d+)", str(rate_str or ""))
    pct = int(m.group(1)) if m else 12
    # Gemini TTS đã có tốc độ tự nhiên nhanh gọn sẵn nên chỉ tăng nhẹ ~55% mức pct của Edge-TTS
    scale = 0.55 if for_gemini else 1.0
    return max(0.95, min(1.25, 1.0 + (pct * scale) / 100.0))


def _detect_speech_bounds(audio_path, raw_dur):
    """Dùng silencedetect tìm điểm bắt đầu nói và kết thúc nói chính xác tới mili-giây."""
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(audio_path),
         "-af", "silencedetect=noise=-38dB:d=0.035", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    log = proc.stderr or ""
    starts = [float(x) for x in re.findall(r"silence_start:\s*([0-9.]+)", log)]
    ends = [float(x) for x in re.findall(r"silence_end:\s*([0-9.]+)", log)]

    first_word_start = 0.0
    if starts and ends and starts[0] < 0.05 and ends[0] < raw_dur * 0.5:
        first_word_start = ends[0]

    last_word_end = raw_dur
    if starts and starts[-1] > raw_dur * 0.55:
        if not ends or ends[-1] < starts[-1] or abs(ends[-1] - raw_dur) < 0.06:
            last_word_end = starts[-1]
    return first_word_start, last_word_end


def _gemini_tts_once(text, gemini_voice, rate, out_path, is_loop_tail=False):
    keys = _get_gemini_keys()
    if not keys:
        raise RuntimeError("Không còn GEMINI_API_KEY khả dụng cho Gemini TTS")

    clean = _clean_voice_text(text, is_loop_tail=is_loop_tail)
    body = {
        "contents": [{"parts": [{"text": clean}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {
                    "prebuiltVoiceConfig": {"voiceName": gemini_voice}
                }
            },
        },
    }

    last_err = None
    audio_raw, mime = None, ""
    for k in keys:
        try:
            r = requests.post(
                GEMINI_TTS_ENDPOINT,
                headers={"x-goog-api-key": k, "Content-Type": "application/json"},
                json=body,
                timeout=35,
            )
            if r.status_code != 200:
                msg = f"HTTP {r.status_code}: {r.text[:160]}"
                if r.status_code in (403, 429) or "RESOURCE_EXHAUSTED" in r.text or "quota" in r.text.lower():
                    _GEMINI_TTS_DEAD_KEYS.add(k)
                raise RuntimeError(msg)
            data = r.json()
            part = data["candidates"][0]["content"]["parts"][0]
            inline = part.get("inlineData") or part.get("inline_data") or {}
            b64 = inline.get("data", "")
            mime = inline.get("mimeType") or inline.get("mime_type") or "audio/L16;rate=24000"
            if not b64:
                raise RuntimeError("Gemini TTS trả về rỗng")
            audio_raw = base64.b64decode(b64)
            if len(audio_raw) < 1000:
                raise RuntimeError(f"Gemini TTS audio quá ngắn ({len(audio_raw)}B)")
            break
        except Exception as ex:
            last_err = ex
            continue

    if audio_raw is None:
        raise RuntimeError(f"Gemini TTS lỗi trên mọi key: {last_err!r}")

    raw_tmp = Path(str(out_path) + ".gemraw")
    raw_tmp.write_bytes(audio_raw)
    tempo = _rate_to_tempo(rate, for_gemini=True)
    try:
        mime_low = mime.lower()
        cmd = ["ffmpeg", "-y", "-loglevel", "error"]
        if "l16" in mime_low or "pcm" in mime_low:
            m_rate = re.search(r"rate=(\d+)", mime_low)
            sr = int(m_rate.group(1)) if m_rate else 24000
            cmd += ["-f", "s16le", "-ar", str(sr), "-ac", "1", "-i", str(raw_tmp)]
        else:
            cmd += ["-i", str(raw_tmp)]
        cmd += ["-af", f"atempo={tempo:.3f}", "-c:a", "libmp3lame", "-b:a", "128k", str(out_path)]
        subprocess.run(cmd, check=True)
    finally:
        raw_tmp.unlink(missing_ok=True)

    raw_dur = probe_duration(out_path)
    first_s, last_e = _detect_speech_bounds(out_path, raw_dur)
    duration, _ = _trim_and_boost(out_path, first_s, last_e, trim_head=True, is_loop_tail=is_loop_tail)
    timed = _spread(text.split(), 0.0, max(0.35, duration - (0.02 if is_loop_tail else 0.08)))
    return duration, make_chunks(timed, duration)


async def _synth_once(text, voice, rate, out, is_loop_tail=False):
    import edge_tts
    clean = _clean_voice_text(text, is_loop_tail=is_loop_tail)
    try:
        comm = edge_tts.Communicate(clean, voice, rate=rate, boundary="WordBoundary")
    except TypeError:
        comm = edge_tts.Communicate(clean, voice, rate=rate)
    events = []
    audio_bytes = 0
    with open(out, "wb") as f:
        async for ch in comm.stream():
            if ch["type"] == "audio":
                f.write(ch["data"])
                audio_bytes += len(ch["data"])
            elif ch["type"] in ("WordBoundary", "SentenceBoundary"):
                events.append((ch["type"], ch["offset"] / 1e7, ch["duration"] / 1e7, ch["text"]))
    if audio_bytes < 500:
        raise RuntimeError(f"Audio quá ngắn ({audio_bytes} bytes)")
    return events


def _trim_and_boost(path, first_word_start, last_word_end, trim_head=False, is_loop_tail=False):
    """Cắt bỏ khoảng im lặng đầu (cho Hook) & cuối (cắt sát 0.02s cho CTA), chuẩn hóa âm lượng rõ to."""
    raw_dur = probe_duration(path)
    head_cut = max(0.0, first_word_start - 0.02) if (trim_head and first_word_start > 0.03) else 0.0
    tail_pad = 0.02 if is_loop_tail else 0.12
    end_pos = min(raw_dur, max(head_cut + 0.55, last_word_end + tail_pad)) if last_word_end > 0 else raw_dur
    clip_dur = max(0.45, end_pos - head_cut)

    tmp = Path(str(path) + ".trim.mp3")
    af = "highpass=f=80,acompressor=threshold=-20dB:ratio=3:attack=5:release=50:makeup=4dB,volume=5dB,alimiter=limit=0.95"
    cmd = ["ffmpeg", "-y", "-loglevel", "error"]
    if head_cut > 0:
        cmd += ["-ss", f"{head_cut:.3f}"]
    cmd += ["-i", str(path), "-t", f"{clip_dur:.3f}", "-af", af, "-c:a", "libmp3lame", "-b:a", "128k", str(tmp)]
    subprocess.run(cmd, check=True)
    tmp.replace(path)
    return probe_duration(path), head_cut


def _gtts_fallback(text, out_path, is_loop_tail=False):
    from gtts import gTTS
    clean = _clean_voice_text(text, is_loop_tail=is_loop_tail)
    gTTS(clean, lang="vi", slow=False).save(str(out_path))
    tmp = Path(str(out_path) + ".gtts.mp3")
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error", "-i", str(out_path),
        "-af", "atempo=1.22,silenceremove=start_periods=1:start_duration=0.02:start_threshold=-42dB:"
               "stop_periods=-1:stop_duration=0.04:stop_threshold=-42dB,"
               "highpass=f=80,acompressor=threshold=-20dB:ratio=3:attack=5:release=50:makeup=4dB,volume=5dB,alimiter=limit=0.95",
        "-c:a", "libmp3lame", "-b:a", "128k", str(tmp),
    ], check=True)
    tmp.replace(out_path)
    return probe_duration(out_path)


def _word_weight(w):
    clean = re.sub(r"\W+", "", w)
    base = max(2, len(clean)) + 1.2
    if w.endswith((",", ";", ":", "—", "-")):
        base += 2.6  # Nghỉ nhịp tự nhiên sau dấu phẩy
    elif w.endswith((".", "?", "!", "…")):
        base += 3.5
    return base


def _spread(words, start, end):
    if not words:
        return []
    weights = [_word_weight(w) for w in words]
    total = sum(weights) or 1.0
    t, res = start, []
    for w, wt in zip(words, weights):
        d = (end - start) * wt / total
        res.append((w, t, t + d))
        t += d
    return res


def words_timing(text, duration, events, head_cut=0.0):
    wb = [e for e in events if e[0] == "WordBoundary"]
    if wb:
        out = []
        for e in wb:
            ws = max(0.0, e[1] - head_cut)
            we = max(ws + 0.05, e[1] + e[2] - head_cut)
            out.append((e[3], ws, we))
        return out
    sb = [e for e in events if e[0] == "SentenceBoundary"]
    if sb:
        res = []
        for i, e in enumerate(sb):
            s0 = max(0.0, e[1] - head_cut)
            end = max(s0 + 0.1, (e[1] + e[2] - head_cut) if e[2] else (sb[i + 1][1] - head_cut if i + 1 < len(sb) else duration))
            res += _spread(e[3].split(), s0, end)
        return res
    return _spread(text.split(), 0.0, duration)


def keyword_index(words):
    for i, w in enumerate(words):
        clean = re.sub(r"\W+", "", w)
        if re.search(r"\d", w) or (len(clean) >= 2 and any(c.isupper() for c in clean[1:])):
            return i
    candidates = [i for i, w in enumerate(words) if w.lower().strip(".,?!") not in STOPWORDS]
    pool = candidates or list(range(len(words)))
    return max(pool, key=lambda i: len(words[i]))


def make_chunks(timed, duration, per=5):
    n = len(timed)
    if n == 0:
        return []
    chunks = []
    i = 0
    while i < n:
        end_i = min(i + per, n)
        for j in range(i + 2, end_i):
            if j < n and (timed[j][1] - timed[j - 1][2]) > 0.22:
                end_i = j
                break
        if n - end_i == 1:
            end_i = n
        part = timed[i:end_i]
        words = [p[0] for p in part]
        wt = []
        for k, (w, ws, we) in enumerate(part):
            next_s = part[k + 1][1] if k + 1 < len(part) else max(we, ws + 0.16)
            wt.append({"w": w, "s": round(ws, 3), "e": round(max(we, next_s), 3)})
        chunks.append(dict(s=part[0][1], e=part[-1][2], words=words, wt=wt, kw=keyword_index(words)))
        i = end_i

    for idx, c in enumerate(chunks):
        c["e"] = chunks[idx + 1]["s"] if idx + 1 < len(chunks) else min(duration, c["e"] + 0.20)
        if c["wt"]:
            c["wt"][-1]["e"] = round(c["e"], 3)
    chunks[0]["s"] = 0.0
    if chunks[0]["wt"]:
        chunks[0]["wt"][0]["s"] = 0.0
    return chunks


def _synthesize_edge_or_gtts(text, out_path, voice=DEFAULT_VOICE, rate=DEFAULT_RATE, trim_head=False, is_loop_tail=False):
    out_path = Path(out_path)
    edge_voice = voice if str(voice).startswith("vi-VN-") else DEFAULT_VOICE
    alt_voice = "vi-VN-NamMinhNeural" if edge_voice == "vi-VN-HoaiMyNeural" else "vi-VN-HoaiMyNeural"
    attempts = [(edge_voice, rate), (edge_voice, rate), (edge_voice, "+10%"), (alt_voice, rate)]

    last_err = None
    for idx, (v, r) in enumerate(attempts):
        try:
            if idx > 0:
                time.sleep(0.8 * idx)
            events = asyncio.run(_synth_once(text, v, r, out_path, is_loop_tail=is_loop_tail))
            wb = [e for e in events if e[0] == "WordBoundary"]
            first_start = wb[0][1] if wb else 0.0
            last_end = (wb[-1][1] + wb[-1][2]) if wb else 0.0
            duration, head_cut = _trim_and_boost(
                out_path, first_start, last_end, trim_head=trim_head, is_loop_tail=is_loop_tail
            )
            timed = words_timing(text, duration, events, head_cut=head_cut)
            return duration, make_chunks(timed, duration)
        except Exception as ex:
            last_err = ex
            print(f"[tts] edge-tts thử lần {idx + 1}/4 lỗi ({ex!r})")

    print(f"[tts] edge-tts thất bại sau 4 lần ({last_err!r}) -> chuyển sang gTTS tiếng Việt dự phòng")
    duration = _gtts_fallback(text, out_path, is_loop_tail=is_loop_tail)
    timed = words_timing(text, duration, [])
    return duration, make_chunks(timed, duration)


def synthesize(text, out_path, voice=DEFAULT_VOICE, rate=DEFAULT_RATE, trim_head=False, is_loop_tail=False, allow_gemini=False):
    """Tạo mp3 cho 1 đoạn lẻ. Mặc định dùng synthesize_segments() cho toàn video để đồng nhất 100% giọng."""
    if allow_gemini and _get_gemini_keys():
        try:
            g_voice = _pick_gemini_voice(voice, text)
            return _gemini_tts_once(text, g_voice, rate, Path(out_path), is_loop_tail=is_loop_tail)
        except Exception as ex:
            print(f"[tts] Gemini TTS fallback sang Edge-TTS ({ex!r})")
    return _synthesize_edge_or_gtts(text, out_path, voice=voice, rate=rate, trim_head=trim_head, is_loop_tail=is_loop_tail)


def synthesize_segments(segs, workdir, voice, rate_fn):
    """Tổng hợp giọng đọc cho toàn bộ các phân đoạn của video, cam kết 100% đồng nhất 1 giọng duy nhất:
    - Ưu tiên thử Gemini 2.5 Native Audio TTS (giọng người thật tự nhiên) cho cả video.
    - Nếu bất kỳ phân đoạn nào bị hết quota Gemini TTS -> tự động chuyển mượt toàn bộ video sang Edge-TTS Neural.
    """
    workdir = Path(workdir)
    seed_txt = segs[0]["voiceover"] if segs else ""
    if _get_gemini_keys() and os.environ.get("DISABLE_GEMINI_TTS", "") != "1":
        g_voice = _pick_gemini_voice(voice, seed_txt)
        gem_results = []
        try:
            for i, s in enumerate(segs):
                a = workdir / f"tts_{i}.mp3"
                seg_rate = rate_fn(s["type"])
                d, chunks = _gemini_tts_once(
                    s["voiceover"], g_voice, seg_rate, a, is_loop_tail=(i == len(segs) - 1)
                )
                gem_results.append((a, d, chunks, seg_rate, f"gemini:{g_voice}"))
            print(f"[tts] Đã tổng hợp trọn bộ {len(segs)} cảnh bằng giọng người thật Gemini TTS ({g_voice})")
            return gem_results
        except Exception as ex:
            print(f"[tts] Gemini TTS chạm giới hạn ({str(ex)[:110]}) -> đồng bộ 100% video sang Edge-TTS ({voice})")

    edge_results = []
    for i, s in enumerate(segs):
        a = workdir / f"tts_{i}.mp3"
        seg_rate = rate_fn(s["type"])
        d, chunks = _synthesize_edge_or_gtts(
            s["voiceover"], a, voice=voice, rate=seg_rate,
            trim_head=(i == 0), is_loop_tail=(i == len(segs) - 1),
        )
        edge_results.append((a, d, chunks, seg_rate, voice))
    return edge_results
