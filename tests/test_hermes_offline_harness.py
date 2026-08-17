from services.hermes_offline_harness import (
    TARGET_CATEGORIES,
    assert_offline_harness_passes,
    run_offline_harness,
)


def test_hermes_offline_harness_passes_without_api_calls():
    report = run_offline_harness()

    assert report["status"] == "pass", report
    assert report["api_calls"] == 0
    assert report["failed_count"] == 0


def test_hermes_offline_harness_covers_all_generation_categories():
    report = run_offline_harness()

    assert set(report["categories"]) == set(TARGET_CATEGORIES)
    for category in TARGET_CATEGORIES:
        assert any(
            check["category"] == category and check["name"].endswith("complete package smoke")
            for check in report["checks"]
        )


def test_hermes_offline_harness_assertion_helper():
    assert_offline_harness_passes()
