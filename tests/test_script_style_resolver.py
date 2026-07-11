import unittest
from unittest.mock import patch

import services.script_style_resolver as resolver
from services.script_style_resolver import (
    _BUILTIN_DEFAULT_DIRECTIVE,
    resolve_script_style_directive,
)


class ScriptStyleResolverTests(unittest.TestCase):
    def setUp(self):
        # 로그 중복 억제 캐시가 테스트 간에 새어나가지 않도록 초기화.
        resolver._last_logged_key = None

    def test_missing_style_uses_db_default_when_available(self):
        with patch("database.get_script_style_presets", return_value={"default": "자연스러운 톤 유지"}):
            directive = resolve_script_style_directive(None)
        self.assertIn("자연스러운 톤 유지", directive)
        self.assertIn("[Writing Style Directive]", directive)

    def test_default_style_uses_db_default_when_available(self):
        with patch("database.get_script_style_presets", return_value={"default": "자연스러운 톤 유지"}) as mock_presets:
            directive = resolve_script_style_directive("DEFAULT")
        self.assertIn("자연스러운 톤 유지", directive)
        mock_presets.assert_called_once()

    def test_missing_style_falls_back_to_builtin_when_db_default_empty(self):
        with patch("database.get_script_style_presets", return_value={}):
            directive = resolve_script_style_directive(None)
        self.assertIn(_BUILTIN_DEFAULT_DIRECTIVE, directive)
        self.assertIn("[Writing Style Directive]", directive)

    def test_valid_style_returns_directive_with_preset_text(self):
        with patch(
            "database.get_script_style_presets",
            return_value={"news": "뉴스 앵커 톤의 차분한 목소리, 신뢰감 있는 정보 전달"},
        ):
            directive = resolve_script_style_directive("news")
        self.assertIn("뉴스 앵커 톤의 차분한 목소리", directive)
        self.assertIn("[Writing Style Directive]", directive)
        self.assertIn("Apply this style strictly", directive)

    def test_style_key_is_case_insensitive(self):
        with patch(
            "database.get_script_style_presets",
            return_value={"news": "뉴스 스타일 지침"},
        ):
            directive = resolve_script_style_directive("NEWS")
        self.assertIn("뉴스 스타일 지침", directive)

    def test_unknown_style_falls_back_to_default_directive(self):
        with patch(
            "database.get_script_style_presets",
            return_value={"news": "뉴스 스타일 지침", "default": "기본 지침 본문"},
        ):
            directive = resolve_script_style_directive("does_not_exist_style")
        self.assertIn("기본 지침 본문", directive)
        self.assertNotIn("뉴스 스타일 지침", directive)

    def test_inactive_style_with_empty_prompt_value_falls_back_to_default(self):
        with patch(
            "database.get_script_style_presets",
            return_value={"disabled_style": "   ", "default": "기본 지침 본문"},
        ):
            directive = resolve_script_style_directive("disabled_style")
        self.assertIn("기본 지침 본문", directive)

    def test_db_lookup_failure_falls_back_to_builtin_directive(self):
        with patch(
            "database.get_script_style_presets",
            side_effect=Exception("db unavailable"),
        ):
            directive = resolve_script_style_directive("news")
        self.assertIn(_BUILTIN_DEFAULT_DIRECTIVE, directive)

    def test_db_failure_never_raises_and_generation_can_continue(self):
        """리졸버가 예외를 던지면 그 위의 모든 생성 경로가 통째로 죽는다.
        DB가 완전히 죽어도 always a usable string을 돌려줘야 한다."""
        with patch("database.get_script_style_presets", side_effect=RuntimeError("db down")):
            for style in (None, "", "default", "news", "unknown_key"):
                directive = resolve_script_style_directive(style)
                self.assertIsInstance(directive, str)
                self.assertTrue(directive)


class AliasResolutionTests(unittest.TestCase):
    def setUp(self):
        resolver._last_logged_key = None

    def test_legacy_alias_key_resolves_to_canonical_preset_content(self):
        presets = {
            "joseon_sageuk": "canonical 조선사극 지침",
            "joseon_drama": "legacy 조선사극 지침(사용되면 안 됨)",
        }
        with patch("database.get_script_style_presets", return_value=presets):
            directive = resolve_script_style_directive("joseon_drama")
        self.assertIn("canonical 조선사극 지침", directive)
        self.assertNotIn("legacy 조선사극 지침", directive)

    def test_alias_key_works_even_when_legacy_row_missing_from_db(self):
        """레거시 키가 DB에서 삭제되어도(또는 애초에 없어도) canonical로 정상 해석되어야 한다."""
        presets = {"story": "canonical 옛날이야기 지침"}
        with patch("database.get_script_style_presets", return_value=presets):
            directive = resolve_script_style_directive("old_story")
        self.assertIn("canonical 옛날이야기 지침", directive)

    def test_all_documented_aliases_map_to_expected_canonical(self):
        expected = {
            "joseon_drama": "joseon_sageuk",
            "north_korea_drama": "north_korean_drama",
            "silent_film_20s": "silent_20s",
            "k_comics": "k_manhwa",
            "cute_animal": "cute_animal_char",
            "neon_citypop": "neonsign_citypop",
            "pencil_sketch": "graphite_sketch",
            "renaissance_religious": "renaissance_sacred",
            "bgm_focus": "bgm",
            "old_story": "story",
        }
        self.assertEqual(resolver._ALIAS_MAP, expected)


class LoggingSafetyTests(unittest.TestCase):
    def setUp(self):
        resolver._last_logged_key = None

    def test_repeated_identical_resolution_logs_only_once(self):
        calls = []
        with patch("services.script_style_resolver._write_log_line", side_effect=lambda line: calls.append(line)), \
             patch("database.get_script_style_presets", return_value={"news": "뉴스 지침"}):
            for _ in range(5):
                resolve_script_style_directive("news")
        self.assertEqual(len(calls), 1)

    def test_changed_resolution_logs_again(self):
        calls = []
        with patch("services.script_style_resolver._write_log_line", side_effect=lambda line: calls.append(line)), \
             patch("database.get_script_style_presets", return_value={"news": "뉴스 지침", "story": "옛날이야기 지침"}):
            resolve_script_style_directive("news")
            resolve_script_style_directive("story")
            resolve_script_style_directive("news")
        self.assertEqual(len(calls), 3)

    def test_broken_stdout_does_not_raise(self):
        """console=False 패키징 환경을 흉내: print()가 예외를 던져도 로그 기록은
        조용히 실패하고, resolve_script_style_directive는 정상적으로 결과를 반환해야 한다."""
        def _broken_print(*args, **kwargs):
            raise AttributeError("'NoneType' object has no attribute 'write'")

        with patch("builtins.print", side_effect=_broken_print), \
             patch("database.get_script_style_presets", return_value={"news": "뉴스 지침"}):
            directive = resolve_script_style_directive("news")
        self.assertIn("뉴스 지침", directive)

    def test_log_fields_present_and_no_prompt_content_logged(self):
        captured = []
        with patch("services.script_style_resolver._write_log_line", side_effect=lambda line: captured.append(line)), \
             patch("database.get_script_style_presets", return_value={"news": "이것은 프롬프트에만 들어가야 하는 민감한 스타일 본문입니다"}):
            resolve_script_style_directive("news")
        self.assertEqual(len(captured), 1)
        line = captured[0]
        self.assertIn("requested_style=news", line)
        self.assertIn("resolved_style=news", line)
        self.assertIn("fallback_used=False", line)
        self.assertIn("db_error=False", line)
        self.assertNotIn("프롬프트에만 들어가야 하는 민감한 스타일 본문", line)


if __name__ == "__main__":
    unittest.main()
