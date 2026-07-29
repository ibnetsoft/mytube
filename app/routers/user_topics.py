"""
?????????용츧???????살퓢癲??API
?????????ル쐞?????ル봿???????거??먲펲?????용츧??鶯ㅺ동??筌믡룓愿?????살퓢癲?????롪퍓肉???????ル뭸????棺堉?댆洹ⓦ럹?????????
"""
import os
import json
import asyncio
import html
import requests
import urllib.parse
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional

import database as db
from config import config
from services.auth_service import auth_service

router = APIRouter(tags=["User Topics"])
_TOPIC_TRANSLATION_CACHE: dict[tuple[str, str, str], str] = {}


class ClaimTopicRequest(BaseModel):
    topic_id: str


class TopicTranslationItem(BaseModel):
    id: str
    topic: str
    category_name: str = ""


class TopicTranslationRequest(BaseModel):
    ui_language: str
    topics: List[TopicTranslationItem]


class BridgeError(Exception):
    """[AIR-0227E-P4] Raised when the desktop-topics-bridge call itself fails
    (network/auth/unexpected server error) - distinct from a well-formed
    'status': 'error' business response (e.g. topic_already_claimed), which
    callers handle explicitly via the returned dict."""


def _call_bridge(action: str, params: dict | None = None) -> dict:
    """[AIR-0227E-P4] Every Supabase read/write this router needs now goes
    through auth-web's POST /api/desktop-topics-bridge instead of a direct
    SUPABASE_SERVICE_ROLE_KEY-authenticated request.

    Why: AIR-0225B (commit 83951d8f) stopped bundling SUPABASE_SERVICE_ROLE_KEY
    into packaged desktop releases (it was leaking into public release zips),
    but this router was never migrated off direct service_role usage - every
    packaged build's topic page has been 500ing ever since. The bridge reuses
    the exact same email+session_token auth already established for
    /api/desktop-resync (services/web_admin_client.py::desktop_resync) - no
    service_role value ever exists on the desktop side of this call.
    """
    email = auth_service.get_user_email()
    session_token = auth_service.get_session_token()
    if not email or not session_token:
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        r = requests.post(
            f"{web_admin_client.dashboard_url}/api/desktop-topics-bridge",
            json={"email": email, "session_token": session_token, "action": action, "params": params or {}},
            timeout=15,
            verify=False,
            proxies={"http": None, "https": None},
        )
    except Exception as e:
        raise BridgeError(f"desktop-topics-bridge unreachable ({action}): {e}")

    try:
        body = r.json()
    except Exception:
        raise BridgeError(f"desktop-topics-bridge returned a non-JSON response ({action}, HTTP {r.status_code})")

    if r.status_code == 401:
        raise HTTPException(status_code=401, detail="Authentication required")
    if r.status_code >= 500:
        raise BridgeError(f"desktop-topics-bridge error ({action}): {body.get('detail')}")
    return body


def _normalize_content_language(value: str, default: str = "ko") -> str:
    """Normalize content language."""
    lang = (str(value or "").strip().lower() or default)
    return lang if lang in {"ko", "en", "ja"} else default


def _to_int(value, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _to_float(value, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _fetch_longform_policy() -> dict:
    defaults = {
        "sys_api_longform_min_duration_minutes": "15",
        "sys_api_longform_base_payout": "4",
        "sys_api_longform_extra_minute_payout": "0",
        "sys_api_longform_duration_lock_enabled": "true",
    }
    try:
        result = _call_bridge("get_longform_policy")
        for row in result.get("rows") or []:
            if row.get("key"):
                defaults[row["key"]] = row.get("value")
    except Exception as e:
        print(f"[User Topics] Failed to fetch longform policy: {e}")
    return defaults


def _normalize_payout_usdt(value) -> float:
    amount = _to_float(value, 0.0)
    if amount <= 0:
        return 0.0
    # Backward compatibility for legacy scaled values.
    if amount >= 1000:
        return round(amount / 1000.0, 1)
    return round(amount, 1)


def _calculate_longform_payout(minutes: int, policy: dict) -> float:
    min_minutes = max(15, _to_int(policy.get("sys_api_longform_min_duration_minutes"), 15))
    base_pay = max(0.0, _to_float(policy.get("sys_api_longform_base_payout"), 4.0))
    extra_pay = max(0.0, _to_float(policy.get("sys_api_longform_extra_minute_payout"), 0.0))
    return round(base_pay + max(0, minutes - min_minutes) * extra_pay, 1)


def _calculate_payout_multiplier(topic: dict, settings: dict) -> float:
    """Calculate payout multiplier."""
    claim_rate = float(topic.get("claim_rate", 0))
    priority_score = int(topic.get("priority_score", 0))
    current_multiplier = float(topic.get("current_multiplier", 1.0))

    min_mult = float(settings.get("min_multiplier", 0.5))
    max_mult = float(settings.get("max_multiplier", 2.0))

    new_multiplier = 1.0

    # ????????????泳?뿀?????곗뒭????
    if claim_rate < 10:
        new_multiplier = 1.5
    elif claim_rate < 30:
        new_multiplier = 1.2
    elif claim_rate > 50:
        new_multiplier = 0.9
    elif claim_rate > 80:
        new_multiplier = 0.7

    # ???????????癲ル슢???쇳맪?????????????泳?뿀?????곗뒭????
    if priority_score > 70:
        new_multiplier = new_multiplier * 1.2
    elif priority_score > 50:
        new_multiplier = new_multiplier * 1.1

    # ?嶺?????????????
    new_multiplier = max(min_mult, min(max_mult, new_multiplier))

    # ????뉖???癲ル슢캉??듭춻?????곗뒭????
    if current_multiplier > 0:
        new_multiplier = current_multiplier + (new_multiplier - current_multiplier) * 0.2
        new_multiplier = max(min_mult, min(max_mult, new_multiplier))

    return round(new_multiplier, 2)


def _get_content_language_label(lang: str) -> str:
    """Return readable language label."""
    labels = {
        'ko': 'Korean',
        'en': 'English',
        'ja': 'Japanese'
    }
    return labels.get(lang, lang)


def _build_translation_prompt(payload: list[dict], lang_name: str) -> str:
    return (
        f"You are translating Korean UI content into {lang_name}.\n"
        f"Return ONLY valid JSON array.\n"
        f"Translate each object's topic and category_name fields into natural {lang_name}.\n"
        f"Keep the same id.\n"
        f"If category_name is empty, keep it empty.\n\n"
        f"Input JSON:\n{json.dumps(payload, ensure_ascii=False)}\n\n"
        f"Output format:\n"
        f"[{{\"id\":\"...\",\"topic_translated\":\"...\",\"category_name_translated\":\"...\"}}]"
    )


def _parse_batch_translation_response(raw: str, valid_target: str) -> dict:
    translated = json.loads((raw or "").strip())
    result = {}
    for row in translated if isinstance(translated, list) else []:
        rid = str((row or {}).get("id") or "").strip()
        if not rid:
            continue
        result[rid] = {
            f"topic_{valid_target}": str((row or {}).get("topic_translated") or "").strip(),
            f"category_name_{valid_target}": str((row or {}).get("category_name_translated") or "").strip(),
        }
    return result


async def _translate_topics_with_gemini(payload: list[dict], valid_target: str, lang_name: str) -> dict:
    from services.gemini_service import gemini_service

    model = config.TRANSLATION_MODEL or "gemini-2.5-flash"
    if str(model).lower().startswith("claude"):
        model = "gemini-2.5-flash"
    res = await gemini_service.generate_text(_build_translation_prompt(payload, lang_name), temperature=0.2, task_type="translation", model=model)
    return _parse_batch_translation_response(res, valid_target)


async def _translate_topics_with_claude(payload: list[dict], valid_target: str, lang_name: str) -> dict:
    from services.claude_service import claude_service

    if not claude_service.api_key:
        return {}

    res = await claude_service.generate_text(
        _build_translation_prompt(payload, lang_name),
        temperature=0.2,
        task_type="translation",
        max_tokens=4096,
        model=config.TRANSLATION_MODEL,
    )
    return _parse_batch_translation_response(res, valid_target)


def _translate_text_via_google(text: str, target_lang_code: str) -> str:
    text = str(text or "").strip()
    if not text:
        return ""

    cache_key = ("google", target_lang_code, text)
    cached = _TOPIC_TRANSLATION_CACHE.get(cache_key)
    if cached:
        return cached

    try:
        query = urllib.parse.quote(text)
        url = (
            "https://translate.googleapis.com/translate_a/single"
            f"?client=gtx&sl=ko&tl={target_lang_code}&dt=t&q={query}"
        )
        response = requests.get(
            url,
            timeout=5,
            verify=False,
            proxies={"http": None, "https": None},
            headers={"User-Agent": "Mozilla/5.0"},
        )
        if response.status_code != 200:
            return ""

        payload = response.json()
        translated = "".join(
            str(chunk[0] or "")
            for chunk in (payload[0] or [])
            if isinstance(chunk, list) and chunk
        ).strip()
        translated = html.unescape(translated)
        if translated:
            _TOPIC_TRANSLATION_CACHE[cache_key] = translated
        return translated
    except Exception as e:
        print(f"[User Topics] Google translation fallback failed ({target_lang_code}): {e}")
        return ""


def _translate_topics_with_http_fallback(payload: list[dict], valid_target: str) -> dict:
    result = {}
    for item in payload:
        rid = str(item.get("id") or "").strip()
        if not rid:
            continue
        translated_topic = _translate_text_via_google(item.get("topic") or "", valid_target)
        translated_category = _translate_text_via_google(item.get("category_name") or "", valid_target)
        if translated_topic or translated_category:
            result[rid] = {
                f"topic_{valid_target}": translated_topic,
                f"category_name_{valid_target}": translated_category,
            }
    return result


async def _translate_topics_with_http_fallback_async(payload: list[dict], valid_target: str) -> dict:
    """Translate topic fields concurrently without blocking the FastAPI event loop."""
    semaphore = asyncio.Semaphore(6)

    async def translate_text(text: str) -> str:
        async with semaphore:
            return await asyncio.to_thread(_translate_text_via_google, text, valid_target)

    async def translate_item(item: dict):
        rid = str(item.get("id") or "").strip()
        if not rid:
            return None
        translated_topic, translated_category = await asyncio.gather(
            translate_text(item.get("topic") or ""),
            translate_text(item.get("category_name") or ""),
        )
        if not translated_topic and not translated_category:
            return None
        return rid, {
            f"topic_{valid_target}": translated_topic,
            f"category_name_{valid_target}": translated_category,
        }

    rows = await asyncio.gather(*(translate_item(item) for item in payload))
    return dict(row for row in rows if row)


async def _translate_topics_batch(items: list[dict], target_lang_code: str) -> dict:
    valid_target = (target_lang_code or "").strip().lower()
    if valid_target not in {"en", "vi", "th"} or not items:
        return {}

    lang_map = {
        "en": "English",
        "vi": "Vietnamese",
        "th": "Thai",
    }
    lang_name = lang_map.get(valid_target, "English")
    payload = [
        {
            "id": str(item.get("id") or ""),
            "topic": str(item.get("topic") or ""),
            "category_name": str(item.get("category_name") or ""),
        }
        for item in items
        if str(item.get("id") or "").strip() and str(item.get("topic") or "").strip()
    ]
    if not payload:
        return {}

    # UI translation should remain available even when paid AI quotas are exhausted.
    translated = await _translate_topics_with_http_fallback_async(payload, valid_target)
    missing_payload = [
        item
        for item in payload
        if not translated.get(item["id"], {}).get(f"topic_{valid_target}")
    ]
    if not missing_payload:
        return translated

    preferred_translation_model = str(config.TRANSLATION_MODEL or "gemini-2.5-flash").lower()
    import services.ai_router as ai_router
    provider_chain = (
        (("claude", _translate_topics_with_claude), ("gemini", _translate_topics_with_gemini))
        if ai_router.detect_provider(preferred_translation_model) == "claude"
        else (("gemini", _translate_topics_with_gemini), ("claude", _translate_topics_with_claude))
    )

    for provider_name, translator in provider_chain:
        try:
            provider_result = await translator(missing_payload, valid_target, lang_name)
            translated.update(provider_result)
            missing_payload = [
                item
                for item in missing_payload
                if not translated.get(item["id"], {}).get(f"topic_{valid_target}")
            ]
            if not missing_payload:
                return translated
        except Exception as e:
            print(f"[User Topics] {provider_name} batch translation failed ({valid_target}): {e}")

    return translated


def _fetch_stored_translations(topic_ids: list[str], lang_code: str) -> dict:
    """Fetch already-persisted translations from Supabase topics_queue via
    the bridge. Returns {str(id): {"topic_{lang}": "...", "category_name_{lang}": "..."}}.
    Returns an empty dict when the translation columns have not been migrated
    yet or on any network/parse error - callers fall back to runtime AI translation."""
    if not topic_ids or lang_code not in {"en", "vi", "th"}:
        return {}

    lang = lang_code
    try:
        result = _call_bridge("get_stored_translations", {"topic_ids": [str(t) for t in topic_ids], "lang": lang})
        out = {}
        for row in result.get("rows") or []:
            rid = str(row.get("id") or "").strip()
            if not rid:
                continue
            topic_t = str(row.get(f"topic_{lang}") or "").strip()
            if topic_t:
                out[rid] = {
                    f"topic_{lang}": topic_t,
                    f"category_name_{lang}": str(row.get(f"category_name_{lang}") or "").strip(),
                }
        return out
    except Exception as e:
        print(f"[User Topics] Failed to fetch stored translations ({lang}): {e}")
        return {}


async def _save_translations_to_db(translations: dict, lang_code: str) -> None:
    """Persist newly AI-translated topic fields back to Supabase topics_queue
    via the bridge. Fire-and-forget: errors are logged but not propagated to
    the caller. Skips rows where the translated topic text is empty."""
    if not translations or lang_code not in {"en", "vi", "th"}:
        return

    lang = lang_code

    async def _patch_one(topic_id: str, data: dict) -> None:
        topic_val = str(data.get(f"topic_{lang}") or "").strip()
        if not topic_val:
            return
        fields = {
            f"topic_{lang}": topic_val,
            f"category_name_{lang}": str(data.get(f"category_name_{lang}") or "").strip(),
        }
        try:
            await asyncio.to_thread(
                _call_bridge, "save_translations", {"topic_id": topic_id, "lang": lang, "fields": fields}
            )
        except Exception as e:
            print(f"[User Topics] Failed to save translation for topic {topic_id} ({lang}): {e}")

    await asyncio.gather(*(_patch_one(tid, data) for tid, data in translations.items()))

def _normalize_topic_payload(topic: dict, policy: dict) -> dict:
    category = topic.get("categories") or {}
    category_name = topic.get("category_name") or category.get("name")
    language = _normalize_content_language(topic.get("language") or category.get("language"))
    video_type = str(topic.get("video_type") or category.get("video_type") or "longform").strip().lower() or "longform"
    min_minutes = max(15, _to_int(policy.get("sys_api_longform_min_duration_minutes"), 15))

    raw_duration = (
        topic.get("duration_minutes")
        or topic.get("recommended_duration_minutes")
        or topic.get("assigned_duration_minutes")
    )
    duration_minutes = _to_int(raw_duration, 0)
    if video_type == "longform":
        duration_minutes = max(min_minutes, duration_minutes or min_minutes)

    script_style = (
        topic.get("script_style")
        or topic.get("assigned_script_style")
        or category.get("default_script_style")
        or "default"
    )
    image_style = (
        topic.get("image_style")
        or topic.get("assigned_image_style")
        or category.get("default_image_style")
        or "realistic"
    )

    raw_estimated_payout = topic.get("estimated_payout")
    if video_type == "longform":
        # Longform payout should always reflect the latest admin policy.
        estimated_payout = _calculate_longform_payout(duration_minutes or min_minutes, policy)
    else:
        estimated_payout = _normalize_payout_usdt(raw_estimated_payout)

    payout_multiplier = float(topic.get("payout_multiplier", 1.0) or 1.0)
    adjusted_payout = round(estimated_payout * payout_multiplier, 1)

    canonical_topic_id = topic.get("topic_queue_id") or topic.get("id")

    return {
        "id": canonical_topic_id,
        "topic": topic.get("topic"),
        "category_name": category_name,
        "category_id": topic.get("category_id"),
        "language": language,
        "language_label": _get_content_language_label(language),
        "duration_minutes": duration_minutes if duration_minutes > 0 else None,
        "recommended_duration_minutes": duration_minutes if duration_minutes > 0 else None,
        "script_style": script_style,
        "image_style": image_style,
        "estimated_payout": estimated_payout,
        "estimated_payout_usdt": estimated_payout,
        "payout_multiplier": payout_multiplier,
        "adjusted_payout": adjusted_payout,
        "adjusted_payout_usdt": adjusted_payout,
        "created_at": topic.get("created_at"),
        "video_type": video_type,
    }


def _has_complete_topic_metadata(topic: dict) -> bool:
    return bool(
        topic.get("topic")
        and (topic.get("duration_minutes") or topic.get("recommended_duration_minutes"))
        and topic.get("script_style")
        and topic.get("image_style")
        and topic.get("estimated_payout") is not None
    )


@router.get("/api/user/recommended-topics")
async def get_recommended_topics(
    request: Request,
    filter_duration: Optional[str] = None,
    filter_language: Optional[str] = None,
    filter_category: Optional[str] = None,
    limit: int = 20,
    refresh: bool = False
):
    """Return recommended topics for the current user."""









    # ??꿔꺂????癒κ섶???꿔꺂??틝?????
    email = auth_service.get_user_email()
    if not email:
        raise HTTPException(status_code=401, detail="Authentication required")

    policy = _fetch_longform_policy()
    # ????袁ｋ쨨???????

    # ????袁ｋ쨨???????
    filters = filter_duration.split(',') if filter_duration else []
    ignore_duration = "duration_ignore" in filters
    ignore_language = "language_ignore" in filters
    ignore_category = "category_ignore" in filters

    # ???????꿔꺂??틝?????(????亦????숈?????????밸븶?????β뼯援????
    if not refresh:
        try:
            cached = _call_bridge("get_cached_recommendations", {"limit": limit})
            rows = cached.get("rows") or []
            if rows:
                topics = [_normalize_topic_payload(topic, policy) for topic in _apply_multipliers_to_topics(rows)]
                if topics and all(_has_complete_topic_metadata(topic) for topic in topics):
                    return {"status": "ok", "topics": topics, "cached": True}
        except Exception as e:
            print(f"[User Topics] Failed to fetch cached recommendations: {e}")

    # ??????????밸븶?ⓥ뮧??????곗뒭????
    profile = (_call_bridge("get_profile_prefs") or {}).get("profile")
    user_prefs = {}
    if profile:
        user_prefs = {
            "preferred_languages": profile.get("preferred_languages", ["ko"]),
            "preferred_video_length": profile.get("preferred_video_length", ""),
            "preferred_category_ids": profile.get("preferred_category_ids", []),
        }

    # ??????????援경퓴??????????癲????濚밸Ŧ???
    preferred_languages = user_prefs.get("preferred_languages", ["ko"])
    preferred_video_length = user_prefs.get("preferred_video_length", "")
    preferred_category_ids = user_prefs.get("preferred_category_ids", [])

    # ???숆강?붺춯?筌????????利????濚밸Ŧ??????곗뒭????
    rebalancing_settings = {}
    try:
        rebalancing_result = _call_bridge("get_rebalancing_settings")
        rows = rebalancing_result.get("rows") or []
        if rows:
            rebalancing_settings = rows[0] or {}
    except Exception:
        pass

    # ????용츧????????????????ル봿????μ떝?롳쭗??????용츧??????곗뒭????
    try:
        available_result = _call_bridge("get_pending_topics", {"limit": 100})
        available_topics = available_result.get("rows") or []
    except HTTPException:
        raise
    except BridgeError as e:
        raise HTTPException(status_code=500, detail=f"Supabase topics unavailable: {str(e)}")

    # ????용츧???????袁ｋ쨨?耀붾굛????????????壤굿?????
    scored_topics = []
    for topic in available_topics:
        score = _calculate_topic_score(
            topic,
            user_prefs,
            {
                'ignore_duration': ignore_duration,
                'ignore_language': ignore_language,
                'ignore_category': ignore_category
            },
            email
        )

        if score > 0:
            topic_data = {
                **topic,
                '_score': score,
                'payout_multiplier': _calculate_payout_multiplier(topic, rebalancing_settings)
            }
            scored_topics.append(topic_data)

    # ???????꿔꺂???影?????????⑤뜪癲?limit????ш끽維뽳쭩???
    scored_topics.sort(key=lambda x: x['_score'], reverse=True)
    result_topics = scored_topics[:limit]

    # recommendation cache
    if result_topics:
        recommendations = [
            {
                "user_id": None,
                "employee_email": email,
                "topic_queue_id": t.get("id"),
                "topic": t.get("topic"),
                "language": _normalize_content_language(t.get("language")),
                "recommended_duration_minutes": _normalize_topic_payload(t, policy).get("recommended_duration_minutes"),
                "estimated_payout": _normalize_topic_payload(t, policy).get("estimated_payout"),
                "script_style": _normalize_topic_payload(t, policy).get("script_style"),
                "image_style": _normalize_topic_payload(t, policy).get("image_style"),
                "category_id": t.get("category_id"),
                "category_name": t.get("categories", {}).get("name") if t.get("categories") else None,
                "payout_multiplier": t.get("payout_multiplier", 1.0),
                "is_claimed": False,
                "expires_at": (datetime.utcnow() + timedelta(days=7)).isoformat()
            }
            for t in result_topics
        ]

        try:
            _call_bridge("save_recommendations", {"rows": recommendations})
        except Exception as e:
            print(f"[User Topics] Failed to save recommendations: {e}")

    # formatted response
    formatted_topics = [_normalize_topic_payload(t, policy) for t in result_topics]
    return {"status": "ok", "topics": formatted_topics, "cached": False}


@router.post("/api/user/recommended-topics/translations")
async def translate_recommended_topics(req: TopicTranslationRequest):
    ui_language = (req.ui_language or "").strip().lower()
    if ui_language not in {"en", "vi", "th"}:
        return {"status": "ok", "translations": {}}

    payload = [
        {
            "id": item.id,
            "topic": item.topic,
            "category_name": item.category_name,
        }
        for item in (req.topics or [])
    ]
    if not payload:
        return {"status": "ok", "translations": {}}

    # --- Step 1: DB-first lookup (no AI call when translation already stored) ---
    all_ids = [str(item["id"]) for item in payload]
    stored: dict = _fetch_stored_translations(all_ids, ui_language)

    # --- Step 2: AI fallback only for topics without a stored translation ---
    needs_translation = [
        item for item in payload
        if not stored.get(str(item["id"]), {}).get(f"topic_{ui_language}")
    ]
    ai_translations: dict = {}
    if needs_translation:
        ai_translations = await _translate_topics_batch(needs_translation, ui_language)
        # Persist new translations back to DB (fire-and-forget; does not block response)
        if ai_translations:
            asyncio.create_task(_save_translations_to_db(ai_translations, ui_language))

    # --- Step 3: Merge — stored (DB) takes precedence, AI fills the gaps ---
    translations = {**ai_translations, **stored}
    return {"status": "ok", "translations": translations}


@router.post("/api/user/claim-topic")
async def claim_topic(req: ClaimTopicRequest):
    """Claim a topic and create a locked project."""
    """Claim a topic and create a locked project."""

    email = auth_service.get_user_email()
    if not email:
        raise HTTPException(status_code=401, detail="Authentication required")

    # [FIX] 아래 블록에 예외가 나면(네트워크 오류, DB 제약 위반 등) 지금까지는
    # try/except가 전혀 없어 Starlette의 기본 미처리 예외 핸들러가 그대로
    # 노출되었다. 이 핸들러는 JSON이 아니라 순수 텍스트 "Internal Server
    # Error"를 반환하는데, 프론트엔드(projects.html의 claimAndCreateProject)는
    # 항상 res.json()을 기대하므로 "Unexpected token 'I', "Internal S"...
    # is not valid JSON" 형태로 깨졌다. HTTPException은 그대로 다시 던져
    # 기존의 401/404/500 상세 메시지를 유지하고, 그 외 모든 예외는 잡아서
    # 항상 유효한 JSON으로 응답한다.
    try:
        policy = _fetch_longform_policy()

        # [AIR-0227E-P4] resolve+fetch+patch(topics_queue)+patch(user_topic_recommendations)
        # now happens as one atomic action on the bridge (auth-web), not four
        # separate direct-to-Supabase calls from here.
        bridge_result = _call_bridge("claim_topic", {"topic_id": req.topic_id})
        if bridge_result.get("status") != "ok":
            detail = bridge_result.get("detail") or "topic_not_found"
            if detail == "topic_already_claimed":
                raise HTTPException(status_code=409, detail="Topic already claimed")
            raise HTTPException(status_code=404, detail="Topic not found")

        topic_data = bridge_result["topic"]
        normalized = _normalize_topic_payload(topic_data, policy)
        category = topic_data.get("categories") or {}
        topic_language = normalized.get("language") or "ko"
        project_mode = str(category.get("video_type") or "longform").strip().lower() or "longform"
        duration_locked = str(
            topic_data.get("duration_locked", policy.get("sys_api_longform_duration_lock_enabled", "true"))
        ).lower() not in ("false", "0", "none")
        resolved_topic_id = topic_data.get("id")

        project_id = db.create_project(
            name=(normalized.get("topic") or "Untitled")[:80],
            topic=normalized.get("topic"),
            app_mode=project_mode,
            language=topic_language,
            employee_email=email,
            script_style=normalized.get("script_style"),
            image_style=normalized.get("image_style"),
        )

        db.update_project_setting(project_id, "topic_queue_id", str(resolved_topic_id))
        db.update_project_setting(project_id, "topic_queue_category_id", str(topic_data.get("category_id") or ""))
        db.update_project_setting(project_id, "target_language", topic_language)
        db.update_project_setting(project_id, "script_style", normalized.get("script_style") or "default")
        db.update_project_setting(project_id, "image_style", normalized.get("image_style") or "realistic")
        db.update_project_setting(project_id, "style_locked", "1")

        # [AIR-0230 §2c] 이 주제가 속한 카테고리에 실제 고성과 영상 분석이 있으면
        # (topics_queue.benchmark_analysis, 웹어드민이 topic_benchmark_analyze job으로
        # 채워둠 - migrations/air_0230_topics_queue_benchmark_analysis_column.sql, 미적용
        # 초안) project_settings로 복사해둔다. generate_script_structure_api()가
        # (app/routers/gemini.py) 이 값을 읽어 scene_planner.plan_scenes()의
        # benchmark_analysis 인자로 전달한다 - PRO 전용 수동 분석(로컬 analysis 테이블)
        # 없이도 STD가 claim한 주제에도 실제 벤치마크 데이터가 붙게 하기 위함.
        benchmark_analysis = topic_data.get("benchmark_analysis")
        if benchmark_analysis:
            db.update_project_setting(project_id, "benchmark_analysis_json", json.dumps(benchmark_analysis, ensure_ascii=False))

        # [AIR-0230 §2d] 이 주제가 이미 기획(씬 구조)까지 사전생성돼 있으면
        # (topics_queue.pregenerated_structure_status == 'ready', 웹어드민이 주제
        # 생성 직후 상위 몇 개에 대해 script_plan_generate job을 큐잉해 채워둠) 그
        # 구조를 그대로 넘겨서 generate_script_structure_api()가 AI를 다시 부르지
        # 않고 즉시 반환하게 한다.
        if topic_data.get("pregenerated_structure_status") == "ready" and topic_data.get("pregenerated_structure"):
            db.update_project_setting(
                project_id, "pregenerated_structure_json",
                json.dumps(topic_data.get("pregenerated_structure"), ensure_ascii=False)
            )

        # [AIR-0230 §2d] 같은 방식으로 사전생성된 대본 본문도 복사한다.
        # generate_script_api()가 이 값을 읽어 대본 생성 화면에 즉시 반영한다.
        if topic_data.get("pregenerated_script_status") == "ready" and topic_data.get("pregenerated_script"):
            db.update_project_setting(project_id, "pregenerated_script_text", topic_data.get("pregenerated_script"))

        if project_mode == "longform":
            assigned_minutes = normalized.get("recommended_duration_minutes") or max(
                15, _to_int(policy.get("sys_api_longform_min_duration_minutes"), 15)
            )
            estimated_payout = _calculate_longform_payout(assigned_minutes, policy)
            db.update_project_setting(project_id, "duration_seconds", assigned_minutes * 60)
            db.update_project_setting(project_id, "assigned_duration_minutes", assigned_minutes)
            db.update_project_setting(project_id, "assigned_duration_seconds", assigned_minutes * 60)
            db.update_project_setting(project_id, "duration_locked", "1" if duration_locked else "0")
            db.update_project_setting(project_id, "estimated_payout", estimated_payout)
            db.update_project_setting(project_id, "duration_reason", topic_data.get("duration_reason") or "")
            db.update_project_setting(project_id, "difficulty_level", topic_data.get("difficulty_level") or "")
            db.update_project_setting(project_id, "payout_policy_json", json.dumps({
                "min_duration_minutes": max(15, _to_int(policy.get("sys_api_longform_min_duration_minutes"), 15)),
                "base_payout": max(0.0, _to_float(policy.get("sys_api_longform_base_payout"), 4.0)),
                "extra_minute_payout": max(0.0, _to_float(policy.get("sys_api_longform_extra_minute_payout"), 0.0)),
            }, ensure_ascii=False))

        # [AIR-0227E-P4] user_topic_recommendations.is_claimed is already set
        # by the bridge's claim_topic action itself - no separate PATCH needed here.

        return {
            "status": "ok",
            "project_id": project_id,
            "project_mode": project_mode,
            "topic": {
                "id": topic_data.get("id"),
                "topic": normalized.get("topic"),
                "language": topic_language,
                "recommended_duration_minutes": normalized.get("recommended_duration_minutes"),
                "estimated_payout": normalized.get("estimated_payout"),
                "script_style": normalized.get("script_style"),
                "image_style": normalized.get("image_style"),
                "category_name": normalized.get("category_name")
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"[User Topics] claim_topic failed for topic_id={req.topic_id}: {e}\n{traceback.format_exc()}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "detail": f"주제를 선택하는 중 오류가 발생했습니다: {e}"}
        )


def _calculate_topic_score(topic: dict, user_prefs: dict, filters: dict, user_email: str) -> int:
    """Score a topic for the current user."""









    score = 0

    # ???癲??????????ル뭸???????용츧????????????
    if topic.get("assigned_employee_email") == user_email:
        score += 50

    # ??꿔꺂??????轅붽틓???????
    if not filters.get('ignore_language'):
        preferred_langs = user_prefs.get("preferred_languages", ["ko"])
        if topic.get("language") in preferred_langs:
            score += 30

    # ?????몃뱥癲????沅걔?癲???轅붽틓???????
    if not filters.get('ignore_duration'):
        pref_length = user_prefs.get("preferred_video_length", "")
        topic_duration = topic.get("assigned_duration_minutes") or topic.get("recommended_duration_minutes")

        if pref_length and topic_duration:
            if pref_length == "15m" and topic_duration <= 15:
                score += 25
            elif pref_length == "30m" and 15 < topic_duration <= 30:
                score += 25
            elif pref_length == "60m_plus" and topic_duration > 30:
                score += 25

    # ???ㅳ늾???雅?퍔瑗?????숈????轅붽틓???????
    if not filters.get('ignore_category'):
        pref_categories = user_prefs.get("preferred_category_ids", [])
        if pref_categories and topic.get("category_id") in pref_categories:
            score += 20

    # ?轅붽틓????彛??????용츧????????????
    created_at = topic.get("created_at")
    if created_at:
        try:
            created_date = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
            if (datetime.utcnow() - created_date.replace(tzinfo=None)).total_seconds() < 86400:
                score += 10
        except Exception:
            pass

    return score


def _apply_multipliers_to_topics(topics: list) -> list:
    """Apply category boost multipliers to cached topics."""
    # ???ㅳ늾???雅?퍔瑗?????숈?????????????????癲ル슢???쇳맪?????뉖???????깅렰 ???곗뒭????
    try:
        boosts_result = _call_bridge("get_boosts")
        boosts = {b.get("category_id"): b.get("boost_multiplier", 1.0) for b in boosts_result.get("rows") or []}
        for topic in topics:
            category_id = topic.get("category_id")
            if category_id and category_id in boosts:
                topic["payout_multiplier"] = boosts[category_id]
            else:
                topic["payout_multiplier"] = 1.0
    except Exception as e:
        print(f"[User Topics] Failed to apply multipliers: {e}")
        for topic in topics:
            topic["payout_multiplier"] = 1.0

    return topics


# web_admin_client import ??ш끽維??λ궔???????袁ｋ쨨???????import
web_admin_client = None
def _init_web_admin_client():
    global web_admin_client
    if web_admin_client is None:
        from services.web_admin_client import web_admin_client as wac
        web_admin_client = wac


_init_web_admin_client()
