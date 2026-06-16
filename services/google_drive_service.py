import logging
import os

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

from services.youtube_upload_service import youtube_upload_service


class GoogleDriveService:
    def __init__(self):
        self.logger = logging.getLogger("GoogleDriveService")

    def _get_drive_service(self, token_path=None):
        """Build a Google Drive client from the existing YouTube OAuth credentials."""
        credentials = youtube_upload_service.get_authenticated_service(token_path=token_path)._http.credentials
        return build("drive", "v3", credentials=credentials)

    def upload_file(
        self,
        local_file_path,
        token_path=None,
        folder_id=None,
        mimetype=None,
        description=None,
        make_public=False,
    ):
        """Upload any local file to Google Drive and return Drive file metadata."""
        if not os.path.exists(local_file_path):
            self.logger.error(f"File not found for Drive upload: {local_file_path}")
            return None

        try:
            drive_service = self._get_drive_service(token_path)
            file_metadata = {"name": os.path.basename(local_file_path)}
            if description:
                file_metadata["description"] = description
            if folder_id:
                file_metadata["parents"] = [folder_id]

            media = MediaFileUpload(
                local_file_path,
                mimetype=mimetype or "application/octet-stream",
                resumable=True,
            )
            file = drive_service.files().create(
                body=file_metadata,
                media_body=media,
                fields="id, name, mimeType, size, md5Checksum, webViewLink",
            ).execute()

            if make_public:
                try:
                    drive_service.permissions().create(
                        fileId=file.get("id"),
                        body={"type": "anyone", "role": "viewer"},
                    ).execute()
                except Exception as pe:
                    self.logger.warning(f"Failed to set permission: {pe}")

            self.logger.info(f"Drive upload success: {file.get('name')} ({file.get('id')})")
            return file
        except Exception as e:
            self.logger.error(f"Google Drive file upload failed: {e}")
            return None

    def download_file(self, file_id, local_file_path, token_path=None):
        """Download a Google Drive file by file ID."""
        try:
            drive_service = self._get_drive_service(token_path)
            os.makedirs(os.path.dirname(local_file_path), exist_ok=True)
            request = drive_service.files().get_media(fileId=file_id)
            with open(local_file_path, "wb") as fh:
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                while not done:
                    _, done = downloader.next_chunk()
            return local_file_path
        except Exception as e:
            self.logger.error(f"Google Drive file download failed: {e}")
            return None

    def upload_video_to_drive(self, local_file_path, token_path=None, folder_id=None):
        """Upload a rendered video to Drive and return a shareable web link."""
        file = self.upload_file(
            local_file_path,
            token_path=token_path,
            folder_id=folder_id,
            mimetype="video/mp4",
            description="AI Generated Video by Picadiri Studio",
            make_public=True,
        )
        return file.get("webViewLink") if file else None


google_drive_service = GoogleDriveService()
