import uuid
from datetime import datetime
from typing import Dict, Any, List
from services.web_admin_client import web_admin_client

class AssetMatchingService:
    def calculate_match(self, asset: Dict[str, Any], shots: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Calculate the best match by first matching the Scene, then the Shot within that Scene.
        """
        analysis = asset.get("analysis_result", {})
        asset_subjects = set([s.lower() for s in analysis.get("subjects", [])])
        asset_emotion = analysis.get("emotion", "").lower()
        asset_bg = analysis.get("background", "").lower()
        
        # Group shots by scene
        scenes = {}
        for shot in shots:
            sid = shot.get("scene_id")
            if sid not in scenes:
                scenes[sid] = {"scene_id": sid, "scene_visual_hint": shot.get("scene_visual_hint", "").lower(), "shots": []}
            scenes[sid]["shots"].append(shot)
            
        # 1. Match Scene
        best_scene_score = -1.0
        best_scene = None
        scene_match_reason = "No scene matched."
        
        for sid, scene in scenes.items():
            score = 0.0
            reasons = []
            
            # Compare Background to Scene Hint
            scene_bg = scene["scene_visual_hint"]
            if scene_bg and asset_bg and asset_bg in scene_bg:
                score += 50.0
                reasons.append("Background matched scene hint")
                
            score += 10.0 # baseline
            
            if score > best_scene_score:
                best_scene_score = score
                best_scene = scene
                if reasons:
                    scene_match_reason = ", ".join(reasons)
                else:
                    scene_match_reason = "Fallback scene match"
                    
        if not best_scene:
            return {"scene_id": None, "shot_id": None, "match_score": 0.0, "match_reason": "No matching scene found.", "confidence": 0.0}
            
        # 2. Match Shot within the best Scene
        best_shot_score = -1.0
        best_shot = None
        shot_match_reason = "No shot matched."
        
        for shot in best_scene["shots"]:
            score = 0.0
            reasons = []
            
            shot_subject = shot.get("subject", "").lower()
            shot_emotion = shot.get("emotion", "").lower()
            
            # Compare Subject
            if shot_subject and any(s in shot_subject for s in asset_subjects):
                score += 40.0
                reasons.append("Subject matched")
            
            # Compare Emotion
            if shot_emotion and asset_emotion and asset_emotion in shot_emotion:
                score += 30.0
                reasons.append("Emotion matched")
                
            score += 10.0 # baseline
            
            if score > best_shot_score:
                best_shot_score = score
                best_shot = shot
                if reasons:
                    shot_match_reason = ", ".join(reasons)
                else:
                    shot_match_reason = "Fallback shot match"
                    
        total_score = best_scene_score + best_shot_score
        normalized_score = total_score / 150.0 if total_score > 0 else 0.0
        
        return {
            "scene_id": best_scene["scene_id"],
            "shot_id": best_shot.get("id") if best_shot else None,
            "match_score": min(normalized_score, 1.0),
            "match_reason": f"Scene: {scene_match_reason} | Shot: {shot_match_reason}",
            "confidence": min(normalized_score, 1.0)
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
