
import os
import logging
from googleapiclient.http import MediaFileUpload
from googleapiclient.discovery import build
from services.youtube_upload_service import youtube_upload_service

class GoogleDriveService:
    def __init__(self):
        self.logger = logging.getLogger("GoogleDriveService")

    def _get_drive_service(self, token_path=None):
        """YouTube 서비스와 동일한 인증 정보를 사용하여 드라이브 서비스 빌드"""
        credentials = youtube_upload_service.get_authenticated_service(token_path=token_path)._http.credentials
        return build('drive', 'v3', credentials=credentials)

    def upload_video_to_drive(self, local_file_path, token_path=None, folder_id=None):
        """
        로컬 영상을 구글 드라이브에 업로드하고 공유 가능한 링크 반환
        """
        if not os.path.exists(local_file_path):
            self.logger.error(f"File not found for Drive upload: {local_file_path}")
            return None

        try:
            drive_service = self._get_drive_service(token_path)
            
            file_metadata = {
                'name': os.path.basename(local_file_path),
                'description': 'AI Generated Video by Picadiri Studio'
            }
            
            if folder_id:
                file_metadata['parents'] = [folder_id]
            
            media = MediaFileUpload(
                local_file_path, 
                mimetype='video/mp4', 
                resumable=True
            )
            
            self.logger.info(f"Uploading {local_file_path} to Google Drive...")
            file = drive_service.files().create(
                body=file_metadata, 
                media_body=media, 
                fields='id, webViewLink'
            ).execute()
            
            file_id = file.get('id')
            web_link = file.get('webViewLink')

            # [Optional] 모든 사람이 링크로 볼 수 있게 권한 설정
            try:
                drive_service.permissions().create(
                    fileId=file_id,
                    body={'type': 'anyone', 'role': 'viewer'}
                ).execute()
            except Exception as pe:
                self.logger.warning(f"Failed to set permission: {pe}")

            self.logger.info(f"Drive Upload Success: {web_link}")
            return web_link

        except Exception as e:
            self.logger.error(f"Google Drive Upload Failed: {e}")
            return None

google_drive_service = GoogleDriveService()
