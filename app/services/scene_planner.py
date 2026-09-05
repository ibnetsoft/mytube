import json
from config import config
import services.ai_router as ai_router

OPENING_MICRO_SCENE_COUNT = 12
OPENING_MICRO_SCENE_SECONDS = 5
OPENING_WINDOW_SECONDS = OPENING_MICRO_SCENE_COUNT * OPENING_MICRO_SCENE_SECONDS
LONGFORM_OPENING_RULE_MIN_SECONDS = 600
PACING_PHASES = [
    {"name": "opening", "until": 60, "step": 5},          # 0 ~ 1분: 5초 (1~12씬)
    {"name": "development", "until": 300, "step": 15},    # 1 ~ 5분: 15초 (13~28씬)
    {"name": "explanation", "until": 600, "step": 20},    # 5 ~ 10분: 20초 (29~43씬)
    {"name": "steady", "until": 900, "step": 30},         # 10 ~ 15분: 30초 (44~53씬)
    {"name": "extended", "until": None, "step": 60},      # 15분 이상: 60초 (54씬부터 1분 고정)
]

class ScenePlannerService:
    def _strip_json_fence(self, response_text: str) -> str:
        response_text = str(response_text or "").strip()
        if response_text.startswith("```json"):
            response_text = response_text[7:]
        if response_text.startswith("```"):
            response_text = response_text[3:]
        if response_text.endswith("```"):
            response_text = response_text[:-3]
        return response_text.strip()

    def _scene_field(self, scene: dict, key: str, fallback: str) -> str:
        value = str((scene or {}).get(key) or "").strip()
        return value if value else fallback

    def _normalize_batch_scene(self, scene: dict, slot: dict, scene_number: int, upload_title: str) -> dict:
        scene = dict(scene or {})
        opening = slot["phase"] == "opening"
        normalized = {
            "scene_id": f"scene{scene_number:03d}",
            "scene_order": scene_number,
            "scene_number": scene_number,
            "opening_micro_scene": opening,
            "target_duration": slot["duration"],
            "pacing_phase": slot["phase"],
            "time_range": f"{slot['start']}-{slot['end']}s",
            "scene_summary": self._scene_field(scene, "scene_summary", f"Scene {scene_number} advances the title promise"),
            "scene_situation": self._scene_field(scene, "scene_situation", f"Scene {scene_number} shows a distinct event tied to {upload_title}"),
            "scene_emotion": self._scene_field(scene, "scene_emotion", "tense curiosity"),
            "scene_purpose": self._scene_field(scene, "scene_purpose", "Advance the story with one new concrete turn"),
            "retention_hook": self._scene_field(scene, "retention_hook", "What new truth will this action reveal?"),
            "title_promise_link": self._scene_field(scene, "title_promise_link", f"Deepens the viewer promise of {upload_title}"),
            "end_bridge": self._scene_field(scene, "end_bridge", "The next scene must answer this with a new event"),
            "visual_direction": self._scene_field(scene, "visual_direction", "Distinct cinematic composition, no text, no captions"),
            "tts_direction": self._scene_field(scene, "tts_direction", "Calm, suspenseful narration"),
        }
        if opening:
            normalized["opening_time_range"] = normalized["time_range"]
        return normalized

    def _normalize_scene_duration(self, value, fallback: int = 60) -> int:
        try:
            duration = int(float(value))
        except (TypeError, ValueError):
            duration = fallback
        return max(1, duration)

    def _make_opening_micro_scene(self, base_scene: dict, order: int, upload_title: str) -> dict:
        start = (order - 1) * OPENING_MICRO_SCENE_SECONDS
        end = start + OPENING_MICRO_SCENE_SECONDS
        summary = base_scene.get("scene_summary") or base_scene.get("scene_situation") or upload_title or "opening hook beat"
        situation = base_scene.get("scene_situation") or summary
        micro_scene = dict(base_scene)
        micro_scene.update({
            "scene_id": f"scene{order:03d}",
            "scene_order": order,
            "target_duration": OPENING_MICRO_SCENE_SECONDS,
            "opening_micro_scene": True,
            "opening_time_range": f"{start}-{end}s",
            "scene_summary": f"Opening 5-second beat {order}: {summary}",
            "scene_situation": (
                f"First-minute micro beat {order}/12 ({start}-{end}s). "
                f"Keep this as a separate fast visual cut that advances the hook: {situation}"
            ),
            "retention_hook": base_scene.get("retention_hook") or "Maintain a sharp unresolved question into the next 5-second beat.",
            "title_promise_link": base_scene.get("title_promise_link") or f"Escalates the opening promise of: {upload_title}",
            "end_bridge": base_scene.get("end_bridge") or "Cut before the answer is complete.",
        })
        visual = base_scene.get("visual_direction") or ""
        micro_scene["visual_direction"] = (
            f"Mandatory 5-second opening cut {order}/12. Use a distinct composition or motion beat. {visual}"
        ).strip()
        return micro_scene

    def _build_pacing_slots(self, target_duration: int) -> list[dict]:
        slots = []
        cursor = 0
        while cursor < target_duration:
            phase = next(
                item for item in PACING_PHASES
                if item["until"] is None or cursor < item["until"]
            )
            phase_end = phase["until"] if phase["until"] is not None else target_duration
            end = min(cursor + phase["step"], phase_end, target_duration)
            slots.append({
                "start": cursor,
                "end": end,
                "duration": end - cursor,
                "phase": phase["name"],
                "step": phase["step"],
            })
            cursor = end
        return slots

    def _build_target_count_pacing_slots(self, target_duration: int, target_scene_count: int) -> list[dict]:
        if target_scene_count <= 0:
            return self._build_pacing_slots(target_duration)
        if target_scene_count == 1:
            return [{"start": 0, "end": target_duration, "duration": target_duration, "phase": "full", "step": target_duration}]

        opening_count = min(OPENING_MICRO_SCENE_COUNT, target_scene_count)
        slots = []
        cursor = 0
        for _ in range(opening_count):
            end = min(target_duration, cursor + OPENING_MICRO_SCENE_SECONDS)
            slots.append({
                "start": cursor,
                "end": end,
                "duration": max(1, end - cursor),
                "phase": "opening",
                "step": OPENING_MICRO_SCENE_SECONDS,
            })
            cursor = end

        remaining_count = target_scene_count - opening_count
        remaining_duration = max(0, target_duration - cursor)
        if remaining_count <= 0:
            if slots:
                slots[-1]["end"] = target_duration
                slots[-1]["duration"] = max(1, target_duration - slots[-1]["start"])
            return slots[:target_scene_count]

        base_duration = max(1, remaining_duration // remaining_count)
        remainder = max(0, remaining_duration - (base_duration * remaining_count))
        for index in range(remaining_count):
            duration = base_duration + (1 if index < remainder else 0)
            end = target_duration if index == remaining_count - 1 else min(target_duration, cursor + duration)
            phase = "development"
            if cursor >= 600:
                phase = "steady"
            elif cursor >= 300:
                phase = "explanation"
            slots.append({
                "start": cursor,
                "end": end,
                "duration": max(1, end - cursor),
                "phase": phase,
                "step": duration,
            })
            cursor = end
        return slots[:target_scene_count]

    def _source_scene_for_time(self, scenes: list[dict], source_offsets: list[tuple[int, int, dict]], slot_start: int) -> dict:
        for start, end, scene in source_offsets:
            if start <= slot_start < end:
                return scene
        return scenes[min(len(scenes) - 1, max(0, len(scenes) - 1))]

    def _make_paced_scene(self, base_scene: dict, slot: dict, order: int, upload_title: str) -> dict:
        if slot["phase"] == "opening":
            return self._make_opening_micro_scene(base_scene, order, upload_title)
        summary = base_scene.get("scene_summary") or base_scene.get("scene_situation") or upload_title or "story beat"
        situation = base_scene.get("scene_situation") or summary
        scene = dict(base_scene)
        scene.update({
            "scene_id": f"scene{order:03d}",
            "scene_order": order,
            "target_duration": slot["duration"],
            "pacing_phase": slot["phase"],
            "time_range": f"{slot['start']}-{slot['end']}s",
            "opening_micro_scene": False,
            "scene_summary": f"{slot['phase'].title()} beat {order}: {summary}",
            "scene_situation": (
                f"Timed visual beat {order} ({slot['start']}-{slot['end']}s, "
                f"{slot['duration']}s). Keep it separate and advance the story: {situation}"
            ),
            "retention_hook": base_scene.get("retention_hook") or "Keep a clear reason to continue into the next visual beat.",
            "title_promise_link": base_scene.get("title_promise_link") or f"Continues paying off the promise of: {upload_title}",
            "end_bridge": base_scene.get("end_bridge") or "Move cleanly into the next beat without resolving everything at once.",
        })
        visual = base_scene.get("visual_direction") or ""
        scene["visual_direction"] = (
            f"Mandatory {slot['duration']}-second {slot['phase']} phase cut. "
            f"Use a distinct composition, action, or camera beat. {visual}"
        ).strip()
        return scene

    def _enforce_longform_pacing_scenes(self, structure: dict, target_duration: int, upload_title: str, target_scene_count: int = None) -> dict:
        if not isinstance(structure, dict) or target_duration < LONGFORM_OPENING_RULE_MIN_SECONDS:
            return structure
        scenes = structure.get("scenes")
        if not isinstance(scenes, list) or not scenes:
            return structure

        pacing_slots = self._build_target_count_pacing_slots(target_duration, int(target_scene_count or 0)) if target_scene_count else self._build_pacing_slots(target_duration)
        existing_opening = [
            scene for scene in scenes
            if isinstance(scene, dict)
            and self._normalize_scene_duration(scene.get("target_duration"), OPENING_MICRO_SCENE_SECONDS) <= OPENING_MICRO_SCENE_SECONDS
            and int(scene.get("scene_order") or 999) <= OPENING_MICRO_SCENE_COUNT
        ]
        if len(scenes) == len(pacing_slots) and len(existing_opening) >= OPENING_MICRO_SCENE_COUNT:
            structure["pacing_scene_rule"] = {
                "status": "already_satisfied",
                "required_count": OPENING_MICRO_SCENE_COUNT,
                "required_duration_each": OPENING_MICRO_SCENE_SECONDS,
                "opening_window_seconds": OPENING_WINDOW_SECONDS,
                "total_scene_count": len(pacing_slots),
                "policy": "0-1m:5s, 1-5m:15s, 5-10m:20s, 10-15m:30s, 15m+:60s",
            }
            structure["target_duration_seconds"] = target_duration
            return structure

        source_offsets = []
        elapsed = 0
        for scene in scenes:
            if not isinstance(scene, dict):
                continue
            duration = self._normalize_scene_duration(scene.get("target_duration"), max(30, int(target_duration / len(scenes))))
            source_offsets.append((elapsed, elapsed + duration, scene))
            elapsed += duration

        paced_scenes = []
        for index, slot in enumerate(pacing_slots, start=1):
            base_scene = self._source_scene_for_time(scenes, source_offsets, slot["start"])
            paced_scenes.append(self._make_paced_scene(base_scene, slot, index, upload_title))

        structure["scenes"] = paced_scenes
        structure["scene_count"] = len(paced_scenes)
        structure["target_duration_seconds"] = target_duration
        structure["opening_micro_scene_rule"] = {
            "status": "enforced",
            "required_count": OPENING_MICRO_SCENE_COUNT,
            "required_duration_each": OPENING_MICRO_SCENE_SECONDS,
            "opening_window_seconds": OPENING_WINDOW_SECONDS,
        }
        structure["pacing_scene_rule"] = {
            "status": "enforced",
            "total_scene_count": len(paced_scenes),
            "target_scene_count": target_scene_count,
            "policy": "0-1m:5s, 1-5m:15s, 5-10m:20s, 10-20m:30s, 20m+:40s",
            "phase_counts": {
                "opening": sum(1 for slot in pacing_slots if slot["phase"] == "opening"),
                "development": sum(1 for slot in pacing_slots if slot["phase"] == "development"),
                "explanation": sum(1 for slot in pacing_slots if slot["phase"] == "explanation"),
                "steady": sum(1 for slot in pacing_slots if slot["phase"] == "steady"),
                "closing": sum(1 for slot in pacing_slots if slot["phase"] == "closing"),
            },
        }
        return structure

    async def plan_scenes(
        self,
        topic: str,
        target_duration: int = 60,
        project_id: int = None,
        style_directive: str = "",
        benchmark_analysis: dict = None,
        upload_title: str = "",
        title_generation: dict = None,
        accumulated_knowledge: list = None,
        recent_titles: list = None,
        target_scene_count: int = None,
    ) -> dict:
        style_section = f"\n{style_directive}\n" if style_directive else ""
        title_generation = title_generation if isinstance(title_generation, dict) else {}
        upload_title = (upload_title or title_generation.get("generated_title") or "").strip()
        title_angle = (title_generation.get("selected_angle") or title_generation.get("angle") or "").strip()
        title_contract_section = ""
        if upload_title:
            title_contract_section = f"""
UPLOAD TITLE CONTRACT:
- Upload title: {upload_title}
- Title angle/promise: {title_angle or "infer the concrete viewer promise from the upload title"}
- Make the title's promise clear in the first scene, deepen it through the middle, and pay it off in the final scene.
- Do NOT drift into creator education, meta analysis, strategy commentary, or "how to make content" unless the title explicitly promises that.
- For story categories, plan the actual story the viewer clicked for, not a lecture about storytelling.
- If the category is a fiction/story category, never turn the topic into a documentary about the genre, writing methods, formulas, secrets, rules, principles, or audience-retention strategy.
"""

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

        research_section = ""
        if benchmark_analysis and benchmark_analysis.get("web_research"):
            research = benchmark_analysis["web_research"]
            facts = research.get("verified_facts") or []
            fact_lines = "\n".join(f"- {item.get('claim', '')}" for item in facts[:8])
            source_lines = "\n".join(f"- {item.get('title', '')}: {item.get('url', '')}" for item in (research.get("sources") or [])[:8])
            research_section = f"""
GEMINI WEB RESEARCH (use only these verified facts; never invent or overstate facts):
{research.get('research_brief', '')}
FACTS:
{fact_lines or '- No discrete facts returned.'}
SOURCES FOR AUDIT:
{source_lines or '- No sources returned.'}
RISK NOTES: {', '.join(research.get('risk_notes') or [])}
- For fictional storytelling, use this only as atmosphere/context. Do not claim invented events are true.
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
{title_contract_section}
TARGET DURATION: {target_duration} seconds
TARGET SCENE COUNT: {target_scene_count or "auto"}
{style_section}
{benchmark_section}
{research_section}
{knowledge_section}
{history_section}
Instructions:
1. Break down the video into distinct scenes based on logical progression, location, or pacing changes.
2. Assign a unique ID to each scene (e.g., 'scene001').
3. Estimate the duration (in seconds) for each scene. The sum of all scene durations MUST approximate {target_duration} seconds.
3a. LONGFORM OPENING RULE: If TARGET DURATION is {LONGFORM_OPENING_RULE_MIN_SECONDS} seconds or longer, the first {OPENING_WINDOW_SECONDS} seconds MUST be exactly {OPENING_MICRO_SCENE_COUNT} separate opening scenes, each exactly {OPENING_MICRO_SCENE_SECONDS} seconds. Do not merge these opening beats into larger scenes.
3b. These first {OPENING_MICRO_SCENE_COUNT} scenes are mandatory fast visual cuts for retention. Each must have its own scene_id, scene_order, scene_summary, scene_situation, visual_direction, retention_hook, and end_bridge.
3c. If TARGET SCENE COUNT is a number, return exactly that many scenes.
3d. Keep every per-scene string concise: one sentence and at most 120 characters. Do not write paragraphs inside scene fields.
3e. Keep scene_summary at most 60 characters and scene_situation at most 120 characters. This is a production plan, not the final script.
4. Provide a brief summary of what happens in the scene.
5. Provide a visual hint for the overall background/setting of the scene.
6. If a Writing Style Directive is provided above, let it shape the scene progression itself — pacing, section count, how much of each scene is dialogue vs narration, and where tension/hooks land — not just the wording of the summaries.
7. Every scene must preserve retention: open a question, escalate stakes, reveal something, or set up the next scene.
8. If an UPLOAD TITLE CONTRACT is present, add title_promise, opening_hook, and payoff fields, and make each scene state how it serves that title promise.
8a. For story categories, title_promise must be the emotional/story promise inside the plot. It must not promise to teach storytelling rules, success formulas, secrets, principles, or genre analysis.
9. Provide the output strictly as a valid JSON object without markdown formatting.

JSON SCHEMA:
{{
  "topic": "...",
  "upload_title": "...",
  "title_promise": "The concrete promise made by the upload title",
  "opening_hook": "The first 20-40 seconds hook that makes viewers stay",
  "payoff": "What the script must finally reveal, prove, or emotionally resolve",
  "scene_count": 3,
  "global_mood": "Overall mood of the video",
  "scenes": [
    {{
      "scene_id": "scene001",
      "scene_order": 1,
      "opening_micro_scene": true,
      "opening_time_range": "0-5s",
      "scene_summary": "Brief summary of the scene",
      "scene_situation": "Detailed situational context for the scene",
      "scene_emotion": "Dominant emotion of the scene",
      "scene_purpose": "The main purpose of this scene in the story",
      "retention_hook": "Question, tension, or reveal that keeps viewers watching into this scene",
      "title_promise_link": "How this scene pays, deepens, or sets up the upload title promise",
      "end_bridge": "A short unresolved question or emotional turn leading to the next scene",
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
            # A detailed scene object typically needs 300-450 output tokens.
            # The old fixed 16K ceiling truncated 53+ scene plans into invalid
            # JSON, so reserve a larger response window for long-form plans.
            planning_max_tokens = 32768 if (target_scene_count or 0) >= 40 else 16384
            response_text = await ai_router.generate_text(
                prompt,
                planning_model,
                temperature=0.4,
                max_tokens=planning_max_tokens,
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
            
            structure = json.loads(response_text)
            return self._enforce_longform_pacing_scenes(structure, int(target_duration or 0), upload_title, target_scene_count=target_scene_count)
        except Exception as e:
            if isinstance(e, ai_router.ProviderCreditExhaustedError):
                raise
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

    async def plan_scenes_batched(
        self,
        topic: str,
        target_duration: int = 60,
        project_id: int = None,
        style_directive: str = "",
        benchmark_analysis: dict = None,
        upload_title: str = "",
        title_generation: dict = None,
        target_scene_count: int = None,
        batch_size: int = 8,
        batch_callback=None,
    ) -> dict:
        """Plan long scene structures in small validated JSON batches.

        The old one-shot 50+ scene JSON response was prone to truncation and
        repeated middle beats. This keeps each provider response small and lets
        the worker persist successful scene ranges before any later failure.
        """
        title_generation = title_generation if isinstance(title_generation, dict) else {}
        upload_title = (upload_title or title_generation.get("generated_title") or topic or "").strip()
        target_scene_count = int(target_scene_count or len(self._build_pacing_slots(int(target_duration or 60))))
        target_scene_count = max(1, min(400, target_scene_count))
        batch_size = max(1, min(12, int(batch_size or 8)))
        pacing_slots = self._build_target_count_pacing_slots(int(target_duration or 60), target_scene_count)
        planning_model = config.SCRIPT_PLANNING_MODEL or config.SCRIPT_GENERATION_MODEL
        scenes: list[dict] = []
        title_promise = (title_generation.get("selected_angle") or title_generation.get("angle") or upload_title).strip()

        for batch_start in range(1, target_scene_count + 1, batch_size):
            batch_end = min(target_scene_count, batch_start + batch_size - 1)
            batch_slots = pacing_slots[batch_start - 1:batch_end]
            previous_summaries = "\n".join(
                f"- {scene['scene_order']}: {scene.get('scene_summary', '')}"
                for scene in scenes[-12:]
            )
            slot_lines = "\n".join(
                f"- scene {batch_start + idx}: {slot['start']}-{slot['end']}s, {slot['phase']}, {slot['duration']}s"
                for idx, slot in enumerate(batch_slots)
            )
            benchmark_summary = ""
            if isinstance(benchmark_analysis, dict):
                script_analysis = benchmark_analysis.get("script_analysis") or {}
                benchmark_summary = "\n".join(
                    f"- {key}: {script_analysis.get(key, '')}"
                    for key in ("structure", "hooks", "pacing", "key_message")
                    if script_analysis.get(key)
                )
            prompt = f"""
You are planning ONE SMALL BATCH of a long video scene structure.
Return valid JSON only. Do not use markdown. Do not include scenes outside this requested range.

TOPIC: {topic}
UPLOAD TITLE: {upload_title}
TITLE PROMISE: {title_promise}
TARGET DURATION: {target_duration} seconds
TOTAL SCENE COUNT: {target_scene_count}
REQUESTED SCENE RANGE: {batch_start}-{batch_end}
SLOTS:
{slot_lines}

STYLE DIRECTIVE:
{style_directive}

BENCHMARK TECHNIQUE NOTES, if any:
{benchmark_summary or "- none"}

PREVIOUS SCENES TO AVOID REPEATING:
{previous_summaries or "- none yet"}

STRICT RULES:
- Output exactly {batch_end - batch_start + 1} scenes.
- Every scene must be a different event, decision, discovery, conflict, physical action, or emotional reversal.
- Do not repeat objects, clues, or dramatic beats from previous scenes unless this scene clearly changes their meaning.
- Do not write fallback, placeholder, template, camera-label, or production-instruction text as story content.
- Keep every field concise: one sentence per field.
- Avoid repeated Korean paragraph openers such as "그런데 말이야".
- The response must parse as a JSON object with a "scenes" array.

JSON SCHEMA:
{{
  "scenes": [
    {{
      "scene_summary": "unique concrete beat",
      "scene_situation": "specific situation and action",
      "scene_emotion": "dominant emotion",
      "scene_purpose": "why this scene must exist",
      "retention_hook": "question or tension pulling into the next scene",
      "title_promise_link": "how this scene advances the upload title promise",
      "end_bridge": "unresolved turn into the next scene",
      "visual_direction": "distinct visual setting and composition hint",
      "tts_direction": "voice tone and pacing"
    }}
  ]
}}
"""
            last_error: Exception | None = None
            parsed = None
            for attempt in range(3):
                try:
                    response_text = await ai_router.generate_text(
                        prompt,
                        planning_model,
                        temperature=0.35,
                        max_tokens=7000,
                        project_id=project_id,
                        task_type="planning_batch",
                        json_mode=True,
                    )
                    parsed = json.loads(self._strip_json_fence(response_text))
                    batch_scenes = parsed.get("scenes")
                    if not isinstance(batch_scenes, list) or len(batch_scenes) != (batch_end - batch_start + 1):
                        raise ValueError(f"batch {batch_start}-{batch_end} returned invalid scene count")
                    normalized_batch = [
                        self._normalize_batch_scene(scene, batch_slots[idx], batch_start + idx, upload_title)
                        for idx, scene in enumerate(batch_scenes)
                    ]
                    trial = {
                        "topic": topic,
                        "upload_title": upload_title,
                        "title_promise": title_promise,
                        "opening_hook": title_promise,
                        "payoff": title_promise,
                        "scene_count": len(scenes) + len(normalized_batch),
                        "global_mood": "tense emotional old-story narration",
                        "scenes": scenes + normalized_batch,
                        "planner_notes": {"strategy": "batched scene planning", "error": False},
                    }
                    break
                except Exception as exc:
                    last_error = exc
                    parsed = None
                    prompt += f"\n\nPrevious attempt failed: {str(exc)[:500]}\nReturn shorter valid JSON for only scenes {batch_start}-{batch_end}."
            if parsed is None:
                return {
                    "topic": topic,
                    "estimated_duration": 0,
                    "scene_count": len(scenes),
                    "global_mood": "unknown",
                    "scenes": scenes,
                    "planner_notes": {
                        "strategy": "batched scene planning failed",
                        "error": True,
                        "error_message": f"batch {batch_start}-{batch_end} failed: {last_error}",
                        "completed_scene_count": len(scenes),
                    },
                }
            scenes = trial["scenes"]
            if batch_callback:
                batch_callback(dict(trial), batch_start, batch_end)

        return {
            "topic": topic,
            "upload_title": upload_title,
            "title_promise": title_promise,
            "opening_hook": title_promise,
            "payoff": title_promise,
            "scene_count": len(scenes),
            "target_duration_seconds": target_duration,
            "global_mood": "tense emotional old-story narration",
            "scenes": scenes,
            "planner_notes": {
                "strategy": "Long-form scene plan generated in small JSON batches and persisted after each batch.",
                "error": False,
                "batched": True,
                "batch_size": batch_size,
            },
        }

scene_planner_service = ScenePlannerService()
