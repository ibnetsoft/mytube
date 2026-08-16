import pathlib
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKER = ROOT / "worker"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(WORKER) not in sys.path:
    sys.path.insert(0, str(WORKER))

from worker import hermes_autopilot
from worker import hermes_worker


TARGET_CATEGORIES = ["경제", "노후금융", "옛날이야기", "황혼19금", "탈북사연"]


def test_worker_start_categories_are_normalized_for_dashboard_start_path():
    manager = hermes_autopilot.HermesAutopilotManager()

    assert manager._normalize_active_categories(TARGET_CATEGORIES) == TARGET_CATEGORIES


def test_target_categories_have_title_styles_and_safe_fallbacks():
    manager = hermes_autopilot.HermesAutopilotManager()

    for category in TARGET_CATEGORIES:
        style = manager._category_title_style(category)
        fallback = manager._category_fallback_title(category)

        assert style
        assert fallback
        assert manager._is_usable_title_candidate(fallback, category)


def test_target_categories_have_rss_relevance_terms():
    for category in TARGET_CATEGORIES:
        terms = hermes_worker.RSS_RELEVANCE_TERMS_BY_CATEGORY.get(category)

        assert terms, f"{category} must have RSS relevance terms"
        assert category in terms


def test_economy_and_twilight_have_local_rss_channel_pools():
    manager = hermes_autopilot.HermesAutopilotManager()

    assert len(manager._load_local_benchmark_channels("경제")) >= 8
    assert len(manager._load_local_benchmark_channels("황혼19금")) >= 8
