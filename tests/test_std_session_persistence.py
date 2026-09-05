from pathlib import Path


LOGIN_ROUTE = Path("auth-web/app/api/std/login/route.ts").read_text(encoding="utf-8")
STD_WEB = Path("auth-web/lib/stdWeb.ts").read_text(encoding="utf-8")


def test_password_login_returns_long_lived_server_signed_session():
    supabase_login = LOGIN_ROUTE.split(
        "if (!authError && authData?.session?.access_token", 1
    )[1].split("// Allow arbitrary login", 1)[0]

    assert "session_token: signDesktopSessionToken(normalizedEmail)" in supabase_login
    assert "session_token: authData.session.access_token" not in supabase_login


def test_invalid_or_expired_bearer_is_not_mapped_to_worker_identity():
    fallback = STD_WEB.split("if (!profile) {", 2)[2].split(
        "return {\n        ok: true", 1
    )[0]

    assert "if (!desktopEmail)" in fallback
    assert "Session expired. Please sign in again." in fallback
    assert "worker@airstudio.io" not in fallback
