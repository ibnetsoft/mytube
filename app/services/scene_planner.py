import json
from services.gemini_service import GeminiService

class ScenePlannerService:
    def __init__(self):
        self.gemini = GeminiService()

    async def plan_scenes(self, topic: str, target_duration: int = 60) -> dict:
        prompt = f"""
You are an expert video production planner.
Plan the SCENE STRUCTURE for a video based on the following topic.
This scene structure will act as the Source of Truth for the entire production pipeline.

TOPIC: {topic}
TARGET DURATION: {target_duration} seconds

Instructions:
1. Break down the video into distinct scenes based on logical progression, location, or pacing changes.
2. Assign a unique ID to each scene (e.g., 'scene001').
3. Estimate the duration (in seconds) for each scene. The sum of all scene durations MUST approximate {target_duration} seconds.
4. Provide a brief summary of what happens in the scene.
5. Provide a visual hint for the overall background/setting of the scene.
6. Provide the output strictly as a valid JSON object without markdown formatting.

JSON SCHEMA:
{{
  "topic": "...",
  "estimated_duration": 60,
  "scene_count": 3,
  "global_mood": "Overall mood of the video",
  "scenes": [
    {{
      "id": "scene001",
      "order": 1,
      "summary": "Brief summary of the scene",
      "estimated_seconds": 20,
      "emotion": "Dominant emotion of the scene",
      "scene_visual_hint": "A visual prompt hint for the setting/background"
    }}
  ],
  "planner_notes": {{
    "strategy": "1-2 sentence overall strategy",
    "error": false
  }}
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
            
            return json.loads(response_text)
        except Exception as e:
            print(f"[ScenePlanner] Failed to plan scenes: {e}")
            return {
                "topic": topic,
                "estimated_duration": 0,
                "scene_count": 0,
                "global_mood": "unknown",
                "scenes": [],
                "planner_notes": {
                    "strategy": "Analysis failed",
                    "error": True,
                    "error_message": str(e)
                }
            }

scene_planner_service = ScenePlannerService()
