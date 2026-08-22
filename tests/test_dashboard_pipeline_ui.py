import pathlib


ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_pipeline_cards_keep_details_open_across_refreshes():
    source = (ROOT / "worker" / "dashboard_app.py").read_text(encoding="utf-8")

    assert "const openPipelineDetails = new Set();" in source
    assert "id: 'pipe_' + stableHash(groupKey)" in source
    assert "id: 'bench_' + stableHash(batchKey)" in source
    assert "openPipelineDetails.add(domId)" in source
    assert "openPipelineDetails.delete(domId)" in source


def test_failed_pipeline_explains_error_and_can_resume():
    source = (ROOT / "worker" / "dashboard_app.py").read_text(encoding="utf-8")

    assert "const failedJob = latestFailedJob(g.jobs, completedTypes);" in source
    assert "const matchingJob = [...g.jobs].reverse().find(j => j.job_type === step.type);" in source
    assert "if (completedCount === totalSteps) overallStatus = 'COMPLETED';" in source
    assert "if (completedCount === totalSteps && !hasFailed)" not in source
    assert "const canResume = !hasRunning && completedCount > 0 && overallStatus !== 'COMPLETED';" in source
    assert "pipeline-error-summary" in source
    assert "오류 이유:" in source
    assert "pipeline-header-resume" in source


def test_hermes_process_card_disables_start_while_busy():
    source = (ROOT / "worker" / "dashboard_app.py").read_text(encoding="utf-8")

    assert "const processBusyStatuses = ['running', 'starting', 'busy', 'claimed', 'preparing', 'rendering', 'uploading'];" in source
    assert "const hasCurrentJob = Boolean(info.current_job || currentJobId);" in source
    assert "const hermesStartDisabled = hermesBusy;" in source
    assert "const hermesStopDisabled = !hermesBusy || normalizedStatus === 'stopped';" in source


def test_pipeline_error_summary_is_rendered_inside_details():
    source = (ROOT / "worker" / "dashboard_app.py").read_text(encoding="utf-8")

    details_index = source.index("📌 포함된 세부 Job 및 로그")
    error_index = source.index("${errorSummary}", details_index)
    subjobs_index = source.index("${subjobsHtml}", details_index)

    assert details_index < error_index < subjobs_index


def test_benchmark_failure_does_not_override_completed_downstream_pipeline():
    source = (ROOT / "worker" / "dashboard_app.py").read_text(encoding="utf-8")

    assert "function hasCompletedDownstreamHermesStep(jobs)" in source
    assert "['script_plan_generate', 'script_generate', 'publish_metadata_generate'].includes(type)" in source
    assert "const completedDownstream = hasCompletedDownstreamHermesStep(g.jobs);" in source
    assert "step.key === 'research' && completedDownstream" in source
    assert "completedTypes.add('topic_benchmark_analyze');" in source
