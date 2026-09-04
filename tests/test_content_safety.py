from services.content_safety import finance_content_matches


def test_finance_detection_does_not_join_english_words_across_spaces():
    assert "etf" not in finance_content_matches("gentle tilt from the window")


def test_finance_detection_still_detects_a_real_english_term():
    assert "etf" in finance_content_matches("The character sells an ETF fund.")


def test_story_bond_is_not_misclassified_as_finance():
    assert "bond" not in finance_content_matches("Their family bond survived the storm.")
