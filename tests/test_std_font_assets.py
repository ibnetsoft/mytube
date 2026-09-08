from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GLOBAL_CSS = (ROOT / "auth-web" / "app" / "globals.css").read_text(encoding="utf-8")
FONT_DIR = ROOT / "auth-web" / "public" / "fonts"


def test_subtitle_fonts_are_served_locally_without_a_noonnu_cdn_request():
    assert "jsdelivr.net/gh/projectnoonnu" not in GLOBAL_CSS
    assert "font-family: 'Gungsuh'" not in GLOBAL_CSS

    expected_files = {
        "CookieRun-Regular.woff",
        "GmarketSansBold.woff",
        "TmonMonsori.woff",
        "JalnanOTF00.woff",
        "Pretendard-Bold.woff",
        "NanumSquareExtraBold.woff2",
        "BinggraeMelona-Bold.woff",
        "netmarbleB.woff",
        "Chosunilbo_myungjo.woff",
        "MapoFlowerIslandA.woff",
        "S-CoreDream-6Bold.woff",
    }
    assert {path.name for path in FONT_DIR.iterdir() if path.is_file()} == expected_files
    for file_name in expected_files:
        assert f"/fonts/{file_name}" in GLOBAL_CSS
