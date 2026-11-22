"""Edge-TTS (có retry 4 lần + dự phòng gTTS tiếng Việt để KHÔNG BAO GIỜ mất tiếng) + phụ đề Karaoke từng từ."""
import asyncio
import re
import subprocess
import time
from pathlib import Path

DEFAULT_VOICE = "vi-VN-HoaiMyNeural"
DEFAULT_RATE = "+22%"

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
    """Làm sạch ký tự đặc biệt khiến edge-tts đôi khi trả NoAudioReceived."""
    t = re.sub(r"[\r\n\t]+", " ", str(text))
    t = re.sub(r"[#*`_~<>[\]{}|\\]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    parts = [p.strip() for p in re.split(r"[.?!]+", t) if p.strip()]
    return ", ".join(parts) + "." if parts else t


async def _synth_once(text, voice, rate, out):
    import edge_tts
    clean = _clean_voice_text(text)
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


def _trim_and_boost(path, last_word_end, atempo=1.0):
    """Cắt bỏ khoảng im lặng thừa cuối file và khuếch đại giọng đọc rõ, dày, không rè."""
    raw_dur = probe_duration(path)
    target = min(raw_dur, max(0.8, last_word_end + 0.14)) if last_word_end > 0 else raw_dur
    tmp = Path(str(path) + ".trim.mp3")
    af = "highpass=f=80,acompressor=threshold=-20dB:ratio=3:attack=5:release=50:makeup=4dB,volume=5dB,alimiter=limit=0.95"
    if atempo and abs(atempo - 1.0) > 0.02:
        af = f"atempo={atempo:.2f}," + af
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error", "-i", str(path),
        "-t", f"{target:.3f}",
        "-af", af,
        "-c:a", "libmp3lame", "-b:a", "128k", str(tmp),
    ], check=True)
    tmp.replace(path)
    return probe_duration(path)


def _gtts_fallback(text, out_path):
    """Dự phòng khi edge-tts bị Microsoft chặn tạm thời trên runner: dùng Google Translate TTS tiếng Việt."""
    from gtts import gTTS
    clean = _clean_voice_text(text)
    gTTS(clean, lang="vi", slow=False).save(str(out_path))
    # gTTS đọc hơi chậm nên tăng tốc 1.25x + cắt khoảng lặng cuối bằng silenceremove
    tmp = Path(str(out_path) + ".gtts.mp3")
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error", "-i", str(out_path),
        "-af", "atempo=1.25,silenceremove=stop_periods=-1:stop_duration=0.18:stop_threshold=-42dB,"
               "highpass=f=80,acompressor=threshold=-20dB:ratio=3:attack=5:release=50:makeup=4dB,volume=5dB,alimiter=limit=0.95",
        "-c:a", "libmp3lame", "-b:a", "128k", str(tmp),
    ], check=True)
    tmp.replace(out_path)
    return probe_duration(out_path)


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
    """Tạo mp3 giọng đọc (retry 4 lần edge-tts -> fallback gTTS tiếng Việt) + phụ đề Karaoke từng từ."""
    out_path = Path(out_path)
    events = []
    alt_voice = "vi-VN-NamMinhNeural" if voice == "vi-VN-HoaiMyNeural" else "vi-VN-HoaiMyNeural"
    attempts = [(voice, rate), (voice, rate), (voice, "+15%"), (alt_voice, rate)]

    last_err = None
    for idx, (v, r) in enumerate(attempts):
        try:
            if idx > 0:
                time.sleep(0.8 * idx)
            events = asyncio.run(_synth_once(text, v, r, out_path))
            wb = [e for e in events if e[0] == "WordBoundary"]
            last_end = (wb[-1][1] + wb[-1][2]) if wb else 0.0
            duration = _trim_and_boost(out_path, last_end)
            timed = words_timing(text, duration, events)
            return duration, make_chunks(timed, duration)
        except Exception as ex:
            last_err = ex
            print(f"[tts] edge-tts thử lần {idx + 1}/4 lỗi ({ex!r})")

    print(f"[tts] edge-tts thất bại sau 4 lần ({last_err!r}) -> chuyển sang gTTS tiếng Việt dự phòng (có tiếng 100%)")
    duration = _gtts_fallback(text, out_path)
    timed = words_timing(text, duration, [])
    return duration, make_chunks(timed, duration)
