import uuid
from datetime import datetime
from typing import Dict, Any, List
from services.web_admin_client import web_admin_client

from app.services.asset_analysis_service import asset_analysis_service

class AssetUploadService:
    def process_upload(self, project_id: str, user_id: str, file_name: str, file_type: str, mime_type: str, file_size: int) -> Dict[str, Any]:
        # 1. Metadata Extraction (Mocked for missing real video processing)
        duration = 5.0 if file_type == "video" else None
        width = 1920
        height = 1080
        aspect_ratio = "16:9"
        file_url = f"/uploads/{file_name}" # Mock local URL
        thumbnail_url = f"/uploads/thumb_{file_name}.jpg" if file_type == "video" else file_url
        
        # 2. Vision Analysis
        analysis_result = asset_analysis_service.analyze_asset(file_name, file_type, file_url)
        quality_score = 85
        
        # 3. Create DB Record Payload
        asset_record = {
            "id": str(uuid.uuid4()),
            "project_id": project_id,
            "user_id": user_id,
            "file_url": file_url,
            "file_name": file_name,
            "file_type": file_type,
            "mime_type": mime_type,
            "duration": duration,
            "width": width,
            "height": height,
            "aspect_ratio": aspect_ratio,
            "file_size": file_size,
            "thumbnail_url": thumbnail_url,
            "analysis_status": "completed",
            "analysis_result": analysis_result,
            "quality_score": quality_score,
            "created_at": datetime.utcnow().isoformat()
        }
        
        # 4. Save to DB (Supabase via WebAdminClient)
        # Note: If this fails in local preview, the fallback is handled in the API or mock layer.
        resp = web_admin_client.supabase_post("uploaded_assets", asset_record, timeout=10)
        
        return {
            "success": resp is not None and resp.status_code in (201, 204),
            "asset": asset_record,
            "error_msg": f"HTTP {resp.status_code}" if resp and resp.status_code not in (201, 204) else None
        }

asset_upload_service = AssetUploadService()
