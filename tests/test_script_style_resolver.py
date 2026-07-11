import unittest
from unittest.mock import patch

from services.script_style_resolver import resolve_script_style_directive


class ScriptStyleResolverTests(unittest.TestCase):
    def test_missing_style_returns_empty_directive(self):
        self.assertEqual(resolve_script_style_directive(None), "")
        self.assertEqual(resolve_script_style_directive(""), "")
        self.assertEqual(resolve_script_style_directive("   "), "")

    def test_default_style_returns_empty_directive(self):
        with patch("database.get_script_style_presets") as mock_presets:
            self.assertEqual(resolve_script_style_directive("default"), "")
            self.assertEqual(resolve_script_style_directive("DEFAULT"), "")
            # "default"/neutral short-circuits before hitting the DB at all.
            mock_presets.assert_not_called()

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

    def test_unknown_style_falls_back_to_default(self):
        with patch(
            "database.get_script_style_presets",
            return_value={"news": "뉴스 스타일 지침"},
        ):
            directive = resolve_script_style_directive("does_not_exist_style")
        self.assertEqual(directive, "")

    def test_inactive_style_with_empty_prompt_value_falls_back_to_default(self):
        with patch(
            "database.get_script_style_presets",
            return_value={"disabled_style": "   "},
        ):
            directive = resolve_script_style_directive("disabled_style")
        self.assertEqual(directive, "")

    def test_db_lookup_failure_falls_back_safely(self):
        with patch(
            "database.get_script_style_presets",
            side_effect=Exception("db unavailable"),
        ):
            directive = resolve_script_style_directive("news")
        self.assertEqual(directive, "")


if __name__ == "__main__":
    unittest.main()
