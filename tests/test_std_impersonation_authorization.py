from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_std_impersonation_requires_authenticated_admin_before_switching_user():
    source = (ROOT / 'auth-web' / 'lib' / 'stdWeb.ts').read_text(encoding='utf-8')

    assert "const SUPER_ADMIN_EMAIL = 'ejsh0519@naver.com'" in source
    assert 'if (!token) return { ok: false, response: jsonError(\'Authentication required\', 401) }' in source
    assert 'if (!canImpersonate(requester))' in source
    assert "jsonError('Admin access required for impersonation', 403)" in source
    assert source.index("if (!token) return") < source.index('if (!canImpersonate(requester))')


def test_std_impersonation_page_uses_a_real_session_token():
    source = (ROOT / 'auth-web' / 'app' / 'std' / 'page.tsx').read_text(encoding='utf-8')

    assert "await supabase.auth.getSession()" in source
    assert 'const impToken = `std_impersonate_${Date.now()}`' not in source
    assert "Authorization: `Bearer ${accessToken}`" in source
