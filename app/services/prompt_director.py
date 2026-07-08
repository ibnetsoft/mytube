import json
from services.gemini_service import GeminiService

class PromptDirectorService:
    def __init__(self):
        self.gemini = GeminiService()

    async def enhance_scenes(self, planning_schema: dict) -> dict:
        prompt = f"""
You are an expert Prompt Director and AI video production enhancer.
Analyze the provided Scene Planning Schema and ENHANCE each scene with detailed visual prompts and shot hints.

SCENE SCHEMA JSON:
{json.dumps(planning_schema, ensure_ascii=False, indent=2)}

Instructions:
1. Iterate over every scene in the `scenes` array.
2. DO NOT change the number of scenes, their `id`, `order`, or `estimated_seconds`. The scene boundaries are fixed.
3. For each scene, generate a highly detailed `image_prompt` (2x2 grid style or single highly detailed image) and a `video_prompt`.
4. Provide a `lighting_hint` and `visual_style` for the scene.
5. Generate an array of `shot_hints` for the scene. These are merely internal camera/composition guidelines and DO NOT split the scene timeline.
6. Return the result strictly as a valid JSON object without markdown formatting.

JSON SCHEMA:
{{
  "scene_count": 3,
  "total_duration": 60,
  "director_notes": {{
    "overall_vision": "...",
    "error": false
  }},
  "scenes": [
    {{
      "id": "scene001",
      "order": 1,
      "estimated_seconds": 20,
      "image_prompt": "Highly detailed visual description for image generation.",
      "video_prompt": "Highly detailed visual and motion description for video generation.",
      "lighting_hint": "cinematic lighting, golden hour...",
      "visual_style": "photorealistic, cinematic...",
      "shot_hints": [
        {{
          "id": "hint001",
          "camera": "close-up",
          "composition": "rule of thirds",
          "movement": "slow push-in",
          "emotion": "sad",
          "purpose": "emphasize character emotion"
        }}
      ]
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
            return result
        except Exception as e:
            print(f"[PromptDirector] Failed to enhance scenes: {e}")
            return {
                "scenes": [],
                "scene_count": 0,
                "total_duration": 0,
                "director_notes": {
                    "overall_vision": "Enhancement failed",
                    "error": True,
                    "error_message": str(e)
                }
            }

prompt_director_service = PromptDirectorService()
