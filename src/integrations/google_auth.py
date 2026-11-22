"""Thông tin xác thực Google dùng chung cho Sheets & Drive (Service Account)."""
import json
import os

from google.oauth2 import service_account

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def get_credentials():
    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if raw:
        info = json.loads(raw)
    else:
        path = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE")
        if not path:
            raise RuntimeError("Thiếu GOOGLE_SERVICE_ACCOUNT_JSON (hoặc GOOGLE_SERVICE_ACCOUNT_FILE)")
        with open(path, encoding="utf-8") as f:
            info = json.load(f)
    return service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
