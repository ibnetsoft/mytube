import json
from services.gemini_service import GeminiService

class ProductionPlannerService:
    DEFAULT_GENERATORS = {
        "image": "flux",
        "video": "kling",
        "reuse": "none"
    }

    def __init__(self):
        self.gemini = GeminiService()

    async def plan_production(self, enhanced_scenes: dict, mode: str = "basic") -> dict:
        is_all_mode = str(mode or "").strip().lower() in ["all", "full"]
        mode_instruction = (
            "2. Decide the `asset_type` strictly from: [\"image\", \"video\", \"reuse\"]."
            if is_all_mode else
            "2. Decide the `asset_type` strictly from: [\"image\", \"video\", \"reuse\"]. IMPORTANT: In 'basic' mode (default), \"video\" can ONLY be assigned to the first 12 scenes (scene 1 to 12). For scenes beyond scene 12 (scene 13+), you MUST choose \"image\" or \"reuse\"."
        )

        prompt = f"""
You are an expert Production Planner AI. Your job is to take a sequence of enhanced scenes and determine how each scene should be produced (Image Generation, Video Generation, or Reuse).

ENHANCED SCENES JSON:
{json.dumps(enhanced_scenes, ensure_ascii=False, indent=2)}

Instructions:
1. Iterate over every scene in the `scenes` array.
{mode_instruction}
   - "video": For scenes with high movement, character action, or dynamic camera motion required.
   - "image": For static scenes, mood/establishing scenes, or when Ken Burns effect is sufficient.
   - "reuse": For repetitive background or stock scenes.
3. Determine the `generator`. Use defaults based on asset_type unless specifically overridden:
   - image -> flux
   - video -> kling
   - reuse -> none
4. Build a structured `prompt` for each item containing: `positive`, `negative`, `camera`, `lighting`, and `style`. Draw only from the scene's `video_prompt`, `visual_style`, `lighting_hint`, and `shot_hints`.
5. Return the result strictly as a valid JSON object without markdown formatting.

JSON SCHEMA:
{{
  "item_count": 5,
  "total_estimated_duration": 25,
  "planner_notes": {{
    "strategy": "...",
    "video_prompt_mode": "{"all" if is_all_mode else "basic"}",
    "error": false
  }},
  "production_items": [
    {{
      "id": "asset001",
      "scene_id": "scene001",
      "asset_type": "image",
      "generator": "flux",
      "target_duration": 3,
      "aspect_ratio": "16:9",
      "resolution": "1920x1080",
      "priority": "normal",
      "reuse_candidate": false,
      "prompt": {{
        "positive": "A detailed positive prompt description...",
        "negative": "ugly, blurry, low quality...",
        "camera": "wide angle, shallow depth of field...",
        "lighting": "cinematic lighting, golden hour...",
        "style": "photorealistic, cinematic..."
      }}
    }}
  ]
}}
"""
        try:
            response_text = await self.gemini.generate_text(
                prompt=prompt,
                temperature=0.4,
                task_type="text_gen"
            )
            
            response_text = response_text.strip()
            if response_text.startswith("```json"):
                response_text = response_text[7:]
            if response_text.startswith("```"):
                response_text = response_text[3:]
            if response_text.endswith("```"):
                response_text = response_text[:-3]
            response_text = response_text.strip()
            
            result = json.loads(response_text)
            
            # Enforce constraints
            for idx, item in enumerate(result.get("production_items", [])):
                scene_num = idx + 1
                scene_id = str(item.get("scene_id") or "")
                if scene_id.startswith("scene") and scene_id[5:].isdigit():
                    scene_num = int(scene_id[5:])

                atype = item.get("asset_type")
                if not is_all_mode and scene_num > 12 and atype == "video":
                    item["asset_type"] = "image"
                    atype = "image"

                if atype not in self.DEFAULT_GENERATORS:
                    item["asset_type"] = "image"
                    atype = "image"
                
                # If generator is empty or missing, apply default
                if not item.get("generator") or (not is_all_mode and scene_num > 12 and item.get("generator") == "kling"):
                    item["generator"] = self.DEFAULT_GENERATORS[item.get("asset_type", "image")]
                    
            return result
        except Exception as e:
            print(f"[ProductionPlanner] Failed: {e}")
            return {
                "production_items": [],
                "item_count": 0,
                "total_estimated_duration": 0,
                "planner_notes": {
                    "strategy": "Failed to generate plan",
                    "video_prompt_mode": "all" if is_all_mode else "basic",
                    "error": True,
                    "error_message": str(e)
                }
            }

production_planner_service = ProductionPlannerService()
