import logging
import os
import re
from io import BytesIO

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
        filename=None,
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
            file_metadata = {"name": filename or os.path.basename(local_file_path)}
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

    def ensure_folder(self, folder_name, token_path=None, parent_folder_id=None):
        """Find or create a Google Drive folder and return its metadata."""
        if not folder_name:
            return None

        try:
            drive_service = self._get_drive_service(token_path)
            safe_name = str(folder_name).strip()
            escaped_name = safe_name.replace("\\", "\\\\").replace("'", "\\'")
            query_parts = [
                "mimeType = 'application/vnd.google-apps.folder'",
                f"name = '{escaped_name}'",
                "trashed = false",
            ]
            if parent_folder_id:
                query_parts.append(f"'{parent_folder_id}' in parents")

            response = drive_service.files().list(
                q=" and ".join(query_parts),
                spaces="drive",
                fields="files(id, name, mimeType, parents, webViewLink)",
                pageSize=10,
            ).execute()
            files = response.get("files", [])
            if files:
                return files[0]

            metadata = {
                "name": safe_name,
                "mimeType": "application/vnd.google-apps.folder",
            }
            if parent_folder_id:
                metadata["parents"] = [parent_folder_id]

            folder = drive_service.files().create(
                body=metadata,
                fields="id, name, mimeType, parents, webViewLink",
            ).execute()
            self.logger.info(f"Drive folder ready: {folder.get('name')} ({folder.get('id')})")
            return folder
        except Exception as e:
            self.logger.error(f"Google Drive ensure folder failed: {e}")
            return None

    def _normalize_drive_name(self, value, fallback="untitled"):
        cleaned = re.sub(r"[\\\\/]+", " ", str(value or "")).strip()
        cleaned = re.sub(r"\s+", " ", cleaned).rstrip(".")
        return cleaned or fallback

    def ensure_project_folder(self, email, project_name, token_path=None, root_folder_id=None):
        email_folder = self.ensure_folder(
            self._normalize_drive_name(email, "unknown-user"),
            token_path=token_path,
            parent_folder_id=root_folder_id,
        )
        if not email_folder or not email_folder.get("id"):
            return None

        project_folder = self.ensure_folder(
            self._normalize_drive_name(project_name, "untitled-project"),
            token_path=token_path,
            parent_folder_id=email_folder.get("id"),
        )
        return project_folder

    def find_file(self, filename, token_path=None, folder_id=None, mime_type=None):
        if not filename:
            return None

        try:
            drive_service = self._get_drive_service(token_path)
            escaped_name = str(filename).replace("\\", "\\\\").replace("'", "\\'")
            query_parts = [
                f"name = '{escaped_name}'",
                "trashed = false",
            ]
            if folder_id:
                query_parts.append(f"'{folder_id}' in parents")
            if mime_type:
                query_parts.append(f"mimeType = '{mime_type}'")

            response = drive_service.files().list(
                q=" and ".join(query_parts),
                spaces="drive",
                fields="files(id, name, mimeType, size, md5Checksum, webViewLink, parents)",
                pageSize=10,
            ).execute()
            files = response.get("files", [])
            return files[0] if files else None
        except Exception as e:
            self.logger.error(f"Google Drive find file failed: {e}")
            return None

    def find_folder(self, folder_name, token_path=None, parent_folder_id=None):
        return self.find_file(
            folder_name,
            token_path=token_path,
            folder_id=parent_folder_id,
            mime_type="application/vnd.google-apps.folder",
        )

    def get_file_metadata(self, file_id, token_path=None, fields=None):
        if not file_id:
            return None
        try:
            drive_service = self._get_drive_service(token_path)
            return drive_service.files().get(
                fileId=file_id,
                fields=fields or "id, name, mimeType, size, md5Checksum, webViewLink, parents",
            ).execute()
        except Exception as e:
            self.logger.error(f"Google Drive get file metadata failed: {e}")
            return None

    def list_files(self, folder_id, token_path=None, page_size=200):
        if not folder_id:
            return []
        try:
            drive_service = self._get_drive_service(token_path)
            response = drive_service.files().list(
                q=f"'{folder_id}' in parents and trashed = false",
                spaces="drive",
                fields="files(id, name, mimeType, size, md5Checksum, webViewLink, parents)",
                pageSize=page_size,
                orderBy="createdTime desc",
            ).execute()
            return response.get("files", [])
        except Exception as e:
            self.logger.error(f"Google Drive list files failed: {e}")
            return []

    def upsert_file(
        self,
        local_file_path,
        token_path=None,
        folder_id=None,
        filename=None,
        mimetype=None,
        description=None,
        make_public=False,
    ):
        if not os.path.exists(local_file_path):
            self.logger.error(f"File not found for Drive upsert: {local_file_path}")
            return None

        final_name = filename or os.path.basename(local_file_path)
        existing = self.find_file(final_name, token_path=token_path, folder_id=folder_id)
        if not existing:
            return self.upload_file(
                local_file_path,
                token_path=token_path,
                folder_id=folder_id,
                filename=final_name,
                mimetype=mimetype,
                description=description,
                make_public=make_public,
            )

        try:
            drive_service = self._get_drive_service(token_path)
            media = MediaFileUpload(
                local_file_path,
                mimetype=mimetype or "application/octet-stream",
                resumable=True,
            )
            body = {"name": final_name}
            if description:
                body["description"] = description

            updated = drive_service.files().update(
                fileId=existing["id"],
                body=body,
                media_body=media,
                fields="id, name, mimeType, size, md5Checksum, webViewLink, parents",
            ).execute()

            if make_public:
                try:
                    drive_service.permissions().create(
                        fileId=updated.get("id"),
                        body={"type": "anyone", "role": "viewer"},
                    ).execute()
                except Exception as pe:
                    self.logger.warning(f"Failed to set permission: {pe}")

            self.logger.info(f"Drive upsert success: {updated.get('name')} ({updated.get('id')})")
            return updated
        except Exception as e:
            self.logger.error(f"Google Drive upsert failed: {e}")
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

    def read_text_file(self, file_id, token_path=None, encoding="utf-8"):
        if not file_id:
            return None
        try:
            drive_service = self._get_drive_service(token_path)
            request = drive_service.files().get_media(fileId=file_id)
            buffer = BytesIO()
            downloader = MediaIoBaseDownload(buffer, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
            return buffer.getvalue().decode(encoding)
        except Exception as e:
            self.logger.error(f"Google Drive text file read failed: {e}")
            return None

    def upload_video_to_drive(self, local_file_path, token_path=None, folder_id=None):
        """Upload a rendered video to Drive and return a shareable web link."""
        file = self.upload_file(
            local_file_path,
            token_path=token_path,
            folder_id=folder_id,
            mimetype="video/mp4",
            description="AI Generated Video by AIR Studio",
            make_public=True,
        )
        return file.get("webViewLink") if file else None


google_drive_service = GoogleDriveService()
