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
from pydantic import BaseModel
from typing import List, Optional

import database as db
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


def _supabase_headers():
    """Build Supabase headers."""
    supabase_url = os.getenv("NEXT_PUBLIC_SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not supabase_key:
        return None, None

    return supabase_url.rstrip("/"), {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
    }


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


def _fetch_longform_policy(supabase_url: str, headers: dict) -> dict:
    defaults = {
        "sys_api_longform_min_duration_minutes": "15",
        "sys_api_longform_base_payout": "4",
        "sys_api_longform_extra_minute_payout": "0",
        "sys_api_longform_duration_lock_enabled": "true",
    }
    try:
        keys = ",".join(defaults.keys())
        url = f"{supabase_url}/rest/v1/global_settings?select=key,value&key=in.({keys})"
        r = requests.get(url, headers=headers, timeout=5, verify=False, proxies={"http": None, "https": None})
        if r.status_code == 200:
            for row in r.json() or []:
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

    res = await gemini_service.generate_text(_build_translation_prompt(payload, lang_name), temperature=0.2)
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

    for provider_name, translator in (
        ("gemini", _translate_topics_with_gemini),
        ("claude", _translate_topics_with_claude),
    ):
        try:
            translated = await translator(payload, valid_target, lang_name)
            if translated:
                return translated
        except Exception as e:
            print(f"[User Topics] {provider_name} batch translation failed ({valid_target}): {e}")

    return _translate_topics_with_http_fallback(payload, valid_target)

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


def _resolve_claimable_topic_id(supabase_url: str, headers: dict, raw_topic_id: str, email: str):
    candidate = str(raw_topic_id or "").strip()
    if not candidate:
        return None

    try:
        lookup_url = (
            f"{supabase_url}/rest/v1/user_topic_recommendations"
            f"?id=eq.{candidate}"
            f"&employee_email=eq.{email}"
            f"&select=topic_queue_id"
            f"&limit=1"
        )
        r = requests.get(
            lookup_url,
            headers=headers,
            timeout=5,
            verify=False,
            proxies={"http": None, "https": None},
        )
        if r.status_code == 200 and r.json():
            resolved = (r.json()[0] or {}).get("topic_queue_id")
            return int(resolved) if resolved is not None else None
    except Exception as e:
        print(f"[User Topics] Failed to resolve recommendation id {candidate}: {e}")

    try:
        return int(candidate)
    except Exception:
        pass

    return None


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

    supabase_url, headers = _supabase_headers()
    if not supabase_url:
        raise HTTPException(status_code=500, detail="Supabase configuration missing")
    policy = _fetch_longform_policy(supabase_url, headers)
    # ????袁ｋ쨨???????

    # ????袁ｋ쨨???????
    filters = filter_duration.split(',') if filter_duration else []
    ignore_duration = "duration_ignore" in filters
    ignore_language = "language_ignore" in filters
    ignore_category = "category_ignore" in filters

    # ???????꿔꺂??틝?????(????亦????숈?????????밸븶?????β뼯援????
    if not refresh:
        now = datetime.utcnow().isoformat()
        try:
            cached_url = (
                f"{supabase_url}/rest/v1/user_topic_recommendations"
                f"?employee_email=eq.{email}"
                f"&is_claimed=eq.false"
                f"&expires_at=gte.{now}"
                f"&order=created_at.desc"
                f"&limit={limit}"
            )
            r = requests.get(cached_url, headers=headers, timeout=5, verify=False, proxies={"http": None, "https": None})
            if r.status_code == 200 and r.json():
                topics = [_normalize_topic_payload(topic, policy) for topic in _apply_multipliers_to_topics(r.json())]
                if topics and all(_has_complete_topic_metadata(topic) for topic in topics):
                    return {"status": "ok", "topics": topics, "cached": True}
        except Exception as e:
            print(f"[User Topics] Failed to fetch cached recommendations: {e}")

    # ??????????밸븶?ⓥ뮧??????곗뒭????
    profile = web_admin_client.fetch_profile_by_email(email)
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
        settings_url = f"{supabase_url}/rest/v1/payout_rebalancing_settings?limit=1"
        r = requests.get(settings_url, headers=headers, timeout=5, verify=False, proxies={"http": None, "https": None})
        if r.status_code == 200 and r.json():
            rebalancing_settings = r.json()[0] or {}
    except Exception:
        pass

    # ????용츧????????????????ル봿????μ떝?롳쭗??????용츧??????곗뒭????
    topic_query_url = (
        f"{supabase_url}/rest/v1/topics_queue"
        f"?status=eq.pending"
        f"&order=created_at.desc"
        f"&limit=100"
        f"&select=*,categories!inner(*)"
    )

    r = requests.get(topic_query_url, headers=headers, timeout=10, verify=False, proxies={"http": None, "https": None})
    if r.status_code != 200:
        raise HTTPException(status_code=500, detail="Failed to fetch available topics")

    available_topics = r.json() or []

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
            insert_r = requests.post(
                f"{supabase_url}/rest/v1/user_topic_recommendations",
                json=recommendations,
                headers=headers,
                timeout=10,
                verify=False,
                proxies={"http": None, "https": None}
            )
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
    translations = await _translate_topics_batch(payload, ui_language)
    return {"status": "ok", "translations": translations}


@router.post("/api/user/claim-topic")
async def claim_topic(req: ClaimTopicRequest):
    """Claim a topic and create a locked project."""
    """Claim a topic and create a locked project."""

    email = auth_service.get_user_email()
    if not email:
        raise HTTPException(status_code=401, detail="Authentication required")

    supabase_url, headers = _supabase_headers()
    if not supabase_url:
        raise HTTPException(status_code=500, detail="Supabase configuration missing")
    policy = _fetch_longform_policy(supabase_url, headers)
    resolved_topic_id = _resolve_claimable_topic_id(supabase_url, headers, req.topic_id, email)
    if resolved_topic_id is None:
        raise HTTPException(status_code=404, detail="Topic not found")

    # ????용츧????????몃뱥?????곗뒭????
    topic_res = requests.get(
        f"{supabase_url}/rest/v1/topics_queue?id=eq.{resolved_topic_id}&select=*,categories!inner(*)",
        headers=headers,
        timeout=5,
        verify=False,
        proxies={"http": None, "https": None}
    )

    if topic_res.status_code != 200 or not topic_res.json():
        raise HTTPException(status_code=404, detail="Topic not found")

    topic_data = topic_res.json()[0]
    normalized = _normalize_topic_payload(topic_data, policy)
    category = topic_data.get("categories") or {}
    topic_language = normalized.get("language") or "ko"
    project_mode = str(category.get("video_type") or "longform").strip().lower() or "longform"
    duration_locked = str(
        topic_data.get("duration_locked", policy.get("sys_api_longform_duration_lock_enabled", "true"))
    ).lower() not in ("false", "0", "none")

    # ????용츧???????釉먮빱????????띻콣?????썹땟???(assigned?????ㅼ뒧????
    update_res = requests.patch(
        f"{supabase_url}/rest/v1/topics_queue?id=eq.{resolved_topic_id}",
        json={
            "status": "assigned",
            "assigned_employee_email": email,
            "assigned_at": datetime.utcnow().isoformat()
        },
        headers=headers,
        timeout=5,
        verify=False,
        proxies={"http": None, "https": None}
    )

    if update_res.status_code not in (200, 204):
        raise HTTPException(status_code=500, detail="Failed to claim topic")

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
    db.update_project_setting(
        project_id,
        "script_generation_provider",
        db.get_global_setting("sys_api_script_generation_provider") or "gemini"
    )
    db.update_project_setting(
        project_id,
        "script_generation_model",
        db.get_global_setting("sys_api_script_generation_model") or "gemini-2.5-flash"
    )

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

    # ????살퓢癲?????????????띻콣?????썹땟???
    try:
        requests.patch(
            f"{supabase_url}/rest/v1/user_topic_recommendations?topic_queue_id=eq.{resolved_topic_id}&employee_email=eq.{email}",
            json={
                "is_claimed": True,
                "claimed_at": datetime.utcnow().isoformat()
            },
            headers=headers,
            timeout=5,
            verify=False,
            proxies={"http": None, "https": None}
        )
    except Exception as e:
        print(f"[User Topics] Failed to update recommendation cache: {e}")

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
    supabase_url, headers = _supabase_headers()
    if not supabase_url or not headers:
        return topics

    try:
        boosts_url = f"{supabase_url}/rest/v1/category_priority_boosts"
        r = requests.get(boosts_url, headers=headers, timeout=5, verify=False, proxies={"http": None, "https": None})
        if r.status_code == 200:
            boosts = {b.get("category_id"): b.get("boost_multiplier", 1.0) for b in r.json() or []}
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
