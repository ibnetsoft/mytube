from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STD_PAGE = (ROOT / "auth-web" / "app" / "std" / "page.tsx").read_text(encoding="utf-8")


def test_project_submit_has_visible_pending_and_completion_feedback():
    assert "const [submittingProjectId, setSubmittingProjectId] = useState('')" in STD_PAGE
    assert "setSubmittingProjectId(String(targetProject.project.id))" in STD_PAGE
    assert "제출 준비 중입니다. 생성 이미지를 Google Drive 보관본으로 확인하고 렌더 큐에 등록합니다" in STD_PAGE
    assert "await loadStdData(token, { showLoading: false })" in STD_PAGE
    assert "프로젝트가 원격 렌더 큐에 등록되었습니다." in STD_PAGE
    assert "submittingProjectId === String(p.id)" in STD_PAGE
