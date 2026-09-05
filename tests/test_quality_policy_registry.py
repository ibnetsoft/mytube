from pathlib import Path

from services.generation_quality_gate import validate_generation_package
from services.quality_policy import DEFAULT_QUALITY_POLICY, normalize_quality_policy
from tests.test_generation_quality_gate import _valid_payload


ROOT = Path(__file__).resolve().parents[1]


def test_policy_normalization_keeps_non_disableable_guards_enabled():
    policy = normalize_quality_policy({
        "script": {"min_quality_score": 91, "prohibit_fallback": False},
        "delivery": {"require_all_prior_stages": False, "require_quality_report_pass": False},
    })

    assert policy["script"]["min_quality_score"] == 91
    assert policy["script"]["prohibit_fallback"] is True
    assert policy["delivery"]["require_all_prior_stages"] is True
    assert policy["delivery"]["require_quality_report_pass"] is True


def test_generation_gate_uses_policy_thresholds():
    payload = _valid_payload()
    policy = normalize_quality_policy(DEFAULT_QUALITY_POLICY)
    policy["script"]["min_quality_score"] = 90

    errors = validate_generation_package(payload, category="옛날이야기", quality_policy=policy)

    assert any("score=86" in error for error in errors)


def test_generation_gate_uses_paragraph_opener_limit():
    payload = _valid_payload()
    paragraph = "그런데 말이야, 마을 사람들은 닫힌 문 안에서 오래된 약속의 진실을 기다리고 있었다."
    payload["script"] = "\n\n".join([paragraph] * 4) + "\n\n" + payload["script"]
    policy = normalize_quality_policy(DEFAULT_QUALITY_POLICY)
    policy["script"]["max_repeated_paragraph_opener"] = 3

    errors = validate_generation_package(payload, category="옛날이야기", quality_policy=policy)

    assert any("paragraph opener repetition" in error and "max=3" in error for error in errors)


def test_worker_policy_route_and_dashboard_are_wired():
    route = (ROOT / "auth-web" / "app" / "api" / "worker-central" / "quality-policy" / "route.ts").read_text(encoding="utf-8")
    dashboard = (ROOT / "worker" / "dashboard_app.py").read_text(encoding="utf-8")
    worker = (ROOT / "worker" / "hermes_worker.py").read_text(encoding="utf-8")

    assert "authenticateWorkerRequest" in route
    assert "expected_version" in route
    assert "/api/quality-policy" in dashboard
    assert "quality_policy_snapshot" in worker
