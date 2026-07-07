import uuid
from datetime import datetime
from typing import Dict, Any, List
from services.web_admin_client import web_admin_client

class RenderOrchestratorService:
    def create_render_jobs(self, production_plan: Dict[str, Any]) -> Dict[str, Any]:
        items = production_plan.get("production_items", [])
        if not items:
            return {"error": True, "error_message": "No production items found."}

        jobs_to_insert = []
        for item in items:
            asset_type = item.get("asset_type", "image")
            
            # 2. Reuse Policy
            if asset_type == "reuse":
                status = "completed"
            else:
                status = "queued"
                
            job = {
                "id": str(uuid.uuid4()),
                "project_id": None,
                "production_item_id": str(item.get("id")),
                "shot_id": str(item.get("shot_id")),
                "scene_id": str(item.get("scene_id")),
                "asset_type": asset_type,
                "generator": item.get("generator", "none"),
                "status": status,
                "priority": item.get("priority", "normal"),
                "input_payload": item.get("prompt", {}),
                "output_payload": {},
                "retry_count": 0,
                "max_retries": 3,
                "created_at": datetime.utcnow().isoformat()
            }
            jobs_to_insert.append(job)

        inserted_jobs = []
        # Insert into Supabase
        for job in jobs_to_insert:
            resp = web_admin_client.supabase_post("render_jobs", job, timeout=10)
            if resp and resp.status_code in (201, 204):
                inserted_jobs.append(job)
            else:
                return {
                    "error": True, 
                    "error_message": f"DB insert failed for job {job['id']}: HTTP {resp.status_code if resp else 'None'}"
                }

        return {
            "job_count": len(inserted_jobs),
            "jobs": inserted_jobs
        }

    def get_render_jobs(self, status: str = None, generator: str = None, asset_type: str = None) -> List[Dict[str, Any]]:
        params = {"order": "created_at.desc"}
        if status:
            params["status"] = f"eq.{status}"
        if generator:
            params["generator"] = f"eq.{generator}"
        if asset_type:
            params["asset_type"] = f"eq.{asset_type}"
            
        resp = web_admin_client.supabase_get("render_jobs", params=params, timeout=10)
        if resp and resp.status_code == 200:
            return resp.json()
        return []

render_orchestrator_service = RenderOrchestratorService()
