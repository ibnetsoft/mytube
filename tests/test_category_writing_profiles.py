import pathlib
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.category_writing_profiles import resolve_category_writing_profile


def test_every_primary_hermes_category_has_a_distinct_writing_profile():
    categories = ["옛날이야기", "무협", "탈북사연", "황혼19금", "한국사연", "해외감동", "노후금융", "경제"]
    profiles = [resolve_category_writing_profile(category) for category in categories]

    assert all(profiles)
    assert len(set(profiles)) == len(categories)


def test_legacy_old_story_style_maps_to_folktale_voice():
    assert resolve_category_writing_profile("old_story") == resolve_category_writing_profile("옛날이야기")


def test_unknown_category_does_not_receive_an_unrelated_voice():
    assert resolve_category_writing_profile("사용자 정의 카테고리") == ""


def test_worker_applies_profile_to_plan_draft_and_rewrite():
    source = (ROOT / "worker" / "hermes_worker.py").read_text(encoding="utf-8")

    assert source.count("resolve_category_writing_profile(category_name)") >= 2
    assert "CATEGORY WRITING PROFILE:" in source
    assert "category_writing_profile=category_writing_profile" in source
    assert "Do not merge, skip, or summarize a scene" in source
    assert "async def _revise_script_sections(" in source
    assert "hermes_script_structured_rewrite" in source
    assert "scene_script_sections = revised_sections" in source
