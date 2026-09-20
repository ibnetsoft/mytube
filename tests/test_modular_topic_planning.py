"""Tests for modular topic planning slots and dynamic writing profile registry."""
import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
WORKER = ROOT / "worker"
if str(WORKER) not in sys.path:
    sys.path.insert(0, str(WORKER))

from services.category_writing_profiles import (
    build_category_writing_profile,
    get_category_writing_profile,
    list_category_writing_profiles,
    register_category_writing_profile,
    remove_category_writing_profile,
    resolve_category_writing_profile,
)
from worker.hermes_worker import (
    _build_prompt,
    _validate_payload,
)


class TestDynamicWritingProfiles(unittest.TestCase):
    def test_builtin_and_new_genre_profiles_exist(self):
        profiles = list_category_writing_profiles()
        # Original categories
        self.assertIn("옛날이야기", profiles)
        self.assertIn("무협", profiles)
        self.assertIn("한국사연", profiles)
        # New modern genres
        self.assertIn("판타지/SF", profiles)
        self.assertIn("일상/웹툰", profiles)
        self.assertIn("지식/미스터리", profiles)
        self.assertIn("힐링/동화", profiles)

    def test_resolve_builtin_and_aliases(self):
        self.assertIn("Korean Folktale", resolve_category_writing_profile("옛날이야기"))
        self.assertIn("Korean Folktale", resolve_category_writing_profile("old_story"))
        self.assertIn("Everyday Webtoon", resolve_category_writing_profile("일상/웹툰"))
        self.assertIn("Everyday Webtoon", resolve_category_writing_profile("webtoon"))

    def test_unknown_category_returns_empty_when_no_custom_profile(self):
        self.assertEqual(resolve_category_writing_profile("완전_새로운_카테고리"), "")

    def test_custom_profile_override_in_resolution(self):
        custom_voice = "냉철한 과학자의 분석 톤, 짧고 명확한 문장"
        resolved = resolve_category_writing_profile("미확인_장르", custom_profile=custom_voice)
        self.assertIn(custom_voice, resolved)
        self.assertIn("Global Narration Rhythm Guard", resolved)

    def test_register_and_remove_dynamic_profile(self):
        genre_name = "사이버펑크_느와르"
        profile_dict = {
            "voice": "시니컬한 30대 해커의 독백",
            "rhythm": "네온사인 골목길의 비트감 있는 짧은 호흡",
            "drama": "거대 기업의 음모와 인간성의 갈등",
            "language": "자연스럽고 세련된 현대 한국어",
        }
        registered = register_category_writing_profile(genre_name, profile_dict, persist=False)
        self.assertIn("Category Writing Profile: 사이버펑크_느와르", registered)
        self.assertIn("시니컬한 30대 해커의 독백", registered)

        # Verify resolution
        resolved = resolve_category_writing_profile(genre_name)
        self.assertIn("시니컬한 30대 해커의 독백", resolved)

        # Verify removal
        removed = remove_category_writing_profile(genre_name, persist=False)
        self.assertTrue(removed)
        self.assertEqual(resolve_category_writing_profile(genre_name), "")


class TestHermesTopicResearchSlots(unittest.TestCase):
    def test_validate_payload_defaults(self):
        payload = {"keyword": "인공지능"}
        kw, lang, country, count, img_style, char_ctx, writing_prof = _validate_payload(payload)
        self.assertEqual(kw, "인공지능")
        self.assertEqual(lang, "ko")
        self.assertEqual(country, "global")
        self.assertEqual(count, 10)
        self.assertEqual(img_style, "")
        self.assertIsNone(char_ctx)
        self.assertEqual(writing_prof, "")

    def test_validate_payload_with_modular_slots(self):
        payload = {
            "keyword": "반려동물과의 하루",
            "language": "ko",
            "country": "KR",
            "count": 5,
            "image_style": "k_webtoon",
            "character_context": {
                "name": "토리",
                "role": "탐정",
                "description": "갈색 털과 큰 꼬리를 가진 영리한 다람쥐",
            },
            "writing_profile": "일상/웹툰",
        }
        kw, lang, country, count, img_style, char_ctx, writing_prof = _validate_payload(payload)
        self.assertEqual(kw, "반려동물과의 하루")
        self.assertEqual(img_style, "k_webtoon")
        self.assertIsNotNone(char_ctx)
        self.assertEqual(char_ctx["name"], "토리")
        self.assertEqual(char_ctx["role"], "탐정")
        self.assertIn("다람쥐", char_ctx["description"])
        self.assertEqual(writing_prof, "일상/웹툰")

    def test_validate_payload_string_character(self):
        payload = {
            "keyword": "미스터리",
            "character": "영호, 30대 사립탐정",
        }
        kw, lang, country, count, img_style, char_ctx, writing_prof = _validate_payload(payload)
        self.assertIsNotNone(char_ctx)
        self.assertEqual(char_ctx["name"], "영호")

    def test_build_prompt_includes_modular_slots(self):
        prompt = _build_prompt(
            keyword="숲속 모험",
            language="ko",
            country="KR",
            count=3,
            image_style="ghibli",
            character_context={
                "name": "루미",
                "role": "마법 견습생",
                "description": "커다란 깃털 모자를 쓴 10대 소녀",
            },
            writing_profile="[Category Writing Profile: 힐링/동화]\n- 따뜻하고 신비로운 분위기",
        )
        self.assertIn("Research keyword/category: 숲속 모험", prompt)
        self.assertIn("[TARGET VISUAL ART STYLE: ghibli]", prompt)
        self.assertIn("[PROTAGONIST / CHARACTER ANCHOR]", prompt)
        self.assertIn("Main Character: 루미", prompt)
        self.assertIn("[WRITING & NARRATIVE TONE DIRECTIVE]", prompt)
        self.assertIn("힐링/동화", prompt)
        self.assertIn("visual_concept", prompt)
        self.assertIn("suggested_character_role", prompt)

    def test_build_prompt_clean_fallback_when_slots_omitted(self):
        prompt = _build_prompt(
            keyword="미래 기술",
            language="en",
            country="US",
            count=5,
        )
        self.assertIn("Research keyword/category: 미래 기술", prompt)
        self.assertNotIn("[TARGET VISUAL ART STYLE", prompt)
        self.assertNotIn("[PROTAGONIST / CHARACTER ANCHOR]", prompt)
        self.assertNotIn("[WRITING & NARRATIVE TONE DIRECTIVE]", prompt)
        self.assertIn("topics", prompt)


if __name__ == "__main__":
    unittest.main()
