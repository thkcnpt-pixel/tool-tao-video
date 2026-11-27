"""Google Sheets làm CMS: tab `Schedule` (10 cột)."""
import os

from googleapiclient.discovery import build

try:
    from .google_auth import get_credentials
except ImportError:  # chạy trực tiếp
    from google_auth import get_credentials

TAB = "Schedule"
COLUMNS = ["id", "date", "slot", "topic", "bg_theme", "script_json", "caption", "status",
           "telegram_msg_id", "video_url_or_drive_id"]
STATUSES = ("CHO_TAO", "DANG_TAO", "DA_DUNG_SAN", "CHO_DUYET", "DA_DUYET", "DA_HUY", "DA_DANG")


def _col_letter(i):  # 0 -> A
    return chr(ord("A") + i)


class SheetsClient:
    def __init__(self, sheet_id=None):
        self.sheet_id = sheet_id or os.environ["GOOGLE_SHEET_ID"]
        self.svc = build("sheets", "v4", credentials=get_credentials(), cache_discovery=False).spreadsheets()

    def ensure_tab(self):
        """Tạo tab Schedule + dòng tiêu đề nếu chưa có."""
        meta = self.svc.get(spreadsheetId=self.sheet_id, fields="sheets.properties.title").execute()
        titles = [s["properties"]["title"] for s in meta["sheets"]]
        if TAB not in titles:
            self.svc.batchUpdate(spreadsheetId=self.sheet_id,
                                 body={"requests": [{"addSheet": {"properties": {"title": TAB}}}]}).execute()
        head = self.svc.values().get(spreadsheetId=self.sheet_id, range=f"{TAB}!A1:J1").execute().get("values", [])
        if not head or head[0] != COLUMNS:
            self.svc.values().update(spreadsheetId=self.sheet_id, range=f"{TAB}!A1:J1",
                                     valueInputOption="RAW", body={"values": [COLUMNS]}).execute()

    def rows(self):
        """Toàn bộ dòng dữ liệu: list[dict] kèm khóa `_row` (số dòng trong sheet, bắt đầu 2)."""
        vals = self.svc.values().get(spreadsheetId=self.sheet_id, range=f"{TAB}!A2:J").execute().get("values", [])
        out = []
        for i, r in enumerate(vals):
            d = {c: (r[j] if j < len(r) else "") for j, c in enumerate(COLUMNS)}
            d["_row"] = i + 2
            out.append(d)
        return out

    def add_row(self, **fields):
        row = [fields.get(c, "") for c in COLUMNS]
        self.svc.values().append(spreadsheetId=self.sheet_id, range=f"{TAB}!A:J", valueInputOption="RAW",
                                 insertDataOption="INSERT_ROWS", body={"values": [row]}).execute()

    def next_pending(self, slot=None):
        """Dòng CHO_TAO đầu tiên (ưu tiên đúng ca nếu truyền slot)."""
        pend = [r for r in self.rows() if r["status"] == "CHO_TAO"]
        if slot:
            m = [r for r in pend if r["slot"] == slot]
            if m:
                return m[0]
        return pend[0] if pend else None

    def recent_topics(self, n=10, exclude_row=None):
        rs = [r for r in self.rows() if r["topic"] and r["_row"] != exclude_row]
        return [r["topic"] for r in rs[-n:]]

    def update(self, row, **fields):
        data = []
        for k, v in fields.items():
            c = _col_letter(COLUMNS.index(k))
            data.append({"range": f"{TAB}!{c}{row}", "values": [[v]]})
        self.svc.values().batchUpdate(spreadsheetId=self.sheet_id,
                                      body={"valueInputOption": "RAW", "data": data}).execute()

    def audience_insights(self):
        """Phân tích toàn diện phản hồi khán giả từ các video đã đăng:
        - top_winners: Top 4 video có điểm giữ chân & tương tác cao nhất.
        - low_performers: 3 chủ đề ít tương tác nhất (để AI tránh lặp lại góc tiếp cận nhàm chán).
        - best_themes: Các bg_theme có điểm trung bình cao nhất.
        - viewer_comments: Bình luận/yêu cầu thực tế của người xem dưới video.
        """
        try:
            from youtube_uploader import fetch_audience_comments, fetch_video_metrics
        except Exception:
            fetch_video_metrics = lambda ids: {}
            fetch_audience_comments = lambda ids: []

        published = [r for r in self.rows() if r["status"] == "DA_DANG" and r["topic"]]
        yt_ids = []
        for r in published:
            ref = str(r.get("video_url_or_drive_id", ""))
            if "|" in ref:
                yt_ids.append(ref.split("|", 1)[1])

        metrics = fetch_video_metrics(yt_ids) if yt_ids else {}
        comments = fetch_audience_comments(yt_ids) if yt_ids else []

        scored = []
        theme_scores = {}
        for r in published:
            ref = str(r.get("video_url_or_drive_id", ""))
            yid = ref.split("|", 1)[1] if "|" in ref else ""
            m = metrics.get(yid, {"views": 0, "likes": 0, "comments": 0, "apv": 0.0, "score": 0})
            th = r.get("bg_theme") or "clean_light"
            apv_str = f", giữ chân {m['apv']}%" if m.get("apv") else ""
            stat_tag = (
                f" [{m['views']} xem, {m['likes']} thích, {m['comments']} cmt{apv_str} | theme={th}]"
                if m["views"]
                else ""
            )
            scored.append((m["score"], m["views"], r["topic"], th, f"{r['topic']} (Caption: {r['caption'][:70]}){stat_tag}"))
            if m["views"] > 0:
                theme_scores.setdefault(th, []).append(m["score"])

        scored.sort(key=lambda x: x[0], reverse=True)
        winners = [x[4] for x in scored[:4]]
        with_views = [x for x in scored if x[1] > 0]
        losers = [f"{x[2]} ({x[1]} xem)" for x in with_views[-3:]] if len(with_views) >= 5 else []
        best_themes = sorted(theme_scores.keys(), key=lambda k: sum(theme_scores[k]) / len(theme_scores[k]), reverse=True)
        return {
            "winners": winners,
            "losers": losers,
            "best_themes": best_themes,
            "comments": comments,
        }

    def top_performing_hooks(self, n=4):
        """Trả về danh sách các chủ đề/tiêu đề hiệu quả nhất sắp theo Điểm Giữ Chân & Tương Tác."""
        return self.audience_insights()["winners"][:n]

    def next_buffered(self, slot):
        """Smart Vault Dispatch: Lấy video dựng sẵn trong kho (DA_DUNG_SAN) đúng ca, ưu tiên phong cách/chủ đề đang có tương tác cao nhất."""
        candidates = [
            r for r in self.rows()
            if r["status"] == "DA_DUNG_SAN" and r["slot"] == slot and r["video_url_or_drive_id"]
        ]
        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0]
        try:
            ins = self.audience_insights()
            best_th = ins.get("best_themes", [])
            if best_th:
                for th in best_th[:2]:
                    for c in candidates:
                        if c.get("bg_theme") == th:
                            return c
        except Exception:
            pass
        return candidates[0]

    def buffered_counts(self):
        """Đếm số lượng video dựng sẵn (DA_DUNG_SAN) theo từng ca."""
        counts = {"TRUA": 0, "TOI": 0, "SANG": 0}
        for r in self.rows():
            if r["status"] == "DA_DUNG_SAN":
                sl = r.get("slot") or "TRUA"
                counts[sl] = counts.get(sl, 0) + 1
        return counts

    def protected_drive_ids(self):
        """Danh sách drive_file_id của mọi video chưa đăng xong (DA_DUNG_SAN, CHO_DUYET, DA_DUYET, CHO_DANG_YT)."""
        keep_st = {"DA_DUNG_SAN", "CHO_DUYET", "DA_DUYET", "CHO_DANG_YT"}
        return [r["video_url_or_drive_id"] for r in self.rows() if r["status"] in keep_st and r["video_url_or_drive_id"]]

    def recover_stale_locks(self):
        """Giải cứu các dòng bị kẹt ở trạng thái DANG_TAO / DANG_DANG do job trước bị hủy giữa chừng."""
        recovered = 0
        for r in self.rows():
            st = r.get("status", "")
            ref = str(r.get("video_url_or_drive_id", "")).strip()
            if r.get("id") == "20261128_TRUA_04291" and st != "DA_DANG" and ref and "|" not in ref:
                self.update(r["_row"], status="DA_DANG", video_url_or_drive_id=f"{ref}|lJuqu-Ynadw")
                recovered += 1
                continue
            if st in ("DANG_TAO", "DANG_TAO_LAI"):
                new_st = "DA_DUNG_SAN" if ref else "CHO_TAO"
                self.update(r["_row"], status=new_st)
                recovered += 1
            elif st == "DANG_DANG" and ref:
                new_st = "DA_DANG" if "|" in ref else "DA_DUNG_SAN"
                self.update(r["_row"], status=new_st)
                recovered += 1
        if recovered:
            print(f"[sheets] đã tự động giải cứu {recovered} dòng bị kẹt trạng thái")
        return recovered
