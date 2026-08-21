import argparse
import html
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKER_DIR = ROOT / "worker"
if str(WORKER_DIR) not in sys.path:
    sys.path.insert(0, str(WORKER_DIR))

from worker_config import SFX_CATALOG_PATH, SFX_LIBRARY_DIR  # noqa: E402


MIXKIT_TAGS = {
    "whoosh": {"category": "transition", "default_volume_db": -16.0},
    "impact": {"category": "impact", "default_volume_db": -14.0},
    "door": {"category": "doors", "default_volume_db": -15.0},
    "rain": {"category": "ambience", "default_volume_db": -24.0},
    "footsteps": {"category": "footsteps", "default_volume_db": -18.0},
    "glass": {"category": "glass", "default_volume_db": -13.0},
    "keyboard": {"category": "technology", "default_volume_db": -20.0},
    "pop": {"category": "ui", "default_volume_db": -18.0},
}

USER_AGENT = "AIRWorkerSFXSetup/1.0 (+https://mixkit.co/free-sound-effects/)"


def slugify(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    return value or "sfx"


def fetch_text(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as res:
        return res.read().decode("utf-8", errors="replace")


def download_file(url: str, path: Path) -> int:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as res:
        data = res.read()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return len(data)


def parse_mixkit_items(tag: str, page_html: str) -> list[dict]:
    items = []
    pattern = re.compile(
        r'data-audio-player-preview-url-value="(?P<url>https://assets\.mixkit\.co/active_storage/sfx/(?P<id>\d+)/[^"]+\.mp3)"'
        r".*?<h2 class=\"item-grid-card__title\">\s*(?P<title>.*?)\s*</h2>",
        re.DOTALL,
    )
    for match in pattern.finditer(page_html):
        title = html.unescape(re.sub(r"\s+", " ", match.group("title")).strip())
        items.append(
            {
                "source_id": match.group("id"),
                "title": title,
                "preview_url": match.group("url"),
                "source_page": f"https://mixkit.co/free-sound-effects/{tag}/",
            }
        )
    return items


def build_catalog(items: list[dict]) -> dict:
    return {
        "version": 1,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "library_dir": str(SFX_LIBRARY_DIR),
        "license_notes": [
            "Mixkit sound effects are listed by Mixkit as free to use in personal and commercial video/audio projects without attribution.",
            "Keep source_url/source_page fields with each item so licensing can be audited later.",
            "Pixabay files can be added manually, but automated Pixabay scraping is not used here because the site may require browser verification.",
        ],
        "items": items,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Download a small starter SFX library for AIR Worker renders.")
    parser.add_argument("--per-tag", type=int, default=2, help="Number of Mixkit SFX files to download per tag.")
    parser.add_argument("--force", action="store_true", help="Re-download files that already exist.")
    args = parser.parse_args()

    all_items = []
    SFX_LIBRARY_DIR.mkdir(parents=True, exist_ok=True)

    for tag, tag_meta in MIXKIT_TAGS.items():
        page_url = f"https://mixkit.co/free-sound-effects/{tag}/"
        print(f"Fetching {page_url}")
        try:
            page = fetch_text(page_url)
            parsed = parse_mixkit_items(tag, page)
        except Exception as exc:
            print(f"  skipped: {exc}")
            continue

        for item in parsed[: max(0, args.per_tag)]:
            title_slug = slugify(item["title"])
            key = f"mixkit_{tag}_{item['source_id']}_{title_slug}"
            filename = f"{key}.mp3"
            rel_path = Path(tag_meta["category"]) / filename
            dest = SFX_LIBRARY_DIR / rel_path
            if args.force or not dest.exists():
                size = download_file(item["preview_url"], dest)
                print(f"  downloaded {rel_path} ({size} bytes)")
            else:
                print(f"  exists {rel_path}")
            all_items.append(
                {
                    "key": key,
                    "title": item["title"],
                    "provider": "mixkit",
                    "source_id": item["source_id"],
                    "source_url": item["preview_url"],
                    "source_page": item["source_page"],
                    "license": "Mixkit Sound Effects Free License",
                    "license_url": "https://mixkit.co/license/",
                    "category": tag_meta["category"],
                    "tags": sorted({tag, tag_meta["category"], *title_slug.split("-")}),
                    "relative_path": rel_path.as_posix(),
                    "default_volume_db": tag_meta["default_volume_db"],
                }
            )

    catalog = build_catalog(all_items)
    SFX_CATALOG_PATH.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote catalog: {SFX_CATALOG_PATH}")
    print(f"Downloaded/indexed {len(all_items)} SFX items under {SFX_LIBRARY_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
