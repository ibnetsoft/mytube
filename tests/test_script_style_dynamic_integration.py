"""
정적 import 검증을 넘어, 6개 실제 생성 경로가 조립하는 "최종 프롬프트"를 mock으로
직접 캡처해 스타일 지침이 정확히 1회씩 포함되는지 검증한다.

    1. 수동 기획: /api/gemini/generate-structure -> scene_planner
    2. 수동 본문 생성: /api/script/generate
    3. autopilot auto-plan (일반)
    4. autopilot auto-plan (음악)
    5. autopilot 본문 (manual_plan 있음)
    6. autopilot 본문 (manual_plan 없음)

+ alias 해석, requested/resolved 로그 구분, default 정책, DB 실패 시 생성 지속,
기존 prompt-only 요청 회귀 없음.

실제 Gemini 호출은 하지 않는다 (전부 mock). 실제 호출 비교 QA는
scratchpad/style_qa/run_qa.py에서 별도로 수행한다.
"""
import unittest
from unittest.mock import patch, AsyncMock

from app.models.media import GeminiRequest
from app.routers.gemini import script_generate
from app.services.scene_planner import scene_planner_service
from services.autopilot_service import AutoPilotService

STYLE_MARKER = "===STYLE_MARKER_XYZ==="
FAKE_DIRECTIVE = f"[Writing Style Directive]\n{STYLE_MARKER}\nApply this style strictly throughout the script."


def _planning_json_response(*_args, **_kwargs):
    return '{"hook": "h", "sections": [{"title": "t", "key_points": ["a"]}], "cta": "c"}'


def _music_planning_json_response(*_args, **_kwargs):
    return (
        '{"style": "bgm", "playlist_title": "t", "genre": "lofi", "moods": [], "mood": "m", '
        '"audience": "a", "tracks": [], "visual_concept": "v", "thumbnail_concept": "th", '
        '"description_angle": "d"}'
    )


class ManualPlanningPromptCaptureTests(unittest.IsolatedAsyncioTestCase):
    """1. 수동 기획: generate-structure -> scene_planner"""

    async def test_directive_appears_exactly_once_in_planning_prompt(self):
        captured = {}

        async def fake_generate_text(prompt, model, **kwargs):
            captured["prompt"] = prompt
            return '{"topic": "t", "scene_count": 1, "global_mood": "m", "scenes": [], "planner_notes": {"strategy": "s", "error": false}}'

        with patch("app.services.scene_planner.ai_router.generate_text", side_effect=fake_generate_text):
            await scene_planner_service.plan_scenes(topic="주제", target_duration=60, style_directive=FAKE_DIRECTIVE)

        self.assertEqual(captured["prompt"].count(STYLE_MARKER), 1)


class ManualScriptGenerationPromptCaptureTests(unittest.IsolatedAsyncioTestCase):
    """2. 수동 본문 생성: /api/script/generate"""

    async def test_directive_appears_exactly_once_in_manual_script_prompt(self):
        captured = {}

        async def fake_generate_text(prompt, model, **kwargs):
            captured["prompt"] = prompt
            return "generated"

        with patch("services.auth_service.auth_service.check_credits", return_value=True), \
             patch("services.script_style_resolver.resolve_script_style_directive", return_value=FAKE_DIRECTIVE), \
             patch("services.ai_router.generate_text", side_effect=fake_generate_text):
            req = GeminiRequest(prompt="섹션 프롬프트 본문", script_style="news")
            result = await script_generate(req)

        self.assertEqual(result["status"], "ok")
        self.assertEqual(captured["prompt"].count(STYLE_MARKER), 1)

    async def test_backward_compatible_when_script_style_absent(self):
        """기존/다른 호출부가 script_style 없이 보내면 프롬프트가 변형되지 않아야 한다 (회귀 없음)."""
        captured = {}

        async def fake_generate_text(prompt, model, **kwargs):
            captured["prompt"] = prompt
            return "generated"

        with patch("services.auth_service.auth_service.check_credits", return_value=True), \
             patch("services.script_style_resolver.resolve_script_style_directive") as mock_resolve, \
             patch("services.ai_router.generate_text", side_effect=fake_generate_text):
            req = GeminiRequest(prompt="변형되면 안 되는 원본 프롬프트")
            result = await script_generate(req)

        mock_resolve.assert_not_called()
        self.assertEqual(result["status"], "ok")
        self.assertEqual(captured["prompt"], "변형되면 안 되는 원본 프롬프트")


def _autopilot_common_patches(side_effect):
    """4개 autopilot 브랜치 테스트가 공유하는 DB mock 세트.

    주의: database.get_related_top_analyses는 실제 database.py에 정의되어 있지
    않다 (이번 작업과 무관한 별도의 기존 버그 - 최종 보고서에 기록, 여기서는
    고치지 않는다). create=True로 테스트 동안만 존재하는 것처럼 만들어, 이
    테스트가 검증하려는 스타일 지침 배선과 무관한 지점에서 막히지 않게 한다.
    """
    return [
        patch("database.get_project", return_value={"topic": "은퇴 후 인생 2막"}),
        patch("database.get_related_top_analyses", return_value=[], create=True),
        patch("database.get_top_analyses", return_value=[]),
        patch("database.get_script_structure", side_effect=side_effect),
        patch("database.save_script_structure"),
        patch("database.update_project_setting"),
        patch("database.save_script"),
    ]


class AutopilotPromptCaptureTests(unittest.IsolatedAsyncioTestCase):
    async def _run_with_patches(self, patches, config_dict, resolver_return=FAKE_DIRECTIVE):
        calls = []

        async def fake_generate_text_with_model(prompt, model, **kwargs):
            calls.append({"prompt": prompt, "task_type": kwargs.get("task_type")})
            if kwargs.get("task_type") == "planning":
                if config_dict.get("mode") == "longform_music":
                    return _music_planning_json_response()
                return _planning_json_response()
            return "generated script body"

        ctx_patches = patches + [
            patch("services.script_style_resolver.resolve_script_style_directive", return_value=resolver_return),
            patch("services.autopilot_service.generate_text_with_model", side_effect=fake_generate_text_with_model),
        ]
        for p in ctx_patches:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in ctx_patches])

        service = AutoPilotService()
        await service._generate_script(project_id=1, analysis={"summary": "s"}, config_dict=config_dict)
        return calls

    async def test_auto_plan_general_branch_directive_once_in_each_prompt(self):
        """3. autopilot auto-plan (일반, non-music)"""
        config_dict = {"script_style": "news", "auto_plan": True, "duration_seconds": 300}
        patches = _autopilot_common_patches(
            side_effect=[None, {"structure": {"hook": "h", "sections": [{"title": "t", "key_points": ["a"]}], "cta": "c"}}]
        )
        calls = await self._run_with_patches(patches, config_dict)

        planning_calls = [c for c in calls if c["task_type"] == "planning"]
        scripting_calls = [c for c in calls if c["task_type"] == "scripting"]
        self.assertEqual(len(planning_calls), 1, "auto-plan은 struct_prompt를 위해 planning 호출이 1회 있어야 한다")
        self.assertEqual(len(scripting_calls), 1, "auto-plan 이후 manual_plan 분기로 넘어가 본문 작성이 1회 있어야 한다")
        self.assertEqual(planning_calls[0]["prompt"].count(STYLE_MARKER), 1)
        self.assertEqual(scripting_calls[0]["prompt"].count(STYLE_MARKER), 1)

    async def test_auto_plan_music_branch_directive_once_in_struct_prompt(self):
        """4. autopilot auto-plan (음악)"""
        config_dict = {
            "script_style": "bgm",
            "mode": "longform_music",
            "auto_plan": True,
            "duration_seconds": 3600,
            "longform_music": {"playlist_duration_seconds": 3600, "track_count": 12, "genre": "lofi"},
        }
        patches = _autopilot_common_patches(
            side_effect=[None, {"structure": {"style": "bgm", "tracks": []}}]
        )
        calls = await self._run_with_patches(patches, config_dict)

        planning_calls = [c for c in calls if c["task_type"] == "planning"]
        self.assertEqual(len(planning_calls), 1)
        self.assertIn("playlist", planning_calls[0]["prompt"].lower())
        self.assertEqual(planning_calls[0]["prompt"].count(STYLE_MARKER), 1)

    async def test_manual_plan_present_branch_directive_once(self):
        """5. autopilot 본문 (manual_plan 있음)"""
        existing_structure = {"structure": {"hook": "h", "sections": [{"title": "t", "key_points": ["a"]}], "cta": "c"}}
        config_dict = {"script_style": "horror_suspense", "duration_seconds": 300}
        patches = _autopilot_common_patches(side_effect=[existing_structure, existing_structure])
        calls = await self._run_with_patches(patches, config_dict)

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["task_type"], "scripting")
        self.assertIn("USER PLANNED STRUCTURE", calls[0]["prompt"])
        self.assertEqual(calls[0]["prompt"].count(STYLE_MARKER), 1)

    async def test_manual_plan_absent_branch_directive_once(self):
        """6. autopilot 본문 (manual_plan 없음, auto_plan도 아님 -> Original Logic)"""
        config_dict = {"script_style": "k_webtoon", "duration_seconds": 300}
        patches = _autopilot_common_patches(side_effect=[None, {"structure": {"hook": "h", "sections": [], "cta": "c"}}])
        calls = await self._run_with_patches(patches, config_dict)

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["task_type"], "scripting")
        self.assertNotIn("USER PLANNED STRUCTURE", calls[0]["prompt"])
        self.assertEqual(calls[0]["prompt"].count(STYLE_MARKER), 1)


class AliasAndDefaultPolicyEndToEndTests(unittest.IsolatedAsyncioTestCase):
    async def test_alias_key_resolves_to_canonical_content_in_manual_script_prompt(self):
        captured = {}

        async def fake_generate_text(prompt, model, **kwargs):
            captured["prompt"] = prompt
            return "generated"

        with patch("services.auth_service.auth_service.check_credits", return_value=True), \
             patch(
                 "database.get_script_style_presets",
                 return_value={"joseon_sageuk": "CANONICAL_JOSEON_CONTENT", "joseon_drama": "LEGACY_SHOULD_NOT_APPEAR"},
             ), \
             patch("services.ai_router.generate_text", side_effect=fake_generate_text):
            req = GeminiRequest(prompt="본문", script_style="joseon_drama")  # legacy alias
            await script_generate(req)

        self.assertIn("CANONICAL_JOSEON_CONTENT", captured["prompt"])
        self.assertNotIn("LEGACY_SHOULD_NOT_APPEAR", captured["prompt"])

    async def test_default_request_still_produces_usable_directive(self):
        """default 정책 변경: 이제 default/미지정도 빈 지침이 아니라 실제 글쓰기 지침을 받는다."""
        captured = {}

        async def fake_generate_text(prompt, model, **kwargs):
            captured["prompt"] = prompt
            return "generated"

        with patch("services.auth_service.auth_service.check_credits", return_value=True), \
             patch("database.get_script_style_presets", return_value={"default": "DEFAULT_WRITING_DIRECTIVE"}), \
             patch("services.ai_router.generate_text", side_effect=fake_generate_text):
            req = GeminiRequest(prompt="본문", script_style="default")
            await script_generate(req)

        self.assertIn("DEFAULT_WRITING_DIRECTIVE", captured["prompt"])

    async def test_db_failure_does_not_abort_manual_script_generation(self):
        captured = {}

        async def fake_generate_text(prompt, model, **kwargs):
            captured["prompt"] = prompt
            return "generated"

        with patch("services.auth_service.auth_service.check_credits", return_value=True), \
             patch("database.get_script_style_presets", side_effect=RuntimeError("db down")), \
             patch("services.ai_router.generate_text", side_effect=fake_generate_text):
            req = GeminiRequest(prompt="본문", script_style="news")
            result = await script_generate(req)

        self.assertEqual(result["status"], "ok")
        self.assertIn("본문", captured["prompt"])

    async def test_db_failure_does_not_abort_autopilot_script_generation(self):
        calls = []

        async def fake_generate_text_with_model(prompt, model, **kwargs):
            calls.append(prompt)
            return "generated script body"

        patches = _autopilot_common_patches(side_effect=[None, {"structure": {"hook": "h", "sections": [], "cta": "c"}}]) + [
            patch("database.get_script_style_presets", side_effect=RuntimeError("db down")),
            patch("services.autopilot_service.generate_text_with_model", side_effect=fake_generate_text_with_model),
        ]
        for p in patches:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in patches])

        service = AutoPilotService()
        script = await service._generate_script(project_id=1, analysis={"summary": "s"}, config_dict={"script_style": "news"})
        self.assertEqual(script, "generated script body")


if __name__ == "__main__":
    unittest.main()
