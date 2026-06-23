import os
import time
import json
import requests
import threading
from config import config
from services.gemini_service import gemini_service
import database as db


# Dynamic EMPLOYEE_PERSONAS handled via Supabase profiles table

SUPPORTED_CONTENT_LANGUAGES = {"ko", "en", "ja"}


def normalize_content_language(value, default="ko"):
    lang = (str(value or "").strip().lower() or default)
    if lang.startswith("en"):
        return "en"
    if lang.startswith("ja") or lang.startswith("jp"):
        return "ja"
    if lang.startswith("ko"):
        return "ko"
    return default


def content_language_label(value):
    lang = normalize_content_language(value)
    return {"ko": "Korean", "en": "English", "ja": "Japanese"}.get(lang, "Korean")


def topic_language_instruction(value):
    lang = normalize_content_language(value)
    if lang == "en":
        return "The topic MUST be written in natural English. Do not mix Korean or Japanese unless it is an unavoidable proper noun."
    if lang == "ja":
        return "The topic MUST be written in natural Japanese. Do not include Korean sentence fragments."
    return "The topic MUST be written in natural Korean."


class DispatcherService:
    def __init__(self):
        self.running = False
        self.thread = None
        self.interval = 3600  # 1시간 간격 실행
        self.auth_server_url = os.getenv("DASHBOARD_URL", "https://mytube-ashy-seven.vercel.app")
        # Antigravity SDK 모니터링/스케줄러 상태
        self.dispatcher_lock = threading.Lock()

    def get_license_key(self):
        if os.path.exists("license.key"):
            with open("license.key", "r") as f:
                return f.read().strip()
        return None

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        print("[Dispatcher] Smart Dispatcher service started (Every 1 hour).")

    def stop(self):
        self.running = False

    def _run(self):
        while self.running:
            try:
                self.dispatch_daily_topics()
            except Exception as e:
                print(f"[Dispatcher Error] Dispatch runner exception: {e}")
            time.sleep(self.interval)

    def dispatch_daily_topics(self):
        """[SDK] Antigravity SDK 스케줄러 기반: 트렌드 분석 후 가용 직원 자동 배정 실행"""
        if not self.dispatcher_lock.acquire(blocking=False):
            return
            
        try:
            print("[Dispatcher] Starting automated trend search & employee load matching...")
            supabase_url = os.getenv("NEXT_PUBLIC_SUPABASE_URL")
            supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
            if not supabase_url or not supabase_key:
                print("[Dispatcher Warning] Supabase credentials missing. Auto Dispatcher aborted.")
                return

            headers = {
                "apikey": supabase_key,
                "Authorization": f"Bearer {supabase_key}",
                "Content-Type": "application/json"
            }

            # 1. 원격 Supabase 카테고리 목록 읽기
            cat_res = requests.get(f"{supabase_url}/rest/v1/categories?select=*", headers=headers, timeout=10)
            if cat_res.status_code != 200:
                print(f"[Dispatcher Error] Failed to fetch remote categories: {cat_res.text}")
                return

            categories = cat_res.json()
            if not categories:
                print("[Dispatcher] No categories found for dispatching.")
                return

            # 2. 원격 Supabase 유저 프로필 및 활성 프로젝트 로드
            user_res = requests.get(f"{supabase_url}/rest/v1/profiles?select=*", headers=headers, timeout=10)
            if user_res.status_code != 200:
                print(f"[Dispatcher Error] Failed to fetch user profiles: {user_res.text}")
                return
            users = user_res.json()

            # 직원별 활성 프로젝트 수(워크로드) 구하기
            workloads = {}
            for user in users:
                email = user.get("email")
                if not email:
                    continue
                # Supabase의 topics_queue에서 현재 담당 직원이고 status가 pending 혹은 assigned인 개수 합산
                assigned_res = requests.get(f"{supabase_url}/rest/v1/topics_queue?assigned_employee_email=eq.{email}&status=eq.assigned&select=count", headers=headers, timeout=10)
                assigned_count = 0
                if assigned_res.status_code == 200:
                    try:
                        assigned_count = int(assigned_res.headers.get("content-range", "0-0/0").split("/")[-1])
                    except: pass
                
                workloads[email] = assigned_count

            # 3. 카테고리별로 무인 자동화 주제 발굴 및 배정 실행
            for category in categories:
                cat_id = category.get("id")
                cat_name = category.get("name")
                keywords = category.get("keywords") or ""
                benchmark_url = category.get("benchmark_channel_url") or ""
                target_country = category.get("target_country", "KR")
                target_language = normalize_content_language(category.get("language"))

                # [SDK Predicates] 활성 직원의 가용성 필터링 (워크로드가 3건 미만 + 콘텐츠 언어 지원)
                language_capable_users = []
                for user in users:
                    email = user.get("email")
                    if not email or workloads.get(email, 0) >= 3:
                        continue
                    raw_languages = user.get("preferred_languages") or ["ko"]
                    if isinstance(raw_languages, str):
                        raw_languages = [item.strip() for item in raw_languages.split(",") if item.strip()]
                    preferred_languages = {normalize_content_language(item) for item in raw_languages}
                    if target_language in preferred_languages:
                        language_capable_users.append(user)

                eligible_employees = [user.get("email") for user in language_capable_users if user.get("email")]
                assigned_email = None
                fallback_email = category.get("assigned_employee_email") or "ejsh0519@naver.com"

                if eligible_employees:
                    # [Multi-Agent Persona Dispatcher] 직원별 페르소나 정보를 결합하여 Gemini로 자율 배정
                    personas_info = []
                    for email in eligible_employees:
                        prof = next((u for u in users if (u.get("email") or "").lower() == email.lower()), {})
                        personas_info.append({
                            "email": email,
                            "name": prof.get("persona_name") or prof.get("full_name") or email.split("@")[0],
                            "style": prof.get("persona_style") or "general writing, standard explanation",
                            "description": prof.get("persona_description") or "일반적인 유튜브 영상 기획 및 대본 작성을 수행합니다.",
                            "workload": workloads.get(email, 0),
                            "preferred_languages": prof.get("preferred_languages") or ["ko"]
                        })
                    
                    matching_prompt = f"""
                    You are Google Antigravity Dispatcher Agent.
                    Please select the best sub-agent (employee) to write a video script for the following category.
                    
                    [Category Info]
                    - Name: {cat_name}
                    - Keywords: {keywords}
                    - Target Market: {target_country}
                    - Target Content Language: {content_language_label(target_language)} ({target_language})
                    
                    [Candidate Sub-Agents (Employees) & Personas]
                    {json.dumps(personas_info, ensure_ascii=False, indent=2)}
                    
                    Instructions:
                    1. Choose the candidate whose persona/writing style matches the theme/mood of the category best.
                    2. Take current workload into consideration (prioritize lower workload, but style fit is very important).
                    3. Output only a JSON object containing the assigned email and a short reason in Korean:
                    {{"assigned_email": "candidate_email@domain.com", "reason": "이유 설명..."}}
                    Do not include any code wrappers, markdown, or text other than the raw JSON.
                    """
                    
                    try:
                        import asyncio
                        import json as _json
                        match_res = asyncio.run(gemini_service.generate_text(matching_prompt, model="gemini-2.5-flash", temperature=0.3))
                        cleaned_match = match_res.replace("```json", "").replace("```", "").strip()
                        match_data = _json.loads(cleaned_match)
                        selected_email = match_data.get("assigned_email")
                        reason = match_data.get("reason", "")
                        if selected_email in eligible_employees:
                            assigned_email = selected_email
                            print(f"🤖 [Dispatcher Agentic Bidding] Category '{cat_name}' matched to {assigned_email}. Reason: {reason}")
                        else:
                            print(f"🤖 [Dispatcher Agentic Bidding] LLM chose invalid email '{selected_email}', using workload default.")
                            assigned_email = min(eligible_employees, key=lambda email: workloads[email])
                    except Exception as match_err:
                        print(f"⚠️ [Dispatcher Agentic Bidding] Failed to match via LLM: {match_err}. Falling back to workload min.")
                        assigned_email = min(eligible_employees, key=lambda email: workloads[email])
                else:
                    print(f"[Dispatcher] No {content_language_label(target_language)}-capable employees under threshold. Topic will stay unassigned instead of falling back to {fallback_email}.")

                print(f"[Dispatcher] Category: '{cat_name}' (Target: {target_country}, Language: {target_language}) -> Assigned to: {assigned_email or 'UNASSIGNED'} (Current load: {workloads.get(assigned_email, 0) if assigned_email else 0})")

                # 4. LLM을 통한 바이럴 트렌드 주제 분석 (1개씩 정교하게 실시간 생성)
                prompt = f"""
                You are Google Antigravity SDK Smart Video Planner.
                Target Country: {target_country}
                Target Content Language: {content_language_label(target_language)} ({target_language})
                Category Name: {cat_name}
                Keywords: {keywords}
                Benchmark Reference: {benchmark_url}

                Based on these settings, please generate exactly one highly compelling, click-worthy, and trending video title or topic.
                {topic_language_instruction(target_language)}

                CRITICAL INSTRUCTION:
                - The result MUST be the actual video title itself. Do not generate meta production suggestions.
                - Output only the plain title string inside a JSON object: {{"topic": "Generated Title"}}
                - Do not include markdown wraps or code fences.
                """

                # [SDK Hook fallback] API 한도나 오류 시 재시도 안전장치 적용
                topic_title = None
                import asyncio
                for attempt in range(3):
                    try:
                        response_text = asyncio.run(gemini_service.generate_text(prompt, model="gemini-2.5-flash", temperature=0.7))
                        import json as _json
                        # clean json wrapper
                        cleaned = response_text.replace("```json", "").replace("```", "").strip()
                        data = _json.loads(cleaned)
                        topic_title = data.get("topic")
                        if topic_title:
                            break
                    except Exception as gen_err:
                        print(f"[Dispatcher Hook] LLM Generation attempt {attempt+1} failed: {gen_err}")
                        time.sleep(5)  # 5초 간 대기 후 retry

                if not topic_title:
                    print(f"[Dispatcher Warning] Failed to generate viral topic for category '{cat_name}' after 3 attempts.")
                    continue

                # 5. 스마트 적재 실행 (is_auto_generated 활성화)
                payload = {
                    "category_id": cat_id,
                    "topic": topic_title,
                    "assigned_employee_email": assigned_email,
                    "language": target_language,
                    "status": "pending",
                    "is_auto_generated": True
                }

                ins_res = requests.post(f"{supabase_url}/rest/v1/topics_queue", json=payload, headers=headers, timeout=10)
                if ins_res.status_code in [200, 201]:
                    print(f"[Dispatcher Success] Dispatched topic: '{topic_title}' -> {assigned_email or 'UNASSIGNED'}")
                    # 할당자의 워크로드 가상 카운트 가중치 증가
                    if assigned_email:
                        workloads[assigned_email] = workloads.get(assigned_email, 0) + 1
                else:
                    print(f"[Dispatcher Error] DB insert failed for topic '{topic_title}': {ins_res.text}")

        except Exception as err:
            print(f"[Dispatcher Error] Auto dispatch system failure: {err}")
        finally:
            self.dispatcher_lock.release()

# Singleton Instance
dispatcher_service = DispatcherService()
