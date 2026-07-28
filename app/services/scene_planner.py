import json
from config import config
import services.ai_router as ai_router

class ScenePlannerService:
    async def plan_scenes(
        self,
        topic: str,
        target_duration: int = 60,
        project_id: int = None,
        style_directive: str = "",
        benchmark_analysis: dict = None,
        accumulated_knowledge: list = None,
        recent_titles: list = None,
    ) -> dict:
        style_section = f"\n{style_directive}\n" if style_directive else ""

        # [FIX] 이 프로젝트에 저장된 벤치마크 영상 분석(구독자 대비 고성과 영상을 분석한 결과)을
        # 씬 기획에 반영한다. 콘텐츠(이름/줄거리)가 아니라 후킹/전개/페이싱 "기법"만 참고하도록
        # 명시해 표절이 아니라 학습이 되게 한다.
        benchmark_section = ""
        if benchmark_analysis:
            script_analysis = benchmark_analysis.get("script_analysis") or {}
            benchmark_lines = [
                f"- Structure: {script_analysis.get('structure', 'N/A')}",
                f"- Hooks: {script_analysis.get('hooks', 'N/A')}",
                f"- Pacing: {script_analysis.get('pacing', 'N/A')}",
                f"- Key message: {script_analysis.get('key_message', 'N/A')}",
                f"- Viewer needs: {', '.join(benchmark_analysis.get('viewer_needs') or [])}",
            ]
            benchmark_section = f"""
BENCHMARK VIDEO ANALYSIS (a high-performing video's analysis — reference the TECHNIQUE only):
{chr(10).join(benchmark_lines)}
- ZERO PLAGIARISM: Do NOT reuse this video's names, exact plot, or specific content. Only borrow *how* it hooks/paces viewers, applied to THIS topic.
"""

        # [FIX] 과거 분석된 고성과 영상들로부터 누적 학습된 일반화된 성공 패턴을 반영한다.
        knowledge_section = ""
        if accumulated_knowledge:
            knowledge_lines = "\n".join(
                f"- [{k.get('category', 'general')}] {k.get('pattern', '')}: {k.get('insight', '')}"
                for k in accumulated_knowledge
            )
            knowledge_section = f"""
ACCUMULATED SUCCESS KNOWLEDGE (patterns learned from previously analyzed high-performing videos — actively apply these where relevant):
{knowledge_lines}
"""

        # [FIX] 최근 생성한 주제와 겹치지 않도록 회피 지시를 넣는다.
        history_section = ""
        if recent_titles:
            history_lines = "\n".join(f"- {t}" for t in recent_titles)
            history_section = f"""
RECENTLY PRODUCED TOPICS (avoid repeating these or creating a near-duplicate):
{history_lines}
"""

        prompt = f"""
You are an expert video production planner.
Plan the SCENE STRUCTURE for a video based on the following topic.
This scene structure will act as the Source of Truth for the entire production pipeline.

TOPIC: {topic}
TARGET DURATION: {target_duration} seconds
{style_section}
{benchmark_section}
{knowledge_section}
{history_section}
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
