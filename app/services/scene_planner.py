import json
from config import config
import services.ai_router as ai_router

class ScenePlannerService:
    async def plan_scenes(self, topic: str, target_duration: int = 60, project_id: int = None, style_directive: str = "") -> dict:
        style_section = f"\n{style_directive}\n" if style_directive else ""
        prompt = f"""
You are an expert video production planner.
Plan the SCENE STRUCTURE for a video based on the following topic.
This scene structure will act as the Source of Truth for the entire production pipeline.

TOPIC: {topic}
TARGET DURATION: {target_duration} seconds
{style_section}
Instructions:
1. Break down the video into distinct scenes based on logical progression, location, or pacing changes.
2. Assign a unique ID to each scene (e.g., 'scene001').
3. Estimate the duration (in seconds) for each scene. The sum of all scene durations MUST approximate {target_duration} seconds.
4. Provide a brief summary of what happens in the scene.
5. Provide a visual hint for the overall background/setting of the scene.
6. If a Writing Style Directive is provided above, let it shape the scene progression itself — pacing, section count, how much of each scene is dialogue vs narration, and where tension/hooks land — not just the wording of the summaries.
7. Provide the output strictly as a valid JSON object without markdown formatting.

JSON SCHEMA:
{{
  "topic": "...",
  "scene_count": 3,
  "global_mood": "Overall mood of the video",
  "scenes": [
    {{
      "scene_id": "scene001",
      "scene_order": 1,
      "scene_summary": "Brief summary of the scene",
      "scene_situation": "Detailed situational context for the scene",
      "scene_emotion": "Dominant emotion of the scene",
      "scene_purpose": "The main purpose of this scene in the story",
      "target_duration": 20,
      "visual_direction": "Visual layout, camera, and setting hints",
      "tts_direction": "Voice acting, tone, and pacing instructions"
    }}
  ],
  "planner_notes": {{
    "strategy": "1-2 sentence overall strategy",
    "error": false
  }}
}}
"""
        try:
            # [FIX] AIR-0209 이전에는 대본 기획 단계가 ai_router를 통해 config.SCRIPT_PLANNING_MODEL
            # (어드민에서 Claude 등으로 설정 가능)을 사용했으나, scene_planner.py 도입 시 GeminiService가
            # 하드코딩되어 해당 설정이 무시되고 있었다. ai_router로 되돌려 모델 선택을 다시 존중한다.
            planning_model = config.SCRIPT_PLANNING_MODEL or config.SCRIPT_GENERATION_MODEL
            # [FIX] 기본 max_tokens(8192)로는 컷 단위로 장면 수가 늘어나는 스타일
            # (예: k_webtoon)에서 JSON이 중간에 잘려("Unterminated string") 기획이
            # 자주 실패했다(재현율 약 2/3). 씬 개수/문체에 따라 여유가 필요해 상향한다.
            response_text = await ai_router.generate_text(
                prompt,
                planning_model,
                temperature=0.4,
                max_tokens=16384,
                project_id=project_id,
                task_type="planning",
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
