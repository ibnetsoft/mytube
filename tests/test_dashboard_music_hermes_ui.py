import pathlib


ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_dashboard_exposes_music_hermes_pipeline_controls():
    source = (ROOT / "auth-web" / "components" / "DashboardContent.tsx").read_text(encoding="utf-8")

    assert "Music Hermes" in source
    assert "handleMusicHermesSubmit" in source
    assert "/api/admin/music-hermes" in source
    assert "Thailand Music Pipeline 큐 등록" in source
    assert "musicHermesJobs.prompt_pack_job" in source
    assert "Trend만 큐 등록" in source
    assert "Prompt만 큐 등록" in source
    assert "Trend Result" in source
    assert "Prompt Pack Result" in source
    assert "태국 유저 큐로 보내기" in source
    assert "전체 트랙 접기" in source
    assert "setMusicHermesTrackListExpanded" in source
    assert "트랙 목록 복사" in source
    assert "JSON 내보내기" in source
    assert "dispatchMusicPromptPackToThaiQueue" in source
