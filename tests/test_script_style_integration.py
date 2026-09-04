"""
수동 대본기획(/api/gemini/generate-structure) -> scene_planner, 수동 대본생성
(/api/script/generate), autopilot(_generate_script) 세 경로가 동일한
services.script_style_resolver.resolve_script_style_directive() 결과를
프롬프트에 반영하는지 검증한다.
"""
import asyncio
import unittest
from unittest.mock import patch, AsyncMock

from app.services.scene_planner import scene_planner_service
from app.routers.gemini import script_generate
from app.models.media import GeminiRequest


FAKE_DIRECTIVE = "[Writing Style Directive]\nTEST STYLE MARKER\nApply this style strictly throughout the script."


class ScenePlannerStyleTests(unittest.IsolatedAsyncioTestCase):
    async def test_long_form_plan_reserves_enough_output_tokens(self):
        captured = {}

        async def fake_generate_text(prompt, model, **kwargs):
            captured.update(kwargs)
            return '{"topic": "t", "scene_count": 53, "global_mood": "calm", "scenes": [], "planner_notes": {"strategy": "x", "error": false}}'

        with patch("app.services.scene_planner.ai_router.generate_text", side_effect=fake_generate_text):
            await scene_planner_service.plan_scenes(
                topic="long-form",
                target_duration=900,
                target_scene_count=53,
            )

        self.assertEqual(captured["max_tokens"], 32768)

    async def test_style_directive_is_embedded_in_planning_prompt(self):
        captured = {}

        async def fake_generate_text(prompt, model, **kwargs):
            captured["prompt"] = prompt
            return '{"topic": "t", "scene_count": 1, "global_mood": "calm", "scenes": [], "planner_notes": {"strategy": "x", "error": false}}'

        with patch("app.services.scene_planner.ai_router.generate_text", side_effect=fake_generate_text):
            await scene_planner_service.plan_scenes(topic="테스트 주제", target_duration=60, style_directive=FAKE_DIRECTIVE)

        self.assertIn(FAKE_DIRECTIVE, captured["prompt"])

    async def test_no_directive_when_style_directive_is_empty(self):
        captured = {}

        async def fake_generate_text(prompt, model, **kwargs):
            captured["prompt"] = prompt
            return '{"topic": "t", "scene_count": 1, "global_mood": "calm", "scenes": [], "planner_notes": {"strategy": "x", "error": false}}'

        with patch("app.services.scene_planner.ai_router.generate_text", side_effect=fake_generate_text):
            await scene_planner_service.plan_scenes(topic="테스트 주제", target_duration=60, style_directive="")

        self.assertNotIn("TEST STYLE MARKER", captured["prompt"])


class ManualScriptGenerateEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_script_style_injects_directive(self):
        captured = {}

        async def fake_generate_text(prompt, model, **kwargs):
            captured["prompt"] = prompt
            return "generated script text"

        with patch("services.auth_service.auth_service.check_credits", return_value=True), \
             patch("services.script_style_resolver.resolve_script_style_directive", return_value=FAKE_DIRECTIVE) as mock_resolve, \
             patch("services.ai_router.generate_text", side_effect=fake_generate_text):
            req = GeminiRequest(prompt="원본 프롬프트", script_style="news")
            result = await script_generate(req)

        mock_resolve.assert_called_once_with("news")
        self.assertEqual(result["status"], "ok")
        self.assertIn(FAKE_DIRECTIVE, captured["prompt"])
        self.assertIn("원본 프롬프트", captured["prompt"])

    async def test_missing_script_style_is_backward_compatible(self):
        """script_style을 아예 보내지 않는 기존/다른 호출부는 prompt가 그대로 전달되어야 한다."""
        captured = {}

        async def fake_generate_text(prompt, model, **kwargs):
            captured["prompt"] = prompt
            return "generated script text"

        with patch("services.auth_service.auth_service.check_credits", return_value=True), \
             patch("services.script_style_resolver.resolve_script_style_directive") as mock_resolve, \
             patch("services.ai_router.generate_text", side_effect=fake_generate_text):
            req = GeminiRequest(prompt="원본 프롬프트만 있음")
            result = await script_generate(req)

        mock_resolve.assert_not_called()
        self.assertEqual(result["status"], "ok")
        self.assertEqual(captured["prompt"], "원본 프롬프트만 있음")

    async def test_unknown_script_style_falls_back_without_crashing(self):
        captured = {}

        async def fake_generate_text(prompt, model, **kwargs):
            captured["prompt"] = prompt
            return "generated script text"

        with patch("services.auth_service.auth_service.check_credits", return_value=True), \
             patch("database.get_script_style_presets", return_value={}), \
             patch("services.ai_router.generate_text", side_effect=fake_generate_text):
            req = GeminiRequest(prompt="원본 프롬프트", script_style="no_such_style")
            result = await script_generate(req)

        # [정책 변경] resolver는 이제 알 수 없는 스타일도 빈 문자열이 아니라
        # 내장 기본 지침으로 폴백하므로, prompt에는 원본 프롬프트 + 기본 지침이
        # 함께 담긴다 (원본 프롬프트가 사라지지는 않는다).
        self.assertEqual(result["status"], "ok")
        self.assertIn("원본 프롬프트", captured["prompt"])
        self.assertIn("[Writing Style Directive]", captured["prompt"])


class SharedResolverUsageTests(unittest.TestCase):
    """수동 생성 경로(app.routers.gemini)와 autopilot 경로(services.autopilot_service)가
    같은 소스 모듈(services.script_style_resolver)의 함수를 호출하는지 정적으로 확인한다."""

    def test_gemini_router_imports_shared_resolver(self):
        import inspect
        import app.routers.gemini as gemini_router
        src = inspect.getsource(gemini_router)
        self.assertIn("from services.script_style_resolver import resolve_script_style_directive", src)

    def test_autopilot_service_imports_shared_resolver(self):
        import inspect
        import services.autopilot_service as autopilot_module
        src = inspect.getsource(autopilot_module)
        self.assertIn("from services.script_style_resolver import resolve_script_style_directive", src)
        # 더 이상 자체적으로 프리셋을 조회해 지침을 조립하지 않는다 (공통 함수로 대체됨).
        self.assertNotIn('script_presets.get(style_key', src)


if __name__ == "__main__":
    unittest.main()
