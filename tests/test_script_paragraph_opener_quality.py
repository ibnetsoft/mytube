from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
WORKER_DIR = ROOT / "worker"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(WORKER_DIR) not in sys.path:
    sys.path.insert(0, str(WORKER_DIR))

import hermes_worker  # noqa: E402


def test_detects_variants_as_one_paragraph_opener_family():
    script = "\n\n".join(
        [
            "그런데 말이야, 첫 번째 단서가 나타났습니다.",
            "그런데 말입니다. 두 번째 문이 열렸습니다.",
            "그런데요, 세 번째 증언은 달랐습니다.",
            "그런데 마지막 기록은 비어 있었습니다.",
        ]
    )

    findings = hermes_worker._detect_repeated_paragraph_openers(script)

    assert findings == [
        {
            "opener": "그런데",
            "count": 4,
            "max_allowed": 2,
            "excess": 2,
            "example": "그런데 말이야, 첫 번째 단서가 나타났습니다.",
        }
    ]


def test_cleanup_keeps_first_two_openers_and_preserves_cues_and_content():
    script = "\n\n".join(
        [
            "(차분하게) 그런데 말이야, 첫 번째 단서가 나타났습니다.",
            "그런데 말입니다. 두 번째 문이 열렸습니다.",
            "(긴장하며) 그런데요, 세 번째 증언은 달랐습니다.",
            "그런데 마지막 기록은 비어 있었습니다.",
        ]
    )

    cleaned = hermes_worker._reduce_repeated_paragraph_openers(script)

    assert cleaned.count("그런데") == 2
    assert "(긴장하며) 세 번째 증언은 달랐습니다." in cleaned
    assert "마지막 기록은 비어 있었습니다." in cleaned
    assert hermes_worker._detect_repeated_paragraph_openers(cleaned) == []


def test_quality_report_forces_revision_when_opener_limit_is_exceeded():
    script = "\n\n".join(
        [
            "글쎄, 첫 장면이었습니다.",
            "글쎄요, 다음 날도 같았습니다.",
            "글쎄, 마지막 선택은 달랐습니다.",
        ]
    )
    report = {"score": 92, "verdict": "pass", "critical_issues": [], "revision_notes": []}

    checked = hermes_worker._apply_paragraph_opener_quality(report, script)

    assert checked["verdict"] == "revise"
    assert checked["score"] == 68
    assert checked["paragraph_opener_repetitions"][0]["opener"] == "글쎄"
    assert hermes_worker._script_needs_revision(checked) is True


def test_normal_concrete_paragraph_openers_are_not_flagged():
    script = "\n\n".join(
        [
            "그날 새벽, 문이 열렸습니다.",
            "여인은 우물가에 멈춰 섰습니다.",
            "바람이 등잔불을 흔들었습니다.",
            "그는 아무 말 없이 편지를 접었습니다.",
        ]
    )

    assert hermes_worker._detect_repeated_paragraph_openers(script) == []
