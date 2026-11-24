"""Edge-TTS (retry 4 lần + dự phòng gTTS) + Seamless Loop Audio Trim:
- Cảnh Hook (trim_head=True): cắt bỏ ~0.15s khoảng lặng đầu file của edge-tts và dịch khớp mốc thời gian phụ đề.
- Cảnh CTA (is_loop_tail=True): giữ ngữ điệu lửng giữa câu (không thêm dấu chấm cuối) và cắt sát đuôi (0.02s) để nối thẳng vào từ đầu tiên của cảnh Hook khi video phát lặp lại!
"""
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
    """Cắt bỏ khoảng im lặng đầu (cho Hook) & cuối (cắt sát 0.02s cho CTA), chuẩn hóa âm lượng rõ to.
    Trả về (duration_mới, head_offset_đã_cắt).
    """
    raw_dur = probe_duration(path)
    head_cut = max(0.0, first_word_start - 0.02) if (trim_head and first_word_start > 0.03) else 0.0
    tail_pad = 0.02 if is_loop_tail else 0.12
    end_pos = min(raw_dur, max(head_cut + 0.6, last_word_end + tail_pad)) if last_word_end > 0 else raw_dur
    clip_dur = max(0.5, end_pos - head_cut)

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
        "-af", "atempo=1.25,silenceremove=start_periods=1:start_duration=0.02:start_threshold=-42dB:"
               "stop_periods=-1:stop_duration=0.04:stop_threshold=-42dB,"
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


def synthesize(text, out_path, voice=DEFAULT_VOICE, rate=DEFAULT_RATE, trim_head=False, is_loop_tail=False):
    """Tạo mp3 giọng đọc + phụ đề Karaoke từng từ (hỗ trợ cắt sát đầu Hook và đuôi CTA cho Seamless Loop)."""
    out_path = Path(out_path)
    events = []
    alt_voice = "vi-VN-NamMinhNeural" if voice == "vi-VN-HoaiMyNeural" else "vi-VN-HoaiMyNeural"
    attempts = [(voice, rate), (voice, rate), (voice, "+18%"), (alt_voice, rate)]

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
