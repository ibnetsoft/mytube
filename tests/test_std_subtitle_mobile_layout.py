from pathlib import Path


STD_PAGE = Path("auth-web/app/std/page.tsx").read_text(encoding="utf-8")


def test_subtitle_workspace_uses_page_scroll_on_mobile_and_keeps_desktop_split_view():
    assert "min-h-[100dvh]" in STD_PAGE
    assert "overflow-y-auto md:overflow-hidden" in STD_PAGE
    assert "h-auto min-h-0 overflow-visible md:h-full md:overflow-hidden" in STD_PAGE
    assert "flex-none min-h-0 overflow-visible lg:grid-cols-[minmax(0,1fr)_430px]" in STD_PAGE


def test_subtitle_cards_and_preview_do_not_clip_on_mobile():
    assert "overflow-visible lg:overflow-hidden" in STD_PAGE
    assert "flex-1 overflow-visible p-2 space-y-2 lg:overflow-y-auto" in STD_PAGE
    assert "w-24 h-[54px] sm:w-40 sm:h-[90px]" in STD_PAGE
    assert "max-h-none overflow-visible lg:max-h-full lg:overflow-y-auto" in STD_PAGE
