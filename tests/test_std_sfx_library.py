from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_sfx_library_uses_the_shared_drive_folder_and_search_fallback():
    source = (ROOT / 'auth-web' / 'app' / 'api' / 'std' / 'sfx-library' / 'route.ts').read_text(encoding='utf-8')

    assert '1xu6GBDh8F8iF5wsSiggzeM6YG2iB-Utq' in source
    assert "process.env.GOOGLE_DRIVE_SFX_LIBRARY_FOLDER_ID" in source
    assert "corpora: 'user'" in source
    assert "includeItemsFromAllDrives: 'true'" in source


def test_sfx_library_request_includes_the_current_std_session_token():
    source = (ROOT / 'auth-web' / 'app' / 'std' / 'page.tsx').read_text(encoding='utf-8')

    assert "fetch('/api/std/sfx-library', { headers })" in source
    assert "Authorization: `Bearer ${token}`" in source
    assert "payload?.error || '효과음 라이브러리를 불러오지 못했습니다.'" in source
    assert '공용 SFX Drive 라이브러리에서 미리듣기 후 배경음 또는 현재 자막 효과음으로 바로 적용할 수 있습니다.' not in source
