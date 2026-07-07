import json
from services.gemini_service import GeminiService

class DirectorAIService:
    def __init__(self):
        self.gemini = GeminiService()

    async def plan_shots(self, script_analysis: dict) -> dict:
        prompt = f"""
You are an expert film director and AI video production planner.
Analyze the provided script analysis and break down each scene into a detailed sequence of shots.

SCRIPT ANALYSIS JSON:
{json.dumps(script_analysis, ensure_ascii=False, indent=2)}

Instructions:
1. Iterate over every scene in the `scenes` array.
2. Break each scene down into multiple detailed shots (at least 2 shots per scene).
3. Provide a duration in seconds for each shot.
   - **CRITICAL RULE**: The sum of `duration` for all shots within a scene MUST match the scene's `estimated_seconds` with a margin of error of at most ±2 seconds.
4. For `generation_type`, choose strictly between "image" or "video":
   - Use "image" for static scenes, emotion-focused close-ups, establishing background cuts, or cuts with almost no movement. Video generation is expensive, so prefer "image" for unnecessary shots.
   - Use "video" for character movement, camera movement, actions, dynamic emotion changes, or critical transition shots.
5. Provide detailed `image_prompt` and `video_prompt` to guide the diffusion models.
6. Return the result strictly as a valid JSON object without markdown formatting.

JSON SCHEMA:
{{
  "shot_count": 5,
  "total_duration": 25,
  "director_notes": {{
    "overall_vision": "...",
    "error": false
  }},
  "shots": [
    {{
      "id": "shot001",
      "scene_id": "scene001",
      "order": 1,
      "duration": 3,
      "camera": "close-up, wide shot, medium shot...",
      "subject": "Main subject of the shot",
      "composition": "rule of thirds, center framed...",
      "movement": "static, slow push-in, pan...",
      "emotion": "sad, happy, tense...",
      "generation_type": "image or video",
      "image_prompt": "Highly detailed visual description for image generation.",
      "video_prompt": "Highly detailed visual and motion description for video generation.",
      "transition": "cut, crossfade..."
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
            print(f"[DirectorAI] Failed to plan shots: {e}")
            return {
                "shots": [],
                "shot_count": 0,
                "total_duration": 0,
                "director_notes": {
                    "overall_vision": "Analysis failed",
                    "error": True,
                    "error_message": str(e)
                }
            }

director_ai_service = DirectorAIService()
