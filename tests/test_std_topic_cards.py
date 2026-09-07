from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STD_PAGE = (ROOT / "auth-web" / "app" / "std" / "page.tsx").read_text(encoding="utf-8")


def test_topic_cards_show_a_single_title_without_an_extra_start_button():
    topic_cards = STD_PAGE.split("{/* 3. AI 추천 주제 큐 카드 그리드", 1)[1].split("{/* 4. 주제 상세 확인", 1)[0]
    assert "{topic.generated_title || topic.topic}" in topic_cards
    assert "주제 상세 확인 & 작업 시작" not in topic_cards
    assert '<p className="text-[11px] text-gray-400 line-clamp-2 leading-relaxed">' not in topic_cards
