"""
AIR-0128 Backfill Script: Populate translation columns for existing topics_queue rows.

PURPOSE
-------
After the migration (migrations/air_0128_topics_queue_translation_columns.sql) has been
applied to Supabase, run this script to translate existing pending/assigned topics that
have NULL translation columns.

PREREQUISITES
-------------
1. Apply the migration first:
   migrations/air_0128_topics_queue_translation_columns.sql
2. Ensure .env (or environment variables) contain:
   - NEXT_PUBLIC_SUPABASE_URL
   - SUPABASE_SERVICE_ROLE_KEY
   - GEMINI_API_KEY  (or ANTHROPIC_API_KEY for Claude)

USAGE
-----
    python scripts/backfill_topic_translations.py [--lang vi] [--batch 50] [--dry-run]

Options:
    --lang      Target language code: vi | en | th (default: vi)
    --batch     Topics per translation batch (default: 50)
    --dry-run   Preview which topics would be translated without saving

SAFETY
------
- Only rows where topic_{lang} IS NULL are processed (idempotent re-runs are safe).
- Fetches at most 500 rows per run; re-run to process more.
- Uses Google Translate HTTP fallback first (free), then Gemini as fallback.
"""

import argparse
import asyncio
import html
import json
import os
import sys
import time
import urllib.parse

import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SUPABASE_URL = os.getenv("NEXT_PUBLIC_SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

SUPPORTED_LANGS = {"vi": "Vietnamese", "en": "English", "th": "Thai"}
MAX_ROWS = 500


def _headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }


# ---------------------------------------------------------------------------
# Google Translate HTTP fallback (individual text)
# ---------------------------------------------------------------------------
def _google_translate(text: str, lang: str) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    try:
        q = urllib.parse.quote(text)
        url = (
            "https://translate.googleapis.com/translate_a/single"
            f"?client=gtx&sl=ko&tl={lang}&dt=t&q={q}"
        )
        r = requests.get(
            url, timeout=6, verify=False,
            proxies={"http": None, "https": None},
            headers={"User-Agent": "Mozilla/5.0"},
        )
        if r.status_code != 200:
            return ""
        payload = r.json()
        translated = "".join(
            str(chunk[0] or "")
            for chunk in (payload[0] or [])
            if isinstance(chunk, list) and chunk
        ).strip()
        return html.unescape(translated)
    except Exception as e:
        print(f"  [Google] error: {e}")
        return ""


# ---------------------------------------------------------------------------
# Gemini batch translation fallback
# ---------------------------------------------------------------------------
def _gemini_batch_translate(items: list[dict], lang: str, lang_name: str) -> dict:
    if not GEMINI_API_KEY or not items:
        return {}
    prompt = (
        f"You are translating Korean UI content into {lang_name}.\n"
        f"Return ONLY valid JSON array.\n"
        f"Translate each object's topic and category_name fields into natural {lang_name}.\n"
        f"Keep the same id. If category_name is empty, keep it empty.\n\n"
        f"Input JSON:\n{json.dumps(items, ensure_ascii=False)}\n\n"
        f"Output format:\n"
        f'[{{"id":"...","topic_translated":"...","category_name_translated":"..."}}]'
    )
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
    )
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json"},
    }
    try:
        r = requests.post(url, json=body, timeout=30, verify=False, proxies={"http": None, "https": None})
        if r.status_code != 200:
            print(f"  [Gemini] HTTP {r.status_code}")
            return {}
        raw = r.json()
        text = raw["candidates"][0]["content"]["parts"][0]["text"]
        rows = json.loads(text)
        result = {}
        for row in (rows if isinstance(rows, list) else []):
            rid = str((row or {}).get("id") or "").strip()
            if rid:
                result[rid] = {
                    f"topic_{lang}": str((row or {}).get("topic_translated") or "").strip(),
                    f"category_name_{lang}": str((row or {}).get("category_name_translated") or "").strip(),
                }
        return result
    except Exception as e:
        print(f"  [Gemini] error: {e}")
        return {}


# ---------------------------------------------------------------------------
# Translate a batch
# ---------------------------------------------------------------------------
def translate_batch(items: list[dict], lang: str, lang_name: str) -> dict:
    """Translate a list of {id, topic, category_name} dicts.
    Returns {id: {topic_{lang}: ..., category_name_{lang}: ...}}.
    """
    result = {}
    # Google translate per-item (free, fast)
    for item in items:
        rid = str(item.get("id") or "").strip()
        if not rid:
            continue
        topic_t = _google_translate(item.get("topic") or "", lang)
        cat_t = _google_translate(item.get("category_name") or "", lang)
        if topic_t:
            result[rid] = {f"topic_{lang}": topic_t, f"category_name_{lang}": cat_t}
        time.sleep(0.05)  # Stay within free-tier rate limit

    # Gemini fallback for items that Google missed
    missing = [i for i in items if not result.get(str(i.get("id") or ""), {}).get(f"topic_{lang}")]
    if missing:
        gemini_result = _gemini_batch_translate(missing, lang, lang_name)
        result.update(gemini_result)

    return result


# ---------------------------------------------------------------------------
# Supabase helpers
# ---------------------------------------------------------------------------
def fetch_untranslated(lang: str, limit: int) -> list[dict]:
    """Fetch pending/assigned topics where topic_{lang} is NULL."""
    url = (
        f"{SUPABASE_URL}/rest/v1/topics_queue"
        f"?topic_{lang}=is.null"
        f"&status=in.(pending,assigned)"
        f"&select=id,topic,categories(name)"
        f"&order=created_at.desc"
        f"&limit={limit}"
    )
    r = requests.get(url, headers=_headers(), timeout=10, verify=False, proxies={"http": None, "https": None})
    if r.status_code != 200:
        print(f"[Backfill] Supabase fetch failed ({r.status_code}): {r.text[:200]}")
        sys.exit(1)
    rows = r.json() or []
    return [
        {
            "id": str(row["id"]),
            "topic": str(row.get("topic") or ""),
            "category_name": str((row.get("categories") or {}).get("name") or ""),
        }
        for row in rows
        if row.get("topic")
    ]


def save_translation(topic_id: str, data: dict) -> bool:
    url = f"{SUPABASE_URL}/rest/v1/topics_queue?id=eq.{topic_id}"
    save_headers = {**_headers(), "Prefer": "return=minimal"}
    r = requests.patch(url, json=data, headers=save_headers, timeout=5, verify=False, proxies={"http": None, "https": None})
    return r.status_code in (200, 204)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="AIR-0128 topic translation backfill")
    parser.add_argument("--lang", default="vi", choices=list(SUPPORTED_LANGS))
    parser.add_argument("--batch", type=int, default=50)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    lang = args.lang
    lang_name = SUPPORTED_LANGS[lang]
    batch_size = min(args.batch, 100)

    if not SUPABASE_URL or not SUPABASE_KEY:
        print("[Backfill] ERROR: NEXT_PUBLIC_SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set.")
        sys.exit(1)

    print(f"[Backfill] Language: {lang_name} ({lang}), batch: {batch_size}, dry-run: {args.dry_run}")

    rows = fetch_untranslated(lang, MAX_ROWS)
    print(f"[Backfill] {len(rows)} rows need translation.")
    if not rows:
        print("[Backfill] Nothing to do.")
        return

    total_saved = 0
    for start in range(0, len(rows), batch_size):
        chunk = rows[start:start + batch_size]
        print(f"[Backfill] Translating rows {start + 1}–{start + len(chunk)}...")
        translations = translate_batch(chunk, lang, lang_name)
        for item in chunk:
            rid = item["id"]
            data = translations.get(rid)
            if not data or not data.get(f"topic_{lang}"):
                print(f"  SKIP  id={rid} (translation empty)")
                continue
            if args.dry_run:
                print(f"  DRY   id={rid}  {data[f'topic_{lang}'][:60]}")
            else:
                ok = save_translation(rid, data)
                status = "OK" if ok else "FAIL"
                print(f"  {status}   id={rid}  {data[f'topic_{lang}'][:60]}")
                if ok:
                    total_saved += 1
        time.sleep(0.5)

    if not args.dry_run:
        print(f"[Backfill] Done. {total_saved}/{len(rows)} rows saved.")
    else:
        print(f"[Backfill] Dry-run complete. {len(rows)} rows would be processed.")


if __name__ == "__main__":
    main()
