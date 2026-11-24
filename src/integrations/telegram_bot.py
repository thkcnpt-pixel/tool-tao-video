"""Telegram Bot API: bàn phím thông minh theo trạng thái (Auto-Published vs Chờ duyệt), đóng file an toàn bằng ExitStack."""
import argparse
from contextlib import ExitStack
import json
import os

import requests

API = "https://api.telegram.org/bot{token}/{method}"


class TelegramBot:
    def __init__(self, token=None, chat_id=None):
        self.token = token or os.environ["TELEGRAM_BOT_TOKEN"]
        self.chat_id = str(chat_id or os.environ["TELEGRAM_CHAT_ID"])

    def _call(self, method, data=None, files=None, timeout=180):
        r = requests.post(API.format(token=self.token, method=method), data=data, files=files, timeout=timeout)
        res = r.json()
        if not res.get("ok"):
            raise RuntimeError(f"Telegram {method} lỗi: {res}")
        return res["result"]

    @staticmethod
    def approval_keyboard(row_id, youtube_url=None):
        """Nếu video đã tự động đăng YouTube -> chỉ hiện nút [▶️ Mở YouTube] + [🔄 Tạo lại bản khác] gọn đẹp."""
        if youtube_url:
            return {"inline_keyboard": [[
                {"text": "▶️ Mở YouTube Shorts", "url": youtube_url},
                {"text": "🔄 Tạo lại bản khác", "callback_data": f"REGEN:{row_id}"},
            ]]}
        return {"inline_keyboard": [[
            {"text": "✅ Duyệt", "callback_data": f"APPROVE:{row_id}"},
            {"text": "🔄 Tạo lại", "callback_data": f"REGEN:{row_id}"},
            {"text": "❌ Hủy", "callback_data": f"REJECT:{row_id}"},
        ]]}

    def send_for_approval(self, video_path, row_id, topic, caption, drive_id="", youtube_url=None, youtube_mode="", fb_url=None, qa_note=""):
        esc_cap = str(caption).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        esc_top = str(topic).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        esc_qa = str(qa_note).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        fb_line = f"📘 <b>Facebook Reels:</b> {fb_url}\n" if fb_url else ""
        qa_line = f"🛡️ <b>AI QA:</b> {esc_qa}\n" if esc_qa else ""
        if youtube_url or fb_url:
            yt_line = f"▶️ <b>YouTube ({youtube_mode or 'PUBLIC'}):</b> {youtube_url}\n" if youtube_url else ""
            text = (f"🚀 <b>ĐÃ TỰ ĐỘNG XUẤT BẢN ({row_id})</b>\n"
                    f"📌 <b>Chủ đề:</b> {esc_top}\n"
                    f"{yt_line}{fb_line}{qa_line}\n"
                    f"📋 <b>Chạm 1 cái vào khung dưới để Copy Caption đăng TikTok:</b>\n"
                    f"<pre>{esc_cap}</pre>")
        else:
            text = (f"🎬 <b>Chờ duyệt:</b> <code>{row_id}</code>\n"
                    f"📌 <b>Chủ đề:</b> {esc_top}\n{qa_line}\n"
                    f"📋 <b>Chạm 1 cái để Copy Caption:</b>\n<pre>{esc_cap}</pre>\n\n"
                    f"<i>💡 Reply tin nhắn này để sửa caption, hoặc bấm 🔄 Tạo lại để dựng kịch bản khác.</i>")
        if drive_id:
            text += f"\n🔗 <a href=\"https://drive.google.com/file/d/{drive_id}/view\">Xem file gốc trên Drive</a>"

        thumb_path = os.path.splitext(video_path)[0] + ".jpg"
        with ExitStack() as stack:
            v_fh = stack.enter_context(open(video_path, "rb"))
            files = {"video": (os.path.basename(video_path), v_fh, "video/mp4")}
            if os.path.exists(thumb_path):
                t_fh = stack.enter_context(open(thumb_path, "rb"))
                files["thumbnail"] = ("thumb.jpg", t_fh, "image/jpeg")
            msg = self._call(
                "sendVideo",
                data={
                    "chat_id": self.chat_id,
                    "caption": text[:1024],
                    "parse_mode": "HTML",
                    "supports_streaming": "true",
                    "reply_markup": json.dumps(self.approval_keyboard(row_id, youtube_url=youtube_url)),
                },
                files=files,
            )
        return str(msg["message_id"])

    def send_final(self, video_path, caption, youtube_url=None):
        extra = f"\n\n▶️ YouTube Shorts: {youtube_url}" if youtube_url else ""
        with open(video_path, "rb") as f:
            msg = self._call(
                "sendVideo",
                data={"chat_id": self.chat_id, "caption": (caption + extra)[:1024], "supports_streaming": "true"},
                files={"video": (os.path.basename(video_path), f, "video/mp4")},
            )
        return str(msg["message_id"])

    def send_text(self, text):
        return self._call("sendMessage", data={"chat_id": self.chat_id, "text": text[:4000]}, timeout=20)

    def set_webhook(self, url):
        return self._call("setWebhook", data={"url": url, "allowed_updates": json.dumps(["message", "callback_query"])})

    def webhook_info(self):
        return self._call("getWebhookInfo")

    def cleanup_duplicate_replies(self, approval_msg_id, final_msg_id):
        try:
            a_id = int(approval_msg_id)
            f_id = int(final_msg_id)
        except Exception:
            return
        for mid in range(a_id + 2, f_id):
            try:
                self._call("deleteMessage", data={"chat_id": self.chat_id, "message_id": mid}, timeout=10)
            except Exception:
                pass

    def clear_pending_webhook(self):
        info = self.webhook_info()
        url = info.get("url")
        if url:
            self._call("setWebhook", data={
                "url": url,
                "drop_pending_updates": "true",
                "allowed_updates": json.dumps(["message", "callback_query"]),
            })


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set-webhook")
    ap.add_argument("--info", action="store_true")
    a = ap.parse_args()
    bot = TelegramBot()
    if a.set_webhook:
        print(bot.set_webhook(a.set_webhook))
    if a.info or not a.set_webhook:
        print(json.dumps(bot.webhook_info(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
