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

    async def plan_production(self, enhanced_scenes: dict) -> dict:
        prompt = f"""
You are an expert Production Planner AI. Your job is to take a sequence of enhanced scenes and determine how each scene should be produced (Image Generation, Video Generation, or Reuse).

ENHANCED SCENES JSON:
{json.dumps(enhanced_scenes, ensure_ascii=False, indent=2)}

Instructions:
1. Iterate over every scene in the `scenes` array.
2. Decide the `asset_type` strictly from: ["image", "video", "reuse"].
   - "video": For scenes with high movement, character action, or dynamic camera motion required.
   - "image": For static scenes, mood/establishing scenes, or when Ken Burns effect is sufficient.
   - "reuse": For repetitive background or stock scenes.
3. Determine the `generator`. Use defaults based on asset_type unless specifically overridden:
   - image -> flux
   - video -> kling
   - reuse -> none
4. Build a structured `prompt` for each item containing: `positive`, `negative`, `camera`, `lighting`, and `style`. Draw from the scene's `image_prompt` or `video_prompt` and its `shot_hints`.
5. Return the result strictly as a valid JSON object without markdown formatting.

JSON SCHEMA:
{{
  "item_count": 5,
  "total_estimated_duration": 25,
  "planner_notes": {{
    "strategy": "...",
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
            for item in result.get("production_items", []):
                atype = item.get("asset_type")
                if atype not in self.DEFAULT_GENERATORS:
                    item["asset_type"] = "image"
                    atype = "image"
                
                # If generator is empty or missing, apply default
                if not item.get("generator"):
                    item["generator"] = self.DEFAULT_GENERATORS[atype]
                    
            return result
        except Exception as e:
            print(f"[ProductionPlanner] Failed: {e}")
            return {
                "production_items": [],
                "item_count": 0,
                "total_estimated_duration": 0,
                "planner_notes": {
                    "strategy": "Failed to generate plan",
                    "error": True,
                    "error_message": str(e)
                }
            }

production_planner_service = ProductionPlannerService()
