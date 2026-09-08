from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STD_PAGE = (ROOT / "auth-web" / "app" / "std" / "page.tsx").read_text(encoding="utf-8")


def test_selected_scene_controls_live_in_the_style_toolbar_and_stay_disabled_until_selected():
    toolbar = STD_PAGE.split("{/* 1. 상단 2줄 스타일 툴바", 1)[1].split("{/* 2. 메인 바디", 1)[0]
    layer_header = STD_PAGE.split("{/* 좌측 자막 레이어 목록", 1)[1].split("{/* 자막 카드 목록 */}", 1)[0]

    assert "const hasSelectedSubtitleSections = selectedSubtitleSceneNumbers.length > 0" in STD_PAGE
    assert "'selected-scenes-bulk'" in toolbar
    assert "renderSelectedSceneTransitionPicker(!hasSelectedSubtitleSections)" in toolbar
    assert "disabled={disabled}" in STD_PAGE
    assert "cursor-not-allowed" in STD_PAGE
    assert "'selected-scenes-bulk'" not in layer_header
    assert "renderSelectedSceneTransitionPicker()" not in layer_header


def test_transition_name_is_not_repeated_below_the_scene_time():
    scene_time = STD_PAGE.split("{group.start_time}s<br />~{group.end_time}s", 1)[1].split("</div>\n                                                        <div className=\"flex-1 min-w-0\">", 1)[0]

    assert "화면전환효과" not in scene_time
    assert "<span className=\"block font-mono text-[8px] text-violet-300\">전환</span>" not in STD_PAGE
