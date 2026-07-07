import uuid
from datetime import datetime
from typing import Dict, Any, List
from services.web_admin_client import web_admin_client

class AssetMatchingService:
    def calculate_match(self, asset: Dict[str, Any], shots: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Calculate the best match for an asset across a list of shots.
        Returns a dict with: scene_id, shot_id, match_score, match_reason, confidence
        """
        best_score = -1.0
        best_shot = None
        match_reason = "No matching shot found."
        
        analysis = asset.get("analysis_result", {})
        asset_subjects = set([s.lower() for s in analysis.get("subjects", [])])
        asset_emotion = analysis.get("emotion", "").lower()
        asset_bg = analysis.get("background", "").lower()
        
        for shot in shots:
            score = 0.0
            reasons = []
            
            shot_subject = shot.get("subject", "").lower()
            shot_emotion = shot.get("emotion", "").lower()
            shot_camera = shot.get("camera", "").lower()
            scene_bg = shot.get("scene_visual_hint", "").lower()
            
            # Compare Subject
            if shot_subject and any(s in shot_subject for s in asset_subjects):
                score += 40.0
                reasons.append("Subject matched")
            
            # Compare Emotion
            if shot_emotion and asset_emotion and asset_emotion in shot_emotion:
                score += 30.0
                reasons.append("Emotion matched")
                
            # Compare Background
            if scene_bg and asset_bg and asset_bg in scene_bg:
                score += 20.0
                reasons.append("Background matched")
                
            # Compare Type/Style basic check
            score += 10.0 # baseline
            
            if score > best_score:
                best_score = score
                best_shot = shot
                if reasons:
                    match_reason = ", ".join(reasons)
                else:
                    match_reason = "Fallback baseline match"
                    
        # Normalize score
        normalized_score = best_score / 100.0 if best_score > 0 else 0.0
        confidence = normalized_score
        
        return {
            "scene_id": best_shot.get("scene_id") if best_shot else None,
            "shot_id": best_shot.get("id") if best_shot else None,
            "match_score": normalized_score,
            "match_reason": match_reason,
            "confidence": confidence
        }

    def auto_match_asset(self, asset: Dict[str, Any], shots: List[Dict[str, Any]]) -> Dict[str, Any]:
        match_info = self.calculate_match(asset, shots)
        
        if match_info["shot_id"]:
            match_record = {
                "id": str(uuid.uuid4()),
                "project_id": asset.get("project_id"),
                "asset_id": asset.get("id"),
                "scene_id": match_info["scene_id"],
                "shot_id": match_info["shot_id"],
                "match_score": match_info["match_score"],
                "match_reason": match_info["match_reason"],
                "confidence": match_info["confidence"],
                "is_auto_matched": True,
                "user_overridden": False,
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
            "updated_at": datetime.utcnow().isoformat()
        }
        resp = web_admin_client.supabase_patch("asset_scene_matches", payload, params={"id": f"eq.{match_id}"})
        return resp is not None and resp.status_code in (200, 204)

asset_matching_service = AssetMatchingService()
