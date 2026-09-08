from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MUSIC_MISSIONS_ROUTE = (ROOT / "auth-web" / "app" / "api" / "std" / "music-missions" / "route.ts").read_text(encoding="utf-8")
FONTS_ROUTE = (ROOT / "auth-web" / "app" / "api" / "std" / "fonts" / "route.ts").read_text(encoding="utf-8")


def test_music_missions_does_not_depend_on_a_postgrest_embedded_relation():
    assert "const MUSIC_TASK_FIELDS" in MUSIC_MISSIONS_ROUTE
    assert ".select(MUSIC_TASK_FIELDS)" in MUSIC_MISSIONS_ROUTE
    assert "isUnavailableMusicMissionSchema" in MUSIC_MISSIONS_ROUTE
    assert "return NextResponse.json({ success: true, tasks: [] })" in MUSIC_MISSIONS_ROUTE
    assert ".from('music_submissions')" in MUSIC_MISSIONS_ROUTE


def test_std_fonts_endpoint_exists_for_legacy_font_clients():
    assert "export function GET()" in FONTS_ROUTE
    assert "success: true, fonts: subtitleFonts" in FONTS_ROUTE
