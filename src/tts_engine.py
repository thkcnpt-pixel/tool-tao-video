"""Edge-TTS + trích xuất phụ đề (WordBoundary -> SentenceBoundary -> chia theo tỷ lệ ký tự)."""
import asyncio
import math
import re
import subprocess
from pathlib import Path

DEFAULT_VOICE = "vi-VN-HoaiMyNeural"
DEFAULT_RATE = "+8%"


def probe_duration(path):
    out = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                   "-of", "default=nw=1:nk=1", str(path)])
    return float(out.strip())


async def _synth(text, voice, rate, out):
    import edge_tts
    try:
        comm = edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary")
    except TypeError:  # phiên bản cũ không có tham số boundary
        comm = edge_tts.Communicate(text, voice, rate=rate)
    events = []
    with open(out, "wb") as f:
        async for ch in comm.stream():
            if ch["type"] == "audio":
                f.write(ch["data"])
            elif ch["type"] in ("WordBoundary", "SentenceBoundary"):
                events.append((ch["type"], ch["offset"] / 1e7, ch["duration"] / 1e7, ch["text"]))
    return events


def _silent(out, seconds):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
                    "-t", f"{seconds:.2f}", "-c:a", "libmp3lame", str(out)], check=True)


def _spread(words, start, end):
    """Chia thời gian cho từng từ theo tỷ lệ độ dài ký tự (fallback)."""
    total = sum(len(w) + 1 for w in words) or 1
    t, res = start, []
    for w in words:
        d = (end - start) * (len(w) + 1) / total
        res.append((w, t, t + d))
        t += d
    return res


def words_timing(text, duration, events):
    """Trả về [(word, start, end)]."""
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
        if re.search(r"\d", w) or (len(w) > 2 and w.isupper()):
            return i
    return max(range(len(words)), key=lambda i: len(words[i]))


def make_chunks(timed, duration, per=5):
    """Gom cụm 4-5 từ, kèm từ khóa highlight."""
    n = len(timed)
    if n == 0:
        return []
    groups = math.ceil(n / per)
    size = math.ceil(n / groups)
    chunks = []
    for g in range(0, n, size):
        part = timed[g:g + size]
        words = [p[0] for p in part]
        chunks.append(dict(s=part[0][1], e=part[-1][2], words=words, kw=keyword_index(words)))
    # nối liền: mỗi cụm hiển thị đến khi cụm sau bắt đầu
    for i, c in enumerate(chunks):
        c["e"] = chunks[i + 1]["s"] if i + 1 < len(chunks) else min(duration, c["e"] + 0.4)
    chunks[0]["s"] = 0.0
    return chunks


def synthesize(text, out_path, voice=DEFAULT_VOICE, rate=DEFAULT_RATE):
    """Tạo mp3 và phụ đề. Trả về (duration, chunks)."""
    out_path = Path(out_path)
    events = []
    try:
        events = asyncio.run(_synth(text, voice, rate, out_path))
        duration = probe_duration(out_path)
    except Exception as ex:  # mất mạng / dịch vụ lỗi: vẫn dựng được video (im lặng) để pipeline không chết
        print(f"[tts] CẢNH BÁO edge-tts lỗi ({ex!r}) -> dùng âm thanh im lặng ước lượng")
        duration = max(2.0, len(text.split()) / 3.2)
        _silent(out_path, duration)
    timed = words_timing(text, duration, events)
    return duration, make_chunks(timed, duration)
