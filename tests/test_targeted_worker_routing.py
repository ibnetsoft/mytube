from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_hermes_claim_rpc_respects_target_worker_id():
    sql = read("migrations/air_0242_targeted_hermes_worker_routing.sql")

    assert "ADD COLUMN IF NOT EXISTS target_worker_id TEXT" in sql
    assert "target_worker_id IS NULL OR target_worker_id = p_worker_id" in sql
    assert "CASE WHEN target_worker_id = p_worker_id THEN 0 ELSE 1 END" in sql


def test_topic_completion_records_generating_worker_and_chains_target():
    source = read("auth-web/app/api/internal/worker/jobs/[jobId]/complete/route.ts")

    assert "generated_by_worker_id = job.worker_id" in source
    assert "generated_by_worker_instance_id = job.worker_instance_id || null" in source
    assert "generated_by_worker_job_id = jobId" in source
    assert "target_worker_id: job.worker_id || job.target_worker_id || null" in source


def test_repair_route_targets_original_generating_worker():
    source = read("auth-web/app/api/admin/topics-queue/repair/route.ts")

    assert "generated_by_worker_id" in source
    assert "const targetWorkerId =" in source
    assert "target_worker_id: targetWorkerId || null" in source
    assert "original_generated_by_worker_id: targetWorkerId || null" in source


def test_desktop_worker_direct_supabase_writes_include_worker_identity():
    autopilot = read("worker/hermes_autopilot.py")
    hermes_worker = read("worker/hermes_worker.py")

    assert "generated_by_worker_id" in autopilot
    assert "WORKER_ID" in autopilot
    assert "generated_by_worker_id" in hermes_worker
    assert "WORKER_INSTANCE_ID" in hermes_worker


def test_central_hermes_chain_preserves_scoped_generation_controls():
    source = read("auth-web/app/api/worker-central/jobs/[jobId]/complete/route.ts")

    assert "ai_model_override: jobPayload.ai_model_override" in source
    assert "defer_ready_until_quality_gate: Boolean(jobPayload.defer_ready_until_quality_gate)" in source
    assert "existing_result_replacement: Boolean(jobPayload.existing_result_replacement)" in source
