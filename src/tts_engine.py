"""Edge-TTS + cắt khoảng lặng thừa + trích xuất phụ đề Karaoke từng từ (có fallback)."""
import asyncio
import re
import subprocess
from pathlib import Path

DEFAULT_VOICE = "vi-VN-HoaiMyNeural"
DEFAULT_RATE = "+22%"

# Các từ đệm phổ biến không nên chọn làm từ khóa tĩnh
STOPWORDS = {
    "và", "của", "cho", "với", "những", "các", "một", "được", "trong", "khi", "này", "đó",
    "rất", "hơn", "nhất", "cùng", "mình", "bạn", "hãy", "nhé", "nhưng", "liệu", "nếu", "thì",
    "là", "có", "để", "từ", "về", "theo", "như", "đang", "sẽ", "đã", "chỉ", "còn", "hay",
}


def probe_duration(path):
    out = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                   "-of", "default=nw=1:nk=1", str(path)])
    return float(out.strip())


def _clean_voice_text(text):
    """Giúp TTS đọc mạch lạc, không nghỉ quá dài ở dấu chấm giữa câu ngắn."""
    t = re.sub(r"\s+", " ", text.strip())
    # Đổi dấu chấm/chấm hỏi ở giữa câu thành dấu phẩy để TTS không nghỉ 0.8s giữa chừng
    parts = [p.strip() for p in re.split(r"[.?!]+", t) if p.strip()]
    return ", ".join(parts) + "." if parts else t


async def _synth(text, voice, rate, out):
    import edge_tts
    clean = _clean_voice_text(text)
    try:
        comm = edge_tts.Communicate(clean, voice, rate=rate, boundary="WordBoundary")
    except TypeError:
        comm = edge_tts.Communicate(clean, voice, rate=rate)
    events = []
    with open(out, "wb") as f:
        async for ch in comm.stream():
            if ch["type"] == "audio":
                f.write(ch["data"])
            elif ch["type"] in ("WordBoundary", "SentenceBoundary"):
                events.append((ch["type"], ch["offset"] / 1e7, ch["duration"] / 1e7, ch["text"]))
    return events


def _trim_tail(path, last_word_end):
    """Cắt bỏ khoảng im lặng thừa cuối file của edge-tts và chuẩn hóa âm lượng giọng đọc."""
    raw_dur = probe_duration(path)
    target = min(raw_dur, max(0.8, last_word_end + 0.14)) if last_word_end > 0 else raw_dur
    tmp = Path(str(path) + ".trim.mp3")
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error", "-i", str(path),
        "-t", f"{target:.3f}",
        "-af", "highpass=f=80,acompressor=threshold=-20dB:ratio=3:attack=5:release=50:makeup=4dB,volume=5dB,alimiter=limit=0.95",
        "-c:a", "libmp3lame", "-b:a", "128k", str(tmp),
    ], check=True)
    tmp.replace(path)
    return probe_duration(path)


def _silent(out, seconds):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
                    "-t", f"{seconds:.2f}", "-c:a", "libmp3lame", str(out)], check=True)


def _spread(words, start, end):
    total = sum(len(w) + 1 for w in words) or 1
    t, res = start, []
    for w in words:
        d = (end - start) * (len(w) + 1) / total
        res.append((w, t, t + d))
        t += d
    return res


def words_timing(text, duration, events):
    wb = [e for e in events if e[0] == "WordBoundary"]
    if wb:
        return [(e[3], e[1], e[1] + e[2]) for e in wb]
    sb = [e for e in events if e[0] == "SentenceBoundary"]
    if sb:
        res = []
        for i, e in enumerate(sb):
            end = e[1] + e[2] if e[2] else (sb[i + 1][1] if i + 1 < len(sb) else duration)
            res += _spread(e[3].split(), e[1], end)
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
    """Gom cụm 4-5 từ; mỗi cụm chứa danh sách từ kèm mốc (w, ws, we) để highlight Karaoke từng từ."""
    n = len(timed)
    if n == 0:
        return []
    chunks = []
    i = 0
    while i < n:
        end_i = min(i + per, n)
        # Nếu gần cuối hoặc có khoảng nghỉ > 0.25s giữa 2 từ thì ngắt cụm tại đó cho tự nhiên
        for j in range(i + 2, end_i):
            if j < n and (timed[j][1] - timed[j - 1][2]) > 0.22:
                end_i = j
                break
        if n - end_i == 1:
            end_i = n
        part = timed[i:end_i]
        words = [p[0] for p in part]
        # Nối liền thời gian kết thúc của từng từ tới đầu từ kế tiếp để highlight không bị nhấp nháy
        wt = []
        for k, (w, ws, we) in enumerate(part):
            next_s = part[k + 1][1] if k + 1 < len(part) else max(we, ws + 0.18)
            wt.append({"w": w, "s": round(ws, 3), "e": round(max(we, next_s), 3)})
        chunks.append(dict(s=part[0][1], e=part[-1][2], words=words, wt=wt, kw=keyword_index(words)))
        i = end_i

    for idx, c in enumerate(chunks):
        c["e"] = chunks[idx + 1]["s"] if idx + 1 < len(chunks) else min(duration, c["e"] + 0.25)
        if c["wt"]:
            c["wt"][-1]["e"] = round(c["e"], 3)
    chunks[0]["s"] = 0.0
    if chunks[0]["wt"]:
        chunks[0]["wt"][0]["s"] = 0.0
    return chunks


def synthesize(text, out_path, voice=DEFAULT_VOICE, rate=DEFAULT_RATE):
    """Tạo mp3 (đã cắt khoảng lặng thừa) và phụ đề Karaoke từng từ. Trả về (duration, chunks)."""
    out_path = Path(out_path)
    events = []
    try:
        events = asyncio.run(_synth(text, voice, rate, out_path))
        wb = [e for e in events if e[0] == "WordBoundary"]
        last_end = (wb[-1][1] + wb[-1][2]) if wb else 0.0
        duration = _trim_tail(out_path, last_end)
    except Exception as ex:
        print(f"[tts] CẢNH BÁO edge-tts lỗi ({ex!r}) -> dùng âm thanh im lặng ước lượng")
        duration = max(2.0, len(text.split()) / 3.5)
        _silent(out_path, duration)
    timed = words_timing(text, duration, events)
    return duration, make_chunks(timed, duration)
