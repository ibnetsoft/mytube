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
    assert "const disabledByProfile = !allowedProcesses.has(name) || normalizedStatus === 'disabled';" in source
    assert "const hermesStartDisabled = disabledByProfile || hermesBusy;" in source
    assert "const hermesStopDisabled = disabledByProfile || !hermesBusy || normalizedStatus === 'stopped';" in source


def test_pipeline_error_summary_is_rendered_inside_details():
    source = (ROOT / "worker" / "dashboard_app.py").read_text(encoding="utf-8")

    details_index = source.index("📌 포함된 세부 Job 및 로그")
    error_index = source.index("${errorSummary}", details_index)
    subjobs_index = source.index("${subjobsHtml}", details_index)

    assert details_index < error_index < subjobs_index


def test_benchmark_failure_does_not_override_downstream_generation_progress():
    source = (ROOT / "worker" / "dashboard_app.py").read_text(encoding="utf-8")

    assert "function hasCompletedHermesJobType(jobs, jobType)" in source
    assert "const completedWebResearch = hasCompletedHermesJobType(g.jobs, 'web_research');" in source
    assert "const completedPlan = hasCompletedHermesJobType(g.jobs, 'script_plan_generate');" in source
    assert "const completedScript = hasCompletedHermesJobType(g.jobs, 'script_generate');" in source
    assert "const completedPublishMetadata = hasCompletedHermesJobType(g.jobs, 'publish_metadata_generate');" in source
    assert "const completedGenerationAfterBenchmark = completedWebResearch || completedPlan || completedScript || completedPublishMetadata;" in source
    assert "step.key === 'research' && completedDownstream" not in source
    assert "} else if (completedPublishMetadata) {" in source
    assert "completedTypes.add('topic_benchmark_analyze');" in source


def test_cached_benchmark_still_submits_real_web_research_job():
    source = (ROOT / "worker" / "hermes_autopilot.py").read_text(encoding="utf-8")

    assert "Cached benchmark data is only a seed; submitting a real web_research job before planning." in source
    assert "cached_benchmark_sources" not in source
    assert "job_type=\"web_research\"" in source


def test_hermes_title_generation_has_timeout_and_fallback():
    source = (ROOT / "worker" / "hermes_autopilot.py").read_text(encoding="utf-8")

    assert "TITLE_GENERATION_TIMEOUT_SECONDS = 90.0" in source
    assert "asyncio.wait_for(" in source
    assert "asyncio.to_thread(" in source
    assert "timeout=TITLE_GENERATION_TIMEOUT_SECONDS" in source
    assert "Title generation timed out/failed; using category fallback title" in source
    assert "category_fallback_after_title_generation_error" in source


def test_server_restart_waits_until_manager_is_alive_before_reload():
    source = (ROOT / "worker" / "dashboard_app.py").read_text(encoding="utf-8")

    assert "보통 10~20초 정도 걸리며" in source
    assert "let count = 45;" in source
    assert "const reloadAfterRestart = () => {" in source
    assert "url.searchParams.set('restarted', String(Date.now()));" in source
    assert "window.location.replace(url.toString());" in source
    assert "const controller = new AbortController();" in source
    assert "setTimeout(() => controller.abort(), 2500)" in source
    assert "restart_probe=${Date.now()}" in source
    assert "data?.manager_alive" in source
    assert "준비되면 자동 새로고침됩니다" in source


def test_server_restart_helper_matches_project_dashboard_processes():
    source = (ROOT / "worker" / "dashboard_app.py").read_text(encoding="utf-8")

    assert "'dashboard_app:app'," in source
    assert "project_root = worker_dir.parent" in source
    assert "def ps_utf8(value: str)" in source
    assert "$projectRoot" in source
    assert "$currentManagerPid" in source
    assert "$_.ProcessId -eq $currentManagerPid" in source
    assert "restart_profile = worker_config.WORKER_PROFILE" in source
    assert "--role manager --profile {restart_profile}" in source
    assert "'air_worker_entry.py'," in source
    assert "server_lifecycle.log" in source
    assert "taskkill.exe' -ArgumentList @('/PID', [string]$proc.ProcessId, '/T', '/F') -WindowStyle Hidden" in source
    assert "-WindowStyle Hidden -Wait" not in source
