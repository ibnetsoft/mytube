import sys
from pathlib import Path

# Ensure project root is in sys.path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from worker_config import ensure_project_root_on_path
ensure_project_root_on_path()

import asyncio
import json
import os
import re
import time
import httpx
import traceback
from datetime import datetime
from difflib import SequenceMatcher

import job_store
from worker_config import STATE_DIR, OUTPUT_DIR
import logging
from services import ai_router

logger = logging.getLogger("hermes_autopilot")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s'))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

STATE_FILE = STATE_DIR / "hermes_autopilot_state.json"
RESULTS_DIR = OUTPUT_DIR / "hermes_autopilot_results"

CATEGORIES = [
    "탈북사연",
    "해외감동",
    "노후금융",
    "황혼19금",
    "옛날이야기",
    "한국사연",
    "무협",
    "경제"
]


def _format_view_count(value) -> str:
    try:
        return f"{int(value):,}회"
    except (TypeError, ValueError):
        return "확인 불가"


def _is_real_youtube_candidate(candidate: dict) -> bool:
    video_id = str(candidate.get("video_id") or "")
    return bool(video_id) and not video_id.startswith("dummy_")

class HermesAutopilotManager:
    _instance = None
    _lock = asyncio.Lock()

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(HermesAutopilotManager, cls).__new__(cls)
            cls._instance.initialized = False
        return cls._instance

    def __init__(self):
        if self.initialized:
            return
        self.is_running = False
        self.current_step = "idle"
        self.current_category = ""
        self.current_topic = ""
        self.current_image_style = ""
        self.logs = []
        self.loop_task = None
        
        # 신규 설정 및 통계 기본값
        self.settings = {
            "mode": "infinite",
            "target_limit": 10,
            "min_buffer_per_category": 5,
            "active_categories": CATEGORIES.copy(),
            "category_image_style_overrides": {},
        }
        self.session_stats = {
            "generated_count": 0
        }
        
        self.initialized = True
        self._load_state()

    def _load_state(self):
        """Loads state from local JSON storage if exists."""
        if STATE_FILE.exists():
            try:
                data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
                self.is_running = data.get("is_running", False)
                self.current_step = data.get("current_step", "idle")
                self.current_category = data.get("current_category", "")
                self.current_topic = data.get("current_topic", "")
                self.current_image_style = data.get("current_image_style", "")
                self.logs = data.get("logs", [])
                
                # settings 로드
                loaded_settings = data.get("settings", {})
                if loaded_settings:
                    # 리스트 인스턴스 복사 누락 보완
                    for k, v in loaded_settings.items():
                        if k in self.settings:
                            self.settings[k] = v
                
                # stats 로드
                loaded_stats = data.get("session_stats", {})
                if loaded_stats:
                    self.session_stats.update(loaded_stats)
                
                # If it crashed/restarted while running, reset running flag gracefully
                if self.is_running:
                    self.is_running = False
                    self.add_log("시스템 재시작으로 인해 오토파일럿이 중단되었습니다. 대기 상태로 전환합니다.")
                    self._save_state()
            except Exception as e:
                logger.warning(f"Failed to load autopilot state: {e}")

    def _save_state(self):
        """Saves current state to local JSON storage."""
        try:
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "is_running": self.is_running,
                "current_step": self.current_step,
                "current_category": self.current_category,
                "current_topic": self.current_topic,
                "current_image_style": self.current_image_style,
                "logs": self.logs[-200:],  # keep last 200 logs
                "settings": self.settings,
                "session_stats": self.session_stats,
                "updated_at": time.time()
            }
            STATE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to save autopilot state: {e}")

    def _normalize_active_categories(self, value) -> list[str]:
        if not isinstance(value, list):
            return CATEGORIES.copy()
        valid = set(CATEGORIES)
        normalized = []
        for item in value:
            category = str(item or "").strip()
            if category in valid and category not in normalized:
                normalized.append(category)
        return normalized

    def _apply_settings(self, new_settings: dict | None = None):
        for k, v in (new_settings or {}).items():
            if k not in self.settings:
                continue
            if k == "active_categories":
                self.settings[k] = self._normalize_active_categories(v)
            else:
                self.settings[k] = v

        self.settings["active_categories"] = self._normalize_active_categories(
            self.settings.get("active_categories", CATEGORIES)
        )
        try:
            self.settings["target_limit"] = max(1, min(100, int(self.settings.get("target_limit", 1))))
        except (TypeError, ValueError):
            self.settings["target_limit"] = 1
        try:
            self.settings["min_buffer_per_category"] = max(0, int(self.settings.get("min_buffer_per_category", 5)))
        except (TypeError, ValueError):
            self.settings["min_buffer_per_category"] = 5
        if self.settings.get("mode") not in {"infinite", "target_limit"}:
            self.settings["mode"] = "target_limit"

    @staticmethod
    def _has_ready_media_prompts(structure: dict | None) -> bool:
        if not isinstance(structure, dict):
            return False
        scenes = structure.get("scenes")
        if not isinstance(scenes, list) or not scenes:
            return False
        if structure.get("media_prompt_status") != "ready":
            return False
        for scene in scenes:
            if not isinstance(scene, dict):
                return False
            if scene.get("media_prompt_status") != "ready":
                return False
            if not str(scene.get("image_prompt") or "").strip():
                return False
            if not str(scene.get("video_prompt") or "").strip():
                return False
        return True

    def add_log(self, message: str):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] {message}"
        self.logs.append(log_entry)
        if len(self.logs) > 300:
            self.logs = self.logs[-200:]
        logger.info(message)
        self._save_state()

    def get_status(self) -> dict:
        self._apply_settings()
        return {
            "is_running": self.is_running,
            "current_step": self.current_step,
            "current_category": self.current_category,
            "current_topic": self.current_topic,
            "current_image_style": self.current_image_style,
            "logs": self.logs,
            "settings": self.settings,
            "session_stats": self.session_stats
        }

    async def start(self, custom_settings: dict = None):
        async with self._lock:
            if self.is_running:
                return {"success": False, "error": "이미 실행 중입니다."}
            
            if custom_settings:
                self._apply_settings(custom_settings)
            else:
                self._apply_settings()
            if not self.settings.get("active_categories"):
                return {"success": False, "error": "At least one active category is required."}
            
            self.session_stats["generated_count"] = 0
            self.is_running = True
            self.current_step = "initializing"
            self.add_log("Hermes 자동 생성기(Autopilot) 시작 요청됨.")
            self.add_log(f"적용 설정: 모드={self.settings['mode']}, 제한량={self.settings['target_limit']}개, 최소유지량={self.settings['min_buffer_per_category']}개, 활성카테고리={len(self.settings['active_categories'])}개")
            
            self.loop_task = asyncio.create_task(self._run_loop())
            self._save_state()
            return {"success": True}

    async def save_settings(self, new_settings: dict):
        async with self._lock:
            self._apply_settings(new_settings)
            self._save_state()
            return {"success": True, "settings": self.settings}

    async def save_category_image_style_override(self, category: str, style_key: str | None):
        """Persist a Worker-local manual style choice with higher priority than AI selection."""
        if category not in CATEGORIES:
            return {"success": False, "error": "지원하지 않는 카테고리입니다."}
        normalized = str(style_key or "").strip().lower()
        async with self._lock:
            overrides = dict(self.settings.get("category_image_style_overrides") or {})
            if normalized:
                overrides[category] = normalized
            else:
                overrides.pop(category, None)
            self.settings["category_image_style_overrides"] = overrides
            self._save_state()
        self.add_log(
            f"이미지 스타일 수동 매칭 변경: {category} -> "
            f"{normalized or '자동 선택'}"
        )
        return {"success": True, "override": normalized or None}

    async def stop(self):
        async with self._lock:
            if not self.is_running:
                return {"success": False, "error": "실행 중이 아닙니다."}
            
            self.is_running = False
            self.add_log("오토파일럿 중지 요청됨. 현재 진행 중인 스텝이 끝나는 대로 정지합니다.")
            if self.loop_task:
                self.loop_task.cancel()
            self.current_step = "stopped"
            self.current_category = ""
            self.current_topic = ""
            self.current_image_style = ""
            self._save_state()
            return {"success": True}

    def _extract_json_object(self, text: str) -> dict:
        cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", text or "").strip()
        try:
            return json.loads(cleaned)
        except Exception:
            pass
        match = re.search(r"\{[\s\S]*\}", cleaned)
        if not match:
            raise ValueError("AI response did not contain a JSON object")
        return json.loads(match.group(0))

    def _clean_title_text(self, value: str) -> str:
        text = re.sub(r"\s+", " ", str(value or "")).strip()
        text = text.strip("\"'`“”‘’[](){}")
        return re.sub(r"^\s*(?:\d+[\).\-\s]+|[-*]+\s*)", "", text).strip()

    def _title_similarity(self, left: str, right: str) -> float:
        a = re.sub(r"\s+", "", (left or "").lower())
        b = re.sub(r"\s+", "", (right or "").lower())
        if not a or not b:
            return 0.0
        return SequenceMatcher(None, a, b).ratio()

    def _is_usable_title_candidate(self, title: str, category: str) -> bool:
        normalized_title = re.sub(r"[\s\W_]+", "", (title or "").lower())
        normalized_category = re.sub(r"[\s\W_]+", "", (category or "").lower())
        forbidden_terms = [
            "성공 공식", "스토리텔링", "벤치마킹", "패턴", "알고리즘",
            "콘텐츠", "조회수", "분석", "전략", "공식", "비결", "연출",
            "노하우", "비법", "비밀", "해부", "황금률", "치트키", "필독", "마스터",
            "모든 것", "덕후", "팬덤", "명작", "망작", "작품", "시청자",
            "몰입감", "클리셰", "떡상", "황금 패턴", "대공개", "법칙", "불문율",
            "반전 사연", "반전 스토리",
        ]
        category_forbidden_terms = {
            "옛날이야기": [
                "옛날이야기", "전래이야기", "전래동화", "고전 재해석",
                "현대적 재해석", "MZ", "넷플릭스", "K-콘텐츠", "대박 콘텐츠",
            ],
        }
        return bool(
            normalized_title
            and normalized_title != normalized_category
            and 12 <= len(title) <= 90
            and not any(term in title for term in forbidden_terms)
            and not any(term in title for term in category_forbidden_terms.get(category, []))
        )

    def _category_fallback_title(self, category: str) -> str:
        fallbacks = {
            "무협": "버림받은 삼류무사가 사부의 낡은 검보를 펼친 날",
            "탈북사연": "두만강 앞에서 마지막 선택을 해야 했던 한 가족의 밤",
            "해외감동": "낯선 나라의 작은 친절이 한 노인의 하루를 바꾼 순간",
            "노후금융": "월세 걱정하던 60대가 시골집 한 채로 생활비를 줄인 방법",
            "황혼19금": "평생 숨겨온 편지 한 장이 황혼의 마음을 흔든 날",
            "옛날이야기": "마을에서 쫓겨난 며느리가 십 년 뒤 들고 온 보따리",
            "한국사연": "가족을 위해 참아온 가장이 명절 아침에 남긴 한마디",
            "경제": "월급은 그대로인데 장바구니가 먼저 무너진 이유",
        }
        return fallbacks.get(category, f"{category} 속 평범한 선택이 인생을 바꾼 순간")

    def _score_title_candidate(
        self,
        title: str,
        category: str,
        benchmark_titles: list[str],
        learning_profile: dict | None = None,
    ) -> tuple[int, list[str]]:
        score = 70
        reasons = []
        length = len(title)
        forbidden_terms = [
            "성공 공식", "스토리텔링 비법", "벤치마킹", "패턴", "알고리즘",
            "콘텐츠", "조회수", "분석", "전략", "공식", "비결 분석",
            "스토리텔링", "연출", "노하우", "비법", "비밀", "해부", "황금률",
            "치트키", "필독", "마스터", "모든 것", "덕후", "팬덤",
            "명작", "망작", "작품", "시청자", "몰입감", "클리셰", "대공개", "법칙",
            "불문율", "반전 사연", "반전 스토리",
        ]
        hype_terms = ["충격", "소름", "레전드", "대박", "실화냐"]

        if 28 <= length <= 58:
            score += 12
            reasons.append("good_length")
        else:
            score -= abs(43 - length)
            reasons.append("length_penalty")

        if any(term in title for term in forbidden_terms):
            score -= 80
            reasons.append("meta_or_report_like_term")

        if category == "무협" and not any(term in title for term in ["무사", "검", "강호", "사부", "문파", "제자", "혈교", "마교", "비급", "복수", "천하", "고수"]):
            score -= 25
            reasons.append("not_martial_story_premise")

        hype_count = sum(1 for term in hype_terms if term in title)
        if hype_count:
            score -= 8 * hype_count
            reasons.append("hype_term_penalty")

        if re.search(r"\d", title):
            score += 5
            reasons.append("specific_detail")

        if any(token in title for token in ["왜", "뒤", "순간", "이유", "벌어진 일", "결국", "알게 된"]):
            score += 6
            reasons.append("curiosity_gap")

        if category and category in title:
            score += 3
            reasons.append("category_relevance")

        max_similarity = max([self._title_similarity(title, t) for t in benchmark_titles] or [0.0])
        if max_similarity >= 0.72:
            score -= 40
            reasons.append("too_similar_to_benchmark")
        elif max_similarity >= 0.55:
            score -= 15
            reasons.append("somewhat_similar_to_benchmark")

        learning_profile = learning_profile or {}
        failed_titles = learning_profile.get("failed_titles") or []
        successful_titles = learning_profile.get("successful_titles") or []
        failed_similarity = max([self._title_similarity(title, t) for t in failed_titles] or [0.0])
        success_similarity = max([self._title_similarity(title, t) for t in successful_titles] or [0.0])
        if failed_similarity >= 0.62:
            score -= 22
            reasons.append("too_similar_to_failed_memory")
        if 0.22 <= success_similarity <= 0.58:
            score += 7
            reasons.append("structurally_close_to_success_memory")
        elif success_similarity >= 0.72:
            score -= 12
            reasons.append("too_similar_to_success_memory")

        if title.endswith(("다", "요", "음")) and "?" not in title:
            score -= 4
            reasons.append("sentence_like_ending")

        return max(0, min(100, score)), reasons

    def _select_title_plan(
        self,
        raw_plan: dict,
        category: str,
        benchmark_titles: list[str],
        learning_profile: dict | None = None,
    ) -> dict:
        production_topic = self._clean_title_text(raw_plan.get("production_topic") or raw_plan.get("topic") or category)
        raw_candidates = raw_plan.get("title_candidates") or raw_plan.get("titles") or []
        if not isinstance(raw_candidates, list):
            raw_candidates = []

        scored = []
        seen = set()
        for item in raw_candidates:
            if isinstance(item, dict):
                title = self._clean_title_text(item.get("title"))
                angle = str(item.get("angle") or "").strip()
            else:
                title = self._clean_title_text(item)
                angle = ""
            if not title or title in seen or not self._is_usable_title_candidate(title, category):
                continue
            seen.add(title)
            score, reasons = self._score_title_candidate(title, category, benchmark_titles, learning_profile)
            scored.append({"title": title, "angle": angle, "score": score, "score_reasons": reasons})

        scored.sort(key=lambda item: item["score"], reverse=True)
        viable = [item for item in scored if item["score"] >= 35]
        if viable:
            scored = viable
        else:
            fallback = self._clean_title_text(self._category_fallback_title(category))
            score, reasons = self._score_title_candidate(fallback, category, benchmark_titles, learning_profile)
            scored = [{"title": fallback, "angle": "fallback_low_quality_candidates", "score": score, "score_reasons": reasons}]

        selected = scored[0]
        return {
            "production_topic": production_topic or selected["title"],
            "generated_title": selected["title"],
            "selected_score": selected["score"],
            "title_candidates": scored[:10],
            "raw_plan": raw_plan,
            "learning_profile": learning_profile or {},
        }

    def _category_title_style(self, category: str) -> str:
        styles = {
            "탈북사연": "Use a human survival-story frame: one person, a concrete danger or choice, emotional stakes, and a restrained documentary tone.",
            "해외감동": "Use an emotional true-story frame: unexpected kindness, a visible conflict, and a warm reversal without melodrama.",
            "노후금융": "Use a retirement-money frame: concrete amounts, everyday anxiety, a decision, and a credible result. Avoid investment-hype wording.",
            "황혼19금": "Use a mature-life relationship frame: loneliness, secret, regret, reunion, or late-life choice. Keep it suggestive but not explicit.",
            "옛날이야기": "Write an in-world folk tale premise only: begin with a character, place, object, or incident, then reveal the conflict. Never use the category label '옛날이야기' in a title. Never mention retelling, modern adaptation, MZ, Netflix, content success, or how to make a folk tale.",
            "한국사연": "Use a Korean real-life story frame: family conflict, sacrifice, betrayal, workplace or neighborhood detail, and emotional payoff.",
            "무협": "Use a martial-arts fiction frame: weak/abandoned protagonist, sect conflict, hidden skill, revenge or awakening. Keep it genre-native.",
            "경제": "Use an economy-explainer frame: specific money/market signal, personal consequence, and a question viewers need answered.",
        }
        return styles.get(category, "Use concrete human stakes, a natural Korean YouTube title rhythm, and a clear curiosity gap.")

    async def _ai_evaluate_title_plan(self, category: str, plan: dict, benchmark_titles: list[str]) -> dict:
        candidates = plan.get("title_candidates") or []
        if not candidates:
            return plan

        prompt = f"""
You are a strict Korean YouTube title editor.

Evaluate these candidate titles for:
1. natural Korean YouTube phrasing
2. click desire
3. fit with the production topic and category
4. low plagiarism risk against benchmark titles
5. low overpromise/clickbait risk

CATEGORY: {category}
CATEGORY STYLE: {self._category_title_style(category)}
PRODUCTION TOPIC: {plan.get("production_topic")}
BENCHMARK TITLES: {json.dumps(benchmark_titles, ensure_ascii=False)}
LEARNING MEMORY: {json.dumps(plan.get("learning_profile") or {}, ensure_ascii=False)}
CANDIDATES: {json.dumps(candidates, ensure_ascii=False)}

Return ONLY JSON:
{{
  "evaluations": [
    {{"title": "same candidate title", "ai_score": 0, "reason": "short reason", "risk": "low|medium|high"}}
  ],
  "best_title": "exact title from candidates"
}}
"""
        try:
            from config import config as app_config
            model = app_config.TITLE_GENERATION_MODEL or app_config.TOPIC_GENERATION_MODEL or "gemini-2.5-flash"
            raw_text = await ai_router.generate_text(
                prompt,
                model=model,
                temperature=0.25,
                max_tokens=2000,
                task_type="hermes_autopilot_title_eval",
            )
            evaluation = self._extract_json_object(raw_text)
        except Exception as e:
            plan["evaluation_error"] = str(e)
            return plan

        by_title = {
            self._clean_title_text(item.get("title")): item
            for item in evaluation.get("evaluations", [])
            if isinstance(item, dict)
        }
        for candidate in candidates:
            ai_item = by_title.get(candidate["title"])
            if not ai_item:
                continue
            try:
                ai_score = max(0, min(100, int(ai_item.get("ai_score", 0))))
            except (TypeError, ValueError):
                ai_score = 0
            candidate["ai_score"] = ai_score
            candidate["ai_reason"] = str(ai_item.get("reason") or "").strip()
            candidate["risk"] = str(ai_item.get("risk") or "").strip()
            risk_penalty = 12 if candidate["risk"] == "high" else 5 if candidate["risk"] == "medium" else 0
            candidate["final_score"] = round(candidate["score"] * 0.45 + ai_score * 0.55 - risk_penalty, 2)

        for candidate in candidates:
            candidate.setdefault("final_score", candidate["score"])

        best_title = self._clean_title_text(evaluation.get("best_title"))
        candidates.sort(key=lambda item: (item.get("final_score", 0), item.get("score", 0)), reverse=True)
        selected = next((item for item in candidates if item["title"] == best_title), candidates[0])
        plan["generated_title"] = selected["title"]
        plan["selected_score"] = selected.get("final_score", selected.get("score", 0))
        plan["title_candidates"] = candidates[:10]
        plan["ai_evaluation"] = evaluation
        return plan

    async def _validate_title_against_script(self, category: str, title_plan: dict, script_text: str) -> dict:
        current_title = title_plan.get("generated_title") or ""
        candidates = title_plan.get("title_candidates") or []
        script_preview = (script_text or "")[:6000]
        prompt = f"""
You are a strict Korean YouTube metadata QA editor.

Check whether the selected upload title honestly matches the generated script.

CATEGORY: {category}
PRODUCTION TOPIC: {title_plan.get("production_topic")}
SELECTED TITLE: {current_title}
OTHER CANDIDATES: {json.dumps(candidates, ensure_ascii=False)}
SCRIPT PREVIEW:
{script_preview}

Rules:
- If the title promises a fact, twist, money amount, relationship, event, or reveal that the script does not support, status must be "revise".
- Prefer an existing candidate when it fits the script better.
- If you suggest a new title, keep it natural Korean and 28-58 characters.

Return ONLY JSON:
{{
  "status": "pass|revise",
  "title": "final title",
  "reason": "short Korean reason"
}}
"""
        try:
            from config import config as app_config
            model = app_config.TITLE_GENERATION_MODEL or app_config.TOPIC_GENERATION_MODEL or "gemini-2.5-flash"
            raw_text = await ai_router.generate_text(
                prompt,
                model=model,
                temperature=0.2,
                max_tokens=1000,
                task_type="hermes_autopilot_title_script_fit",
            )
            result = self._extract_json_object(raw_text)
        except Exception as e:
            title_plan["script_fit_error"] = str(e)
            return title_plan

        proposed_title = self._clean_title_text(result.get("title") or current_title)
        if result.get("status") == "revise" and proposed_title and self._is_usable_title_candidate(proposed_title, category):
            candidate_titles = [item.get("title") for item in candidates]
            if proposed_title not in candidate_titles:
                score, reasons = self._score_title_candidate(proposed_title, category, candidate_titles)
                candidates.append({
                    "title": proposed_title,
                    "angle": "script_fit_revision",
                    "score": score,
                    "final_score": score,
                    "score_reasons": reasons,
                })
            title_plan["generated_title"] = proposed_title
            title_plan["selected_score"] = next(
                (item.get("final_score", item.get("score", 0)) for item in candidates if item.get("title") == proposed_title),
                title_plan.get("selected_score", 0),
            )

        title_plan["title_candidates"] = candidates[:10]
        title_plan["script_fit"] = result
        return title_plan

    async def _fetch_learning_profile(
        self,
        supabase_url: str,
        headers: dict,
        category_id: str | None,
        category: str,
    ) -> dict:
        if not supabase_url or not headers.get("apikey"):
            return {}

        params = {
            "select": "generated_title,production_topic,title_score,script_score,outcome_quality,feedback_source,metrics,evaluation,created_at",
            "order": "created_at.desc",
            "limit": "30",
        }
        if category_id:
            params["category_id"] = f"eq.{category_id}"
        else:
            params["category_name"] = f"eq.{category}"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{supabase_url}/rest/v1/content_generation_feedback",
                    headers=headers,
                    params=params,
                )
            if response.status_code != 200:
                self.add_log(f"Learning memory unavailable (status={response.status_code}): {response.text[:160]}")
                return {}
            rows = response.json()
        except Exception as e:
            self.add_log(f"Learning memory fetch failed (ignored): {e}")
            return {}

        successful_titles = []
        failed_titles = []
        for row in rows or []:
            title = str(row.get("generated_title") or "").strip()
            if not title:
                continue
            title_score = float(row.get("title_score") or 0)
            script_score = float(row.get("script_score") or 0)
            blended = title_score * 0.45 + script_score * 0.55
            quality = row.get("outcome_quality")
            if quality in ("excellent", "good") or blended >= 75:
                successful_titles.append(title)
            elif quality in ("poor", "rejected") or blended < 55:
                failed_titles.append(title)

        return {
            "sample_count": len(rows or []),
            "successful_titles": successful_titles[:8],
            "failed_titles": failed_titles[:8],
            "recent_feedback": [
                {
                    "title": row.get("generated_title"),
                    "quality": row.get("outcome_quality"),
                    "title_score": row.get("title_score"),
                    "script_score": row.get("script_score"),
                    "source": row.get("feedback_source"),
                    "metrics": row.get("metrics") or {},
                }
                for row in (rows or [])[:10]
            ],
        }

    async def _generate_topic_title_plan(
        self,
        category: str,
        candidates: list[dict],
        learning_profile: dict | None = None,
    ) -> dict:
        compact_candidates = []
        for candidate in candidates[:3]:
            compact_candidates.append({
                "title": candidate.get("title", ""),
                "view_count": candidate.get("view_count", 0),
                "subscriber_count": candidate.get("subscriber_count", 0),
                "performance_ratio": candidate.get("performance_ratio", 0.0),
                "analysis": candidate.get("analysis", {}),
                "success_strategies": candidate.get("success_strategies", []),
            })

        benchmark_titles = [item.get("title", "") for item in compact_candidates if item.get("title")]
        category_style = self._category_title_style(category)
        learning_profile = learning_profile or {}
        prompt = f"""
You are a senior Korean YouTube title strategist.

Create a production topic and multiple upload-title candidates for an AI-generated longform Korean video.

CATEGORY:
{category}

CATEGORY-SPECIFIC TITLE STYLE:
{category_style}

BENCHMARK VIDEOS TO LEARN FROM:
{json.dumps(compact_candidates, ensure_ascii=False)}

LEARNING MEMORY FROM PREVIOUS GENERATED OUTPUTS:
{json.dumps(learning_profile, ensure_ascii=False)}

Rules:
- Separate the production topic from the upload title.
- production_topic must be plain and useful for script generation, not a clickbait title.
- Generate 10 Korean upload title candidates.
- Titles must sound like real Korean YouTube titles, not reports or analysis memos.
- Do not copy benchmark titles, names, exact incidents, or phrasing.
- Avoid these words and phrases in titles: 성공 공식, 스토리텔링, 벤치마킹, 패턴, 황금 패턴, 비밀, 비결, 반전 사연, 반전 스토리, 알고리즘, 콘텐츠, 조회수, 분석, 전략, 공식, 연출, 노하우, 해부, 대공개, 법칙, 불문율.
- Never write creator-education, writing-advice, critique, or "how to make good stories" titles. The title must be the title of the fictional/story video itself.
- For the 옛날이야기 category, never write the words 옛날이야기, 전래동화, MZ, 넷플릭스, 재해석, or K-콘텐츠 in a title. Title the incident itself, such as a character's choice, a village conflict, a hidden object, or a consequence.
- For martial-arts fiction, titles must describe an in-world premise: a martial artist, sect, master, secret manual, betrayal, revenge, awakening, or Jianghu incident.
- Prefer concrete situations, human stakes, curiosity, and a natural documentary/story tone.
- Keep titles roughly 28-58 Korean characters.
- Use successful learning-memory titles only as structural inspiration; do not copy their wording.
- Avoid title shapes that are similar to failed or rejected learning-memory titles.

Return ONLY valid JSON in this schema:
{{
  "production_topic": "담백한 제작 주제",
  "title_candidates": [
    {{"title": "업로드 제목 후보", "angle": "why it may work"}}
  ]
}}
"""
        from config import config as app_config
        model = app_config.TITLE_GENERATION_MODEL or app_config.TOPIC_GENERATION_MODEL or "gemini-2.5-flash"
        raw_text = await ai_router.generate_text(
            prompt,
            model=model,
            temperature=0.85,
            max_tokens=2500,
            task_type="hermes_autopilot_title_gen",
        )
        raw_plan = self._extract_json_object(raw_text)
        plan = self._select_title_plan(raw_plan, category, benchmark_titles, learning_profile)
        plan["category_style"] = category_style
        return await self._ai_evaluate_title_plan(category, plan, benchmark_titles)

    def _available_image_styles(self) -> list[dict]:
        """Read the Worker-managed image styles without inventing style keys."""
        try:
            from services.web_admin_client import web_admin_client
            remote = web_admin_client.fetch_style_presets(["image"])
            if remote:
                return remote
        except Exception as e:
            logger.warning(f"Image style catalog sync failed; using local cache: {e}")

        try:
            import database as db
            local = db.get_style_presets()
            return [
                {
                    "key_code": key,
                    "display_name_ko": value.get("display_name_ko") or key,
                    "prompt_template": value.get("prompt_value") or "",
                    "gemini_instruction": value.get("gemini_instruction") or "",
                }
                for key, value in local.items()
            ]
        except Exception as e:
            logger.warning(f"Local image style catalog unavailable: {e}")
            return []

    async def _select_image_style(
        self,
        category: str,
        production_topic: str,
        upload_title: str,
        category_default: str,
        manual_override: str | None = None,
    ) -> dict:
        """Select one existing visual style for a generated video.

        The model may choose only from the Worker style catalog.  A category
        default remains the fallback so a temporary AI/API failure never
        leaves the topic without a usable visual direction.
        """
        styles = self._available_image_styles()
        by_key = {str(item.get("key_code") or "").strip().lower(): item for item in styles}
        by_key = {key: item for key, item in by_key.items() if key}
        manual_override = str(manual_override or "").strip().lower()
        if manual_override and manual_override in by_key:
            return {
                "assigned_image_style": manual_override,
                "automatic_style": None,
                "selection_source": "worker_manual_override",
                "reason": "Worker에서 수동 지정한 카테고리 이미지 스타일을 우선 적용합니다.",
            }
        fallback = str(category_default or "").strip().lower()
        if fallback not in by_key:
            fallback = "realistic" if "realistic" in by_key else next(iter(by_key), "realistic")
        if not by_key:
            return {
                "assigned_image_style": fallback,
                "automatic_style": fallback,
                "selection_source": "fallback",
                "reason": "등록된 이미지 스타일 목록을 읽지 못해 카테고리 기본값을 사용합니다.",
            }

        catalog = [
            {
                "key": key,
                "name": item.get("display_name_ko") or key,
                "description": str(item.get("prompt_template") or "")[:260],
            }
            for key, item in by_key.items()
        ]
        prompt = f"""
You are a visual director for a Korean YouTube longform video.
Choose exactly one visual style for this specific video from the provided catalog.
Do not invent a key. Do not default to realistic merely because it is safe.
Use the category default as a strong prior, but override it only when the title's era, genre, and emotional tone clearly need a different existing style.

CATEGORY: {category}
CATEGORY DEFAULT STYLE: {fallback}
PRODUCTION TOPIC: {production_topic}
UPLOAD TITLE: {upload_title}

AVAILABLE STYLE CATALOG:
{json.dumps(catalog, ensure_ascii=False)}

Return ONLY JSON:
{{"style_key":"one catalog key", "reason":"short Korean reason"}}
""".strip()
        try:
            from config import config as app_config
            model = app_config.TITLE_GENERATION_MODEL or app_config.TOPIC_GENERATION_MODEL or "gemini-2.5-flash"
            raw = await ai_router.generate_text(
                prompt,
                model=model,
                temperature=0.2,
                max_tokens=500,
                task_type="hermes_image_style_select",
            )
            selected = self._extract_json_object(raw)
            style_key = str(selected.get("style_key") or "").strip().lower()
            if style_key not in by_key:
                raise ValueError(f"invalid image style key: {style_key!r}")
            return {
                "assigned_image_style": style_key,
                "automatic_style": style_key,
                "selection_source": "ai_catalog_selection",
                "reason": str(selected.get("reason") or "AI가 영상의 장르와 정서에 맞춰 선택했습니다.").strip()[:300],
                "category_default": fallback,
            }
        except Exception as e:
            logger.warning(f"Image style selection failed; using category default '{fallback}': {e}")
            return {
                "assigned_image_style": fallback,
                "automatic_style": fallback,
                "selection_source": "category_default_fallback",
                "reason": "스타일 자동 선택을 완료하지 못해 카테고리 기본 스타일을 사용합니다.",
                "category_default": fallback,
            }

    async def _run_loop(self):
        try:
            self.add_log("오토파일럿 백그라운드 태스크가 성공적으로 기동되었습니다.")
            idx = 0
            
            while self.is_running:
                active_cats = self._normalize_active_categories(
                    self.settings.get("active_categories", CATEGORIES)
                )
                self.settings["active_categories"] = active_cats
                if not active_cats:
                    self.add_log("No active categories configured. Autopilot stopped.")
                    break

                category = active_cats[idx % len(active_cats)]
                idx += 1
                
                # 활성 카테고리 체크
                active_cats = self.settings.get("active_categories", CATEGORIES)
                if category not in active_cats:
                    logger.info(f"카테고리 '{category}'는 설정에서 비활성화되어 있어 스킵합니다.")
                    await asyncio.sleep(0.5)
                    continue
                
                self.current_category = category
                self.current_step = f"[{category}] 유튜브 탐색 준비"
                self.add_log(f"==================================================")
                self.add_log(f"카테고리 '{category}'의 생성 루프 시작")
                
                try:
                    await self._process_category(category)
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    self.add_log(f"❌ 카테고리 '{category}' 처리 중 에러 발생: {e}")
                    logger.error(traceback.format_exc())
                    await asyncio.sleep(5.0)  # 에러 발생 시 잠시 대기
                
                # 다음 카테고리 시작 전 짧은 간격
                await asyncio.sleep(3.0)

        except asyncio.CancelledError:
            self.add_log("오토파일럿 루프가 취소되었습니다. 정지 완료.")
        finally:
            self.is_running = False
            self.current_step = "stopped"
            self._save_state()

    async def _process_category(self, category: str):
        # 0. Supabase URL 및 키 읽기
        supabase_url = (os.getenv("NEXT_PUBLIC_SUPABASE_URL") or "").rstrip("/")
        supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or ""
        
        headers = {
            "apikey": supabase_key,
            "Authorization": f"Bearer {supabase_key}",
            "Content-Type": "application/json"
        }
        
        # categories 테이블에서 ID 확인 시도
        category_id = None
        # The category's default style is the authoritative choice for
        # automatic production. Carry it through the queue row, plan, and
        # script jobs instead of silently forcing every category to default.
        category_script_style = "default"
        category_image_style = "realistic"
        if supabase_url and supabase_key:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    r = await client.get(
                        f"{supabase_url}/rest/v1/categories?select=id,name,default_script_style,default_image_style",
                        headers=headers
                    )
                    if r.status_code == 200:
                        cats = r.json()
                        for c in cats:
                            if c.get("name") == category:
                                category_id = c.get("id")
                                category_script_style = str(c.get("default_script_style") or "default").strip() or "default"
                                category_image_style = str(c.get("default_image_style") or "realistic").strip() or "realistic"
                                break
            except Exception as e:
                self.add_log(f"Supabase 카테고리 ID 조회 실패 (무시): {e}")

        # [신규] 카테고리별 최소 대기주제 유지량(min_buffer_per_category) 검사
        if supabase_url and supabase_key and category_id:
            try:
                min_buffer = self.settings.get("min_buffer_per_category", 5)
                async with httpx.AsyncClient(timeout=10.0) as client:
                    # Count only topics that the user app can actually expose:
                    # plan ready + script ready + scene image/video prompts ready.
                    r = await client.get(
                        f"{supabase_url}/rest/v1/topics_queue?select=id,pregenerated_structure,pregenerated_script"
                        f"&category_id=eq.{category_id}"
                        f"&status=eq.pending"
                        f"&pregenerated_structure_status=eq.ready"
                        f"&pregenerated_script_status=eq.ready"
                        f"&pregenerated_structure=not.is.null"
                        f"&pregenerated_script=not.is.null",
                        headers=headers
                    )
                    if r.status_code == 200:
                        existing_rows = r.json()
                        existing_pregens = [
                            row for row in existing_rows
                            if self._has_ready_media_prompts(row.get("pregenerated_structure"))
                            and str(row.get("pregenerated_script") or "").strip()
                        ]
                        if len(existing_pregens) >= min_buffer:
                            self.add_log(f"📋 '{category}' 카테고리는 이미 노출 가능한 준비 완료 주제가 {len(existing_pregens)}개 존재합니다. (설정 유지량: {min_buffer}개)")
                            self.add_log("목표 개수를 충족하여 생성을 생략합니다.")
                            return
            except Exception as e:
                self.add_log(f"Supabase 대기주제 개수 조회 실패 (무시하고 진행): {e}")

        # Do not persist a category-name placeholder.  Exploration can use a
        # local correlation ID; the real queue row is created only after title QA.
        topic_queue_id = f"local-auto-{int(time.time())}"
        self.add_log(f"적용 대본 스타일: {category_script_style}")

        # 2. 유튜브 탐색 및 분석 실행
        self.current_step = "유튜브 탐색 및 고성과 분석"
        self.add_log(f"유튜브에서 '{category}' 관련 인기 영상 탐색 시작...")
        
        benchmark_job_id = job_store.submit_job(
            job_type="topic_benchmark_analyze",
            payload={
                "keyword": category,
                "language": "ko",
                "video_type": "longform",
                "max_candidates": 3,
                "search_pool_size": 20,
                "topic_queue_id": topic_queue_id
            },
            priority=100,
            source="autopilot"
        )
        self.add_log(f"-> topic_benchmark_analyze 작업 제출 완료 (Job ID: {benchmark_job_id})")
        
        # 작업 완료 대기
        await self._wait_for_job(benchmark_job_id)
        
        # 결과 읽기
        result_data = self._read_result_file(benchmark_job_id)
        if not result_data or "candidates" not in result_data or not result_data["candidates"]:
            raise RuntimeError("유튜브 벤치마크 탐색 결과 분석 데이터가 유효하지 않습니다.")
            
        candidates = result_data["candidates"]
        audit_path = result_data.get("audit_path")
        audit_summary = result_data.get("audit_summary") or {}
        best_candidate = candidates[0]
        video_title = best_candidate.get("title", "")
        performance_ratio = best_candidate.get("performance_ratio", 0.0)
        self.add_log(f"📈 벤치마크 탐색 완료: 대본 기획에 참조할 영상 {len(candidates)}개")
        for index, candidate in enumerate(candidates, start=1):
            if not _is_real_youtube_candidate(candidate):
                self.add_log(f"⚠️ 참조 영상 #{index}: 실제 YouTube 영상을 찾지 못해 대체값이 반환되었습니다. 이 결과로 생성하지 않습니다.")
                raise RuntimeError("실제 YouTube 참조 영상을 확보하지 못했습니다.")
            if candidate.get("performance_data_source") != "youtube_api":
                self.add_log(f"⚠️ 참조 영상 #{index}: YouTube 조회수 통계를 확인하지 못했습니다. 임의 성과 수치로는 생성하지 않습니다.")
                raise RuntimeError("실제 YouTube 성과 통계를 확보하지 못했습니다.")
            video_id = candidate.get("video_id")
            self.add_log(f"📺 참조 영상 #{index}: {candidate.get('title') or '(제목 없음)'}")
            self.add_log(
                f"   채널: {candidate.get('channel_title') or '확인 불가'} | "
                f"조회수: {_format_view_count(candidate.get('view_count'))} | "
                f"구독자 대비: {candidate.get('performance_ratio', 0)}배"
            )
            self.add_log(f"   URL: https://www.youtube.com/watch?v={video_id}")
        self.add_log(f"✅ 대표 참조 영상: '{video_title}' (구독자 대비 조회수 {performance_ratio}배)")

        # 3. AI 기반 새로운 영상 제목(주제) 도출
        self.current_step = "신규 오리지널 영상 주제 도출"
        self.add_log("학습된 벤치마크 분석 내용을 토대로 신규 유튜브 제목 기획 중...")
        
        
        learning_profile = await self._fetch_learning_profile(
            supabase_url,
            headers,
            str(category_id) if category_id else None,
            category,
        )
        if learning_profile.get("sample_count"):
            self.add_log(f"Learning memory loaded: {learning_profile['sample_count']} prior feedback row(s)")
        title_plan = await self._generate_topic_title_plan(category, candidates, learning_profile)
        new_topic = title_plan["production_topic"]
        generated_title = title_plan["generated_title"]
        if not self._is_usable_title_candidate(generated_title, category):
            raise RuntimeError(f"Title QA rejected generated upload title: {generated_title!r}")
        if not self._is_usable_title_candidate(new_topic, category):
            new_topic = generated_title
        self.current_step = "Gemini 웹 자료 조사"
        self.add_log(f"🔎 Gemini 웹 검색으로 '{generated_title}' 대본 자료를 조사합니다.")
        research_job_id = job_store.submit_job(
            job_type="web_research",
            payload={"category": category, "topic": new_topic, "upload_title": generated_title},
            priority=100,
            source="autopilot",
        )
        await self._wait_for_job(research_job_id)
        research_result = self._read_result_file(research_job_id) or {}
        research_bundle = research_result.get("research_bundle") or {}
        research_sources = research_bundle.get("sources") or []
        if not research_sources:
            raise RuntimeError("Gemini 웹 조사 결과에 검증 가능한 출처가 없습니다.")
        self.add_log(f"📚 Gemini 웹 자료 조사 완료: 출처 {len(research_sources)}개")
        for source in research_sources:
            self.add_log(f"   자료: {source.get('title') or '(제목 없음)'} | {source.get('url')}")
        manual_image_style = (self.settings.get("category_image_style_overrides") or {}).get(category)
        image_style_plan = await self._select_image_style(
            category, new_topic, generated_title, category_image_style, manual_image_style
        )
        assigned_image_style = image_style_plan["assigned_image_style"]
        self.current_image_style = assigned_image_style
        self.add_log(
            f"이미지 스타일 확정: {assigned_image_style} "
            f"({image_style_plan.get('selection_source')}) - {image_style_plan.get('reason')}"
        )
        benchmark_payload = {
            "benchmark_job_id": benchmark_job_id,
            "audit_path": audit_path,
            "audit_summary": audit_summary,
            "candidates": candidates,
            "selected_candidate": best_candidate,
            "web_research": research_bundle,
            "title_generation": title_plan,
            "image_style_selection": image_style_plan,
        }
        self.current_topic = new_topic
        self.add_log(f"✨ AI 기획 신규 오리지널 주제: '{new_topic}'")
        self.add_log(f"AI title selected: '{generated_title}' (score={title_plan['selected_score']})")

        # Persist only a QA-approved real upload title.  `production_topic`
        # remains in title_generation for script planning, never as the UI title.
        if supabase_url and supabase_key:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    row_data = {
                        "topic": generated_title,
                        "assigned_employee_email": "hermes_worker@local",
                        "language": "ko",
                        "status": "pending",
                        "is_auto_generated": True,
                        "pregenerated_structure_status": "queued",
                        "pregenerated_script_status": "queued",
                        "benchmark_analysis": benchmark_payload,
                        "generated_title": generated_title,
                        "title_candidates": title_plan["title_candidates"],
                        "assigned_script_style": category_script_style,
                        "assigned_image_style": assigned_image_style,
                    }
                    if category_id:
                        row_data["category_id"] = category_id
                    r = await client.post(
                        f"{supabase_url}/rest/v1/topics_queue",
                        headers={**headers, "Prefer": "return=representation"},
                        json=row_data,
                    )
                    if r.status_code not in (200, 204):
                        raise RuntimeError(f"Supabase approved topic insert failed: {r.status_code} {r.text[:200]}")
                    response_rows = r.json()
                    topic_queue_id = response_rows[0].get("id") if isinstance(response_rows, list) else response_rows.get("id")
                    if not topic_queue_id:
                        raise RuntimeError("Supabase approved topic insert did not return an ID")
                    self.add_log(f"Supabase: 검증된 업로드 제목 '{generated_title}' 등록 완료")
            except Exception as e:
                self.add_log(f"Supabase 검증 제목 등록 실패: {e}")
                raise

        # 4. 구조 및 씬 기획 생성
        self.current_step = "대본 구조 및 씬 기획"
        self.add_log(f"주제 '{new_topic}'에 대한 씬 구조(Scene Plan) 생성 시작...")
        
        plan_job_id = job_store.submit_job(
            job_type="script_plan_generate",
            payload={
                "topic_queue_id": topic_queue_id,
                "topic": new_topic,
                "target_duration_seconds": 600,
                "script_style": category_script_style,
                "image_style": assigned_image_style,
                "image_style_selection": image_style_plan,
                "language": "ko",
                "benchmark_analysis": {**(best_candidate.get("analysis") or best_candidate), "web_research": research_bundle},
                "upload_title": generated_title,
                "title_generation": title_plan,
                "research_bundle": research_bundle,
            },
            priority=100,
            source="autopilot"
        )
        self.add_log(f"-> script_plan_generate 작업 제출 완료 (Job ID: {plan_job_id})")
        
        await self._wait_for_job(plan_job_id)
        
        plan_data = self._read_result_file(plan_job_id)
        if not plan_data or "structure" not in plan_data:
            raise RuntimeError("대본 구조 생성 데이터가 유효하지 않습니다.")
            
        structure = plan_data["structure"]
        scene_count = structure.get("scene_count", 0)
        self.add_log(f"📋 대본 구조 기획 성공. 총 {scene_count}개 씬 분할")

        # Supabase에 구조 동기화
        if supabase_url and supabase_key and topic_queue_id:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    r = await client.patch(
                        f"{supabase_url}/rest/v1/topics_queue?id=eq.{topic_queue_id}",
                        headers={**headers, "Prefer": "return=minimal"},
                        json={
                            "pregenerated_structure": structure,
                            "pregenerated_structure_status": "ready",
                            "total_scenes": scene_count
                        }
                    )
                    if r.status_code in (200, 204):
                        self.add_log("Supabase: 대본 구조 및 상태 동기화 완료")
            except Exception as e:
                self.add_log(f"Supabase 대본 구조 동기화 실패: {e}")

        # 5. 최종 대본 텍스트 생성
        self.current_step = "나레이션 대본 집필"
        self.add_log(f"씬 구조를 바탕으로 나레이션 본문 생성 중...")
        
        script_job_id = job_store.submit_job(
            job_type="script_generate",
            payload={
                "topic_queue_id": topic_queue_id,
                "topic": new_topic,
                "structure": structure,
                "target_duration_seconds": 600,
                "script_style": category_script_style,
                "image_style": assigned_image_style,
                "image_style_selection": image_style_plan,
                "language": "ko",
                "narration_mode": "dramatic_single",
                "upload_title": generated_title,
                "title_generation": title_plan,
            },
            priority=100,
            source="autopilot"
        )
        self.add_log(f"-> script_generate 작업 제출 완료 (Job ID: {script_job_id})")
        
        await self._wait_for_job(script_job_id)
        
        script_data = self._read_result_file(script_job_id)
        if not script_data or "script" not in script_data:
            raise RuntimeError("대본 생성 본문 데이터가 유효하지 않습니다.")
            
        final_script = script_data["script"]
        narrative_blueprint = script_data.get("narrative_blueprint")
        script_quality_report = script_data.get("script_quality_report")
        char_count = len(final_script)
        self.add_log(f"✍️ 최종 대본 집필 완료 (총 글자수: {char_count}자)")

        title_plan = await self._validate_title_against_script(category, title_plan, final_script)
        generated_title = title_plan["generated_title"]
        benchmark_payload["title_generation"] = title_plan
        self.add_log(f"Script-fit title: '{generated_title}'")

        # Supabase에 최종 대본 동기화 및 큐 완료 처리
        if supabase_url and supabase_key and topic_queue_id:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    r = await client.patch(
                        f"{supabase_url}/rest/v1/topics_queue?id=eq.{topic_queue_id}",
                        headers={**headers, "Prefer": "return=minimal"},
                        json={
                            "topic": generated_title,
                            "pregenerated_script": final_script,
                            "pregenerated_script_status": "ready",
                            "generated_title": generated_title,
                            "title_candidates": title_plan["title_candidates"],
                            "benchmark_analysis": benchmark_payload,
                            "narrative_blueprint": narrative_blueprint,
                            "script_quality_report": script_quality_report,
                            "status": "pending"
                        }
                    )
                    if r.status_code not in (200, 204):
                        r = await client.patch(
                            f"{supabase_url}/rest/v1/topics_queue?id=eq.{topic_queue_id}",
                            headers={**headers, "Prefer": "return=minimal"},
                            json={
                                "topic": generated_title,
                                "pregenerated_script": final_script,
                                "pregenerated_script_status": "ready",
                                "generated_title": generated_title,
                                "title_candidates": title_plan["title_candidates"],
                                "benchmark_analysis": benchmark_payload,
                                "status": "pending"
                            }
                        )
                    if r.status_code in (200, 204):
                        self.add_log("Supabase: 대본 본문 및 상태(completed) 동기화 완료")
            except Exception as e:
                self.add_log(f"Supabase 대본 본문 동기화 실패: {e}")

        # 6. 로컬에 종합 최종 결과물 저장
        self.current_step = "로컬 저장 완료"
        self.add_log("종합 데이터를 로컬 결과 디렉토리에 백업 중...")
        
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        local_result_path = RESULTS_DIR / f"{topic_queue_id}.json"
        
        summary_payload = {
            "topic_queue_id": topic_queue_id,
            "category": category,
            "original_benchmark_title": video_title,
            "performance_ratio": performance_ratio,
            "benchmark_analysis": benchmark_payload,
            "benchmark_job_id": benchmark_job_id,
            "benchmark_audit_path": audit_path,
            "benchmark_audit_summary": audit_summary,
            "generated_topic": new_topic,
            "generated_title": generated_title,
            "title_candidates": title_plan["title_candidates"],
            "narrative_blueprint": narrative_blueprint,
            "script_quality_report": script_quality_report,
            "structure": structure,
            "script": final_script,
            "char_count": char_count,
            "completed_at": time.time()
        }
        
        local_result_path.write_text(
            json.dumps(summary_payload, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        self.add_log(f"💾 로컬 백업 완료: {local_result_path}")
        self.add_log(f"🎉 '{category}' 카테고리의 1회차 자동 생성 완료!")

        # 세션 통계 및 목표 도달 점검
        self.session_stats["generated_count"] += 1
        self._save_state()
        
        mode = self.settings.get("mode", "infinite")
        limit = self.settings.get("target_limit", 10)
        generated = self.session_stats["generated_count"]
        
        if mode == "target_limit" and generated >= limit:
            self.add_log(f"🏁 설정된 목표 생성 총량({limit}개)에 도달했습니다. (현재 생성량: {generated}개)")
            self.is_running = False
            self.current_step = "stopped"
            self._save_state()

    async def _wait_for_job(self, job_id: str):
        """Waits until the job state is COMPLETED, FAILED or CANCELED."""
        self.add_log(f"작업({job_id}) 처리 대기 시작...")
        
        while self.is_running:
            job = job_store.get_job(job_id)
            if not job:
                raise RuntimeError(f"작업({job_id})을 job_store에서 찾을 수 없습니다.")
                
            status = job.get("status")
            progress = job.get("progress", 0)
            progress_msg = job.get("progress_message", "")
            
            if status == "COMPLETED":
                self.add_log(f"작업 완료: {job_id}")
                return
            elif status in ("FAILED", "CANCELED"):
                err_msg = job.get("error_message") or "알 수 없는 에러"
                raise RuntimeError(f"작업({job_id})이 실패/취소되었습니다. 상태: {status}, 원인: {err_msg}")
                
            # 진행 상태 로그 노출
            step_desc = f"진행률 {progress}%"
            if progress_msg:
                step_desc += f" ({progress_msg})"
            self.current_step = f"Hermes 작업 처리 중 ({step_desc})"
            
            await asyncio.sleep(3.0)
            
        # 루프가 정지된 경우 취소 에러 발생
        raise asyncio.CancelledError()

    def _read_result_file(self, job_id: str) -> dict | None:
        """Reads result JSON file from hermes_results folder."""
        result_path = OUTPUT_DIR / "hermes_results" / f"{job_id}.json"
        if result_path.exists():
            try:
                return json.loads(result_path.read_text(encoding="utf-8"))
            except Exception as e:
                logger.error(f"Failed to read result file {result_path}: {e}")
        return None
