import uuid
from datetime import datetime
from typing import Dict, Any, List
from services.web_admin_client import web_admin_client

class AssetMatchingService:
    def calculate_match(self, asset: Dict[str, Any], scenes: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Calculate the best match by directly matching the Scene.
        """
        analysis = asset.get("analysis_result", {})
        asset_subjects = set([s.lower() for s in analysis.get("subjects", [])])
        asset_emotion = analysis.get("emotion", "").lower()
        asset_bg = analysis.get("background", "").lower()
            
        best_scene_score = -1.0
        best_scene = None
        scene_match_reason = "No scene matched."
        
        for scene in scenes:
            score = 0.0
            reasons = []
            
            # Compare Background to Scene Hint
            scene_bg = scene.get("scene_visual_hint", "").lower()
            if scene_bg and asset_bg and asset_bg in scene_bg:
                score += 50.0
                reasons.append("Background matched scene hint")
                
            # Compare Emotion
            scene_emotion = scene.get("emotion", "").lower()
            if scene_emotion and asset_emotion and asset_emotion in scene_emotion:
                score += 30.0
                reasons.append("Emotion matched scene emotion")
                
            # Compare Subjects (if scene has a summary or character hint)
            scene_summary = scene.get("summary", "").lower()
            if scene_summary and any(s in scene_summary for s in asset_subjects):
                score += 20.0
                reasons.append("Subject matched scene summary")
                
            # Check shot_hints for supplementary scoring
            shot_hints = scene.get("shot_hints", [])
            for hint in shot_hints:
                if hint.get("emotion", "").lower() == asset_emotion:
                    score += 10.0
                    reasons.append("Emotion matched a shot hint")
                    break
                    
            score += 10.0 # baseline
            
            if score > best_scene_score:
                best_scene_score = score
                best_scene = scene
                if reasons:
                    scene_match_reason = ", ".join(reasons)
                else:
                    scene_match_reason = "Fallback scene match"
                    
        if not best_scene:
            return {"scene_id": None, "match_score": 0.0, "match_reason": "No matching scene found.", "confidence": 0.0}
            
        normalized_score = best_scene_score / 150.0 if best_scene_score > 0 else 0.0
        
        return {
            "scene_id": best_scene["scene_id"] if "scene_id" in best_scene else best_scene.get("id"),
            "match_score": min(normalized_score, 1.0),
            "match_reason": f"Scene: {scene_match_reason}",
            "confidence": min(normalized_score, 1.0)
        }

    def auto_match_asset(self, asset: Dict[str, Any], scenes: List[Dict[str, Any]]) -> Dict[str, Any]:
        match_info = self.calculate_match(asset, scenes)
        
        if match_info["scene_id"]:
            match_record = {
                "id": str(uuid.uuid4()),
                "project_id": asset.get("project_id"),
                "asset_id": asset.get("id"),
                "scene_id": match_info["scene_id"],
                "shot_id": None, # Deprecated
                "match_score": match_info["match_score"],
                "match_reason": match_info["match_reason"],
                "confidence": match_info["confidence"],
                "is_auto_matched": True,
                "user_overridden": False,
                "match_status": "suggested",
                "created_at": datetime.utcnow().isoformat()
            }
            
            # Save to Supabase DB
            resp = web_admin_client.supabase_post("asset_scene_matches", match_record, timeout=10)
            success = resp is not None and resp.status_code in (201, 204)
            
            return {
                "success": success,
                "match": match_record
            }
        return {"success": False, "error_msg": "No suitable shot found"}

    def override_match(self, match_id: str, scene_id: str, shot_id: str) -> bool:
        payload = {
            "scene_id": scene_id,
            "shot_id": shot_id,
            "user_overridden": True,
            "match_status": "approved",
            "updated_at": datetime.utcnow().isoformat()
        }
        resp = web_admin_client.supabase_patch("asset_scene_matches", payload, params={"id": f"eq.{match_id}"})
        return resp is not None and resp.status_code in (200, 204)
        
    def update_match_status(self, match_id: str, status: str) -> bool:
        payload = {
            "match_status": status,
            "updated_at": datetime.utcnow().isoformat()
        }
        resp = web_admin_client.supabase_patch("asset_scene_matches", payload, params={"id": f"eq.{match_id}"})
        return resp is not None and resp.status_code in (200, 204)

asset_matching_service = AssetMatchingService()
