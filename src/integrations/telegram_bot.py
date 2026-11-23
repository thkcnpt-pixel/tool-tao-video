"""Telegram Bot API: gửi video chờ duyệt (kèm nút Duyệt / Tạo lại / Hủy) + bản final đăng TikTok + quản lý webhook."""
import argparse
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
    def approval_keyboard(row_id):
        return {"inline_keyboard": [
            [
                {"text": "✅ Duyệt", "callback_data": f"APPROVE:{row_id}"},
                {"text": "🔄 Tạo lại", "callback_data": f"REGEN:{row_id}"},
                {"text": "❌ Hủy", "callback_data": f"REJECT:{row_id}"},
            ]
        ]}

    def send_for_approval(self, video_path, row_id, topic, caption, drive_id=""):
        text = (f"🎬 <b>Chờ duyệt:</b> <code>{row_id}</code>\n"
                f"📌 <b>Chủ đề:</b> {topic}\n\n"
                f"📝 <b>Caption:</b>\n{caption}\n\n"
                f"<i>💡 Reply tin nhắn này để sửa caption, hoặc bấm 🔄 Tạo lại để dựng kịch bản khác.</i>")
        if drive_id:
            text += f"\n🔗 <a href=\"https://drive.google.com/file/d/{drive_id}/view\">Xem trên Drive</a>"
        with open(video_path, "rb") as f:
            msg = self._call(
                "sendVideo",
                data={"chat_id": self.chat_id, "caption": text[:1024], "parse_mode": "HTML",
                      "supports_streaming": "true", "reply_markup": json.dumps(self.approval_keyboard(row_id))},
                files={"video": (os.path.basename(video_path), f, "video/mp4")},
            )
        return str(msg["message_id"])

    def send_final(self, video_path, caption, youtube_url=None):
        """Gửi bản final + caption sạch về Telegram để đăng tay TikTok 10s."""
        extra = f"\n\n▶️ YouTube (Private): {youtube_url}" if youtube_url else ""
        with open(video_path, "rb") as f:
            msg = self._call(
                "sendVideo",
                data={"chat_id": self.chat_id, "caption": (caption + extra)[:1024], "supports_streaming": "true"},
                files={"video": (os.path.basename(video_path), f, "video/mp4")},
            )
        return str(msg["message_id"])

    def set_webhook(self, url):
        return self._call("setWebhook", data={"url": url, "allowed_updates": json.dumps(["message", "callback_query"])})

    def webhook_info(self):
        return self._call("getWebhookInfo")


    def cleanup_duplicate_replies(self, approval_msg_id, final_msg_id):
        """Xóa các tin nhắn '✅ Đã duyệt...' bị lặp nằm giữa (approval_msg_id + 1) và final_msg_id."""
        try:
            a_id = int(approval_msg_id)
            f_id = int(final_msg_id)
        except Exception:
            return
        # Giữ lại duy nhất 1 tin báo "✅ Đã duyệt" đầu tiên (a_id + 1), xóa toàn bộ các tin lặp từ (a_id + 2) tới (f_id - 1)
        for mid in range(a_id + 2, f_id):
            try:
                self._call("deleteMessage", data={"chat_id": self.chat_id, "message_id": mid}, timeout=10)
            except Exception:
                pass

    def clear_pending_webhook(self):
        """Xóa gói tin callback_query đang bị Telegram retry lặp lại do mã 302 Found của Google Apps Script."""
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
    ap.add_argument("--set-webhook", help="URL Web App của Google Apps Script (kết thúc bằng /exec)")
    ap.add_argument("--info", action="store_true")
    a = ap.parse_args()
    bot = TelegramBot()
    if a.set_webhook:
        print(bot.set_webhook(a.set_webhook))
    if a.info or not a.set_webhook:
        print(json.dumps(bot.webhook_info(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
