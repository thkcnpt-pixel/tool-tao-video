"""Google Drive: upload output.mp4 + kho nhạc nền động."""
import io
import os
import random

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

from google.oauth2.credentials import Credentials

DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive"]


def get_drive_credentials():
    """Drive chạy bằng OAuth tài khoản chủ kênh (Service Account không có dung lượng lưu trữ)."""
    return Credentials(
        token=None,
        refresh_token=os.environ["DRIVE_OAUTH_REFRESH_TOKEN"],
        client_id=os.environ["DRIVE_OAUTH_CLIENT_ID"],
        client_secret=os.environ["DRIVE_OAUTH_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token",
        scopes=DRIVE_SCOPES,
    )


class DriveClient:
    def __init__(self):
        self.svc = build("drive", "v3", credentials=get_drive_credentials(), cache_discovery=False)

    def upload(self, path, folder_id=None, name=None, mime="video/mp4"):
        """Upload file, trả về drive_file_id."""
        folder_id = folder_id or os.environ["DRIVE_OUTPUT_FOLDER_ID"]
        meta = {"name": name or os.path.basename(path), "parents": [folder_id]}
        media = MediaFileUpload(path, mimetype=mime, resumable=True)
        f = self.svc.files().create(body=meta, media_body=media, fields="id", supportsAllDrives=True).execute()
        return f["id"]

    def download(self, file_id, dest):
        req = self.svc.files().get_media(fileId=file_id, supportsAllDrives=True)
        with io.FileIO(dest, "wb") as fh:
            dl = MediaIoBaseDownload(fh, req, chunksize=8 * 1024 * 1024)
            done = False
            while not done:
                _, done = dl.next_chunk()
        return dest

    def list_music(self, folder_id=None):
        folder_id = folder_id or os.environ.get("DRIVE_MUSIC_FOLDER_ID")
        if not folder_id:
            return []
        q = f"'{folder_id}' in parents and trashed=false and (mimeType='audio/mpeg' or name contains '.mp3')"
        res = self.svc.files().list(q=q, fields="files(id,name)", pageSize=100, supportsAllDrives=True,
                                    includeItemsFromAllDrives=True).execute()
        return res.get("files", [])

    def random_music(self, dest_dir, folder_id=None):
        """Tải 1 bản .mp3 ngẫu nhiên; trả None nếu thư mục trống / lỗi (để fallback assets/music)."""
        try:
            files = self.list_music(folder_id)
            if not files:
                return None
            f = random.choice(files)
            return self.download(f["id"], os.path.join(dest_dir, "music.mp3"))
        except Exception as ex:
            print(f"[drive] không lấy được nhạc từ Drive ({ex!r}) -> fallback assets/music/")
            return None

    def cleanup_old_videos(self, keep_latest=100, folder_id=None):
        """Tự động dọn các video cũ hơn 100 bản gần nhất (~33 ngày) trên Drive để không bao giờ đầy 15GB."""
        try:
            folder_id = folder_id or os.environ.get("DRIVE_OUTPUT_FOLDER_ID")
            if not folder_id:
                return 0
            q = f"'{folder_id}' in parents and trashed=false and mimeType='video/mp4'"
            res = self.svc.files().list(q=q, orderBy="createdTime desc", pageSize=100,
                                        fields="files(id,name,createdTime)", supportsAllDrives=True).execute()
            files = res.get("files", [])
            removed = 0
            for f in files[keep_latest:]:
                self.svc.files().delete(fileId=f["id"], supportsAllDrives=True).execute()
                removed += 1
            if removed:
                print(f"[drive] đã dọn {removed} video cũ trên Drive")
            return removed
        except Exception as ex:
            print(f"[drive] bỏ qua cleanup ({ex!r})")
            return 0
