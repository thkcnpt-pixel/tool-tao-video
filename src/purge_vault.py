"""Dọn kho dự trữ: hủy mọi video DA_DUNG_SAN / CHO_TAO(BUF_) cũ và xóa file mp4 tương ứng trên Drive."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "integrations"))

from drive_client import DriveClient  # noqa: E402
from sheets_client import SheetsClient  # noqa: E402


def main():
    sheets, drive = SheetsClient(), DriveClient()
    n_vid = n_topic = 0
    for r in sheets.rows():
        if r["status"] == "DA_DUNG_SAN":
            ref = str(r["video_url_or_drive_id"]).split("|")[0]
            if ref:
                try:
                    drive.svc.files().delete(fileId=ref, supportsAllDrives=True).execute()
                except Exception as ex:
                    print(f"[purge] bỏ qua file {ref}: {ex!r}")
            sheets.update(r["_row"], status="DA_HUY", video_url_or_drive_id="")
            n_vid += 1
        elif r["status"] == "CHO_TAO" and str(r["id"]).startswith("BUF_"):
            sheets.update(r["_row"], status="DA_HUY")
            n_topic += 1
    print(f"[purge] đã hủy {n_vid} video dựng sẵn + {n_topic} chủ đề chờ tạo cũ")


if __name__ == "__main__":
    main()
