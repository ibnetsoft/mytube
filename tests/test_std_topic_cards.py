from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STD_PAGE = (ROOT / "auth-web" / "app" / "std" / "page.tsx").read_text(encoding="utf-8")


def test_topic_cards_show_a_single_title_without_an_extra_start_button():
    topic_cards = STD_PAGE.split("{/* 3. AI 추천 주제 큐 카드 그리드", 1)[1].split("{/* 4. 주제 상세 확인", 1)[0]
    assert "{topic.generated_title || topic.topic}" in topic_cards
    assert "주제 상세 확인 & 작업 시작" not in topic_cards
    assert '<p className="text-[11px] text-gray-400 line-clamp-2 leading-relaxed">' not in topic_cards
    assert "xl:grid-cols-5" in topic_cards
    assert "{formatTopicPayout(topic)}" not in topic_cards
    assert "{topic.assigned_duration_minutes || 15}분 영상" not in topic_cards
    assert "{topic.scene_count || 53} Scenes" not in topic_cards
